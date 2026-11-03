import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from app.database import get_db, calculate_pmp
from app.models import (
    CatalogProductCreate, StockInRequest, DestockRequest, ReserveRequest, 
    BatchDestockRequest, BatchReserveRequest, InventoryCountItem, 
    InventorySaveCountsRequest, InventoryAdjustmentRequest
)

def create_catalog_product(data: CatalogProductCreate) -> Dict[str, Any]:
    """
    Création d'un nouvel article dans le Catalogue Maître.
    RÈGLE STRICTE : INTERDICTION DES RÉFÉRENCES DOUBLONS [Référence + Couleur].
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    clean_ref = data.reference.strip().upper()
    clean_color = data.color.strip()

    # Contrôle strict anti-doublon
    cursor.execute("SELECT id FROM variants WHERE UPPER(product_reference) = ? AND UPPER(color) = ?", (clean_ref, clean_color.upper()))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        raise ValueError(f"L'article {clean_ref} sous la couleur '{clean_color}' existe déjà dans le Catalogue Maître. Veuillez utiliser 'Entrée en Stock' pour réapprovisionner.")

    # Vérifier ou créer le produit maître
    cursor.execute("SELECT reference FROM products WHERE reference = ?", (clean_ref,))
    prod = cursor.fetchone()
    location = data.location.strip() if (data.location and data.location.strip()) else "EN_ATTENTE_AFFECTATION"

    if not prod:
        cursor.execute("""
            INSERT INTO products (reference, designation, category, gamme, unit, image_url, threshold, supplier, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (clean_ref, data.designation.strip(), data.category, data.gamme, data.unit, 
              (data.image_url or "").strip(),
              data.threshold, data.supplier, location, now))

    # Génération du code-barres par défaut si non fourni
    barcode = data.barcode.strip() if (data.barcode and data.barcode.strip()) else f"BAR-{clean_ref}-{clean_color[:3].upper()}"

    # Insertion de la variante avec PMP initial et Code RAL
    pmp_val = round(float(data.unit_price or 0), 2)
    cursor.execute("""
        INSERT INTO variants (product_reference, color, ral_code, color_hex, barcode, initial_quantity, real_quantity, reserved_quantity,
                              threshold, current_price, previous_price, pmp, supplier, location, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
    """, (clean_ref, clean_color, data.ral_code, data.color_hex or '#64748b', barcode, data.initial_quantity, data.initial_quantity,
          data.threshold, pmp_val, pmp_val, pmp_val, data.supplier, location, now))
    variant_id = cursor.lastrowid

    # Si stock initial > 0, enregistrer dans l'historique et les mouvements
    if data.initial_quantity > 0:
        cursor.execute("""
            INSERT INTO price_history (variant_id, product_reference, price, pmp_after, quantity, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (variant_id, clean_ref, pmp_val, pmp_val, data.initial_quantity, now))

        tot_val = round(data.initial_quantity * pmp_val, 2)
        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
            VALUES (?, 'STOCKAGE', ?, ?, ?, ?, ?, ?, ?, NULL, 'Atelier', 0, 'Création initiale au catalogue')
        """, (now, clean_ref, data.designation.strip(), clean_color, data.initial_quantity, pmp_val, pmp_val, tot_val))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Article {clean_ref} ({clean_color}) créé avec succès au Catalogue Maître.",
        "variant_id": variant_id,
        "location": location,
        "pmp": pmp_val
    }

def stock_in_operation(data: StockInRequest) -> Dict[str, Any]:
    """
    Entrée en stock d'un produit existant au Catalogue.
    RÈGLES STRICTES :
    - Interdiction des mouvements orphelins (doit exister au catalogue maître).
    - Contrôle du prix d'achat à 0 DZD.
    - Emplacement par défaut 'EN_ATTENTE_AFFECTATION' si omis.
    - Calcul dynamique du PMP selon la formule imposée :
      Nouveau PMP = ((Stock Existant * PMP Actuel) + (Qté Entrante * Prix Achat)) / (Stock Existant + Qté Entrante)
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Contrôle du prix à 0 DZD
    if (data.unit_price is None or data.unit_price <= 0) and not data.allow_zero_price:
        conn.close()
        raise ValueError("Prix d'achat non renseigné ou à 0 DZD. Une confirmation explicite est obligatoire.")

    # 2. Vérification que la variante existe dans le catalogue maître
    if data.variant_id:
        cursor.execute("""
            SELECT v.*, p.designation, p.unit 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE v.id = ?
        """, (data.variant_id,))
    else:
        cursor.execute("""
            SELECT v.*, p.designation, p.unit 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE UPPER(v.product_reference) = ? AND UPPER(v.color) = ?
        """, (data.reference.strip().upper(), data.color.strip().upper()))

    variant = cursor.fetchone()
    if not variant:
        conn.close()
        raise ValueError(f"Mouvement orphelin interdit : L'article '{data.reference}' ({data.color}) n'existe pas dans le Catalogue Maître. Veuillez d'abord créer l'article au catalogue.")

    var_id = variant["id"]
    ref = variant["product_reference"]
    color = variant["color"]
    designation = variant["designation"]
    existing_stock = float(variant["real_quantity"] or 0)
    current_pmp = float(variant["pmp"] or variant["current_price"] or 0)
    prev_price = float(variant["current_price"] or 0)

    # 3. Calcul du Nouveau PMP
    new_pmp = calculate_pmp(
        stock_existant=existing_stock,
        pmp_actuel=current_pmp,
        qte_entrante=data.quantity,
        prix_achat_unitaire=data.unit_price
    )

    new_real_stock = existing_stock + data.quantity

    # 4. Emplacement / Case
    target_location = data.location.strip() if (data.location and data.location.strip()) else (variant["location"] or "EN_ATTENTE_AFFECTATION")
    supplier = data.supplier.strip() if (data.supplier and data.supplier.strip()) else variant["supplier"]
    threshold = data.threshold if (data.threshold is not None) else variant["threshold"]

    # 5. Mise à jour de la variante
    cursor.execute("""
        UPDATE variants 
        SET previous_price = ?, current_price = ?, pmp = ?, real_quantity = ?, 
            threshold = ?, supplier = ?, location = ?, updated_at = ?
        WHERE id = ?
    """, (prev_price, data.unit_price, new_pmp, new_real_stock, threshold, supplier, target_location, now, var_id))

    # 6. Historique des prix & PMP
    cursor.execute("""
        INSERT INTO price_history (variant_id, product_reference, price, pmp_after, quantity, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (var_id, ref, data.unit_price, new_pmp, data.quantity, now))

    # 7. Journalisation du mouvement (pas d'opérateur lors du stockage)
    tot_val = round(data.quantity * data.unit_price, 2)
    cursor.execute("""
        INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
        VALUES (?, 'STOCKAGE', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?)
    """, (now, ref, designation, color, data.quantity, data.unit_price, new_pmp, tot_val, data.notes or f"Entrée en stock - PMP: {new_pmp} DZD"))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Stockage validé : {data.quantity} barres/unités. Nouveau PMP calculé : {new_pmp:,.2f} DZD.",
        "variant_id": var_id,
        "pmp": new_pmp,
        "new_stock": new_real_stock,
        "location": target_location
    }

