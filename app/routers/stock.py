from fastapi import APIRouter, Query, HTTPException, UploadFile, File
from typing import Optional
import os
import uuid
import shutil
import re
from app.services import get_products_with_variants, create_catalog_product
from app.models import CatalogProductCreate, VariantUpdateRequest
from app.database import get_db
from app.supabase_sync import sync_product_to_cloud, sync_variant_to_cloud

router = APIRouter(prefix="/api/stock", tags=["Stock"])

@router.get("")
def list_stock(
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    gamme: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    chantier: Optional[str] = Query(None)
):
    """Retourne la liste des profilés aluminium et volets avec variantes, PMP et filtres."""
    return get_products_with_variants(
        search=search,
        category=category,
        gamme=gamme,
        supplier=supplier,
        status_filter=status,
        chantier_filter=chantier
    )

@router.post("/catalog")
def add_product_to_catalog(data: CatalogProductCreate):
    """
    Création d'un nouvel article dans le Catalogue Maître.
    Bloque avec une erreur explicite toute tentative de doublon [Référence + Couleur].
    Synchronise instantanément avec Supabase Cloud.
    """
    try:
        result = create_catalog_product(data)
        try:
            sync_product_to_cloud({
                "reference": data.reference.strip().upper(),
                "designation": data.designation.strip(),
                "category": data.category,
                "gamme": data.gamme,
                "unit": data.unit,
                "image_url": data.image_url or "",
                "threshold": data.threshold,
                "supplier": data.supplier,
                "location": data.location
            })
            sync_variant_to_cloud({
                "product_reference": data.reference.strip().upper(),
                "color": data.color.strip(),
                "ral_code": data.ral_code or "",
                "color_hex": data.color_hex or "#64748b",
                "barcode": data.barcode or f"BAR-{data.reference.strip().upper()}-{data.color.strip()}",
                "initial_quantity": data.initial_quantity,
                "real_quantity": data.initial_quantity,
                "reserved_quantity": 0.0,
                "threshold": data.threshold,
                "current_price": data.unit_price,
                "previous_price": data.unit_price,
                "pmp": data.unit_price,
                "supplier": data.supplier,
                "location": data.location
            })
        except Exception:
            pass
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/references")
def get_available_references():
    """Liste de toutes les références du catalogue maître pour l'autocomplétion des mouvements."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reference, designation, category, gamme, unit, supplier, location, image_url, threshold 
        FROM products 
        ORDER BY reference ASC
    """)
    products = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("""
        SELECT id, product_reference, color, color_hex, barcode, real_quantity, reserved_quantity, current_price, pmp, location 
        FROM variants
        ORDER BY product_reference ASC, color ASC
    """)
    variants = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        "products": products,
        "variants": variants
    }

@router.get("/variant/{variant_id}")
def get_variant_details(variant_id: int):
    """Détails d'une variante avec historique PMP et des prix."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.*, p.designation, p.category, p.gamme, p.unit, p.image_url
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        WHERE v.id = ?
    """, (variant_id,))
    variant = cursor.fetchone()

    if not variant:
        conn.close()
        raise HTTPException(status_code=404, detail="Variante introuvable")

    cursor.execute("""
        SELECT price, pmp_after, quantity, recorded_at 
        FROM price_history 
        WHERE variant_id = ? 
        ORDER BY recorded_at DESC
    """, (variant_id,))
    price_history = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "variant": dict(variant),
        "price_history": price_history
    }

