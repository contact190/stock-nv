from fastapi import APIRouter, Query, HTTPException, UploadFile, File
from typing import Optional
import os
import uuid
import shutil
import re
from app.services import get_products_with_variants, create_catalog_product
from app.models import CatalogProductCreate, VariantUpdateRequest
from app.database import get_db
from app.supabase_sync import sync_product_to_cloud, sync_variant_to_cloud, push_pending_to_cloud
from datetime import datetime
import urllib.parse

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

# Tables locales et Cloud qui recopient la référence / la couleur d'un article
_REF_TABLES = ["price_history", "movements", "order_items", "inventory_counts", "inventory_anomalies"]


def _local_cols(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cursor.fetchall()}


def _cloud_rename(old_ref, new_ref, old_color, new_color):
    """
    Renomme d'abord dans Supabase (UPDATE, jamais supprimer/recréer : l'historique et les
    liens des commandes sont conservés). Renvoie False si Supabase n'a pas répondu.
    """
    from app.supabase_sync import is_supabase_enabled, _supabase_request
    if not is_supabase_enabled():
        return True
    q = lambda v: urllib.parse.quote(str(v), safe="")
    if new_ref != old_ref:
        # La référence change dans products ; les variantes suivent (ON UPDATE CASCADE)
        if _supabase_request(f"products?reference=eq.{q(old_ref)}", method="PATCH",
                             data={"reference": new_ref}) is None:
            return False
        for t in _REF_TABLES:
            _supabase_request(f"{t}?product_reference=eq.{q(old_ref)}", method="PATCH",
                              data={"product_reference": new_ref})
    if new_color != old_color:
        if _supabase_request(f"variants?product_reference=eq.{q(new_ref)}&color=eq.{q(old_color)}",
                             method="PATCH", data={"color": new_color}) is None:
            return False
        for t in _REF_TABLES:
            _supabase_request(f"{t}?product_reference=eq.{q(new_ref)}&color=eq.{q(old_color)}",
                              method="PATCH", data={"color": new_color})
    return True


@router.get("/reference-impact")
def reference_impact(reference: str = Query(...)):
    """Ce qui sera touché par un renommage de référence (pour la fenêtre de sécurité)."""
    conn = get_db()
    cursor = conn.cursor()
    counts = {}
    for key, sql in (("colors", "SELECT COUNT(*) FROM variants WHERE product_reference = ?"),
                     ("movements", "SELECT COUNT(*) FROM movements WHERE product_reference = ?"),
                     ("order_lines", "SELECT COUNT(*) FROM order_items WHERE product_reference = ?")):
        try:
            cursor.execute(sql, (reference,))
            counts[key] = cursor.fetchone()[0]
        except Exception:
            counts[key] = 0
    conn.close()
    return counts