def destock_operation(data: DestockRequest) -> Dict[str, Any]:
    """
    Sortie de stock physique avec contrôle de stock négatif strict,
    opérateur par défaut 'Atelier', et gestion des déstockages non assignés à une commande.
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT v.*, p.designation, p.unit 
        FROM variants v 
        JOIN products p ON v.product_reference = p.reference 
        WHERE v.id = ?
    """, (data.variant_id,))
    variant = cursor.fetchone()

    if not variant:
        conn.close()
        raise ValueError("Variante introuvable au catalogue maître.")

    real_qty = float(variant["real_quantity"] or 0)
    pmp_val = float(variant["pmp"] or variant["current_price"] or 0)

    # 1. INTERDICTION DU STOCK NÉGATIF (Blocage strict)
    if real_qty < data.quantity:
        conn.close()
        raise ValueError(f"Déstockage interdit (Stock Négatif) : Quantité physique disponible insuffisante ({real_qty} barres/unités en atelier, {data.quantity} demandée).")

    # 2. Gestion de l'affectation à une Commande avec saisie manuelle du lot ou texte libre si non assigné
    raw_order = data.order_number or data.chantier
    is_anonyme = 0
    warning_message = None

    if raw_order and raw_order.strip() and raw_order.strip().upper() not in ("NONE", "STOCK_GENERAL", "NON_ASSIGNE", "AUCUN"):
        lot_suffix = f" (Lot: {data.lot_number.strip().upper()})" if (data.lot_number and data.lot_number.strip()) else ""
        order_code = f"{raw_order.strip()}{lot_suffix}"
    else:
        is_anonyme = 1
        order_code = data.unassigned_reason.strip() if (data.unassigned_reason and data.unassigned_reason.strip()) else "Non assigné (Débit atelier libre)"
        warning_message = f"Sortie atelier non assignée à une commande : {order_code}."

    operator_name = data.operator.strip() if (data.operator and data.operator.strip()) else (data.poseur or "Atelier")
    new_real = real_qty - data.quantity

    # Mise à jour du stock physique
    cursor.execute("UPDATE variants SET real_quantity = ?, updated_at = ? WHERE id = ?", (new_real, now, data.variant_id))

    tot_val = round(data.quantity * pmp_val, 2)
    cursor.execute("""
        INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
        VALUES (?, 'DESTOCKAGE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now, variant["product_reference"], variant["designation"], variant["color"], data.quantity, pmp_val, pmp_val, tot_val, order_code, operator_name, is_anonyme, data.notes or f"Sortie: {order_code}"))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Déstockage de {data.quantity} {variant['color']} réalisé avec succès (Reste: {new_real}).",
        "warning": warning_message,
        "remaining_real_quantity": new_real,
        "pmp": pmp_val
    }

def batch_destock_operation(data: BatchDestockRequest) -> Dict[str, Any]:
    """
    Déstockage groupé de plusieurs articles pour un même lot ou commande.
    Champs communs partagés : Commande, Lot, Opérateur, Motif non assigné, Notes.
    Validation préalable de sécurité : aucun stock négatif autorisé sur l'ensemble du lot.
    """
    if not data.items:
        raise ValueError("Aucun article spécifié dans la liste de déstockage.")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Vérification préalable des stocks cumulés demandés
    requested_by_variant = {}
    for item in data.items:
        if item.quantity <= 0:
            conn.close()
            raise ValueError("Chaque quantité à déstocker doit être strictement supérieure à 0.")
        requested_by_variant[item.variant_id] = requested_by_variant.get(item.variant_id, 0.0) + item.quantity

    for v_id, total_qty in requested_by_variant.items():
        cursor.execute("""
            SELECT v.*, p.designation 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE v.id = ?
        """, (v_id,))
        variant = cursor.fetchone()
        if not variant:
            conn.close()
            raise ValueError(f"Variante #{v_id} introuvable au catalogue maître.")

        real_qty = float(variant["real_quantity"] or 0)
        if real_qty < total_qty:
            conn.close()
            raise ValueError(
                f"Déstockage refusé (Stock Négatif) pour '{variant['product_reference']} - {variant['color']}' : "
                f"Disponible en atelier : {real_qty}, Quantité totale demandée : {total_qty}."
            )

    # 2. Gestion de l'affectation à une Commande / Lot
    raw_order = data.order_number or data.chantier
    is_anonyme = 0
    warning_message = None

    if raw_order and raw_order.strip() and raw_order.strip().upper() not in ("NONE", "STOCK_GENERAL", "NON_ASSIGNE", "AUCUN"):
        lot_suffix = f" (Lot: {data.lot_number.strip().upper()})" if (data.lot_number and data.lot_number.strip()) else ""
        order_code = f"{raw_order.strip()}{lot_suffix}"
    else:
        is_anonyme = 1
        order_code = data.unassigned_reason.strip() if (data.unassigned_reason and data.unassigned_reason.strip()) else "Non assigné (Débit atelier libre)"
        warning_message = f"Sortie atelier groupée non assignée à une commande : {order_code}."

    operator_name = data.operator.strip() if (data.operator and data.operator.strip()) else (data.poseur or "Atelier")

    # 3. Application des déstockages et écriture des mouvements
    destocked_results = []
    for item in data.items:
        cursor.execute("""
            SELECT v.*, p.designation 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE v.id = ?
        """, (item.variant_id,))
        variant = cursor.fetchone()
        real_qty = float(variant["real_quantity"] or 0)
        pmp_val = float(variant["pmp"] or variant["current_price"] or 0)
        new_real = real_qty - item.quantity

        cursor.execute("UPDATE variants SET real_quantity = ?, updated_at = ? WHERE id = ?", (new_real, now, item.variant_id))

        tot_val = round(item.quantity * pmp_val, 2)
        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
            VALUES (?, 'DESTOCKAGE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, variant["product_reference"], variant["designation"], variant["color"], item.quantity, pmp_val, pmp_val, tot_val, order_code, operator_name, is_anonyme, data.notes or f"Sortie: {order_code}"))

        destocked_results.append({
            "variant_id": item.variant_id,
            "product_reference": variant["product_reference"],
            "color": variant["color"],
            "quantity": item.quantity,
            "remaining_real_quantity": new_real
        })

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Déstockage groupé de {len(data.items)} article(s) pour '{order_code}' validé avec succès.",
        "warning": warning_message,
        "items_count": len(data.items),
        "results": destocked_results
    }

def reserve_operation(data: ReserveRequest) -> Dict[str, Any]:
    """
    Réservation de barres pour un chantier spécifique :
    - Réduit la quantité DISPONIBLE mais préserve la quantité PHYSIQUE réelle.
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT v.*, p.designation 
        FROM variants v 
        JOIN products p ON v.product_reference = p.reference 
        WHERE v.id = ?
    """, (data.variant_id,))
    variant = cursor.fetchone()

    if not variant:
        conn.close()
        raise ValueError("Variante introuvable au catalogue.")

    real_qty = float(variant["real_quantity"] or 0)
    reserved_qty = float(variant["reserved_quantity"] or 0)
    avail_qty = max(0.0, real_qty - reserved_qty)

    if avail_qty < data.quantity:
        conn.close()
        raise ValueError(f"Réservation impossible : Quantité disponible insuffisante ({avail_qty} dispo, {data.quantity} demandée).")

    # Vérifier ou créer la commande / chantier
    order_num = data.order_number.strip().upper()
    lot_suffix = f" (Lot: {data.lot_number.strip().upper()})" if (data.lot_number and data.lot_number.strip()) else ""
    full_order_desc = f"{order_num}{lot_suffix}"

    cursor.execute("SELECT id FROM orders WHERE order_number = ?", (order_num,))
    order = cursor.fetchone()
    if not order:
        cursor.execute("""
            INSERT INTO orders (order_number, client_name, status, notes, created_at, updated_at)
            VALUES (?, ?, 'RESERVEE', ?, ?, ?)
        """, (order_num, data.client_name or f"Chantier {order_num}", data.notes, now, now))
        order_id = cursor.lastrowid
    else:
        order_id = order["id"]
        cursor.execute("UPDATE orders SET status = 'RESERVEE', updated_at = ? WHERE id = ?", (now, order_id))

    # Ajouter / mettre à jour les lignes de commande
    pmp_val = float(variant["pmp"] or variant["current_price"] or 0)
    cursor.execute("""
        SELECT id, quantity_reserved FROM order_items 
        WHERE order_id = ? AND variant_id = ? AND status = 'RESERVED' AND order_number = ?
    """, (order_id, data.variant_id, full_order_desc))
    existing_item = cursor.fetchone()

    if existing_item:
        cursor.execute("""
            UPDATE order_items 
            SET quantity_reserved = quantity_reserved + ? 
            WHERE id = ?
        """, (data.quantity, existing_item["id"]))
    else:
        cursor.execute("""
            INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color, quantity_reserved, quantity_destocked, unit_price, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'RESERVED')
        """, (order_id, full_order_desc, data.variant_id, variant["product_reference"], variant["designation"], variant["color"], data.quantity, pmp_val))

    # Bloquer la quantité réservée sur la variante
    cursor.execute("UPDATE variants SET reserved_quantity = reserved_quantity + ?, updated_at = ? WHERE id = ?", (data.quantity, now, data.variant_id))

    tot_val = round(data.quantity * pmp_val, 2)
    cursor.execute("""
        INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
        VALUES (?, 'RESERVATION', ?, ?, ?, ?, ?, ?, ?, ?, 'Atelier', 0, ?)
    """, (now, variant["product_reference"], variant["designation"], variant["color"], data.quantity, pmp_val, pmp_val, tot_val, full_order_desc, data.notes or f"Réservation pour {full_order_desc}"))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Réservation de {data.quantity} barres ({variant['color']}) pour {full_order_desc} validée.",
        "physical_stock": real_qty,
        "available_stock": avail_qty - data.quantity
    }

def batch_reserve_operation(data: BatchReserveRequest) -> Dict[str, Any]:
    """
    Réservation groupée de plusieurs articles pour une commande / chantier et un lot donnés.
    """
    if not data.items:
        raise ValueError("Aucun article spécifié dans la liste de réservation.")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Vérification préalable des disponibilités
    requested_by_variant = {}
    for item in data.items:
        if item.quantity <= 0:
            conn.close()
            raise ValueError("Chaque quantité à réserver doit être strictement supérieure à 0.")
        requested_by_variant[item.variant_id] = requested_by_variant.get(item.variant_id, 0.0) + item.quantity

    for v_id, total_qty in requested_by_variant.items():
        cursor.execute("""
            SELECT v.*, p.designation 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE v.id = ?
        """, (v_id,))
        variant = cursor.fetchone()
        if not variant:
            conn.close()
            raise ValueError(f"Variante #{v_id} introuvable au catalogue.")

        real_qty = float(variant["real_quantity"] or 0)
        reserved_qty = float(variant["reserved_quantity"] or 0)
        avail_qty = max(0.0, real_qty - reserved_qty)
        if avail_qty < total_qty:
            conn.close()
            raise ValueError(
                f"Réservation refusée : Disponibilité insuffisante pour '{variant['product_reference']} - {variant['color']}' "
                f"({avail_qty} dispo, {total_qty} demandées)."
            )

    # 2. Vérifier ou créer la commande / chantier
    order_num = data.order_number.strip().upper()
    lot_suffix = f" (Lot: {data.lot_number.strip().upper()})" if (data.lot_number and data.lot_number.strip()) else ""
    full_order_desc = f"{order_num}{lot_suffix}"

    cursor.execute("SELECT id FROM orders WHERE order_number = ?", (order_num,))
    order = cursor.fetchone()
    if not order:
        cursor.execute("""
            INSERT INTO orders (order_number, client_name, status, notes, created_at, updated_at)
            VALUES (?, ?, 'RESERVEE', ?, ?, ?)
        """, (order_num, data.client_name or f"Chantier {order_num}", data.notes, now, now))
        order_id = cursor.lastrowid
    else:
        order_id = order["id"]
        cursor.execute("UPDATE orders SET status = 'RESERVEE', updated_at = ? WHERE id = ?", (now, order_id))

    # 3. Application des réservations
    results = []
    for item in data.items:
        cursor.execute("""
            SELECT v.*, p.designation 
            FROM variants v 
            JOIN products p ON v.product_reference = p.reference 
            WHERE v.id = ?
        """, (item.variant_id,))
        variant = cursor.fetchone()
        pmp_val = float(variant["pmp"] or variant["current_price"] or 0)

        cursor.execute("""
            SELECT id, quantity_reserved FROM order_items 
            WHERE order_id = ? AND variant_id = ? AND status = 'RESERVED' AND order_number = ?
        """, (order_id, item.variant_id, full_order_desc))
        existing_item = cursor.fetchone()

        if existing_item:
            cursor.execute("""
                UPDATE order_items 
                SET quantity_reserved = quantity_reserved + ? 
                WHERE id = ?
            """, (item.quantity, existing_item["id"]))
        else:
            cursor.execute("""
                INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color, quantity_reserved, quantity_destocked, unit_price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 'RESERVED')
            """, (order_id, full_order_desc, item.variant_id, variant["product_reference"], variant["designation"], variant["color"], item.quantity, pmp_val))

        cursor.execute("UPDATE variants SET reserved_quantity = reserved_quantity + ?, updated_at = ? WHERE id = ?", (item.quantity, now, item.variant_id))

        tot_val = round(item.quantity * pmp_val, 2)
        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
            VALUES (?, 'RESERVATION', ?, ?, ?, ?, ?, ?, ?, ?, 'Atelier', 0, ?)
        """, (now, variant["product_reference"], variant["designation"], variant["color"], item.quantity, pmp_val, pmp_val, tot_val, full_order_desc, data.notes or f"Réservation groupée pour {full_order_desc}"))

        results.append({
            "variant_id": item.variant_id,
            "product_reference": variant["product_reference"],
            "color": variant["color"],
            "quantity": item.quantity
        })

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Réservation groupée de {len(data.items)} article(s) pour '{full_order_desc}' validée avec succès.",
        "items_count": len(data.items),
        "results": results
    }

