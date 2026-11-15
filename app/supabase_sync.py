import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import sqlite3
import threading
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

def _movement_payload(movement: dict) -> dict:
    return {
        "timestamp": movement.get("timestamp"),
        "action_type": movement.get("action_type"),
        "product_reference": movement.get("product_reference"),
        "product_name": movement.get("product_name") or movement.get("product_reference") or "",
        "color": movement.get("color") or "",
        "quantity": float(movement.get("quantity") or 0.0),
        "unit_price": float(movement.get("unit_price") or 0.0),
        "pmp_at_movement": float(movement.get("pmp_at_movement") or 0.0),
        "total_value": float(movement.get("total_value") or 0.0),
        "order_number": movement.get("order_number"),
        "operator": movement.get("operator") or "Atelier",
        "is_anonyme": int(movement.get("is_anonyme") or 0),
        "notes": movement.get("notes") or ""
    }

def sync_movement_to_cloud(movement: dict):
    """Envoie un mouvement. Renvoie l'id Supabase en cas de succès, sinon None."""
    if not is_supabase_enabled():
        return None
    res = _supabase_request("movements", method="POST", data=[_movement_payload(movement)],
                            headers_extra={"Prefer": "return=representation"})
    if isinstance(res, list) and res:
        return res[0].get("id")
    return None

# Verrou : évite que deux requêtes simultanées envoient deux fois le même mouvement
_push_lock = threading.Lock()

