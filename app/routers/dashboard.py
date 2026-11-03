from fastapi import APIRouter, Query, Request
from typing import Optional, List
from app.services import get_dashboard_metrics
from app.database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/metrics")
def get_metrics(
    period: Optional[str] = Query("ALL"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    orders: Optional[List[str]] = Query(None)
):
    """
    Retourne les KPIs et graphiques financiers.
    Filtres :
    - period : 'ALL', 'WEEK', 'MONTH', 'YEAR', 'CUSTOM'
    - start_date, end_date : pour plage personnalisée (YYYY-MM-DD)
    - orders : filtrage sur une ou plusieurs commandes / lots (ex: CMD-2026-001, LOT-03)
    """
    flat_orders = []
    if orders:
        for o in orders:
            if "," in o:
                flat_orders.extend([item.strip() for item in o.split(",") if item.strip()])
            else:
                flat_orders.append(o.strip())

    return get_dashboard_metrics(
        period=period,
        start_date=start_date,
        end_date=end_date,
        selected_orders=flat_orders if flat_orders else None
    )

@router.get("/orders-list")
def get_orders_filter_options():
    """Liste de toutes les commandes et lots simples pour le filtre du Dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT order_number, client_name, status, created_at FROM orders ORDER BY created_at DESC")
    orders = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "orders": orders
    }

