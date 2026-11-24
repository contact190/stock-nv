from fastapi import APIRouter, Query, Response, HTTPException
from datetime import datetime
import urllib.parse
from typing import Optional
import csv
import io
from app.database import get_db

router = APIRouter(prefix="/api/movements", tags=["Mouvements"])

@router.get("")
def list_movements(
    action_type: Optional[str] = Query(None),
    order_number: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """Journal chronologique complet des mouvements de profilés alu et volets."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT id, timestamp, action_type, product_reference, product_name, color,
               quantity, unit_price, pmp_at_movement, total_value, order_number, poseur, user, is_anonyme, notes
        FROM movements
        WHERE 1=1
    """
    params = []

    if action_type and action_type != "ALL":
        query += " AND action_type = ?"
        params.append(action_type)

    if order_number and order_number != "ALL":
        query += " AND order_number = ?"
        params.append(order_number)

    if start_date:
        query += " AND timestamp >= ?"
        params.append(f"{start_date} 00:00:00")

    if end_date:
        query += " AND timestamp <= ?"
        params.append(f"{end_date} 23:59:59")

    if search:
        search_term = f"%{search.strip()}%"
        query += """ AND (
            product_reference LIKE ? OR 
            product_name LIKE ? OR 
            color LIKE ? OR 
            order_number LIKE ? OR
            poseur LIKE ? OR
            user LIKE ? OR
            notes LIKE ?
        )"""
        params.extend([search_term] * 7)

    query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]