def validate_and_destock_order(order_number: str, user: str = "Admin") -> Dict[str, Any]:
    """Déstocke définitivement tous les articles réservés à une commande / chantier."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    order_num = order_number.strip().upper()
    cursor.execute("SELECT * FROM orders WHERE order_number = ?", (order_num,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        raise ValueError(f"Commande / Chantier {order_num} introuvable.")

    cursor.execute("SELECT * FROM order_items WHERE order_number = ? AND status = 'RESERVED'", (order_num,))
    items = cursor.fetchall()
    if not items:
        conn.close()
        return {"success": False, "message": "Aucun article en attente de déstockage sur ce chantier."}

    destocked_count = 0
    total_val = 0.0

    for itm in items:
        qty = itm["quantity_reserved"]
        var_id = itm["variant_id"]
        price = itm["unit_price"]

        cursor.execute("SELECT real_quantity, reserved_quantity, pmp FROM variants WHERE id = ?", (var_id,))
        var_data = cursor.fetchone()
        if var_data:
            new_real = max(0.0, var_data["real_quantity"] - qty)
            new_res = max(0.0, var_data["reserved_quantity"] - qty)
            cursor.execute("UPDATE variants SET real_quantity = ?, reserved_quantity = ?, updated_at = ? WHERE id = ?", (new_real, new_res, now, var_id))

        cursor.execute("""
            UPDATE order_items 
            SET quantity_destocked = quantity_destocked + ?, quantity_reserved = 0, status = 'DESTOCKED'
            WHERE id = ?
        """, (qty, itm["id"]))

        line_val = round(qty * price, 2)
        total_val += line_val
        destocked_count += 1

        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes)
            VALUES (?, 'DESTOCKAGE', ?, ?, ?, ?, ?, ?, ?, ?, 'Atelier', 0, ?)
        """, (now, itm["product_reference"], itm["product_name"], itm["color"], qty, price, price, line_val, order_num, f"Validation déstockage commande/lot {order_num}"))

    cursor.execute("UPDATE orders SET status = 'DESTOCKED', updated_at = ? WHERE order_number = ?", (now, order_num))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Chantier {order_num} validé : {destocked_count} lignes déstockées ({round(total_val, 2):,.2f} DZD).",
        "total_destocked_value": round(total_val, 2)
    }

