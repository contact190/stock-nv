from fastapi import APIRouter, Query, Response
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
