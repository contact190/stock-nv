from fastapi import APIRouter, HTTPException
from app.models import StockInRequest, DestockRequest, ReserveRequest, BatchDestockRequest, BatchReserveRequest
from app.services import (
    stock_in_operation,
    destock_operation,
    batch_destock_operation,
    reserve_operation,
    batch_reserve_operation
)

router = APIRouter(prefix="/api/actions", tags=["Actions"])

@router.post("/stock-in")
def action_stock_in(data: StockInRequest):
    """
    [📥 STOCKER] Entrée en stock sur article existant.
    - Calcule le PMP dynamique.
    - Bloque si le prix est à 0 sans confirmation.
    - Attribue l'emplacement 'EN_ATTENTE_AFFECTATION' si omis.
    """
    try:
        result = stock_in_operation(data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/destock")
def action_destock(data: DestockRequest):
    """
    [📤 DESTOCKER] Sortie de stock physique (article unique).
    """
    try:
        result = destock_operation(data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/destock-batch")
def action_destock_batch(data: BatchDestockRequest):
    """
    [📤 DESTOCKER MULTI-ARTICLES] Sortie groupée de plusieurs articles pour un même lot ou chantier.
    """
    try:
        result = batch_destock_operation(data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reserve")
def action_reserve(data: ReserveRequest):
    """
    [🔒 RESERVER] Bloque une quantité pour un chantier sans déstockage immédiat (article unique).
    """
    try:
        result = reserve_operation(data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reserve-batch")
def action_reserve_batch(data: BatchReserveRequest):
    """
    [🔒 RESERVER MULTI-ARTICLES] Bloque plusieurs profilés pour un même chantier et lot.
    """
    try:
        result = batch_reserve_operation(data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