def get_products_with_variants(
    search: Optional[str] = None,
    category: Optional[str] = None,
    gamme: Optional[str] = None,
    supplier: Optional[str] = None,
    status_filter: Optional[str] = None,
    chantier_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Récupération du catalogue avec calcul PMP, statuts de stock et filtres réservé/chantier."""
    conn = get_db()
    cursor = conn.cursor()

    # Si filtrage par chantier/commande, récupérer les IDs de variantes associées
    chantier_variant_ids = set()
    if chantier_filter and chantier_filter != "ALL":
        cursor.execute("""
            SELECT DISTINCT oi.variant_id 
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE o.order_number = ? OR oi.order_number LIKE ?
        """, (chantier_filter, f"{chantier_filter}%"))
        chantier_variant_ids = {r["variant_id"] for r in cursor.fetchall()}

    query = """
        SELECT p.reference, p.designation, p.category, p.gamme, p.unit, p.image_url,
               p.supplier as default_supplier, p.location as default_location,
               v.id as variant_id, v.color, v.ral_code, v.color_hex, v.barcode, v.initial_quantity,
               v.real_quantity, v.reserved_quantity, v.threshold,
               v.current_price, v.previous_price, v.pmp,
               v.supplier as variant_supplier, v.location as variant_location,
               v.updated_at
        FROM products p
        LEFT JOIN variants v ON p.reference = v.product_reference
        WHERE 1=1
    """
    params = []

    if category and category != "ALL":
        query += " AND p.category = ?"
        params.append(category)

    if gamme and gamme != "ALL":
        query += " AND p.gamme = ?"
        params.append(gamme)

    if supplier and supplier != "ALL":
        query += " AND (v.supplier = ? OR p.supplier = ?)"
        params.extend([supplier, supplier])

    if search:
        search_term = f"%{search.strip()}%"
        query += """ AND (
            p.reference LIKE ? OR 
            p.designation LIKE ? OR 
            v.color LIKE ? OR 
            v.barcode LIKE ? OR 
            v.location LIKE ? OR 
            p.location LIKE ? OR 
            v.supplier LIKE ?
        )"""
        params.extend([search_term] * 7)

    query += " ORDER BY p.reference ASC, v.color ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    products_map = {}
    for r in rows:
        ref = r["reference"]
        if ref not in products_map:
            products_map[ref] = {
                "reference": ref,
                "designation": r["designation"],
                "category": r["category"],
                "gamme": r["gamme"],
                "unit": r["unit"],
                "image_url": r["image_url"],
                "supplier": r["default_supplier"],
                "location": r["default_location"],
                "total_real_quantity": 0,
                "total_reserved_quantity": 0,
                "total_value": 0,
                "variants": []
            }

        if r["variant_id"] is not None:
            real_q = float(r["real_quantity"] or 0)
            res_q = float(r["reserved_quantity"] or 0)
            avail_q = max(0.0, real_q - res_q)
            curr_p = float(r["current_price"] or 0)
            pmp_val = float(r["pmp"] or curr_p)
            thresh = float(r["threshold"] or 0)
            
            if real_q <= 0:
                status = "RUPTURE"
            elif real_q <= thresh:
                status = "STOCK_BAS"
            else:
                status = "EN_STOCK"

            if status_filter and status_filter != "ALL":
                if status_filter == "STOCK_BAS" and status not in ("STOCK_BAS", "RUPTURE"):
                    continue
                elif status_filter == "RUPTURE" and status != "RUPTURE":
                    continue
                elif status_filter == "EN_STOCK" and status != "EN_STOCK":
                    continue
                elif status_filter == "RESERVE" and res_q <= 0:
                    continue

            if chantier_filter and chantier_filter != "ALL":
                if r["variant_id"] not in chantier_variant_ids:
                    continue

            variant_data = {
                "id": r["variant_id"],
                "product_reference": ref,
                "color": r["color"],
                "ral_code": r["ral_code"] or "",
                "color_hex": r["color_hex"] or "#64748b",
                "barcode": r["barcode"] or f"BAR-{ref}-{r['color'][:3].upper()}",
                "initial_quantity": float(r["initial_quantity"] or 0),
                "real_quantity": real_q,
                "reserved_quantity": res_q,
                "available_quantity": avail_q,
                "threshold": thresh,
                "current_price": curr_p,
                "previous_price": float(r["previous_price"] or 0),
                "pmp": pmp_val,
                "real_stock_value": round(real_q * pmp_val, 2),
                "supplier": r["variant_supplier"] or r["default_supplier"],
                "location": r["variant_location"] or r["default_location"] or "EN_ATTENTE_AFFECTATION",
                "status": status,
                "updated_at": r["updated_at"]
            }

            products_map[ref]["variants"].append(variant_data)
            products_map[ref]["total_real_quantity"] += real_q
            products_map[ref]["total_reserved_quantity"] += res_q
            products_map[ref]["total_value"] += variant_data["real_stock_value"]

    result = []
    has_active_filter = (status_filter and status_filter != "ALL") or (chantier_filter and chantier_filter != "ALL")
    for p in products_map.values():
        p["total_value"] = round(p["total_value"], 2)
        if has_active_filter and len(p["variants"]) == 0:
            continue
        result.append(p)

    return result

def get_dashboard_metrics(
    period: Optional[str] = "ALL",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    selected_orders: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Indicateurs financiers et KPIs synchronisés :
    - Valeur d'achat totale (filtrable par période)
    - Valeur du stock réel au PMP = Sum(Quantité Réelle * PMP)
    - Valeur déstockée (filtrable par commande/lot et par période)
    - Alertes de stock bas
    - Alertes d'emplacements non affectés (EN_ATTENTE_AFFECTATION)
    """
    conn = get_db()
    cursor = conn.cursor()

    # Calcul de la plage de dates selon la période
    clean_period = (period or "ALL").upper()
    now_dt = datetime.now()
    start_ts = None
    end_ts = None

    if clean_period == "WEEK":
        # Début de la semaine en cours (Lundi 00:00:00)
        monday = now_dt - timedelta(days=now_dt.weekday())
        start_ts = monday.strftime("%Y-%m-%d 00:00:00")
        end_ts = now_dt.strftime("%Y-%m-%d 23:59:59")
    elif clean_period == "MONTH":
        # Début du mois en cours
        start_ts = now_dt.strftime("%Y-%m-01 00:00:00")
        end_ts = now_dt.strftime("%Y-%m-%d 23:59:59")
    elif clean_period == "YEAR":
        # Début de l'année en cours
        start_ts = now_dt.strftime("%Y-01-01 00:00:00")
        end_ts = now_dt.strftime("%Y-%m-%d 23:59:59")
    elif clean_period == "CUSTOM":
        if start_date and start_date.strip():
            start_ts = f"{start_date.strip()} 00:00:00"
        if end_date and end_date.strip():
            end_ts = f"{end_date.strip()} 23:59:59"

    # 1. Valeur d'achat sur la période
    purchase_query = """
        SELECT COALESCE(SUM(total_value), 0) as total_purchase_value,
               COALESCE(SUM(quantity), 0) as total_units_in
        FROM movements 
        WHERE action_type = 'STOCKAGE'
    """
    p_params = []
    if start_ts:
        purchase_query += " AND timestamp >= ?"
        p_params.append(start_ts)
    if end_ts:
        purchase_query += " AND timestamp <= ?"
        p_params.append(end_ts)

    cursor.execute(purchase_query, p_params)
    purchase_data = cursor.fetchone()
    total_purchase_val = round(float(purchase_data["total_purchase_value"] or 0), 2)

    # 2. Valeur du stock réel au PMP = SUM(Quantité Réelle * PMP)
    cursor.execute("""
        SELECT COALESCE(SUM(real_quantity * pmp), 0) as real_stock_val,
               COALESCE(SUM(real_quantity), 0) as total_real_qty,
               COALESCE(SUM(reserved_quantity), 0) as total_reserved_qty,
               COALESCE(SUM(reserved_quantity * pmp), 0) as total_reserved_val,
               COUNT(*) as total_variants_count
        FROM variants
    """)
    stock_stat = cursor.fetchone()
    real_stock_val = round(float(stock_stat["real_stock_val"] or 0), 2)
    total_real_qty = float(stock_stat["total_real_qty"] or 0)
    total_reserved_qty = float(stock_stat["total_reserved_qty"] or 0)
    total_reserved_val = round(float(stock_stat["total_reserved_val"] or 0), 2)
    total_variants_count = int(stock_stat["total_variants_count"] or 0)

    # 3. Valeur du stock déstocké (filtrable par période et par commande/lot)
    destock_query = """
        SELECT COALESCE(SUM(total_value), 0) as destocked_val,
               COALESCE(SUM(quantity), 0) as destocked_qty
        FROM movements 
        WHERE action_type = 'DESTOCKAGE'
    """
    destock_params = []
    if start_ts:
        destock_query += " AND timestamp >= ?"
        destock_params.append(start_ts)
    if end_ts:
        destock_query += " AND timestamp <= ?"
        destock_params.append(end_ts)
    if selected_orders and len(selected_orders) > 0 and "ALL" not in selected_orders:
        placeholders = ",".join(["?"] * len(selected_orders))
        destock_query += f" AND order_number IN ({placeholders})"
        destock_params.extend(selected_orders)

    cursor.execute(destock_query, destock_params)
    destock_stat = cursor.fetchone()
    destocked_val = round(float(destock_stat["destocked_val"] or 0), 2)
    destocked_qty = float(destock_stat["destocked_qty"] or 0)

    # 4. Alertes de stock bas : Quantité Réelle <= Seuil
    cursor.execute("""
        SELECT v.id, v.product_reference, p.designation, p.category, p.unit, p.image_url,
               v.color, v.ral_code, v.color_hex, v.real_quantity, v.reserved_quantity, v.threshold,
               v.pmp, v.location, v.supplier
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        WHERE v.real_quantity <= v.threshold
        ORDER BY (v.real_quantity / CASE WHEN v.threshold = 0 THEN 1 ELSE v.threshold END) ASC, v.real_quantity ASC
    """)
    alerts_rows = cursor.fetchall()
    alerts = []
    for a in alerts_rows:
        q = float(a["real_quantity"])
        t = float(a["threshold"])
        alerts.append({
            "variant_id": a["id"],
            "reference": a["product_reference"],
            "designation": a["designation"],
            "category": a["category"],
            "unit": a["unit"],
            "image_url": a["image_url"],
            "color": a["color"],
            "ral_code": a["ral_code"] or "",
            "color_hex": a["color_hex"],
            "real_quantity": q,
            "reserved_quantity": float(a["reserved_quantity"]),
            "threshold": t,
            "pmp": float(a["pmp"]),
            "location": a["location"],
            "supplier": a["supplier"],
            "severity": "CRITICAL" if q <= 0 else "WARNING"
        })

    # 5. Alertes d'inventaire : Articles en attente d'affectation de casier
    cursor.execute("""
        SELECT v.id, v.product_reference, p.designation, v.color, v.real_quantity, p.unit
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        WHERE v.location = 'EN_ATTENTE_AFFECTATION' OR v.location IS NULL OR v.location = ''
    """)
    unassigned_rows = cursor.fetchall()
    unassigned_locations = [
        {"variant_id": r["id"], "reference": r["product_reference"], "designation": r["designation"], "color": r["color"], "quantity": float(r["real_quantity"]), "unit": r["unit"]}
        for r in unassigned_rows
    ]

    # 6. Répartition par Catégorie au PMP
    cursor.execute("""
        SELECT p.category, 
               COALESCE(SUM(v.real_quantity * v.pmp), 0) as category_value,
               COALESCE(SUM(v.real_quantity), 0) as category_qty
        FROM products p
        JOIN variants v ON p.reference = v.product_reference
        GROUP BY p.category
        ORDER BY category_value DESC
    """)
    categories_dist = [
        {"category": r["category"], "value": round(float(r["category_value"]), 2), "quantity": float(r["category_qty"])}
        for r in cursor.fetchall()
    ]

    # 7. Évolution des flux (filtrée par période et commande)
    timeline_query = """
        SELECT SUBSTR(timestamp, 1, 10) as day_date, action_type,
               COALESCE(SUM(quantity), 0) as day_qty,
               COALESCE(SUM(total_value), 0) as day_val
        FROM movements
        WHERE 1=1
    """
    t_params = []
    if start_ts:
        timeline_query += " AND timestamp >= ?"
        t_params.append(start_ts)
    if end_ts:
        timeline_query += " AND timestamp <= ?"
        t_params.append(end_ts)
    if selected_orders and len(selected_orders) > 0 and "ALL" not in selected_orders:
        placeholders = ",".join(["?"] * len(selected_orders))
        timeline_query += f" AND (order_number IN ({placeholders}) OR action_type = 'STOCKAGE')"
        t_params.extend(selected_orders)

    timeline_query += " GROUP BY day_date, action_type ORDER BY day_date ASC"
    cursor.execute(timeline_query, t_params)
    mvt_history = cursor.fetchall()

    days_set = sorted(list(set(r["day_date"] for r in mvt_history)))
    timeline_data = {
        "labels": days_set,
        "stockage": [0.0] * len(days_set),
        "destockage": [0.0] * len(days_set)
    }
    day_indices = {day: idx for idx, day in enumerate(days_set)}

    for r in mvt_history:
        d_idx = day_indices[r["day_date"]]
        act = r["action_type"]
        val = round(float(r["day_val"]), 2)
        if act == "STOCKAGE":
            timeline_data["stockage"][d_idx] += val
        elif act == "DESTOCKAGE":
            timeline_data["destockage"][d_idx] += val

    # 8. Alertes d'inventaire en anomalie (désaccord entre personnes ou avec stock réel)
    cursor.execute("""
        SELECT ic.id as count_id, ic.variant_id, ic.product_reference, p.designation, p.unit, p.image_url,
               v.color, v.ral_code, v.color_hex, v.location, v.pmp,
               v.real_quantity as current_real_qty, ic.expected_quantity,
               ic.person1_name, ic.count1, ic.person2_name, ic.count2,
               ic.status, ic.updated_at
        FROM inventory_counts ic
        JOIN variants v ON ic.variant_id = v.id
        JOIN products p ON v.product_reference = p.reference
        WHERE ic.status IN ('DISCREPANCY', 'RECOUNT_NEEDED')
           OR (ic.count1 IS NOT NULL AND ic.count2 IS NOT NULL AND (ic.count1 != ic.count2 OR ic.count1 != v.real_quantity))
        ORDER BY ic.updated_at DESC
    """)
    inv_anom_rows = cursor.fetchall()
    inventory_anomalies_alerts = []
    for r in inv_anom_rows:
        c1 = r["count1"]
        c2 = r["count2"]
        rq = float(r["current_real_qty"])
        
        # Déterminer la nature de l'anomalie
        if c1 is not None and c2 is not None and c1 != c2:
            issue_type = "DISCORDANCE_COMPTAGE"
            issue_label = f"Désaccord comptage : {r['person1_name']} ({c1:g}) ≠ {r['person2_name']} ({c2:g})"
        elif c1 is not None and c2 is not None and c1 != rq:
            diff = c1 - rq
            issue_type = "ECART_STOCK"
            issue_label = f"Écart stock réel : {rq:g} vs Compté : {c1:g} ({diff:+g})"
        else:
            issue_type = "RECOMPTAGE_REQUIS"
            issue_label = "Recomptage requis"

        inventory_anomalies_alerts.append({
            "count_id": r["count_id"],
            "variant_id": r["variant_id"],
            "reference": r["product_reference"],
            "designation": r["designation"],
            "unit": r["unit"],
            "image_url": r["image_url"],
            "color": r["color"],
            "ral_code": r["ral_code"] or "",
            "color_hex": r["color_hex"],
            "location": r["location"],
            "pmp": float(r["pmp"]),
            "real_quantity": rq,
            "person1_name": r["person1_name"],
            "count1": c1,
            "person2_name": r["person2_name"],
            "count2": c2,
            "status": r["status"],
            "issue_type": issue_type,
            "issue_label": issue_label,
            "updated_at": r["updated_at"]
        })

    cursor.execute("SELECT COUNT(*) as cnt FROM products")
    total_products_count = cursor.fetchone()["cnt"]

    conn.close()

    return {
        "kpis": {
            "period": clean_period,
            "start_date": start_ts,
            "end_date": end_ts,
            "total_purchase_value": total_purchase_val,
            "real_stock_value": real_stock_val,
            "destocked_value": destocked_val,
            "total_reserved_value": total_reserved_val,
            "total_real_quantity": total_real_qty,
            "total_reserved_quantity": total_reserved_qty,
            "available_quantity": max(0.0, total_real_qty - total_reserved_qty),
            "total_products_count": total_products_count,
            "total_variants_count": total_variants_count,
            "low_stock_count": len(alerts),
            "unassigned_location_count": len(unassigned_locations),
            "inventory_anomalies_count": len(inventory_anomalies_alerts)
        },
        "alerts": alerts,
        "unassigned_locations": unassigned_locations,
        "inventory_anomalies_alerts": inventory_anomalies_alerts,
        "charts": {
            "categories": categories_dist,
            "timeline": timeline_data
        }
    }

# =========================================================================
# GESTION DE L'INVENTAIRE CROISÉ (DOUBLE COMPTAGE PAR 2 PERSONNES & ANOMALIES)
# =========================================================================

def get_inventory_items(
    search: Optional[str] = None,
    status_filter: Optional[str] = "ALL",
    selected_only: bool = False
) -> Dict[str, Any]:
    """
    Retourne la liste complète des articles déclinés par référence et couleur pour l'inventaire.
    Règles :
    - Chaque référence s'affiche autant de fois qu'elle a de couleurs différentes.
    - Double comptage : Personne 1 et Personne 2.
    - Si les deux calculs ne correspondent pas entre eux OU ne correspondent pas avec la quantité réelle :
      l'article est marqué en anomalie (rouge).
    - Date d'inventaire affichée si effectuée, sinon 'Pas passé par inventaire'.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT v.id as variant_id, v.product_reference, p.designation, p.category, p.gamme, p.unit, p.image_url,
               v.color, v.ral_code, v.color_hex, v.location, v.real_quantity, v.reserved_quantity, v.threshold,
               v.pmp, v.last_inventory_date,
               ic.id as count_id, ic.person1_name, ic.count1, ic.person2_name, ic.count2,
               ic.expected_quantity, ic.status as count_status, ic.is_selected, ic.notes as count_notes,
               ic.updated_at as count_updated_at
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        LEFT JOIN inventory_counts ic ON v.id = ic.variant_id
        WHERE 1=1
    """
    params = []

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += """ AND (
            v.product_reference LIKE ? OR 
            p.designation LIKE ? OR 
            v.color LIKE ? OR 
            v.ral_code LIKE ? OR 
            p.category LIKE ? OR 
            p.gamme LIKE ? OR 
            v.location LIKE ?
        )"""
        params.extend([term] * 7)

    query += " ORDER BY v.product_reference ASC, v.color ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    counts_stats = {
        "total": len(rows),
        "not_inventoried": 0,
        "in_progress": 0,
        "conforme": 0,
        "discrepancy_persons": 0,
        "discrepancy_stock": 0,
        "recount_needed": 0,
        "adjusted": 0,
        "total_anomalies": 0,
        "selected_count": 0
    }

    for r in rows:
        rq = float(r["real_quantity"] or 0)
        c1 = r["count1"]
        c2 = r["count2"]
        db_status = r["count_status"]
        last_date = r["last_inventory_date"]
        is_sel = bool(r["is_selected"])
        if is_sel:
            counts_stats["selected_count"] += 1

        # Évaluation du statut et de l'anomalie
        # Règle d'or utilisateur :
        # "si les deux calcule ne se correspand pas entre eux ou avec la quantité reel donc l'article se met en rouge"
        status = "NOT_INVENTORIED"
        status_label = "Pas passé par inventaire"
        is_red = False
        discrepancy_type = None
        discrepancy_diff = 0.0

        if db_status == "ADJUSTED":
            status = "ADJUSTED"
            status_label = "Inventaire validé (Mis à niveau)"
            counts_stats["adjusted"] += 1
        elif db_status == "RECOUNT_NEEDED":
            status = "RECOUNT_NEEDED"
            status_label = "Recomptage requis"
            is_red = True
            counts_stats["recount_needed"] += 1
            counts_stats["total_anomalies"] += 1
        elif c1 is None and c2 is None:
            if last_date:
                status = "PREVIOUSLY_INVENTORIED"
                status_label = f"Dernier inventaire : {last_date}"
            else:
                status = "NOT_INVENTORIED"
                status_label = "Pas passé par inventaire"
                counts_stats["not_inventoried"] += 1
        elif c1 is not None and c2 is None:
            status = "IN_PROGRESS"
            status_label = f"En cours ({r['person1_name'] or 'Pers. 1'} a compté)"
            counts_stats["in_progress"] += 1
        elif c1 is None and c2 is not None:
            status = "IN_PROGRESS"
            status_label = f"En cours ({r['person2_name'] or 'Pers. 2'} a compté)"
            counts_stats["in_progress"] += 1
        else: # c1 is not None and c2 is not None
            c1_val = float(c1)
            c2_val = float(c2)
            if c1_val != c2_val:
                status = "DISCREPANCY_PERSONS"
                status_label = f"Désaccord comptage ({r['person1_name'] or 'Pers. 1'}: {c1_val:g} ≠ {r['person2_name'] or 'Pers. 2'}: {c2_val:g})"
                is_red = True
                discrepancy_type = "PERSONS_MISMATCH"
                discrepancy_diff = abs(c1_val - c2_val)
                counts_stats["discrepancy_persons"] += 1
                counts_stats["total_anomalies"] += 1
            elif c1_val != rq:
                status = "DISCREPANCY_STOCK"
                diff = c1_val - rq
                status_label = f"Écart stock réel ({rq:g} réel vs {c1_val:g} compté [{diff:+g}])"
                is_red = True
                discrepancy_type = "STOCK_MISMATCH"
                discrepancy_diff = diff
                counts_stats["discrepancy_stock"] += 1
                counts_stats["total_anomalies"] += 1
            else:
                status = "CONFORME"
                status_label = f"Conforme ({c1_val:g} = stock réel)"
                counts_stats["conforme"] += 1

        item = {
            "variant_id": r["variant_id"],
            "count_id": r["count_id"],
            "reference": r["product_reference"],
            "designation": r["designation"],
            "category": r["category"],
            "gamme": r["gamme"],
            "unit": r["unit"],
            "image_url": r["image_url"],
            "color": r["color"],
            "ral_code": r["ral_code"] or "",
            "color_hex": r["color_hex"] or "#64748b",
            "location": r["location"] or "EN_ATTENTE_AFFECTATION",
            "real_quantity": rq,
            "reserved_quantity": float(r["reserved_quantity"] or 0),
            "pmp": float(r["pmp"] or 0),
            "last_inventory_date": last_date,
            "last_inventory_date_display": last_date if last_date else "Pas passé par inventaire",
            "person1_name": r["person1_name"] or "Personne 1",
            "count1": c1,
            "person2_name": r["person2_name"] or "Personne 2",
            "count2": c2,
            "status": status,
            "status_label": status_label,
            "is_red": is_red,
            "discrepancy_type": discrepancy_type,
            "discrepancy_diff": discrepancy_diff,
            "is_selected": is_sel,
            "count_notes": r["count_notes"] or "",
            "count_updated_at": r["count_updated_at"]
        }

        # Filtrage applicatif par status si demandé
        if selected_only and not is_sel:
            continue

        if status_filter and status_filter != "ALL":
            if status_filter == "DISCREPANCY" and not is_red:
                continue
            elif status_filter == "NOT_INVENTORIED" and status != "NOT_INVENTORIED":
                continue
            elif status_filter == "CONFORME" and status != "CONFORME":
                continue
            elif status_filter == "SELECTED" and not is_sel:
                continue
            elif status_filter == "ADJUSTED" and status != "ADJUSTED":
                continue

        items.append(item)

    return {
        "stats": counts_stats,
        "items": items
    }