def push_pending_to_cloud() -> Dict[str, int]:
    """
    Envoie vers Supabase tout ce qui n'y est pas encore :
    - les mouvements marqués cloud_synced = 0
    - les variantes marquées cloud_dirty = 1 (quantités, prix, emplacements modifiés)
    Un envoi raté reste en file d'attente et sera retenté à la prochaine action
    ou au prochain démarrage du serveur : plus aucune saisie n'est perdue en silence.
    """
    result = {"movements_sent": 0, "variants_sent": 0, "movements_pending": 0, "variants_pending": 0,
              "queue_sent": 0, "queue_pending": 0}
    if not is_supabase_enabled():
        return result

    from app.database import get_db
    with _push_lock:
        conn = get_db()
        cursor = conn.cursor()
        try:
            # 0. Articles, réglages, commandes, inventaire, historique des prix
            result["queue_sent"], result["queue_pending"] = _process_sync_queue(conn)

            # 1. Variantes (le stock à jour est le plus important)
            cursor.execute("SELECT * FROM variants WHERE cloud_dirty = 1")
            for row in cursor.fetchall():
                v = dict(row)
                ok = _upsert_variant(v)
                if ok:
                    # Ne remet à 0 que si la variante n'a pas bougé entre-temps
                    cursor.execute("UPDATE variants SET cloud_dirty = 0 WHERE id = ? AND updated_at IS ? AND real_quantity IS ? AND reserved_quantity IS ?",
                                   (v["id"], v["updated_at"], v["real_quantity"], v["reserved_quantity"]))
                    conn.commit()
                    result["variants_sent"] += 1

            # 2. Mouvements dans l'ordre chronologique
            cursor.execute("SELECT * FROM movements WHERE cloud_synced = 0 ORDER BY id ASC")
            for row in cursor.fetchall():
                m = dict(row)
                cloud_id = sync_movement_to_cloud(m)
                if cloud_id is None:
                    # Supabase injoignable ou refus : on arrête et on retentera plus tard
                    break
                cursor.execute("UPDATE movements SET cloud_synced = 1, cloud_id = ? WHERE id = ?", (cloud_id, m["id"]))
                conn.commit()
                result["movements_sent"] += 1

            cursor.execute("SELECT COUNT(*) FROM movements WHERE cloud_synced = 0")
            result["movements_pending"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM variants WHERE cloud_dirty = 1")
            result["variants_pending"] = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error pushing pending data to Supabase: {e}")
            print(f"[SUPABASE ERROR] push_pending_to_cloud: {e}")
        finally:
            conn.close()

    if result["movements_sent"] or result["variants_sent"]:
        print(f"[SUPABASE SYNC] {result['movements_sent']} mouvement(s), {result['variants_sent']} variante(s) envoyés")
    if result["queue_sent"]:
        print(f"[SUPABASE SYNC] {result['queue_sent']} élément(s) (articles/réglages/commandes/inventaire/prix) envoyés")
    if result["movements_pending"] or result["variants_pending"] or result["queue_pending"]:
        print(f"[SUPABASE SYNC] EN ATTENTE : {result['movements_pending']} mouvement(s), {result['variants_pending']} variante(s), {result['queue_pending']} autre(s)")
    return result

def _upsert_variant(variant: dict) -> bool:
    ref = variant.get("product_reference")
    color = variant.get("color")
    if not ref or not color:
        return True  # rien d'envoyable, on ne bloque pas la file
    v_data = {
        "product_reference": ref,
        "color": color,
        "ral_code": variant.get("ral_code") or "",
        "color_hex": variant.get("color_hex") or "#64748b",
        "barcode": variant.get("barcode") or f"BAR-{ref}-{color}",
        "initial_quantity": float(variant.get("initial_quantity") or 0.0),
        "real_quantity": float(variant.get("real_quantity") or 0.0),
        "reserved_quantity": float(variant.get("reserved_quantity") or 0.0),
        "threshold": float(variant.get("threshold") or 10.0),
        "current_price": float(variant.get("current_price") or 0.0),
        "previous_price": float(variant.get("previous_price") or 0.0),
        "pmp": float(variant.get("pmp") or 0.0),
        "supplier": variant.get("supplier") or "",
        "location": variant.get("location") or "EN_ATTENTE_AFFECTATION"
    }
    res = _supabase_request("variants?on_conflict=product_reference,color", method="POST",
                            data=[v_data],
                            headers_extra={"Prefer": "resolution=merge-duplicates"})
    return res is not None

def sync_variant_by_id(variant_id: int):
    # Conservé pour compatibilité : la variante est déjà marquée "à envoyer" par la base
    push_pending_to_cloud()

def sync_latest_movement():
    # Conservé pour compatibilité : envoie TOUS les mouvements en attente (pas seulement le dernier)
    push_pending_to_cloud()

def _normalize_ts(ts: Optional[str]) -> str:
    if not ts:
        return ""
    return str(ts).replace("T", " ")[:19]

def pull_movements_from_supabase(cursor) -> int:
    """Recharge l'historique complet des mouvements depuis Supabase (par pages de 1000)."""
    total = 0
    offset = 0
    page = 1000
    while True:
        rows = _supabase_request(f"movements?select=*&order=id.asc&limit={page}&offset={offset}")
        if not isinstance(rows, list) or not rows:
            break
        for m in rows:
            cursor.execute("""
                INSERT OR IGNORE INTO movements (timestamp, action_type, product_reference, product_name, color,
                    quantity, unit_price, pmp_at_movement, total_value, order_number, operator, is_anonyme, notes,
                    cloud_synced, cloud_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (_normalize_ts(m.get("timestamp")), m.get("action_type"), m.get("product_reference"),
                  m.get("product_name") or "", m.get("color") or "",
                  float(m.get("quantity") or 0), float(m.get("unit_price") or 0),
                  float(m.get("pmp_at_movement") or 0), float(m.get("total_value") or 0),
                  m.get("order_number"), m.get("operator") or "Atelier", int(m.get("is_anonyme") or 0),
                  m.get("notes") or "", m.get("id")))
            total += cursor.rowcount if cursor.rowcount > 0 else 0
        if len(rows) < page:
            break
        offset += page
    return total

# --- CHARGEMENT AU DÉMARRAGE : SUPABASE -> SQLITE ---

def pull_all_from_supabase_to_sqlite():
    """
    Au démarrage du serveur (notamment sur Render), télécharge l'état complet
    depuis Supabase Cloud pour que la base SQLite soit toujours à jour et persistante.
    """
    if not is_supabase_enabled():
        logger.info("Supabase credentials not configured. Skipping cloud sync.")
        return

    # D'abord envoyer ce qui serait resté en attente localement (ne rien écraser)
    push_pending_to_cloud()

    from app.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    # Ce qui est rechargé depuis le Cloud ne doit pas être renvoyé vers le Cloud
    try:
        queue_start = cursor.execute("SELECT COALESCE(MAX(id), 0) FROM sync_queue").fetchone()[0]
    except sqlite3.OperationalError:
        queue_start = None

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

        # Les variantes qui viennent d'être rechargées depuis le Cloud sont à jour
        if isinstance(cloud_vars, list):
            for v in cloud_vars:
                cursor.execute("UPDATE variants SET cloud_dirty = 0 WHERE product_reference = ? AND color = ?",
                               (v["product_reference"], v["color"]))
            conn.commit()

        # 7. Historique des mouvements (avant : jamais rechargé -> perdu à chaque redémarrage)
        n_mvts = pull_movements_from_supabase(cursor)
        conn.commit()
        print(f"[SUPABASE SYNC] {n_mvts} mouvement(s) rechargé(s) depuis Supabase au démarrage")

        # 8. Unités, commandes, inventaire, historique des prix
        extra = pull_extra_from_supabase(cursor)
        conn.commit()
        print(f"[SUPABASE SYNC] Rechargé depuis Supabase : {extra}")

    except Exception as e:
        logger.error(f"Error during Supabase startup pull: {e}")
        print(f"[SUPABASE ERROR] startup pull: {e}")
    finally:
        try:
            if queue_start is not None:
                cursor.execute("DELETE FROM sync_queue WHERE id > ?", (queue_start,))
                conn.commit()
        except Exception:
            pass
        conn.close()


# =============================================================================
# FILE D'ATTENTE GÉNÉRIQUE (articles, réglages, commandes, inventaire, prix)
# =============================================================================

# Ordre d'envoi : un article doit exister dans le Cloud avant ses lignes dépendantes
_QUEUE_PRIORITY = ["categories", "gammes", "units", "colors", "workshop_cases", "products",
                   "orders", "order_items", "inventory_counts", "price_history", "inventory_anomalies"]

def _q(v: str) -> str:
    return urllib.parse.quote(str(v), safe="")

def _ok(res) -> bool:
    return res is not None

def _row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None

def _upsert(table: str, conflict: str, data: dict) -> bool:
    return _ok(_supabase_request(f"{table}?on_conflict={conflict}", method="POST", data=[data],
                                 headers_extra={"Prefer": "resolution=merge-duplicates"}))

def _delete(path: str) -> bool:
    return _ok(_supabase_request(path, method="DELETE"))

def _send_queue_item(conn, tbl: str, key: str, op: str) -> bool:
    """Envoie un élément de la file. Renvoie True si c'est fait (ou s'il n'y a plus rien à envoyer)."""
    if tbl == "products":
        if op == "delete":
            return _delete(f"products?reference=eq.{_q(key)}")
        p = _row(conn, "SELECT * FROM products WHERE reference = ?", (key,))
        if not p:
            return True
        return _upsert("products", "reference", {
            "reference": p["reference"], "designation": p.get("designation") or p["reference"],
            "category": p.get("category") or "", "gamme": p.get("gamme") or "",
            "unit": p.get("unit") or "barre", "image_url": p.get("image_url") or "",
            "threshold": float(p.get("threshold") or 10.0), "supplier": p.get("supplier") or "",
            "location": p.get("location") or "EN_ATTENTE_AFFECTATION"})

    if tbl in ("categories", "gammes", "units", "colors"):
        if op == "delete":
            return _delete(f"{tbl}?name=eq.{_q(key)}")
        r = _row(conn, f"SELECT * FROM {tbl} WHERE name = ?", (key,))
        if not r:
            return True
        if tbl == "units":
            data = {"name": r["name"], "symbol": r.get("symbol") or r["name"]}
        elif tbl == "colors":
            data = {"name": r["name"], "ral_code": r.get("ral_code") or "", "hex_code": r.get("hex_code") or "#474a51"}
        else:
            data = {"name": r["name"], "description": r.get("description") or ""}
        return _upsert(tbl, "name", data)

    if tbl == "workshop_cases":
        if op == "delete":
            return _delete(f"workshop_cases?code=eq.{_q(key)}")
        r = _row(conn, "SELECT * FROM workshop_cases WHERE code = ?", (key,))
        if not r:
            return True
        return _upsert("workshop_cases", "code", {"type": r["type"], "code": r["code"], "description": r.get("description") or ""})

    if tbl == "orders":
        if op == "delete":
            return _delete(f"order_items?order_number=eq.{_q(key)}") and _delete(f"orders?order_number=eq.{_q(key)}")
        o = _row(conn, "SELECT * FROM orders WHERE order_number = ?", (key,))
        if not o:
            return True
        return _upsert("orders", "order_number", {
            "order_number": o["order_number"], "client_name": o.get("client_name") or "",
            "status": o.get("status") or "EN_ATTENTE", "notes": o.get("notes") or ""})

    if tbl == "order_items":
        # On remplace toutes les lignes de cette commande dans le Cloud par les lignes locales
        o = _row(conn, "SELECT * FROM orders WHERE order_number = ?", (key,))
        if o and not _send_queue_item(conn, "orders", key, "upsert"):
            return False
        if not _delete(f"order_items?order_number=eq.{_q(key)}"):
            return False
        items = [dict(r) for r in conn.execute("SELECT * FROM order_items WHERE order_number = ? ORDER BY id", (key,)).fetchall()]
        if not items:
            return True
        payload = [{
            "order_id": it["order_id"], "order_number": it["order_number"], "variant_id": it["variant_id"],
            "product_reference": it["product_reference"], "product_name": it.get("product_name") or "",
            "color": it.get("color") or "", "quantity_reserved": float(it.get("quantity_reserved") or 0),
            "quantity_destocked": float(it.get("quantity_destocked") or 0),
            "unit_price": float(it.get("unit_price") or 0), "status": it.get("status") or "RESERVED"} for it in items]
        return _ok(_supabase_request("order_items", method="POST", data=payload))

    if tbl == "inventory_counts":
        ref, _, color = key.partition("|")
        if op == "delete":
            return _delete(f"inventory_counts?product_reference=eq.{_q(ref)}&color=eq.{_q(color)}")
        r = _row(conn, "SELECT * FROM inventory_counts WHERE product_reference = ? AND color = ?", (ref, color))
        if not r:
            return True
        return _upsert("inventory_counts", "product_reference,color", {
            "product_reference": ref, "color": color,
            "person1_name": r.get("person1_name"), "count1": r.get("count1"),
            "person2_name": r.get("person2_name"), "count2": r.get("count2"),
            "expected_quantity": float(r.get("expected_quantity") or 0), "status": r.get("status") or "PENDING",
            "is_selected": int(r.get("is_selected") or 0), "inventory_date": r.get("inventory_date"),
            "notes": r.get("notes"), "created_at": r.get("created_at"), "updated_at": r.get("updated_at")})

    if tbl == "price_history":
        r = _row(conn, """SELECT ph.*, v.color AS v_color FROM price_history ph
                          LEFT JOIN variants v ON v.id = ph.variant_id WHERE ph.id = ?""", (int(key),))
        if not r:
            return True
        return _ok(_supabase_request("price_history", method="POST", data=[{
            "variant_id": r["variant_id"], "product_reference": r["product_reference"], "color": r.get("v_color") or "",
            "price": float(r.get("price") or 0), "pmp_after": float(r.get("pmp_after") or 0),
            "quantity": float(r.get("quantity") or 0), "recorded_at": r.get("recorded_at")}]))

    if tbl == "inventory_anomalies":
        r = _row(conn, "SELECT * FROM inventory_anomalies WHERE id = ?", (int(key),))
        if not r:
            return True
        data = {k: r.get(k) for k in ("product_reference", "designation", "color", "real_quantity_before",
                                      "counted_quantity", "discrepancy_quantity", "pmp_at_adjustment",
                                      "financial_impact", "person1_name", "count1", "person2_name", "count2",
                                      "reason", "notes", "adjusted_by", "created_at")}
        return _ok(_supabase_request("inventory_anomalies", method="POST", data=[data]))

    return True  # table inconnue : on ne bloque pas la file

def _process_sync_queue(conn):
    """Traite la file d'attente. Un échec laisse l'élément (et ceux de la même table) pour plus tard."""
    sent = 0
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM sync_queue ORDER BY id").fetchall()]
    except sqlite3.OperationalError:
        return 0, 0  # table pas encore créée
    # Dernière opération par élément (les doublons sont regroupés), sauf les ajouts de journaux
    latest = {}
    for r in rows:
        k = (r["tbl"], r["row_key"]) if r["op"] != "insert" else (r["tbl"], r["row_key"], r["id"])
        latest[k] = r
    ordered = sorted(latest.values(), key=lambda r: (_QUEUE_PRIORITY.index(r["tbl"]) if r["tbl"] in _QUEUE_PRIORITY else 99, r["id"]))
    failed_tables = set()
    for r in ordered:
        if r["tbl"] in failed_tables:
            continue
        ok = False
        try:
            ok = _send_queue_item(conn, r["tbl"], r["row_key"], r["op"])
        except Exception as e:
            print(f"[SUPABASE ERROR] file d'attente {r['tbl']} {r['row_key']}: {e}")
        if ok:
            if r["op"] == "insert":
                conn.execute("DELETE FROM sync_queue WHERE id = ?", (r["id"],))
            else:
                conn.execute("DELETE FROM sync_queue WHERE tbl = ? AND row_key = ? AND id <= ? AND op != 'insert'",
                             (r["tbl"], r["row_key"], r["id"]))
            conn.commit()
            sent += 1
        else:
            failed_tables.add(r["tbl"])
    pending = conn.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0]
    return sent, pending

# =============================================================================
# RECHARGEMENT AU DÉMARRAGE DES DONNÉES SUPPLÉMENTAIRES
# =============================================================================

def _ts(v) -> str:
    return _normalize_ts(v) if v else ""

def _variant_id(cursor, ref, color):
    r = cursor.execute("SELECT id FROM variants WHERE product_reference = ? AND color = ?", (ref, color)).fetchone()
    return r[0] if r else None

def _local_count(cursor, table) -> int:
    return cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def _get_all(table: str) -> list:
    out, offset = [], 0
    while True:
        rows = _supabase_request(f"{table}?select=*&order=id.asc&limit=1000&offset={offset}")
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return out

def pull_extra_from_supabase(cursor) -> dict:
    """Recharge unités, commandes, lignes de commande, inventaire et historique des prix."""
    stats = {}
    # Unités
    units = _supabase_request("units?select=name,symbol")
    if isinstance(units, list):
        for u in units:
            cursor.execute("INSERT OR IGNORE INTO units (name, symbol) VALUES (?, ?)", (u["name"], u.get("symbol") or u["name"]))
        stats["unités"] = len(units)

    # Commandes
    orders = _get_all("orders")
    for o in orders:
        cursor.execute("""INSERT OR IGNORE INTO orders (order_number, client_name, status, notes, created_at, updated_at)
                          VALUES (?, ?, ?, ?, ?, ?)""",
                       (o["order_number"], o.get("client_name") or "", o.get("status") or "EN_ATTENTE",
                        o.get("notes") or "", _ts(o.get("created_at")), _ts(o.get("updated_at"))))
    stats["commandes"] = len(orders)

    # Lignes de commande (uniquement si la base locale n'en a pas, pour éviter les doublons)
    if _local_count(cursor, "order_items") == 0:
        n = 0
        for it in _get_all("order_items"):
            o = cursor.execute("SELECT id FROM orders WHERE order_number = ?", (it["order_number"],)).fetchone()
            vid = _variant_id(cursor, it["product_reference"], it["color"])
            if not o or not vid:
                continue
            cursor.execute("""INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color,
                              quantity_reserved, quantity_destocked, unit_price, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (o[0], it["order_number"], vid, it["product_reference"], it.get("product_name") or "", it["color"],
                            float(it.get("quantity_reserved") or 0), float(it.get("quantity_destocked") or 0),
                            float(it.get("unit_price") or 0), it.get("status") or "RESERVED"))
            n += 1
        stats["lignes de commande"] = n

    # Historique des prix
    if _local_count(cursor, "price_history") == 0:
        n = 0
        for ph in _get_all("price_history"):
            vid = _variant_id(cursor, ph["product_reference"], ph.get("color") or "")
            if not vid:
                r = cursor.execute("SELECT id FROM variants WHERE product_reference = ? ORDER BY id LIMIT 1", (ph["product_reference"],)).fetchone()
                vid = r[0] if r else None
            if not vid:
                continue
            cursor.execute("""INSERT INTO price_history (variant_id, product_reference, price, pmp_after, quantity, recorded_at)
                              VALUES (?, ?, ?, ?, ?, ?)""",
                           (vid, ph["product_reference"], float(ph.get("price") or 0), float(ph.get("pmp_after") or 0),
                            float(ph.get("quantity") or 0), _ts(ph.get("recorded_at"))))
            n += 1
        stats["historique des prix"] = n

    # Comptages d'inventaire
    counts = _get_all("inventory_counts")
    n = 0
    for c in counts:
        vid = _variant_id(cursor, c["product_reference"], c["color"])
        if not vid:
            continue
        cursor.execute("""INSERT OR IGNORE INTO inventory_counts (variant_id, product_reference, color, person1_name, count1,
                          person2_name, count2, expected_quantity, status, is_selected, inventory_date, notes, created_at, updated_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (vid, c["product_reference"], c["color"], c.get("person1_name") or "Personne 1", c.get("count1"),
                        c.get("person2_name") or "Personne 2", c.get("count2"), float(c.get("expected_quantity") or 0),
                        c.get("status") or "PENDING", int(c.get("is_selected") or 0), c.get("inventory_date"),
                        c.get("notes"), c.get("created_at") or "", c.get("updated_at") or ""))
        n += 1
    stats["comptages d'inventaire"] = n

    # Anomalies d'inventaire
    if _local_count(cursor, "inventory_anomalies") == 0:
        n = 0
        for a in _get_all("inventory_anomalies"):
            vid = _variant_id(cursor, a["product_reference"], a["color"])
            if not vid:
                continue
            cursor.execute("""INSERT INTO inventory_anomalies (variant_id, product_reference, designation, color, real_quantity_before,
                              counted_quantity, discrepancy_quantity, pmp_at_adjustment, financial_impact, person1_name, count1,
                              person2_name, count2, reason, notes, adjusted_by, created_at)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           (vid, a["product_reference"], a["designation"], a["color"], float(a["real_quantity_before"] or 0),
                            float(a["counted_quantity"] or 0), float(a["discrepancy_quantity"] or 0),
                            float(a.get("pmp_at_adjustment") or 0), float(a.get("financial_impact") or 0),
                            a.get("person1_name"), a.get("count1"), a.get("person2_name"), a.get("count2"),
                            a["reason"], a.get("notes"), a.get("adjusted_by") or "Admin", a["created_at"]))
            n += 1
        stats["anomalies d'inventaire"] = n
    return stats

# =============================================================================
# PHOTOS DES ARTICLES : Supabase Storage
# =============================================================================

PHOTO_BUCKET = "product-images"

def upload_image_to_cloud(filename: str, content: bytes, content_type: str) -> Optional[str]:
    """Envoie une photo dans Supabase Storage. Renvoie son URL publique, ou None en cas d'échec."""
    url, key = get_supabase_credentials()
    if not url or not key:
        return None
    req = urllib.request.Request(
        f"{url}/storage/v1/object/{PHOTO_BUCKET}/{_q(filename)}", data=content, method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": content_type or "application/octet-stream", "x-upsert": "true"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[SUPABASE SYNC OK] photo {filename} -> HTTP {resp.status}")
        return f"{url}/storage/v1/object/public/{PHOTO_BUCKET}/{_q(filename)}"
    except urllib.error.HTTPError as e:
        print(f"[SUPABASE ERROR] upload photo HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"[SUPABASE ERROR] upload photo: {e}")
    return None