@router.put("/variant/{variant_id}")
def update_variant(variant_id: int, data: VariantUpdateRequest):
    """
    Modifie un article sauf ses quantités (stock réel, réservé, initial).
    Champs de la teinte : seuil, casier, fournisseur, couleur affichée, RAL, code-barres, prix d'achat, PMP.
    Champs de l'article (toutes teintes) : désignation, catégorie, gamme, unité, photo.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM variants WHERE id = ?", (variant_id,))
    variant = cursor.fetchone()
    if not variant:
        conn.close()
        raise HTTPException(status_code=404, detail="Variante introuvable")
    reference = variant["product_reference"]

    # --- Teinte ---
    v_updates, v_params = [], []
    if data.threshold is not None:
        if data.threshold < 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Le seuil d'alerte ne peut pas être négatif")
        v_updates.append("threshold = ?"); v_params.append(data.threshold)
    if data.location is not None:
        loc = data.location.strip() if data.location.strip() else "EN_ATTENTE_AFFECTATION"
        v_updates.append("location = ?"); v_params.append(loc)
    if data.supplier is not None:
        v_updates.append("supplier = ?"); v_params.append(data.supplier.strip())
    if data.color_hex is not None:
        v_updates.append("color_hex = ?"); v_params.append(data.color_hex)
    if data.ral_code is not None:
        v_updates.append("ral_code = ?"); v_params.append(data.ral_code.strip())
    if data.barcode is not None:
        v_updates.append("barcode = ?"); v_params.append(data.barcode.strip())
    if data.current_price is not None:
        if data.current_price < 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Le prix d'achat ne peut pas être négatif")
        v_updates.append("current_price = ?"); v_params.append(data.current_price)
    if data.pmp is not None:
        if data.pmp < 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Le PMP ne peut pas être négatif")
        v_updates.append("pmp = ?"); v_params.append(data.pmp)

    # --- Article ---
    p_updates, p_params = [], []
    if data.designation is not None:
        if not data.designation.strip():
            conn.close()
            raise HTTPException(status_code=400, detail="La désignation ne peut pas être vide")
        p_updates.append("designation = ?"); p_params.append(data.designation.strip())
    for field in ("category", "gamme", "unit", "image_url"):
        val = getattr(data, field)
        if val is not None:
            p_updates.append(f"{field} = ?"); p_params.append(val.strip())
    if data.supplier is not None:
        p_updates.append("supplier = ?"); p_params.append(data.supplier.strip())

    if not v_updates and not p_updates:
        conn.close()
        return {"success": True, "message": "Aucune modification"}

    if v_updates:
        v_updates.append("updated_at = CURRENT_TIMESTAMP")
        cursor.execute(f"UPDATE variants SET {', '.join(v_updates)} WHERE id = ?", v_params + [variant_id])
    if p_updates:
        cursor.execute(f"UPDATE products SET {', '.join(p_updates)} WHERE reference = ?", p_params + [reference])
    conn.commit()

    cursor.execute("SELECT * FROM variants WHERE id = ?", (variant_id,))
    updated_variant = cursor.fetchone()
    cursor.execute("SELECT * FROM products WHERE reference = ?", (reference,))
    updated_product = cursor.fetchone()
    conn.close()

    # Envoi immédiat vers Supabase (la file d'attente reprend le relais en cas d'échec)
    try:
        if updated_product and p_updates:
            sync_product_to_cloud(dict(updated_product))
        if updated_variant and v_updates:
            sync_variant_to_cloud(dict(updated_variant))
    except Exception:
        pass

    return {"success": True, "message": "Article modifié avec succès"}

@router.post("/upload-image")
async def upload_product_image(file: UploadFile = File(...)):
    """Upload d'une image produit en local dans static/uploads/"""
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
    original_name = file.filename or "image.jpg"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Format non supporté (autorisés: PNG, JPG, JPEG, WEBP, GIF, SVG)")

    # Nettoyer nom et générer nom unique
    safe_name = re.sub(r'[^a-zA-Z0-9_\.-]', '_', original_name) if 're' in globals() else original_name.replace(" ", "_")
    unique_filename = f"{uuid.uuid4().hex[:10]}_{safe_name}"
    
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, unique_filename)

    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    # Photo envoyée dans Supabase Storage : elle survit aux redémarrages du serveur
    from app.supabase_sync import upload_image_to_cloud
    from starlette.concurrency import run_in_threadpool
    cloud_url = await run_in_threadpool(upload_image_to_cloud, unique_filename, content, file.content_type or "")

    return {
        "status": "success",
        "url": cloud_url or f"/static/uploads/{unique_filename}",
        "filename": unique_filename,
        "cloud": bool(cloud_url)
    }

@router.post("/update-image")
def update_product_image(reference: str = Query(...), image_url: str = Query(...)):
    """Met à jour l'URL d'image d'un article du catalogue."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET image_url = ? WHERE reference = ?", (image_url, reference))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Image mise à jour avec succès"}

