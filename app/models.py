from pydantic import BaseModel, Field
from typing import Optional, List

class CategoryModel(BaseModel):
    name: str
    description: Optional[str] = ""

class GammeModel(BaseModel):
    name: str
    description: Optional[str] = ""

class UnitModel(BaseModel):
    name: str
    symbol: str

class ColorModel(BaseModel):
    name: str
    ral_code: Optional[str] = ""
    hex_code: Optional[str] = "#474a51"

class WorkshopCaseModel(BaseModel):
    type: str = Field(description="'PROFILE' ou 'ACCESSOIRE'")
    number: str = Field(description="Numéro de case (ex: 01, 05) ou code complet (ex: P-01, A-02)")
    description: Optional[str] = ""

class CatalogProductCreate(BaseModel):
    """Création d'un nouvel article dans le Catalogue Maître avec contrôle anti-doublon strict [Ref + Couleur]."""
    reference: str = Field(min_length=2, description="Code référence unique du produit (ex: HPS-40)")
    designation: str = Field(min_length=2, description="Désignation (ex: Profilé Dormant Alu 40mm RPT)")
    category: str
    gamme: str
    unit: str
    color: str = Field(min_length=1, description="Déclinaison de couleur (ex: Blanc 9010)")
    ral_code: Optional[str] = None
    color_hex: Optional[str] = "#64748b"
    barcode: Optional[str] = None
    initial_quantity: float = Field(default=0, ge=0)
    unit_price: float = Field(default=0, ge=0)
    threshold: float = Field(default=10, ge=0)
    supplier: Optional[str] = ""
    location: Optional[str] = "EN_ATTENTE_AFFECTATION"
    image_url: Optional[str] = ""

class StockInRequest(BaseModel):
    """Entrée en stock sur un article existant au catalogue avec calcul PMP et contrôle prix."""
    reference: str
    color: str
    quantity: float = Field(gt=0, description="Quantité entrante")
    unit_price: float = Field(ge=0, description="Prix d'achat unitaire en DZD")
    supplier: Optional[str] = None
    allow_zero_price: Optional[bool] = False
    notes: Optional[str] = None
    variant_id: Optional[int] = None
    threshold: Optional[float] = None
    location: Optional[str] = None
    poseur: Optional[str] = None
    user: Optional[str] = "Admin"

class DestockRequest(BaseModel):
    """Sortie de stock physique avec sélection de commande et saisie manuelle du lot."""
    variant_id: int
    quantity: float = Field(gt=0, description="Quantité à déstocker")
    order_number: Optional[str] = None
    lot_number: Optional[str] = None
    unassigned_reason: Optional[str] = None
    operator: Optional[str] = "Atelier"
    notes: Optional[str] = ""
    chantier: Optional[str] = None
    poseur: Optional[str] = None
    mode: str = Field(default="DIRECT")
    confirmed_anonyme: Optional[bool] = False
    user: Optional[str] = "Admin"

class BatchItem(BaseModel):
    variant_id: int
    quantity: float = Field(gt=0, description="Quantité pour cette variante")

class BatchDestockRequest(BaseModel):
    """Déstockage groupé de plusieurs articles avec métadonnées communes de lot/commande."""
    items: List[BatchItem] = Field(min_length=1)
    order_number: Optional[str] = None
    lot_number: Optional[str] = None
    unassigned_reason: Optional[str] = None
    operator: Optional[str] = "Atelier"
    notes: Optional[str] = ""
    chantier: Optional[str] = None
    poseur: Optional[str] = None
    user: Optional[str] = "Admin"

class ReserveRequest(BaseModel):
    """Réservation pour commande avec saisie manuelle du lot."""
    variant_id: int
    order_number: str
    lot_number: Optional[str] = None
    quantity: float = Field(gt=0, description="Quantité à réserver")
    client_name: Optional[str] = None
    poseur: Optional[str] = None
    notes: Optional[str] = ""
    user: Optional[str] = "Admin"

class BatchReserveRequest(BaseModel):
    """Réservation groupée de plusieurs articles pour une commande / lot."""
    items: List[BatchItem] = Field(min_length=1)
    order_number: str
    lot_number: Optional[str] = None
    client_name: Optional[str] = None
    notes: Optional[str] = ""
    user: Optional[str] = "Admin"

class OrderCreateRequest(BaseModel):
    order_number: str
    client_name: str
    notes: Optional[str] = ""

class OrderValidateRequest(BaseModel):
    order_number: str
    user: Optional[str] = "Admin"

class VariantUpdateRequest(BaseModel):
    threshold: Optional[float] = None
    location: Optional[str] = None
    supplier: Optional[str] = None
    color_hex: Optional[str] = None
    barcode: Optional[str] = None

class InventoryCountItem(BaseModel):
    variant_id: int
    person1_name: Optional[str] = "Personne 1"
    count1: Optional[float] = None
    person2_name: Optional[str] = "Personne 2"
    count2: Optional[float] = None
    notes: Optional[str] = ""

class InventorySaveCountsRequest(BaseModel):
    items: List[InventoryCountItem] = Field(min_length=1)
    person1_name: Optional[str] = "Personne 1"
    person2_name: Optional[str] = "Personne 2"

class InventorySelectionRequest(BaseModel):
    variant_ids: List[int]
    is_selected: bool = True

class InventoryRecountRequest(BaseModel):
    variant_id: int
    notes: Optional[str] = ""

class InventoryAdjustmentRequest(BaseModel):
    variant_id: int
    chosen_quantity: float = Field(ge=0, description="Quantité d'inventaire retenue pour mise à niveau")
    reason: str = Field(min_length=3, description="Motif obligatoire de l'écart / anomalie (ex: casse, chute, erreur précédente)")
    notes: Optional[str] = ""
    operator: Optional[str] = "Admin"
