#!/usr/bin/env python3
"""
MIGRATION AUTOMATIQUE SQLITE (stock.db) -> SUPABASE CLOUD (PostgreSQL)
Conçu avec les meilleures pratiques Supabase (sans dépendance externe requise).
Gère la correspondance relationnelle des clés étrangères et des identités.
"""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock.db")
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if (not SUPABASE_URL or not SUPABASE_KEY) and os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "SUPABASE_URL" and not SUPABASE_URL:
                    SUPABASE_URL = v.rstrip("/")
                elif k == "SUPABASE_KEY" and not SUPABASE_KEY:
                    SUPABASE_KEY = v

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def send_to_supabase(table: str, rows: list, return_rep: bool = False) -> list:
    if not rows:
        return []

    endpoint = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation" if return_rep else "resolution=merge-duplicates"
    }

    inserted_records = []
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        data = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status in (200, 201):
                    res_body = resp.read().decode('utf-8', errors='ignore')
                    if return_rep and res_body:
                        try:
                            inserted_records.extend(json.loads(res_body))
                        except Exception:
                            pass
                    log(f"Table '{table}': {len(batch)} lignes migrées ({min(i + batch_size, len(rows))}/{len(rows)}).")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8', errors='ignore')
            log(f"Erreur HTTP sur table '{table}': {e.code} - {err_msg}", "ERROR")
        except Exception as e:
            log(f"Erreur réseau sur table '{table}': {e}", "ERROR")

    return inserted_records

def migrate_all():
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Veuillez définir SUPABASE_URL et SUPABASE_KEY dans .env.", "ERROR")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        log(f"Fichier de base SQLite introuvable: {DB_PATH}", "ERROR")
        sys.exit(1)

    log(f"Connexion SQLite locale : {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    log(f"Démarrage de la migration vers Supabase Cloud ({SUPABASE_URL})...")

    # 1. Catégories, Gammes, Unités, Workshop Cases, Colors (sans forcer l'id)
    lookup_tables = ["categories", "gammes", "units", "workshop_cases", "colors"]
    for tbl in lookup_tables:
        cursor.execute(f"SELECT * FROM {tbl}")
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            r.pop("id", None)
            for k in list(r.keys()):
                if r[k] is None and k in ('description', 'ral_code'):
                    r[k] = ''
        log(f"-> Migration {tbl} ({len(rows)} lignes)...")
        send_to_supabase(tbl, rows)

    # 2. Produits (Clé primaire = reference textuelle)
    cursor.execute("SELECT * FROM products")
    products = [dict(r) for r in cursor.fetchall()]
    for p in products:
        for k in list(p.keys()):
            if p[k] is None:
                p[k] = '' if k in ('image_url', 'supplier', 'location') else 0
    log(f"-> Migration products ({len(products)} lignes)...")
    send_to_supabase("products", products)

    # 3. Variantes (Récupération des nouveaux IDs générés par PostgreSQL)
    cursor.execute("SELECT * FROM variants")
    sqlite_variants = [dict(r) for r in cursor.fetchall()]

    variant_payloads = []
    old_to_payload_idx = {}
    for idx, v in enumerate(sqlite_variants):
        old_id = v.get("id")
        old_to_payload_idx[old_id] = idx
        v_copy = dict(v)
        v_copy.pop("id", None)
        v_copy.pop("last_inventory_date", None)
        for k in list(v_copy.keys()):
            if v_copy[k] is None:
                v_copy[k] = '' if k in ('ral_code', 'barcode', 'supplier', 'location') else 0
        variant_payloads.append(v_copy)

    log(f"-> Migration variants ({len(variant_payloads)} lignes)...")
    inserted_variants = send_to_supabase("variants", variant_payloads, return_rep=True)

    # Construction du dictionnaire de correspondance des IDs de variantes
    variant_id_map = {}
    if inserted_variants:
        for new_v in inserted_variants:
            ref = new_v.get("product_reference")
            col = new_v.get("color")
            # Trouver l'ancien id correspondant
            for old_v in sqlite_variants:
                if old_v.get("product_reference") == ref and old_v.get("color") == col:
                    variant_id_map[old_v.get("id")] = new_v.get("id")
                    break

    log(f"Map de variantes résolue : {len(variant_id_map)} variantes liées.")

    # 4. Historique des prix (mapping variant_id)
    cursor.execute("SELECT * FROM price_history")
    prices = [dict(r) for r in cursor.fetchall()]
    valid_prices = []
    for ph in prices:
        ph.pop("id", None)
        old_vid = ph.get("variant_id")
        if old_vid in variant_id_map:
            ph["variant_id"] = variant_id_map[old_vid]
            valid_prices.append(ph)

    log(f"-> Migration price_history ({len(valid_prices)}/{len(prices)} lignes éligibles)...")
    send_to_supabase("price_history", valid_prices)

    # 5. Mouvements
    cursor.execute("SELECT * FROM movements")
    movements = [dict(r) for r in cursor.fetchall()]
    for m in movements:
        m.pop("id", None)
        for k in list(m.keys()):
            if m[k] is None:
                m[k] = '' if k in ('notes', 'order_number') else 0
    log(f"-> Migration movements ({len(movements)} lignes)...")
    send_to_supabase("movements", movements)

    # 6. Commandes
    cursor.execute("SELECT * FROM orders")
    orders = [dict(r) for r in cursor.fetchall()]
    for o in orders:
        o.pop("id", None)
        for k in list(o.keys()):
            if o[k] is None and k == 'notes':
                o[k] = ''
    log(f"-> Migration orders ({len(orders)} lignes)...")
    send_to_supabase("orders", orders)

    conn.close()
    log("==================================================", "SUCCESS")
    log("Toutes les données de SQLite sont migrées sur Supabase Cloud !", "SUCCESS")
    log("==================================================", "SUCCESS")

if __name__ == "__main__":
    migrate_all()
