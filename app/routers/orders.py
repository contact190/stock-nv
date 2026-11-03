from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
from app.models import OrderCreateRequest, OrderValidateRequest
from app.services import validate_and_destock_order
from app.database import get_db

router = APIRouter(prefix="/api/orders", tags=["Commandes"])

@router.get("")
def list_orders(status: Optional[str] = None):
    """Liste des commandes avec statistiques financières et statuts."""
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT o.id, o.order_number, o.client_name, o.status, o.notes, o.created_at, o.updated_at,
               COALESCE(SUM(oi.quantity_reserved), 0) as total_reserved_qty,
               COALESCE(SUM(oi.quantity_destocked), 0) as total_destocked_qty,
               COALESCE(SUM(oi.quantity_reserved * oi.unit_price), 0) as total_reserved_value,
               COALESCE(SUM(oi.quantity_destocked * oi.unit_price), 0) as total_destocked_value,
               COUNT(oi.id) as items_count
        FROM orders o
        LEFT JOIN order_items oi ON o.order_number = oi.order_number
        WHERE 1=1
    """
    params = []
    if status and status != "ALL":
        query += " AND o.status = ?"
        params.append(status)

    query += " GROUP BY o.id ORDER BY o.created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "order_number": r["order_number"],
            "client_name": r["client_name"],
            "status": r["status"],
            "notes": r["notes"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "total_reserved_qty": float(r["total_reserved_qty"]),
            "total_destocked_qty": float(r["total_destocked_qty"]),
            "total_reserved_value": round(float(r["total_reserved_value"]), 2),
            "total_destocked_value": round(float(r["total_destocked_value"]), 2),
            "items_count": int(r["items_count"])
        }
        for r in rows
    ]

@router.get("/{order_number}")
def get_order_details(order_number: str):
    """Détail complet d'une commande et des articles réservés/déstockés."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="Commande introuvable")

    cursor.execute("""
        SELECT oi.*, v.real_quantity as current_stock_real, v.reserved_quantity as current_stock_reserved
        FROM order_items oi
        LEFT JOIN variants v ON oi.variant_id = v.id
        WHERE oi.order_number = ?
    """, (order_number,))
    items = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "order": dict(order),
        "items": items
    }

@router.post("")
def create_order(data: OrderCreateRequest):
    """Création manuelle d'une nouvelle commande client ou projet."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT id FROM orders WHERE order_number = ?", (data.order_number,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Ce numéro de commande existe déjà.")

    cursor.execute("""
        INSERT INTO orders (order_number, client_name, status, notes, created_at, updated_at)
        VALUES (?, ?, 'EN_ATTENTE', ?, ?, ?)
    """, (data.order_number, data.client_name, data.notes, now, now))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"success": True, "order_id": order_id, "order_number": data.order_number}

@router.post("/{order_number}/validate-destock")
def validate_destock_route(order_number: str, data: Optional[OrderValidateRequest] = None):
    """Action 'Valider & Déstocker' : Déstocke définitivement tous les articles réservés."""
    user = data.user if data and data.user else "Admin"
    try:
        result = validate_and_destock_order(order_number, user=user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{order_number}/cancel")
def cancel_order(order_number: str):
    """Annule la commande et libère les articles réservés pour qu'ils redeviennent disponibles."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="Commande introuvable")

    if order["status"] == "DESTOCKED":
        conn.close()
        raise HTTPException(status_code=400, detail="Impossible d'annuler une commande déjà déstockée.")

    cursor.execute("SELECT * FROM order_items WHERE order_number = ? AND status = 'RESERVED'", (order_number,))
    items = cursor.fetchall()

    for itm in items:
        qty = itm["quantity_reserved"]
        var_id = itm["variant_id"]
        # Libérer la quantité réservée sur la variante
        cursor.execute("UPDATE variants SET reserved_quantity = MAX(0, reserved_quantity - ?), updated_at = ? WHERE id = ?", (qty, now, var_id))
        cursor.execute("UPDATE order_items SET status = 'CANCELLED' WHERE id = ?", (itm["id"],))

        # Enregistrer le mouvement d'annulation de réservation
        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, total_value, order_number, user, notes)
            VALUES (?, 'LIBERATION', ?, ?, ?, ?, ?, ?, ?, 'Admin', ?)
        """, (now, itm["product_reference"], itm["product_name"], itm["color"], qty, itm["unit_price"], round(qty * itm["unit_price"], 2), order_number, f"Annulation commande {order_number}"))

    cursor.execute("UPDATE orders SET status = 'ANNULEE', updated_at = ? WHERE order_number = ?", (now, order_number))
    conn.commit()
    conn.close()

    return {"success": True, "message": f"Commande {order_number} annulée et réservations libérées."}

@router.delete("/{order_number}")
def delete_order(order_number: str):
    """Supprime une commande si elle n'a pas de stock réservé actif."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_number,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        raise HTTPException(status_code=404, detail="Commande introuvable")

    cursor.execute("SELECT COALESCE(SUM(quantity_reserved), 0) as res_sum FROM order_items WHERE order_number = ? AND status = 'RESERVED'", (order_number,))
    row = cursor.fetchone()
    if row and row["res_sum"] > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Impossible de supprimer une commande avec du stock réservé. Annulez-la d'abord.")

    cursor.execute("DELETE FROM order_items WHERE order_number = ?", (order_number,))
    cursor.execute("DELETE FROM orders WHERE order_number = ?", (order_number,))
    conn.commit()
    conn.close()

    return {"success": True, "message": f"Commande {order_number} supprimée avec succès."}
