import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import sqlite3
from typing import Optional, Dict, Any, List

logger = logging.getLogger("supabase_sync")

def get_supabase_credentials():
    url = os.environ.get("SUPABASE_URL", "").strip().strip('"').strip("'").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")

    if not url or not key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k == "SUPABASE_URL" and not url:
                                url = v.rstrip("/")
                            elif k == "SUPABASE_KEY" and not key:
                                key = v
            except Exception as e:
                logger.error(f"Error reading .env for Supabase: {e}")

    return url, key

def is_supabase_enabled() -> bool:
    url, key = get_supabase_credentials()
    return bool(url and key)

def _supabase_request(endpoint: str, method: str = "GET", data: Any = None, headers_extra: Dict[str, str] = None) -> Any:
    url, key = get_supabase_credentials()
    if not url or not key:
        return None

    full_url = f"{url}/rest/v1/{endpoint}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    if headers_extra:
        headers.update(headers_extra)

    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(full_url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="ignore")
            print(f"[SUPABASE SYNC OK] {method} {endpoint} -> HTTP {status}")
            if body:
                try:
                    return json.loads(body)
                except Exception:
                    return body
            return {"status": status}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"[SUPABASE ERROR] HTTP {e.code} on {method} {endpoint}: {err_msg}")
        logger.error(f"Supabase HTTP {e.code} on {method} {endpoint}: {err_msg}")
        return None
    except Exception as e:
        print(f"[SUPABASE ERROR] on {method} {endpoint}: {e}")
        logger.error(f"Supabase request failed on {method} {endpoint}: {e}")
        return None

# --- SYNC DES RÉFÉRENTIELS ET PARAMÈTRES ---