@router.put("/variant/{variant_id}")
def update_variant(variant_id: int, data: VariantUpdateRequest):
    """
    Modifie TOUT un article.
    Article (toutes teintes) : référence, désignation, catégorie, gamme, unité, photo, fournisseur.
    Teinte : nom de couleur, seuil, casier, fournisseur, couleur affichée, RAL, code-barres,
             prix d'achat, PMP, stock réel et réservé.
    - Un renommage de référence / couleur est répercuté partout (historique, commandes, inventaire, Cloud).
    - Une correction du stock réel est enregistrée dans le journal des mouvements (CORRECTION).
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT v.*, p.designation FROM variants v
        LEFT JOIN products p ON p.reference = v.product_reference WHERE v.id = ?
    """, (variant_id,))
    variant = cursor.fetchone()
    if not variant:
        conn.close()
        raise HTTPException(status_code=404, detail="Variante introuvable")
    old = dict(variant)
    old_ref, old_color = old["product_reference"], old["color"]

    def fail(msg, code=400):
        conn.close()
        raise HTTPException(status_code=code, detail=msg)

    new_ref = data.reference.strip().upper() if data.reference and data.reference.strip() else old_ref
    new_color = data.color.strip() if data.color and data.color.strip() else old_color
    if len(new_ref) < 2:
        fail("La référence doit contenir au moins 2 caractères")

    # --- Contrôles ---
    for label, val in (("Le seuil d'alerte", data.threshold), ("Le prix d'achat", data.current_price),
                       ("Le PMP", data.pmp), ("Le stock réel", data.real_quantity),
                       ("La quantité réservée", data.reserved_quantity)):
        if val is not None and val < 0:
            fail(f"{label} ne peut pas être négatif")
    new_real = data.real_quantity if data.real_quantity is not None else float(old["real_quantity"] or 0)
    new_reserved = data.reserved_quantity if data.reserved_quantity is not None else float(old["reserved_quantity"] or 0)
    if new_reserved > new_real + 1e-9:
        fail("La quantité réservée ne peut pas dépasser le stock réel")
    if data.designation is not None and not data.designation.strip():
        fail("La désignation ne peut pas être vide")

    ref_changed = new_ref != old_ref
    color_changed = new_color != old_color
    if ref_changed:
        cursor.execute("SELECT 1 FROM products WHERE reference = ?", (new_ref,))
        if cursor.fetchone():
            fail(f"La référence « {new_ref} » existe déjà dans le catalogue")
    if color_changed:
        cursor.execute("SELECT 1 FROM variants WHERE product_reference = ? AND color = ? AND id != ?",
                       (old_ref, new_color, variant_id))
        if cursor.fetchone():
            fail(f"La couleur « {new_color} » existe déjà pour la référence {old_ref}")

    # --- Renommage côté Cloud d'abord (sinon on ne touche à rien) ---
    if (ref_changed or color_changed) and not _cloud_rename(old_ref, new_ref, old_color, new_color):
        fail("Connexion Supabase impossible : le renommage n'a pas été fait. Réessayez dans un instant.", 503)

    try:
        # --- Renommage local ---
        if ref_changed:
            cursor.execute("UPDATE products SET reference = ? WHERE reference = ?", (new_ref, old_ref))
            cursor.execute("UPDATE variants SET product_reference = ? WHERE product_reference = ?", (new_ref, old_ref))
            for t in _REF_TABLES:
                if "product_reference" in _local_cols(cursor, t):
                    cursor.execute(f"UPDATE {t} SET product_reference = ? WHERE product_reference = ?", (new_ref, old_ref))
        if color_changed:
            cursor.execute("UPDATE variants SET color = ? WHERE id = ?", (new_color, variant_id))
            for t in _REF_TABLES:
                if {"product_reference", "color"} <= _local_cols(cursor, t):
                    cursor.execute(f"UPDATE {t} SET color = ? WHERE product_reference = ? AND color = ?",
                                   (new_color, new_ref, old_color))
        if ref_changed or color_changed:
            # Le Cloud est déjà renommé : on retire les « suppressions » ajoutées par la file d'attente,
            # pour ne jamais effacer côté Cloud un article qui vient d'être renommé.
            cursor.execute("DELETE FROM sync_queue WHERE op = 'delete' AND ((tbl = 'products' AND row_key = ?) OR (tbl = 'inventory_counts' AND row_key = ?))",
                           (old_ref, f"{old_ref}|{old_color}"))

        # --- Teinte ---
        v_updates, v_params = [], []
        if data.threshold is not None:
            v_updates.append("threshold = ?"); v_params.append(data.threshold)
        if data.location is not None:
            v_updates.append("location = ?"); v_params.append(data.location.strip() or "EN_ATTENTE_AFFECTATION")
        for field in ("supplier", "ral_code", "barcode"):
            val = getattr(data, field)
            if val is not None:
                v_updates.append(f"{field} = ?"); v_params.append(val.strip())
        if data.color_hex is not None:
            v_updates.append("color_hex = ?"); v_params.append(data.color_hex)
        if data.current_price is not None:
            v_updates.append("current_price = ?"); v_params.append(data.current_price)
        if data.pmp is not None:
            v_updates.append("pmp = ?"); v_params.append(data.pmp)
        if data.real_quantity is not None:
            v_updates.append("real_quantity = ?"); v_params.append(new_real)
        if data.reserved_quantity is not None:
            v_updates.append("reserved_quantity = ?"); v_params.append(new_reserved)

        # --- Article ---
        p_updates, p_params = [], []
        if data.designation is not None:
            p_updates.append("designation = ?"); p_params.append(data.designation.strip())
        for field in ("category", "gamme", "unit", "image_url", "supplier"):
            val = getattr(data, field)
            if val is not None:
                p_updates.append(f"{field} = ?"); p_params.append(val.strip())

        if v_updates:
            v_updates.append("updated_at = ?"); v_params.append(now)
            cursor.execute(f"UPDATE variants SET {', '.join(v_updates)} WHERE id = ?", v_params + [variant_id])
        if p_updates:
            cursor.execute(f"UPDATE products SET {', '.join(p_updates)} WHERE reference = ?", p_params + [new_ref])

        # --- Correction de stock tracée dans le journal ---
        diff = round(new_real - float(old["real_quantity"] or 0), 4)
        if diff != 0:
            pmp_val = float(data.pmp if data.pmp is not None else (old["pmp"] or 0))
            designation = (data.designation or old.get("designation") or new_ref).strip()
            reason = (data.correction_reason or "").strip() or "Modification manuelle de l'article"
            cursor.execute("""
                INSERT INTO movements (timestamp, action_type, product_reference, product_name, color,
                    quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'CORRECTION', ?, 0, ?)
            """, (now, "STOCKAGE" if diff > 0 else "DESTOCKAGE", new_ref, designation, new_color,
                  abs(diff), pmp_val, pmp_val, round(abs(diff) * pmp_val, 2), data.user or "Admin",
                  f"Correction manuelle : {reason} (Écart : {diff:+g})"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        fail(f"Erreur lors de la modification : {e}", 500)

    cursor.execute("SELECT * FROM variants WHERE id = ?", (variant_id,))
    updated_variant = cursor.fetchone()
    cursor.execute("SELECT * FROM products WHERE reference = ?", (new_ref,))
    updated_product = cursor.fetchone()
    conn.close()

    # Envoi immédiat vers Supabase (la file d'attente reprend le relais en cas d'échec)
    try:
        if updated_product:
            sync_product_to_cloud(dict(updated_product))
        if updated_variant:
            sync_variant_to_cloud(dict(updated_variant))
        push_pending_to_cloud()
    except Exception:
        pass

    msg = "Article modifié avec succès"
    if diff != 0:
        msg += f" (correction de stock {diff:+g} enregistrée dans le journal)"
    return {"success": True, "message": msg, "reference": new_ref, "color": new_color}

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