def save_inventory_counts(
    items: List[Dict[str, Any]],
    person1_default: Optional[str] = "Personne 1",
    person2_default: Optional[str] = "Personne 2"
) -> Dict[str, Any]:
    """
    Enregistre ou met à jour les comptages de deux personnes pour une liste de variantes.
    Calcule automatiquement les désaccords (Personne 1 != Personne 2) ou écarts de stock réel.
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    updated_count = 0
    anomalies_detected = 0

    for it in items:
        v_id = it.get("variant_id")
        if not v_id:
            continue

        cursor.execute("SELECT product_reference, color, real_quantity FROM variants WHERE id = ?", (v_id,))
        var = cursor.fetchone()
        if not var:
            continue

        ref = var["product_reference"]
        color = var["color"]
        real_qty = float(var["real_quantity"] or 0)

        p1_name = it.get("person1_name") or person1_default or "Personne 1"
        c1 = it.get("count1")
        p2_name = it.get("person2_name") or person2_default or "Personne 2"
        c2 = it.get("count2")
        notes = it.get("notes") or ""

        c1_float = float(c1) if c1 is not None and str(c1).strip() != "" else None
        c2_float = float(c2) if c2 is not None and str(c2).strip() != "" else None

        # Calcul du statut
        status = "PENDING"
        if c1_float is not None and c2_float is not None:
            if c1_float != c2_float or c1_float != real_qty:
                status = "DISCREPANCY"
                anomalies_detected += 1
            else:
                status = "CONFORME"
        elif c1_float is not None or c2_float is not None:
            status = "PENDING"

        # Insertion ou mise à jour
        cursor.execute("""
            INSERT INTO inventory_counts (
                variant_id, product_reference, color, person1_name, count1, person2_name, count2,
                expected_quantity, status, inventory_date, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(variant_id) DO UPDATE SET
                person1_name = excluded.person1_name,
                count1 = excluded.count1,
                person2_name = excluded.person2_name,
                count2 = excluded.count2,
                expected_quantity = excluded.expected_quantity,
                status = excluded.status,
                inventory_date = excluded.inventory_date,
                notes = excluded.notes,
                updated_at = excluded.updated_at
        """, (v_id, ref, color, p1_name, c1_float, p2_name, c2_float, real_qty, status, now, notes, now, now))

        updated_count += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Comptages enregistrés pour {updated_count} article(s). ({anomalies_detected} anomalie(s) détectée(s))",
        "updated_count": updated_count,
        "anomalies_detected": anomalies_detected
    }

def set_inventory_selection(variant_ids: List[int], is_selected: bool = True) -> Dict[str, Any]:
    """Sélectionne ou désélectionne des articles pour lancer une session d'inventaire ciblée."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sel_val = 1 if is_selected else 0
    for v_id in variant_ids:
        cursor.execute("SELECT product_reference, color, real_quantity FROM variants WHERE id = ?", (v_id,))
        var = cursor.fetchone()
        if not var:
            continue
        cursor.execute("""
            INSERT INTO inventory_counts (variant_id, product_reference, color, expected_quantity, is_selected, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(variant_id) DO UPDATE SET
                is_selected = excluded.is_selected,
                updated_at = excluded.updated_at
        """, (v_id, var["product_reference"], var["color"], float(var["real_quantity"] or 0), sel_val, now, now))

    conn.commit()
    conn.close()
    return {"success": True, "count": len(variant_ids), "is_selected": is_selected}

def recount_inventory_item(variant_id: int, notes: Optional[str] = "") -> Dict[str, Any]:
    """
    Réinitialise les comptages d'un article en anomalie et le passe en 'RECOUNT_NEEDED'.
    Permet aux 2 personnes de refaire le comptage physique en atelier.
    """
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT v.product_reference, v.color, v.real_quantity 
        FROM variants v WHERE v.id = ?
    """, (variant_id,))
    var = cursor.fetchone()
    if not var:
        conn.close()
        raise ValueError(f"Variante #{variant_id} introuvable.")

    cursor.execute("""
        INSERT INTO inventory_counts (
            variant_id, product_reference, color, expected_quantity, status, count1, count2, notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'RECOUNT_NEEDED', NULL, NULL, ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            status = 'RECOUNT_NEEDED',
            count1 = NULL,
            count2 = NULL,
            notes = excluded.notes,
            updated_at = excluded.updated_at
    """, (variant_id, var["product_reference"], var["color"], float(var["real_quantity"] or 0), notes or "Recomptage demandé suite à anomalie", now, now))

    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": f"Demande de recomptage enregistrée pour {var['product_reference']} ({var['color']})."
    }

def adjust_stock_to_inventory(data: InventoryAdjustmentRequest) -> Dict[str, Any]:
    """
    Mise à niveau du stock vers la quantité d'inventaire retenue suite à une anomalie.
    Exigences strictes :
    - Motif obligatoire de l'anomalie (ex: casse, chute de coupe non déclarée, erreur de saisie précédente).
    - Enregistrement dans la table `inventory_anomalies` pour le sous-onglet d'historique.
    - Synchronisation automatique du journal des mouvements et de la date du dernier inventaire.
    """
    if not data.reason or len(data.reason.strip()) < 3:
        raise ValueError("Le motif de l'anomalie est obligatoire pour valider la mise à niveau du stock.")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Récupération de la variante et de l'article maître
    cursor.execute("""
        SELECT v.*, p.designation, p.unit
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        WHERE v.id = ?
    """, (data.variant_id,))
    var = cursor.fetchone()
    if not var:
        conn.close()
        raise ValueError(f"Variante #{data.variant_id} introuvable.")

    real_before = float(var["real_quantity"] or 0)
    pmp_val = float(var["pmp"] or 0)
    new_qty = float(data.chosen_quantity)
    diff = round(new_qty - real_before, 2)
    fin_impact = round(diff * pmp_val, 2)

    # 2. Récupération des comptages pour historique
    cursor.execute("SELECT * FROM inventory_counts WHERE variant_id = ?", (data.variant_id,))
    count_row = cursor.fetchone()
    p1_name = count_row["person1_name"] if count_row else "Personne 1"
    c1 = count_row["count1"] if count_row else None
    p2_name = count_row["person2_name"] if count_row else "Personne 2"
    c2 = count_row["count2"] if count_row else None

    # 3. Mise à niveau du stock réel et mise à jour de la date d'inventaire
    cursor.execute("""
        UPDATE variants 
        SET real_quantity = ?, last_inventory_date = ?, updated_at = ?
        WHERE id = ?
    """, (new_qty, now, now, data.variant_id))

    # 4. Enregistrement dans l'historique des anomalies (pour le sous-onglet Anomalies)
    cursor.execute("""
        INSERT INTO inventory_anomalies (
            variant_id, product_reference, designation, color,
            real_quantity_before, counted_quantity, discrepancy_quantity,
            pmp_at_adjustment, financial_impact,
            person1_name, count1, person2_name, count2,
            reason, notes, adjusted_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.variant_id, var["product_reference"], var["designation"], var["color"],
        real_before, new_qty, diff,
        pmp_val, fin_impact,
        p1_name, c1, p2_name, c2,
        data.reason.strip(), data.notes or "", data.operator or "Admin", now
    ))
    anomaly_id = cursor.lastrowid

    # 5. Traçabilité dans le journal des mouvements
    if diff != 0:
        action_type = "STOCKAGE" if diff > 0 else "DESTOCKAGE"
        cursor.execute("""
            INSERT INTO movements (
                timestamp, action_type, product_reference, product_name, color,
                quantity, unit_price, pmp_at_movement, total_value,
                order_number, operator, is_anonyme, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'INVENTAIRE', ?, 0, ?)
        """, (
            now, action_type, var["product_reference"], var["designation"], var["color"],
            abs(diff), pmp_val, pmp_val, abs(fin_impact),
            data.operator or "Admin",
            f"Mise à niveau inventaire : {data.reason.strip()} (Écart: {diff:+g} {var['unit']})"
        ))

    # 6. Mise à jour de l'état du comptage
    cursor.execute("""
        INSERT INTO inventory_counts (
            variant_id, product_reference, color, count1, count2, expected_quantity, status, inventory_date, updated_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'ADJUSTED', ?, ?, ?)
        ON CONFLICT(variant_id) DO UPDATE SET
            status = 'ADJUSTED',
            count1 = excluded.count1,
            count2 = excluded.count2,
            expected_quantity = excluded.expected_quantity,
            inventory_date = excluded.inventory_date,
            updated_at = excluded.updated_at
    """, (data.variant_id, var["product_reference"], var["color"], new_qty, new_qty, new_qty, now, now, now))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Stock de {var['product_reference']} ({var['color']}) mis à niveau avec succès à {new_qty:g} {var['unit']}.",
        "anomaly_id": anomaly_id,
        "variant_id": data.variant_id,
        "quantity_before": real_before,
        "quantity_after": new_qty,
        "discrepancy": diff,
        "financial_impact": fin_impact,
        "reason": data.reason.strip()
    }