@router.get("/export-csv")
def export_movements_csv(
    action_type: Optional[str] = Query(None),
    order_number: Optional[str] = Query(None)
):
    """Export au format CSV Excel avec PMP et traçabilité chantiers/poseurs."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT timestamp, action_type, product_reference, product_name, color,
               quantity, unit_price, pmp_at_movement, total_value, order_number, poseur, user, is_anonyme, notes
        FROM movements
        WHERE 1=1
    """
    params = []
    if action_type and action_type != "ALL":
        query += " AND action_type = ?"
        params.append(action_type)
    if order_number and order_number != "ALL":
        query += " AND order_number = ?"
        params.append(order_number)

    query += " ORDER BY timestamp DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    output.write("\ufeff") # BOM UTF-8 pour Excel
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Date & Heure", "Action", "Référence", "Désignation", "Couleur", "Quantité", "Prix Achat Unitaire (DZD)", "PMP au Mouvement (DZD)", "Valeur Totale (DZD)", "Chantier / Commande", "Poseur / Opérateur", "Alerte Anonyme", "Notes"])

    for r in rows:
        writer.writerow([
            r["timestamp"],
            r["action_type"],
            r["product_reference"],
            r["product_name"],
            r["color"],
            r["quantity"],
            f"{r['unit_price']:.2f}",
            f"{r['pmp_at_movement']:.2f}",
            f"{r['total_value']:.2f}",
            r["order_number"] or "STOCK_GENERAL",
            r["poseur"] or "Non renseigné",
            "OUI (Sans chantier/poseur)" if r["is_anonyme"] == 1 else "NON",
            r["notes"] or ""
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tracabilite_mouvements_alu.csv"}
    )


def _effect_text(m, unit=""):
    q = m["quantity"]
    t = m["action_type"]
    if t == "STOCKAGE":
        return f"Le stock réel baissera de {q:g} {unit}. Le PMP sera recalculé sans cette entrée."
    if t == "DESTOCKAGE":
        return f"Le stock réel remontera de {q:g} {unit}."
    if t == "RESERVATION":
        return f"La réservation de {q:g} {unit} sera libérée (et retirée de la commande {m['order_number'] or ''})."
    if t == "LIBERATION":
        return f"La quantité réservée remontera de {q:g} {unit}."
    return "Le mouvement sera seulement retiré du journal (aucun effet sur le stock)."


def _load(cursor, movement_id):
    cursor.execute("SELECT * FROM movements WHERE id = ?", (movement_id,))
    m = cursor.fetchone()
    if not m:
        return None, None
    m = dict(m)
    cursor.execute("""SELECT v.*, p.unit FROM variants v LEFT JOIN products p ON p.reference = v.product_reference
                      WHERE v.product_reference = ? AND v.color = ?""", (m["product_reference"], m["color"]))
    v = cursor.fetchone()
    return m, (dict(v) if v else None)


@router.get("/{movement_id}/cancel-preview")
def cancel_preview(movement_id: int):
    """Ce que va produire la suppression d'un mouvement (pour la fenêtre de confirmation)."""
    conn = get_db()
    cursor = conn.cursor()
    m, v = _load(cursor, movement_id)
    conn.close()
    if not m:
        raise HTTPException(status_code=404, detail="Mouvement introuvable")
    return {"movement": m, "effect": _effect_text(m, (v or {}).get("unit") or ""), "article_found": bool(v)}


@router.delete("/{movement_id}")
def delete_movement(movement_id: int):
    """
    Supprime un mouvement ET annule son effet sur le stock :
    - Entrée (STOCKAGE)      : stock réel - qté, PMP recalculé, ligne d'historique des prix retirée
    - Sortie (DESTOCKAGE)    : stock réel + qté
    - Réservation            : réservé - qté, ligne de commande réduite ou retirée
    - Libération             : réservé + qté
    Le mouvement est aussi supprimé de Supabase.
    """
    from app.supabase_sync import is_supabase_enabled, _supabase_request, push_pending_to_cloud

    conn = get_db()
    cursor = conn.cursor()
    m, v = _load(cursor, movement_id)
    if not m:
        conn.close()
        raise HTTPException(status_code=404, detail="Mouvement introuvable")

    def fail(msg, code=400):
        conn.close()
        raise HTTPException(status_code=code, detail=msg)

    t = m["action_type"]
    qty = float(m["quantity"] or 0)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates = {}
    order_item = None

    if v and t in ("STOCKAGE", "DESTOCKAGE", "RESERVATION", "LIBERATION"):
        real = float(v["real_quantity"] or 0)
        reserved = float(v["reserved_quantity"] or 0)
        if t == "STOCKAGE":
            new_real = round(real - qty, 4)
            if new_real < 0:
                fail(f"Annulation impossible : il ne reste que {real:g} en stock, cette entrée était de {qty:g}.")
            if new_real < reserved:
                fail(f"Annulation impossible : {reserved:g} sont réservés et il ne resterait que {new_real:g} en stock. Libérez d'abord une réservation.")
            updates["real_quantity"] = new_real
            # PMP recalculé comme si cette entrée n'avait pas eu lieu
            pmp = float(v["pmp"] or 0)
            price = float(m["unit_price"] or 0)
            if new_real > 0:
                updates["pmp"] = max(0.0, round((real * pmp - qty * price) / new_real, 2))
        elif t == "DESTOCKAGE":
            updates["real_quantity"] = round(real + qty, 4)
        elif t == "RESERVATION":
            updates["reserved_quantity"] = max(0.0, round(reserved - qty, 4))
            cursor.execute("""SELECT * FROM order_items WHERE variant_id = ? AND order_number = ? AND status = 'RESERVED'
                              ORDER BY id DESC LIMIT 1""", (v["id"], m["order_number"]))
            order_item = cursor.fetchone()
        elif t == "LIBERATION":
            new_res = round(reserved + qty, 4)
            if new_res > real:
                fail("Annulation impossible : la quantité réservée dépasserait le stock réel.")
            updates["reserved_quantity"] = new_res

    # Le mouvement doit d'abord disparaître de Supabase, sinon il reviendrait au prochain démarrage
    if is_supabase_enabled() and m.get("cloud_synced"):
        if m.get("cloud_id"):
            path = f"movements?id=eq.{m['cloud_id']}"
        else:
            q = lambda x: urllib.parse.quote(str(x if x is not None else ""), safe="")
            path = (f"movements?timestamp=eq.{q(m['timestamp'])}&action_type=eq.{q(t)}"
                    f"&product_reference=eq.{q(m['product_reference'])}&color=eq.{q(m['color'])}&quantity=eq.{qty}")
        if _supabase_request(path, method="DELETE") is None:
            fail("Connexion Supabase impossible : le mouvement n'a pas été supprimé. Réessayez dans un instant.", 503)

    try:
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = ?"
            cursor.execute(f"UPDATE variants SET {sets} WHERE id = ?", list(updates.values()) + [now, v["id"]])
        if t == "STOCKAGE" and v:
            cursor.execute("""DELETE FROM price_history WHERE id = (
                                SELECT id FROM price_history WHERE variant_id = ? AND quantity = ? AND price = ?
                                ORDER BY ABS(julianday(recorded_at) - julianday(?)) LIMIT 1)""",
                           (v["id"], qty, float(m["unit_price"] or 0), m["timestamp"]))
            if cursor.rowcount and is_supabase_enabled():
                q = lambda x: urllib.parse.quote(str(x), safe="")
                _supabase_request(f"price_history?product_reference=eq.{q(m['product_reference'])}&color=eq.{q(m['color'])}"
                                  f"&quantity=eq.{qty}&price=eq.{float(m['unit_price'] or 0)}&recorded_at=eq.{q(m['timestamp'])}",
                                  method="DELETE")
        if order_item:
            left = round(float(order_item["quantity_reserved"] or 0) - qty, 4)
            if left > 0:
                cursor.execute("UPDATE order_items SET quantity_reserved = ? WHERE id = ?", (left, order_item["id"]))
            else:
                cursor.execute("DELETE FROM order_items WHERE id = ?", (order_item["id"],))
        cursor.execute("DELETE FROM movements WHERE id = ?", (movement_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        fail(f"Erreur lors de la suppression : {e}", 500)
    conn.close()

    try:
        push_pending_to_cloud()
    except Exception:
        pass

    msg = "Mouvement supprimé et annulé"
    if not v and t in ("STOCKAGE", "DESTOCKAGE", "RESERVATION", "LIBERATION"):
        msg = "Mouvement supprimé (article introuvable : stock non modifié)"
    return {"success": True, "message": msg}
