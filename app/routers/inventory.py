from fastapi import APIRouter, Query, HTTPException, Body, Response
from fastapi.responses import HTMLResponse
from typing import Optional, List
from datetime import datetime
from app.services import (
    get_inventory_items,
    save_inventory_counts,
    set_inventory_selection,
    recount_inventory_item,
    adjust_stock_to_inventory,
    get_inventory_anomalies,
    generate_inventory_print_sheet,
    generate_inventory_pdf_bytes
)
from app.models import (
    InventorySaveCountsRequest,
    InventorySelectionRequest,
    InventoryRecountRequest,
    InventoryAdjustmentRequest
)

router = APIRouter(prefix="/api/inventory", tags=["Inventaire"])

@router.get("/items")
def list_inventory_items(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
    selected_only: bool = Query(False)
):
    """
    Retourne la liste complète des articles déclinés [Référence + Couleur].
    Inclut les deux comptages de personnes, le calcul d'anomalie (rouge si désaccord ou écart stock),
    la date du dernier inventaire et la sélection.
    """
    try:
        return get_inventory_items(search=search, status_filter=status, selected_only=selected_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/save-counts")
def save_counts(data: InventorySaveCountsRequest):
    """
    Enregistre les comptages saisis pour deux personnes.
    Détecte automatiquement les discordances et met à jour les statuts.
    """
    try:
        items_payload = [item.model_dump() for item in data.items]
        return save_inventory_counts(
            items=items_payload,
            person1_default=data.person1_name,
            person2_default=data.person2_name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/select")
def update_selection(data: InventorySelectionRequest):
    """Sélectionne ou désélectionne des articles pour lancer une session d'inventaire ciblée."""
    try:
        return set_inventory_selection(variant_ids=data.variant_ids, is_selected=data.is_selected)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/recount")
def recount_item(data: InventoryRecountRequest):
    """Marque un article en anomalie pour un recomptage physique complet par les deux personnes."""
    try:
        return recount_inventory_item(variant_id=data.variant_id, notes=data.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/adjust")
def adjust_stock(data: InventoryAdjustmentRequest):
    """
    Mise à niveau du stock réel vers la quantité d'inventaire retenue.
    Exige obligatoirement un motif d'anomalie et archive dans le sous-onglet Anomalies.
    """
    try:
        return adjust_stock_to_inventory(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/anomalies")
def list_inventory_anomalies(search: Optional[str] = Query(None)):
    """
    Retourne l'historique de toutes les anomalies d'inventaire après mise à niveau (pour le sous-onglet Anomalies).
    """
    try:
        anomalies = get_inventory_anomalies(search=search)
        return {"anomalies": anomalies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/print-sheet", response_class=HTMLResponse)
def print_inventory_sheet(
    variant_ids: Optional[str] = Query(None),
    person1: Optional[str] = Query("Opérateur 1"),
    person2: Optional[str] = Query("Opérateur 2")
):
    """
    Génère la fiche de comptage physique d'inventaire au format HTML/A4 paysage,
    prête pour impression directe ou exportation en PDF.
    """
    try:
        ids_list = None
        if variant_ids and variant_ids.strip():
            ids_list = [int(v.strip()) for v in variant_ids.split(",") if v.strip().isdigit()]

        html_sheet = generate_inventory_print_sheet(
            variant_ids=ids_list,
            person1=person1,
            person2=person2
        )
        return HTMLResponse(content=html_sheet)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export-pdf")
def export_inventory_pdf(
    variant_ids: Optional[str] = Query(None),
    person1: Optional[str] = Query("Opérateur 1"),
    person2: Optional[str] = Query("Opérateur 2"),
    hide_stock: bool = Query(False)
):
    """
    Génère et télécharge directement un fichier PDF vectoriel natif A4 Paysage
    de la fiche de comptage physique d'inventaire.
    """
    try:
        ids_list = None
        if variant_ids and variant_ids.strip():
            ids_list = [int(v.strip()) for v in variant_ids.split(",") if v.strip().isdigit()]

        pdf_bytes = generate_inventory_pdf_bytes(
            variant_ids=ids_list,
            person1=person1,
            person2=person2,
            hide_stock=hide_stock
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=Fiche_Inventaire_{timestamp}.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