def get_inventory_anomalies(search: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retourne la liste des anomalies d'inventaire régularisées après mise à niveau.
    Alimente le sous-onglet Anomalies.
    """
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT ia.*, p.unit, p.category, p.image_url, v.ral_code, v.color_hex, v.location
        FROM inventory_anomalies ia
        JOIN variants v ON ia.variant_id = v.id
        JOIN products p ON ia.product_reference = p.reference
        WHERE 1=1
    """
    params = []

    if search and search.strip():
        term = f"%{search.strip()}%"
        query += """ AND (
            ia.product_reference LIKE ? OR 
            ia.designation LIKE ? OR 
            ia.color LIKE ? OR 
            ia.reason LIKE ? OR 
            ia.adjusted_by LIKE ? OR 
            ia.notes LIKE ?
        )"""
        params.extend([term] * 6)

    query += " ORDER BY ia.created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    anomalies = []
    for r in rows:
        anomalies.append({
            "id": r["id"],
            "variant_id": r["variant_id"],
            "reference": r["product_reference"],
            "designation": r["designation"],
            "category": r["category"],
            "unit": r["unit"],
            "image_url": r["image_url"],
            "color": r["color"],
            "ral_code": r["ral_code"] or "",
            "color_hex": r["color_hex"] or "#64748b",
            "location": r["location"] or "EN_ATTENTE_AFFECTATION",
            "real_quantity_before": float(r["real_quantity_before"]),
            "counted_quantity": float(r["counted_quantity"]),
            "discrepancy_quantity": float(r["discrepancy_quantity"]),
            "pmp": float(r["pmp_at_adjustment"]),
            "financial_impact": float(r["financial_impact"]),
            "person1_name": r["person1_name"],
            "count1": r["count1"],
            "person2_name": r["person2_name"],
            "count2": r["count2"],
            "reason": r["reason"],
            "notes": r["notes"] or "",
            "adjusted_by": r["adjusted_by"],
            "created_at": r["created_at"]
        })

    return anomalies

def generate_inventory_pdf_bytes(
    variant_ids: Optional[List[int]] = None,
    person1: str = "Opérateur 1",
    person2: str = "Opérateur 2",
    hide_stock: bool = True
) -> bytes:
    """
    Génère un document PDF natif A4 paysage vectoriel haute définition via ReportLab.
    Génère 2 exemplaires distincts (1 pour Opérateur 1, 1 pour Opérateur 2) sans afficher
    le stock théorique (comptage contradictoire aveugle strict).
    """
    import io
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.pdfgen import canvas

    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT v.id as variant_id, v.product_reference, p.designation, p.category, p.gamme, p.unit,
               v.color, v.ral_code, v.location, v.real_quantity, v.pmp, v.last_inventory_date,
               ic.person1_name, ic.count1, ic.person2_name, ic.count2, ic.is_selected
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        LEFT JOIN inventory_counts ic ON v.id = ic.variant_id
        WHERE 1=1
    """
    params = []
    if variant_ids and len(variant_ids) > 0:
        placeholders = ",".join(["?"] * len(variant_ids))
        query += f" AND v.id IN ({placeholders})"
        params.extend(variant_ids)
    else:
        query += " AND (ic.is_selected = 1)"

    query += " ORDER BY v.location ASC, v.product_reference ASC, v.color ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    if not rows and not variant_ids:
        cursor.execute("""
            SELECT v.id as variant_id, v.product_reference, p.designation, p.category, p.gamme, p.unit,
                   v.color, v.ral_code, v.location, v.real_quantity, v.pmp, v.last_inventory_date,
                   ic.person1_name, ic.count1, ic.person2_name, ic.count2, ic.is_selected
            FROM variants v
            JOIN products p ON v.product_reference = p.reference
            LEFT JOIN inventory_counts ic ON v.id = ic.variant_id
            ORDER BY v.location ASC, v.product_reference ASC, v.color ASC
        """)
        rows = cursor.fetchall()

    conn.close()

    p1_name = person1 or "Opérateur 1"
    p2_name = person2 or "Opérateur 2"
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
    doc_ref = f"INV-{datetime.now().strftime('%Y%m%d-%H%M')}"

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_decorations(num_pages)
                super().showPage()
            super().save()

        def draw_page_decorations(self, page_count):
            self.saveState()
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawString(25, 14, "StockMaster Alu & Volets Roulants - Fiche Officielle de Comptage Physique Contradictoire (Sans Stock Theorique)")
            page_str = f"Page {self._pageNumber} sur {page_count}"
            self.drawRightString(landscape(A4)[0] - 25, 14, page_str)
            self.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=20,
        bottomMargin=26
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=13, leading=15, textColor=colors.HexColor('#0f172a'))
    cell_norm = ParagraphStyle('CellN', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9)
    cell_muted = ParagraphStyle('CellM', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.5, textColor=colors.HexColor('#64748b'))

    elements = []
    ITEMS_PER_PAGE = 10
    total_articles = len(rows)
    pages_per_copy = max(1, (total_articles + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    # Définition des 2 exemplaires (1 pour chaque opérateur)
    copies = [
        {"num": 1, "name": p1_name, "title": "EXEMPLAIRE 1 • PREMIER COMPTAGE", "color": "#4f46e5"},
        {"num": 2, "name": p2_name, "title": "EXEMPLAIRE 2 • DEUXIÈME COMPTAGE (CONTRÔLE CROISÉ)", "color": "#059669"}
    ]

    for copy_idx, copy_info in enumerate(copies):
        for page_idx in range(1, pages_per_copy + 1):
            page_slice = rows[(page_idx - 1) * ITEMS_PER_PAGE : page_idx * ITEMS_PER_PAGE]

            head_data = [
                [
                    Paragraph(f"<b>FICHE DE COMPTAGE D'INVENTAIRE PHYSIQUE</b><br/><font color=\"{copy_info['color']}\" size=\"8\"><b>{copy_info['title']}</b> - Opérateur désigné : {copy_info['name']}</font>", title_style),
                    Paragraph(f"<b>N° Fiche :</b> {doc_ref}<br/><b>Date & Heure :</b> {now_str}<br/><b>Opérateur :</b> {copy_info['name']}<br/><b>Articles :</b> {total_articles} réf. (Page {page_idx}/{pages_per_copy})", cell_norm)
                ]
            ]
            head_table = Table(head_data, colWidths=[540, 250])
            head_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            elements.append(head_table)
            elements.append(Spacer(1, 6))

            # Table sans colonne de stock théorique, avec grande case de comptage dédiée
            col_widths = [25, 95, 250, 110, 85, 45, 100, 80]
            table_data = [
                ['N°', 'RÉF. PROFILÉ', 'DÉSIGNATION & GAMME', 'TEINTE / RAL', 'CASIER', 'UNITÉ', f'COMPTAGE ({copy_info["name"][:12]})', 'OBSERVATIONS']
            ]

            for item_idx, r in enumerate(page_slice, start=(page_idx - 1) * ITEMS_PER_PAGE + 1):
                loc = r['location'] or 'EN_ATTENTE'
                desig_p = Paragraph(f"<b>{r['designation']}</b><br/><font color=\"#64748b\" size=\"6.5\">{r['category']} • {r['gamme']}</font>", cell_norm)
                ral_str = f"RAL {r['ral_code']}" if r['ral_code'] else ""
                color_p = Paragraph(f"<b>{r['color']}</b>" + (f"<br/><font color=\"#64748b\" size=\"6.5\">{ral_str}</font>" if ral_str else ""), cell_norm)
                
                # Valeur déjà enregistrée si existante, sinon vide pour écriture manuelle
                existing_count = r['count1'] if copy_info["num"] == 1 else r['count2']
                count_str = f"{existing_count:g}" if existing_count is not None else ""

                table_data.append([
                    str(item_idx),
                    r['product_reference'],
                    desig_p,
                    color_p,
                    loc,
                    r['unit'],
                    count_str,
                    ""
                ])

            if len(page_slice) < ITEMS_PER_PAGE:
                for blank_idx in range(len(page_slice) + 1, ITEMS_PER_PAGE + 1):
                    row_num = (page_idx - 1) * ITEMS_PER_PAGE + blank_idx
                    table_data.append([
                        str(row_num),
                        "",
                        Paragraph("<font color=\"#94a3b8\">--- Ligne libre atelier (Réf. ajoutée non répertoriée) ---</font>", cell_muted),
                        "",
                        "Casier: ....",
                        "",
                        "",
                        ""
                    ])

            t = Table(table_data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 7.5),
                ('ALIGN', (0,0), (-1,0), 'CENTER'),
                ('ALIGN', (0,1), (0,-1), 'CENTER'),
                ('ALIGN', (4,1), (5,-1), 'CENTER'),
                ('ALIGN', (6,1), (6,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
                ('BOX', (6,1), (6,-1), 1.2, colors.HexColor(copy_info['color'])),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 3.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

            # Signature de l'opérateur concerné et visa
            sig_data = [
                [
                    f"OPÉRATEUR : {copy_info['name']} ({copy_info['title']})\n\nJe certifie l'exactitude du comptage physique réalisé.\nDate & Signature :",
                    "VISA RESPONSABLE ATELIER / DIRECTION\n\nContrôle & Émargement :"
                ]
            ]
            sig_table = Table(sig_data, colWidths=[490, 300])
            sig_table.setStyle(TableStyle([
                ('BOX', (0,0), (0,0), 0.8, colors.HexColor('#94a3b8')),
                ('BOX', (1,0), (1,0), 0.8, colors.HexColor('#94a3b8')),
                ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 7.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 16),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ]))
            elements.append(sig_table)

            # Saut de page entre chaque feuille
            if not (copy_idx == len(copies) - 1 and page_idx == pages_per_copy):
                elements.append(PageBreak())

    doc.build(elements, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def generate_inventory_print_sheet(
    variant_ids: Optional[List[int]] = None,
    person1: str = "Opérateur 1",
    person2: str = "Opérateur 2"
) -> str:
    """
    Génère les fiches officielles de comptage d'inventaire physique A4.
    Produit 2 fiches distinctes (1 pour chaque comptage / opérateur), prêtes pour un comptage
    contradictoire strict à l'aveugle SANS affichage du stock théorique.
    """
    conn = get_db()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M")
    doc_ref = f"INV-{datetime.now().strftime('%Y%m%d-%H%M')}"

    query = """
        SELECT v.id as variant_id, v.product_reference, p.designation, p.category, p.gamme, p.unit,
               p.image_url, v.color, v.ral_code, v.location, v.real_quantity, v.pmp, v.last_inventory_date,
               ic.person1_name, ic.count1, ic.person2_name, ic.count2, ic.is_selected
        FROM variants v
        JOIN products p ON v.product_reference = p.reference
        LEFT JOIN inventory_counts ic ON v.id = ic.variant_id
        WHERE 1=1
    """
    params = []
    if variant_ids and len(variant_ids) > 0:
        placeholders = ",".join(["?"] * len(variant_ids))
        query += f" AND v.id IN ({placeholders})"
        params.extend(variant_ids)
    else:
        query += " AND (ic.is_selected = 1)"

    query += " ORDER BY v.location ASC, v.product_reference ASC, v.color ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    if not rows and not variant_ids:
        cursor.execute("""
            SELECT v.id as variant_id, v.product_reference, p.designation, p.category, p.gamme, p.unit,
                   p.image_url, v.color, v.ral_code, v.location, v.real_quantity, v.pmp, v.last_inventory_date,
                   ic.person1_name, ic.count1, ic.person2_name, ic.count2, ic.is_selected
            FROM variants v
            JOIN products p ON v.product_reference = p.reference
            LEFT JOIN inventory_counts ic ON v.id = ic.variant_id
            ORDER BY v.location ASC, v.product_reference ASC, v.color ASC
        """)
        rows = cursor.fetchall()

    conn.close()

    p1_name = person1 or "Opérateur 1"
    p2_name = person2 or "Opérateur 2"
    total_articles = len(rows)

    # Paramètres de pagination A4 Paysage (10 articles par feuille)
    ITEMS_PER_PAGE = 10
    pages_per_copy = max(1, (total_articles + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    total_pages = pages_per_copy * 2

    # URL pour l'export PDF natif des 2 exemplaires
    query_vids = ",".join(str(r["variant_id"]) for r in rows) if rows else ""
    pdf_export_url = f"/api/inventory/export-pdf?variant_ids={query_vids}&person1={p1_name}&person2={p2_name}&hide_stock=true"

    # Configuration des deux exemplaires
    copies_def = [
        {
            "id": "copy-p1",
            "copy_num": 1,
            "badge_title": "EXEMPLAIRE 1 • PREMIER COMPTAGE",
            "operator_label": f"Opérateur 1 : {p1_name}",
            "operator_name": p1_name,
            "field_count": "count1",
            "theme_color": "#4f46e5",
            "theme_bg": "#eef2ff",
            "border_class": "border-p1",
            "box_border": "2px solid #4f46e5"
        },
        {
            "id": "copy-p2",
            "copy_num": 2,
            "badge_title": "EXEMPLAIRE 2 • DEUXIÈME COMPTAGE (CONTRÔLE CROISÉ)",
            "operator_label": f"Opérateur 2 : {p2_name}",
            "operator_name": p2_name,
            "field_count": "count2",
            "theme_color": "#059669",
            "theme_bg": "#ecfdf5",
            "border_class": "border-p2",
            "box_border": "2px solid #059669"
        }
    ]

    pages_html = ""
    for c_info in copies_def:
        for page_idx in range(1, pages_per_copy + 1):
            start_idx = (page_idx - 1) * ITEMS_PER_PAGE
            end_idx = min(start_idx + ITEMS_PER_PAGE, total_articles)
            page_slice = rows[start_idx:end_idx]

            rows_html = ""
            for idx_in_page, r in enumerate(page_slice, start=1):
                global_idx = start_idx + idx_in_page
                loc = r["location"] or "EN_ATTENTE_AFFECTATION"
                saved_count = r[c_info["field_count"]]
                count_val = f"{saved_count:g}" if saved_count is not None else ""
                img_tag = f'<img src="{r["image_url"]}" alt="" style="width: 28px; height: 28px; object-fit: contain; border-radius: 3px; border: 1px solid #cbd5e1; background: #fff;" />' if r["image_url"] else '<span style="font-size: 16px; opacity: 0.5;">📐</span>'

                rows_html += f"""
                <tr class="{'bg-slate-50' if global_idx % 2 == 0 else 'bg-white'}">
                    <td style="text-align: center; font-weight: bold; width: 32px; font-size: 10px;">{global_idx}</td>
                    <td style="text-align: center; width: 40px; padding: 2px;">{img_tag}</td>
                    <td style="font-family: ui-monospace, monospace; font-weight: 800; width: 120px; font-size: 12px; color: #0f172a;">{r['product_reference']}</td>
                    <td>
                        <div style="font-weight: 700; font-size: 11px; color: #1e293b; line-height: 1.2;">{r['designation']}</div>
                        <div style="font-size: 9.5px; color: #64748b;">{r['category']} • {r['gamme']}</div>
                    </td>
                    <td style="width: 140px;">
                        <div style="font-weight: 700; font-size: 11px; color: #334155;">{r['color']}</div>
                        {f'<div style="font-size: 9px; font-family: ui-monospace, monospace; color: #475569;">RAL: {r["ral_code"]}</div>' if r["ral_code"] else ''}
                    </td>
                    <td style="text-align: center; font-weight: 800; font-family: ui-monospace, monospace; width: 105px; background-color: #f8fafc; font-size: 11px; color: #1e293b;">
                        {loc}
                    </td>
                    <td style="text-align: center; width: 60px; font-size: 10.5px; font-weight: 600;">{r['unit']}</td>
                    <!-- Case de comptage manuscrit dédiée à l'opérateur (stock théorique masqué) -->
                    <td style="width: 125px; height: 34px; text-align: center; font-size: 14px; font-weight: 800; font-family: ui-monospace, monospace; background: #fff; border: {c_info['box_border']} !important;">
                        {count_val}
                    </td>
                    <!-- Observations / Notes atelier -->
                    <td style="width: 120px; font-size: 9.5px; color: #64748b; border: 1px dashed #cbd5e1;">
                        &nbsp;
                    </td>
                </tr>
                """

            # Lignes de remplissage quadrillées vierges pour compléter la feuille
            if len(page_slice) < ITEMS_PER_PAGE:
                for blank_idx in range(len(page_slice) + 1, ITEMS_PER_PAGE + 1):
                    blank_row_num = start_idx + blank_idx
                    rows_html += f"""
                    <tr style="height: 34px; background: #fbfcfe;">
                        <td style="text-align: center; font-weight: 700; width: 32px; font-size: 10px; color: #94a3b8;">{blank_row_num}</td>
                        <td style="text-align: center; width: 40px; color: #cbd5e1; font-size: 12px;">▫️</td>
                        <td style="font-family: ui-monospace, monospace; color: #94a3b8; font-size: 11px; border: 1px dashed #cbd5e1;">..................</td>
                        <td style="color: #94a3b8; font-size: 10px; font-style: italic; border: 1px dashed #cbd5e1;">
                            Ligne libre atelier (Réf. ajoutée non répertoriée)
                        </td>
                        <td style="color: #cbd5e1; font-size: 9.5px; border: 1px dashed #cbd5e1;">..................</td>
                        <td style="text-align: center; color: #94a3b8; font-size: 10px; border: 1px dashed #cbd5e1;">Casier Atelier</td>
                        <td style="text-align: center; color: #cbd5e1; font-size: 10px; border: 1px dashed #cbd5e1;">...</td>
                        <td style="width: 125px; height: 34px; background: #fff; border: 1.5px dashed {c_info['theme_color']} !important;">&nbsp;</td>
                        <td style="width: 120px; border: 1px dashed #cbd5e1;">&nbsp;</td>
                    </tr>
                    """

            pages_html += f"""
            <!-- FEUILLE A4 - {c_info['badge_title']} - PAGE {page_idx}/{pages_per_copy} -->
            <div class="a4-sheet copy-sheet {c_info['id']}" data-copy="{c_info['copy_num']}" data-page="{page_idx}">
                
                <!-- En-tête officiel de la feuille -->
                <div class="sheet-header">
                    <div class="brand-block">
                        <div class="copy-badge" style="background: {c_info['theme_bg']}; color: {c_info['theme_color']}; border: 1px solid {c_info['theme_color']};">
                            {c_info['badge_title']}
                        </div>
                        <h1>FICHE DE COMPTAGE D'INVENTAIRE PHYSIQUE</h1>
                        <p>Contrôle Contradictoire à Double Comptage • Traçabilité Magasin & Atelier • <span style="font-weight: 700; color: #b91c1c;">Stock théorique non affiché (Comptage aveugle)</span></p>
                    </div>
                    <div class="meta-grid">
                        <div class="meta-card">
                            <span class="meta-lbl">N° FICHE</span>
                            <strong class="meta-val" style="font-family: ui-monospace, monospace;">{doc_ref}</strong>
                        </div>
                        <div class="meta-card">
                            <span class="meta-lbl">DATE & HEURE</span>
                            <strong class="meta-val">{now_str}</strong>
                        </div>
                        <div class="meta-card" style="border-left: 3px solid {c_info['theme_color']};">
                            <span class="meta-lbl">OPÉRATEUR DÉSIGNÉ</span>
                            <strong class="meta-val" style="color: {c_info['theme_color']};">{c_info['operator_name']}</strong>
                        </div>
                        <div class="meta-card meta-card-page">
                            <span class="meta-lbl">PAGINATION</span>
                            <strong class="meta-val" style="color: #0f172a;">Page {page_idx} / {pages_per_copy}</strong>
                        </div>
                    </div>
                </div>

                <!-- Grille du tableau d'inventaire -->
                <div class="table-container">
                    <table class="inventory-table">
                        <thead>
                            <tr>
                                <th style="width: 32px;">N°</th>
                                <th style="width: 40px;">VISUEL</th>
                                <th style="width: 120px;">RÉF. PROFILÉ</th>
                                <th>DÉSIGNATION & GAMME</th>
                                <th style="width: 140px;">TEINTE / LAQUAGE</th>
                                <th style="width: 105px;">CASIER ATELIER</th>
                                <th style="width: 60px;">UNITÉ</th>
                                <th style="width: 125px; background: {c_info['theme_color']} !important; color: #ffffff !important;">
                                    QUANTITÉ COMPTÉE<br/><span style="font-size: 8.5px; opacity: 0.95;">({c_info['operator_name']})</span>
                                </th>
                                <th style="width: 120px;">OBSERVATIONS / ÉCART</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>

                <!-- Blocs d'émargement et signatures officielles -->
                <div class="signatures-grid-dual">
                    <div class="sig-card" style="border: 1.5px solid {c_info['theme_color']};">
                        <div class="sig-title" style="color: {c_info['theme_color']};">DÉCLARATION OPÉRATEUR : {c_info['operator_name']}</div>
                        <div class="sig-role">Je certifie sur l'honneur avoir procédé au comptage physique exact des références listées ci-dessus.</div>
                        <div class="sig-line">Date & Signature : ..........................................................................................</div>
                    </div>
                    <div class="sig-card sig-card-chief">
                        <div class="sig-title">VISA RESPONSABLE ATELIER / DIRECTION</div>
                        <div class="sig-role">Contrôle de réception de la fiche & Vérification des écarts</div>
                        <div class="sig-line">Émargement & Cachet : ...............................................................................</div>
                    </div>
                </div>

                <!-- Pied de page officiel de la feuille -->
                <div class="sheet-footer">
                    <span>StockMaster Alu & Volets Roulants • Fiche Officielle {c_info['badge_title']} • Ne pas divulguer les quantités</span>
                    <span class="sheet-page-indicator">Fiche {c_info['copy_num']}/2 • Page {page_idx} sur {pages_per_copy} • {total_articles} référence(s)</span>
                </div>

            </div>
            """

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fiches de Comptage d'Inventaire Physique A4 (2 Exemplaires) • StockMaster Alu</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 0;
        }}

        * {{
            box-sizing: border-box;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}

        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #334155;
            color: #0f172a;
            -webkit-font-smoothing: antialiased;
        }}

        /* Barre d'outils supérieure fixe */
        .toolbar-a4 {{
            position: sticky;
            top: 0;
            z-index: 1000;
            background: #0f172a;
            color: #ffffff;
            padding: 10px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            border-bottom: 1px solid #1e293b;
        }}

        .toolbar-title {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .toolbar-title h2 {{
            margin: 0;
            font-size: 15px;
            font-weight: 800;
            letter-spacing: -0.3px;
            color: #f8fafc;
        }}

        .toolbar-badge {{
            background: #1e293b;
            color: #94a3b8;
            font-size: 11px;
            padding: 3px 10px;
            border-radius: 9999px;
            font-weight: 600;
            border: 1px solid #334155;
        }}

        .toolbar-actions {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .btn {{
            cursor: pointer;
            border: none;
            padding: 7px 14px;
            border-radius: 7px;
            font-weight: 700;
            font-size: 12px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
            transition: all 0.15s ease-in-out;
        }}

        .btn-print {{
            background: #4f46e5;
            color: white;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4);
        }}
        .btn-print:hover {{
            background: #4338ca;
            transform: translateY(-1px);
        }}

        .btn-pdf {{
            background: #059669;
            color: white;
            box-shadow: 0 2px 8px rgba(5, 150, 105, 0.4);
        }}
        .btn-pdf:hover {{
            background: #047857;
            transform: translateY(-1px);
        }}

        .btn-filter {{
            background: #1e293b;
            color: #cbd5e1;
            border: 1px solid #475569;
        }}
        .btn-filter.active {{
            background: #3b82f6;
            color: white;
            border-color: #2563eb;
        }}

        .btn-close {{
            background: #334155;
            color: #94a3b8;
        }}
        .btn-close:hover {{
            background: #475569;
            color: white;
        }}

        /* Espace Canvas */
        .document-canvas {{
            padding: 25px 10px 40px 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 25px;
        }}

        /* VRAIE FEUILLE DE PAPIER A4 PAYSAGE (297mm x 210mm) */
        .a4-sheet {{
            background: #ffffff;
            width: 297mm;
            height: 210mm;
            max-height: 210mm;
            box-sizing: border-box;
            padding: 8mm 11mm;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
            border-radius: 2px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            overflow: hidden;
            page-break-after: always;
            break-after: page;
        }}

        /* En-tête */
        .sheet-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 2px solid #0f172a;
            padding-bottom: 6px;
            margin-bottom: 6px;
        }}

        .copy-badge {{
            display: inline-block;
            font-size: 9.5px;
            font-weight: 900;
            letter-spacing: 0.8px;
            padding: 2px 8px;
            border-radius: 4px;
            text-transform: uppercase;
            margin-bottom: 3px;
        }}

        .brand-block h1 {{
            margin: 0;
            font-size: 16px;
            font-weight: 900;
            letter-spacing: -0.4px;
            color: #0f172a;
        }}

        .brand-block p {{
            margin: 2px 0 0 0;
            font-size: 9px;
            color: #64748b;
            font-weight: 500;
        }}

        .meta-grid {{
            display: flex;
            gap: 8px;
        }}

        .meta-card {{
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 4px 9px;
            background: #f8fafc;
            min-width: 105px;
        }}

        .meta-card-page {{
            background: #f1f5f9;
        }}

        .meta-lbl {{
            display: block;
            font-size: 8px;
            font-weight: 800;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .meta-val {{
            font-size: 10.5px;
            font-weight: 800;
            color: #0f172a;
        }}

        /* Tableau */
        .table-container {{
            flex-grow: 1;
            margin-bottom: 6px;
        }}

        .inventory-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .inventory-table th {{
            background: #0f172a;
            color: #ffffff;
            font-size: 9px;
            font-weight: 800;
            text-transform: uppercase;
            padding: 6px 4px;
            letter-spacing: 0.4px;
            border: 1px solid #0f172a;
            text-align: center;
        }}

        .inventory-table td {{
            padding: 3px 5px;
            border: 1px solid #cbd5e1;
            vertical-align: middle;
        }}

        /* Signatures */
        .signatures-grid-dual {{
            display: grid;
            grid-template-columns: 1.4fr 1fr;
            gap: 14px;
            margin-top: 4px;
            padding-top: 6px;
            border-top: 1px solid #e2e8f0;
        }}

        .sig-card {{
            border: 1px dashed #94a3b8;
            border-radius: 6px;
            padding: 6px 12px;
            background: #fafafa;
            height: 60px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}

        .sig-card-chief {{
            background: #f8fafc;
            border-color: #64748b;
        }}

        .sig-title {{
            font-size: 9px;
            font-weight: 800;
            text-transform: uppercase;
        }}

        .sig-role {{
            font-size: 8px;
            color: #64748b;
            margin-top: -3px;
        }}

        .sig-line {{
            font-size: 8.5px;
            color: #94a3b8;
            font-style: italic;
        }}

        /* Pied de page */
        .sheet-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 4px;
            padding-top: 4px;
            font-size: 8.5px;
            color: #94a3b8;
            border-top: 1px solid #f1f5f9;
        }}

        .sheet-page-indicator {{
            font-weight: 700;
            color: #64748b;
        }}

        /* Filtres d'affichage écran */
        body.show-only-p1 .copy-p2 {{
            display: none !important;
        }}
        body.show-only-p2 .copy-p1 {{
            display: none !important;
        }}

        /* IMPRESSION PAPIER / ENREGISTREMENT PDF */
        @media print {{
            body {{
                background: transparent !important;
                margin: 0 !important;
                padding: 0 !important;
            }}
            .toolbar-a4 {{
                display: none !important;
            }}
            .document-canvas {{
                padding: 0 !important;
                gap: 0 !important;
            }}
            .a4-sheet {{
                box-shadow: none !important;
                border-radius: 0 !important;
                margin: 0 !important;
                width: 297mm !important;
                height: 210mm !important;
                max-height: 210mm !important;
                page-break-after: always !important;
                break-after: page !important;
                padding: 8mm 10mm !important;
            }}
            .inventory-table th {{
                background: #0f172a !important;
                color: #ffffff !important;
            }}
        }}
    </style>
</head>
<body>

    <!-- Barre d'outils écran -->
    <div class="toolbar-a4 no-print">
        <div class="toolbar-title">
            <span style="font-size: 18px;">📋</span>
            <div>
                <h2>Fiches de Comptage d'Inventaire A4 (2 Fiches Séparées)</h2>
                <div style="font-size: 10.5px; color: #94a3b8;">
                    1 Fiche pour {p1_name} • 1 Fiche pour {p2_name} • Stock théorique masqué (Comptage aveugle)
                </div>
            </div>
            <span class="toolbar-badge">{doc_ref}</span>
        </div>
        <div class="toolbar-actions">
            <button class="btn btn-print" onclick="window.print()">
                <span>🖨️</span> Imprimer (Ctrl+P)
            </button>
            <a class="btn btn-pdf" href="{pdf_export_url}">
                <span>📥</span> Télécharger PDF (2 Fiches)
            </a>
            <div style="display: flex; gap: 4px; margin-left: 8px;">
                <button class="btn btn-filter active" id="btnFilterAll" onclick="filterView('all')">
                    Les 2 Fiches ({total_pages} p.)
                </button>
                <button class="btn btn-filter" id="btnFilterP1" onclick="filterView('p1')">
                    Fiche {p1_name}
                </button>
                <button class="btn btn-filter" id="btnFilterP2" onclick="filterView('p2')">
                    Fiche {p2_name}
                </button>
            </div>
            <button class="btn btn-close" onclick="window.close()" style="margin-left: 8px;">
                Fermer
            </button>
        </div>
    </div>

    <!-- Espace Canvas Document A4 -->
    <div class="document-canvas">
        {pages_html}
    </div>

    <script>
        function filterView(mode) {{
            document.body.classList.remove('show-only-p1', 'show-only-p2');
            document.getElementById('btnFilterAll').classList.remove('active');
            document.getElementById('btnFilterP1').classList.remove('active');
            document.getElementById('btnFilterP2').classList.remove('active');

            if (mode === 'p1') {{
                document.body.classList.add('show-only-p1');
                document.getElementById('btnFilterP1').classList.add('active');
            }} else if (mode === 'p2') {{
                document.body.classList.add('show-only-p2');
                document.getElementById('btnFilterP2').classList.add('active');
            }} else {{
                document.getElementById('btnFilterAll').classList.add('active');
            }}
        }}

        // Raccourci clavier Ctrl+P pour impression directe
        window.addEventListener('keydown', (e) => {{
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') {{
                e.preventDefault();
                window.print();
            }}
        }});

        // Déclencheur auto-print si ?autoprint=1
        if (new URLSearchParams(window.location.search).get('autoprint') === '1') {{
            window.addEventListener('load', () => {{
                setTimeout(() => window.print(), 350);
            }});
        }}
    </script>
</body>
</html>
    """
    return html_content
