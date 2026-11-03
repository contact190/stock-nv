import csv
import re
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock.db")

def clean_num(val):
    if not val or not val.strip():
        return 0.0
    v = re.sub(r'[\s\u202f\xa0]', '', val).replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None

def run_import():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("1. Purging test data...")
    cursor.execute("DELETE FROM order_items")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM movements")
    cursor.execute("DELETE FROM price_history")
    cursor.execute("DELETE FROM variants")
    cursor.execute("DELETE FROM products")
    conn.commit()

    # 2. Workshop Cases
    print("2. Populating workshop cases...")
    cursor.execute("DELETE FROM workshop_cases")
    cases_set = set()
    if os.path.exists("cases.csv"):
        with open("cases.csv", mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    c = row[0].strip()
                    c_type = "PROFILE" if c.lower().startswith("p") and len(c) > 1 and c[1].isalpha() else "ACCESSOIRE"
                    cases_set.add((c_type, c))

    # Also extract any cases present in base_articles.csv
    if os.path.exists("base_articles.csv"):
        with open("base_articles.csv", mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)
            for r in reader:
                if len(r) > 16 and r[16].strip():
                    raw_cases = [x.strip() for x in r[16].split(",") if x.strip()]
                    for rc in raw_cases:
                        c_type = "PROFILE" if rc.lower().startswith("p") and len(rc) > 1 and rc[1].isalpha() else "ACCESSOIRE"
                        cases_set.add((c_type, rc))

    for c_type, code in sorted(list(cases_set)):
        cursor.execute("INSERT OR IGNORE INTO workshop_cases (type, code, description) VALUES (?, ?, ?)",
                       (c_type, code, f"Casier Atelier {code}"))
    conn.commit()
    print(f"   -> Inserted {len(cases_set)} workshop cases.")

    # 3. Categories & Gammes
    print("3. Populating categories and gammes...")
    categories_set = set()
    gammes_set = set()

    if os.path.exists("categories.csv"):
        with open("categories.csv", mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    categories_set.add(row[0].strip())
                for cell in row[1:]:
                    if cell.strip():
                        gammes_set.add(cell.strip())

    if os.path.exists("base_articles.csv"):
        with open("base_articles.csv", mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)
            for r in reader:
                if len(r) > 3 and r[3].strip():
                    categories_set.add(r[3].strip())
                if len(r) > 4 and r[4].strip():
                    gammes_set.add(r[4].strip())

    for cat in sorted(list(categories_set)):
        cursor.execute("INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)", (cat, f"Catégorie {cat}"))
    for g in sorted(list(gammes_set)):
        cursor.execute("INSERT OR IGNORE INTO gammes (name, description) VALUES (?, ?)", (g, f"Gamme {g}"))
    conn.commit()
    print(f"   -> Inserted {len(categories_set)} categories and {len(gammes_set)} gammes.")

    # 4. Units & Couleurs
    print("4. Populating units and colors...")
    units_data = [
        ("Barre", "Barre"),
        ("Pièce", "Piece"),
        ("Mètre Linéaire", "ML"),
        ("Carton", "ctn")
    ]
    for u_name, u_sym in units_data:
        cursor.execute("INSERT OR IGNORE INTO units (name, symbol) VALUES (?, ?)", (u_name, u_sym))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            ral_code TEXT,
            hex_code TEXT DEFAULT '#474a51'
        )
    """)
    default_colors = [
        ("RAL 7024", "RAL 7024", "#474a51"),
        ("Blanc Pur RAL 9010", "RAL 9010", "#f8fafc"),
        ("Blanc Trafic RAL 9016", "RAL 9016", "#f1f5f9"),
        ("Gris Anthracite RAL 7016", "RAL 7016", "#334155"),
        ("Noir Sablé RAL 2100", "RAL 2100", "#020617"),
        ("Noir Foncé RAL 9005", "RAL 9005", "#0f172a"),
        ("Alu Gris Métal RAL 9006", "RAL 9006", "#94a3b8"),
        ("Ivoire Clair RAL 1013", "RAL 1013", "#fef3c7"),
        ("Brun Sépia RAL 8014", "RAL 8014", "#78350f")
    ]
    for c_name, c_ral, c_hex in default_colors:
        cursor.execute("INSERT OR IGNORE INTO colors (name, ral_code, hex_code) VALUES (?, ?, ?)", (c_name, c_ral, c_hex))
    conn.commit()

    # 5. Parse base_articles.csv
    print("5. Parsing base_articles.csv and validating rules...")
    valid_articles = []
    skipped_articles = []
    seen_refs = set()

    with open("base_articles.csv", mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        rows = list(reader)

    for i, r in enumerate(rows):
        line_num = i + 2
        ref = r[0].strip() if len(r) > 0 else ""
        desig = r[2].strip() if len(r) > 2 else ""
        cat = r[3].strip() if len(r) > 3 else ""
        gamme = r[4].strip() if len(r) > 4 else ""
        unit = r[5].strip() if len(r) > 5 else ""
        q_reel_str = r[7].strip() if len(r) > 7 else ""
        q_init_str = r[6].strip() if len(r) > 6 else ""
        p_act_str = r[11].strip() if len(r) > 11 else ""
        p_moy_str = r[12].strip() if len(r) > 12 else ""
        p_der_str = r[10].strip() if len(r) > 10 else ""
        case_str = r[16].strip() if len(r) > 16 else ""

        reasons = []
        if not ref:
            reasons.append("Référence manquante")
        elif ref in seen_refs:
            reasons.append("Référence en doublon dans le fichier")

        if not desig:
            reasons.append("Désignation manquante")

        if not unit:
            reasons.append("Unité de mesure manquante")

        if not cat:
            reasons.append("Catégorie manquante")

        q_reel = clean_num(q_reel_str)
        q_init = clean_num(q_init_str)
        if q_reel is None or q_init is None:
            reasons.append(f"Format quantité non numérique (réel: '{q_reel_str}', init: '{q_init_str}')")
        elif q_reel < 0:
            reasons.append(f"Quantité négative ({q_reel})")

        p_act = clean_num(p_act_str)
        p_moy = clean_num(p_moy_str)
        p_der = clean_num(p_der_str)
        if p_act is None or p_moy is None or p_der is None:
            reasons.append(f"Format prix non numérique (actuel: '{p_act_str}', moyen: '{p_moy_str}')")
        elif p_act < 0 or p_moy < 0:
            reasons.append(f"Prix négatif")

        if reasons:
            skipped_articles.append({
                "ligne": line_num,
                "reference": ref or "(vide)",
                "designation": desig or "(vide)",
                "categorie": cat or "(vide)",
                "unite": unit or "(vide)",
                "quantite_reel": q_reel_str,
                "prix_actuel": p_act_str,
                "motifs": reasons
            })
        else:
            seen_refs.add(ref)
            final_qty = q_reel if q_reel_str != "" else q_init
            final_price = p_act if (p_act is not None and p_act > 0) else (p_moy if (p_moy is not None and p_moy > 0) else (p_der or 0.0))
            final_location = case_str if case_str else "EN_ATTENTE_AFFECTATION"

            valid_articles.append({
                "reference": ref,
                "designation": desig,
                "category": cat,
                "gamme": gamme or "Standard",
                "unit": unit,
                "quantity": final_qty,
                "price": final_price,
                "location": final_location
            })

    print(f"   -> Found {len(valid_articles)} valid articles and {len(skipped_articles)} skipped articles.")

    # 6. Insert into database
    print("6. Inserting valid articles into products, variants, price_history...")
    for art in valid_articles:
        ref = art["reference"]
        desig = art["designation"]
        cat = art["category"]
        gamme = art["gamme"]
        unit = art["unit"]
        qty = art["quantity"]
        price = art["price"]
        loc = art["location"]

        cursor.execute("""
            INSERT INTO products (reference, designation, category, gamme, unit, image_url, threshold, supplier, location, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ref, desig, cat, gamme, unit, "", 10.0, "", loc, now))

        barcode = f"BAR-{ref}"
        cursor.execute("""
            INSERT INTO variants (product_reference, color, ral_code, color_hex, barcode, initial_quantity, real_quantity, reserved_quantity,
                                  threshold, current_price, previous_price, pmp, supplier, location, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 10.0, ?, ?, ?, '', ?, ?)
        """, (ref, "RAL 7024", "RAL 7024", "#474a51", barcode, qty, qty, price, price, price, loc, now))
        var_id = cursor.lastrowid

        if price > 0 or qty > 0:
            cursor.execute("""
                INSERT INTO price_history (variant_id, product_reference, price, pmp_after, quantity, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (var_id, ref, price, price, qty, now))

    conn.commit()
    conn.close()

    # Save skipped report
    with open("skipped_articles_report.json", "w", encoding="utf-8") as f:
        json.dump(skipped_articles, f, indent=2, ensure_ascii=False)

    print("=== IMPORT COMPLETE ===")
    print(f"Imported successfully: {len(valid_articles)} products and variants.")
    print(f"Skipped: {len(skipped_articles)} rows.")
    print("Skipped report saved to skipped_articles_report.json")

if __name__ == "__main__":
    run_import()