def sync_category_to_cloud(name: str, description: str = "", delete: bool = False):
    if not is_supabase_enabled():
        return
    if delete:
        encoded_name = urllib.parse.quote(name)
        _supabase_request(f"categories?name=eq.{encoded_name}", method="DELETE")
    else:
        _supabase_request("categories?on_conflict=name", method="POST",
                          data=[{"name": name, "description": description or ""}],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_gamme_to_cloud(name: str, description: str = "", delete: bool = False):
    if not is_supabase_enabled():
        return
    if delete:
        encoded_name = urllib.parse.quote(name)
        _supabase_request(f"gammes?name=eq.{encoded_name}", method="DELETE")
    else:
        _supabase_request("gammes?on_conflict=name", method="POST",
                          data=[{"name": name, "description": description or ""}],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_unit_to_cloud(name: str, symbol: str, delete: bool = False):
    if not is_supabase_enabled():
        return
    if delete:
        encoded_name = urllib.parse.quote(name)
        _supabase_request(f"units?name=eq.{encoded_name}", method="DELETE")
    else:
        _supabase_request("units?on_conflict=name", method="POST",
                          data=[{"name": name, "symbol": symbol}],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_workshop_case_to_cloud(case_type: str, code: str, description: str = "", delete: bool = False):
    if not is_supabase_enabled():
        return
    if delete:
        encoded_code = urllib.parse.quote(code)
        _supabase_request(f"workshop_cases?code=eq.{encoded_code}", method="DELETE")
    else:
        _supabase_request("workshop_cases?on_conflict=code", method="POST",
                          data=[{"type": case_type, "code": code, "description": description or ""}],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_color_to_cloud(name: str, ral_code: str = "", hex_code: str = "#474a51", delete: bool = False):
    if not is_supabase_enabled():
        return
    if delete:
        encoded_name = urllib.parse.quote(name)
        _supabase_request(f"colors?name=eq.{encoded_name}", method="DELETE")
    else:
        _supabase_request("colors?on_conflict=name", method="POST",
                          data=[{"name": name, "ral_code": ral_code or "", "hex_code": hex_code or "#474a51"}],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

# --- SYNC PRODUITS & VARIANTES ---

def sync_product_to_cloud(product: dict, delete: bool = False):
    if not is_supabase_enabled():
        return
    ref = product.get("reference")
    if not ref:
        return
    if delete:
        encoded_ref = urllib.parse.quote(ref)
        _supabase_request(f"products?reference=eq.{encoded_ref}", method="DELETE")
    else:
        p_data = {
            "reference": ref,
            "designation": product.get("designation", ""),
            "category": product.get("category", ""),
            "gamme": product.get("gamme", ""),
            "unit": product.get("unit", "barre"),
            "image_url": product.get("image_url", ""),
            "threshold": float(product.get("threshold") or 10.0),
            "supplier": product.get("supplier", ""),
            "location": product.get("location", "EN_ATTENTE_AFFECTATION")
        }
        _supabase_request("products?on_conflict=reference", method="POST",
                          data=[p_data],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_variant_to_cloud(variant: dict, delete: bool = False):
    if not is_supabase_enabled():
        return
    ref = variant.get("product_reference")
    color = variant.get("color")
    if not ref or not color:
        return
    if delete:
        encoded_ref = urllib.parse.quote(ref)
        encoded_col = urllib.parse.quote(color)
        _supabase_request(f"variants?product_reference=eq.{encoded_ref}&color=eq.{encoded_col}", method="DELETE")
    else:
        v_data = {
            "product_reference": ref,
            "color": color,
            "ral_code": variant.get("ral_code", ""),
            "color_hex": variant.get("color_hex", "#64748b"),
            "barcode": variant.get("barcode", f"BAR-{ref}-{color}"),
            "initial_quantity": float(variant.get("initial_quantity") or 0.0),
            "real_quantity": float(variant.get("real_quantity") or 0.0),
            "reserved_quantity": float(variant.get("reserved_quantity") or 0.0),
            "threshold": float(variant.get("threshold") or 10.0),
            "current_price": float(variant.get("current_price") or 0.0),
            "previous_price": float(variant.get("previous_price") or 0.0),
            "pmp": float(variant.get("pmp") or 0.0),
            "supplier": variant.get("supplier", ""),
            "location": variant.get("location", "EN_ATTENTE_AFFECTATION")
        }
        _supabase_request("variants?on_conflict=product_reference,color", method="POST",
                          data=[v_data],
                          headers_extra={"Prefer": "resolution=merge-duplicates"})

def sync_movement_to_cloud(movement: dict):
    if not is_supabase_enabled():
        return
    m_data = {
        "timestamp": movement.get("timestamp"),
        "action_type": movement.get("action_type"),
        "product_reference": movement.get("product_reference"),
        "product_name": movement.get("product_name"),
        "color": movement.get("color"),
        "quantity": float(movement.get("quantity") or 0.0),
        "unit_price": float(movement.get("unit_price") or 0.0),
        "pmp_at_movement": float(movement.get("pmp_at_movement") or 0.0),
        "total_value": float(movement.get("total_value") or 0.0),
        "order_number": movement.get("order_number"),
        "operator": movement.get("operator", "Atelier"),
        "notes": movement.get("notes", "")
    }
    _supabase_request("movements", method="POST", data=[m_data])

def sync_variant_by_id(variant_id: int):
    if not is_supabase_enabled():
        return
    try:
        from app.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM variants WHERE id = ?", (variant_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            sync_variant_to_cloud(dict(row))
    except Exception as e:
        logger.error(f"Error syncing variant {variant_id}: {e}")

def sync_latest_movement():
    if not is_supabase_enabled():
        return
    try:
        from app.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM movements ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            sync_movement_to_cloud(dict(row))
    except Exception as e:
        logger.error(f"Error syncing latest movement: {e}")

# --- CHARGEMENT AU DÉMARRAGE : SUPABASE -> SQLITE ---

def pull_all_from_supabase_to_sqlite():
    """
    Au démarrage du serveur (notamment sur Render), télécharge l'état complet
    depuis Supabase Cloud pour que la base SQLite soit toujours à jour et persistante.
    """
    if not is_supabase_enabled():
        logger.info("Supabase credentials not configured. Skipping cloud sync.")
        return

    from app.database import get_db
    conn = get_db()
    cursor = conn.cursor()

    try:
        # 1. Catégories
        cloud_cats = _supabase_request("categories?select=name,description")
        if isinstance(cloud_cats, list) and len(cloud_cats) > 0:
            for c in cloud_cats:
                cursor.execute("INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                               (c["name"], c.get("description", "")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_cats)} categories from Supabase.")

        # 2. Gammes
        cloud_gammes = _supabase_request("gammes?select=name,description")
        if isinstance(cloud_gammes, list) and len(cloud_gammes) > 0:
            for g in cloud_gammes:
                cursor.execute("INSERT OR IGNORE INTO gammes (name, description) VALUES (?, ?)",
                               (g["name"], g.get("description", "")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_gammes)} gammes from Supabase.")

        # 3. Cases Atelier
        cloud_cases = _supabase_request("workshop_cases?select=type,code,description")
        if isinstance(cloud_cases, list) and len(cloud_cases) > 0:
            for cs in cloud_cases:
                cursor.execute("INSERT OR IGNORE INTO workshop_cases (type, code, description) VALUES (?, ?, ?)",
                               (cs["type"], cs["code"], cs.get("description", "")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_cases)} workshop cases from Supabase.")

        # 4. Couleurs
        cloud_colors = _supabase_request("colors?select=name,ral_code,hex_code")
        if isinstance(cloud_colors, list) and len(cloud_colors) > 0:
            for cl in cloud_colors:
                cursor.execute("INSERT OR IGNORE INTO colors (name, ral_code, hex_code) VALUES (?, ?, ?)",
                               (cl["name"], cl.get("ral_code", ""), cl.get("hex_code", "#474a51")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_colors)} colors from Supabase.")

        # 5. Produits
        cloud_prods = _supabase_request("products?select=*")
        if isinstance(cloud_prods, list) and len(cloud_prods) > 0:
            for p in cloud_prods:
                cursor.execute("""
                    INSERT INTO products (reference, designation, category, gamme, unit, image_url, threshold, supplier, location, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(reference) DO UPDATE SET
                        designation = excluded.designation,
                        category = excluded.category,
                        gamme = excluded.gamme,
                        unit = excluded.unit,
                        image_url = excluded.image_url,
                        threshold = excluded.threshold,
                        supplier = excluded.supplier,
                        location = excluded.location
                """, (p["reference"], p["designation"], p.get("category", ""), p.get("gamme", ""),
                      p.get("unit", "barre"), p.get("image_url", ""), float(p.get("threshold") or 10.0),
                      p.get("supplier", ""), p.get("location", "EN_ATTENTE_AFFECTATION"),
                      p.get("created_at", "")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_prods)} products from Supabase.")

        # 6. Variantes
        cloud_vars = _supabase_request("variants?select=*")
        if isinstance(cloud_vars, list) and len(cloud_vars) > 0:
            for v in cloud_vars:
                cursor.execute("""
                    INSERT INTO variants (product_reference, color, ral_code, color_hex, barcode,
                                          initial_quantity, real_quantity, reserved_quantity,
                                          threshold, current_price, previous_price, pmp, supplier, location, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_reference, color) DO UPDATE SET
                        ral_code = excluded.ral_code,
                        color_hex = excluded.color_hex,
                        barcode = excluded.barcode,
                        real_quantity = excluded.real_quantity,
                        reserved_quantity = excluded.reserved_quantity,
                        threshold = excluded.threshold,
                        current_price = excluded.current_price,
                        previous_price = excluded.previous_price,
                        pmp = excluded.pmp,
                        supplier = excluded.supplier,
                        location = excluded.location
                """, (v["product_reference"], v["color"], v.get("ral_code", ""), v.get("color_hex", "#64748b"),
                      v.get("barcode", ""), float(v.get("initial_quantity") or 0.0),
                      float(v.get("real_quantity") or 0.0), float(v.get("reserved_quantity") or 0.0),
                      float(v.get("threshold") or 10.0), float(v.get("current_price") or 0.0),
                      float(v.get("previous_price") or 0.0), float(v.get("pmp") or 0.0),
                      v.get("supplier", ""), v.get("location", "EN_ATTENTE_AFFECTATION"),
                      v.get("updated_at", "")))
            conn.commit()
            logger.info(f"Pulled {len(cloud_vars)} variants from Supabase.")

    except Exception as e:
        logger.error(f"Error during Supabase startup pull: {e}")
    finally:
        conn.close()
