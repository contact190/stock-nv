import sqlite3
import os
from datetime import datetime

def get_db_path():
    return os.environ.get("STOCK_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stock.db"))

def get_db():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_pmp(stock_existant: float, pmp_actuel: float, qte_entrante: float, prix_achat_unitaire: float) -> float:
    """
    Formule stricte du PMP (Prix Moyen Pondéré) :
    Nouveau PMP = ((Stock Existant * PMP Actuel) + (Qté Entrante * Prix Achat)) / (Stock Existant + Qté Entrante)
    """
    if stock_existant <= 0:
        return round(float(prix_achat_unitaire), 2)
    
    total_valeur = (stock_existant * pmp_actuel) + (qte_entrante * prix_achat_unitaire)
    total_qte = stock_existant + qte_entrante
    if total_qte <= 0:
        return round(float(prix_achat_unitaire), 2)
    
    return round(float(total_valeur / total_qte), 2)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Catégories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
    """)

    # 2. Gammes / Séries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gammes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
    """)

    # 3. Unités de mesure
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            symbol TEXT NOT NULL
        )
    """)

    # 4. Gestion des Cases Atelier (P-N° pour Profilés, A-N° pour Accessoires)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workshop_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, /* 'PROFILE' ou 'ACCESSOIRE' */
            code TEXT NOT NULL UNIQUE, /* ex: 'P-01', 'A-02' */
            description TEXT
        )
    """)

    # 4b. Nuancier et Couleurs RAL (Gestion dynamique)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            ral_code TEXT,
            hex_code TEXT DEFAULT '#474a51'
        )
    """)

    # 5. Catalogue Maître (Produits)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            reference TEXT PRIMARY KEY,
            designation TEXT NOT NULL,
            category TEXT NOT NULL,
            gamme TEXT NOT NULL,
            unit TEXT NOT NULL,
            image_url TEXT,
            threshold REAL DEFAULT 10,
            supplier TEXT,
            location TEXT DEFAULT 'EN_ATTENTE_AFFECTATION',
            created_at TEXT NOT NULL
        )
    """)

    # 6. Variantes (Déclinaison par Couleur avec Code RAL et PMP)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_reference TEXT NOT NULL,
            color TEXT NOT NULL,
            ral_code TEXT,
            color_hex TEXT DEFAULT '#64748b',
            barcode TEXT,
            initial_quantity REAL DEFAULT 0,
            real_quantity REAL DEFAULT 0,
            reserved_quantity REAL DEFAULT 0,
            threshold REAL DEFAULT 10,
            current_price REAL DEFAULT 0,
            previous_price REAL DEFAULT 0,
            pmp REAL DEFAULT 0,
            supplier TEXT,
            location TEXT DEFAULT 'EN_ATTENTE_AFFECTATION',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (product_reference) REFERENCES products (reference) ON DELETE CASCADE,
            UNIQUE(product_reference, color)
        )
    """)

    # 7. Historique des prix & PMP
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL,
            product_reference TEXT NOT NULL,
            price REAL NOT NULL,
            pmp_after REAL NOT NULL,
            quantity REAL NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE
        )
    """)

    # 8. Mouvements (Journal chronologique)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_type TEXT NOT NULL, /* STOCKAGE, DESTOCKAGE, RESERVATION, LIBERATION */
            product_reference TEXT NOT NULL,
            product_name TEXT NOT NULL,
            color TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            pmp_at_movement REAL NOT NULL DEFAULT 0,
            total_value REAL NOT NULL,
            order_number TEXT, /* N° Commande / Lot ou texte libre motif si non assigné */
            operator TEXT DEFAULT 'Atelier',
            is_anonyme INTEGER DEFAULT 0,
            notes TEXT
        )
    """)

    # 9. Commandes / Lots simples
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT NOT NULL UNIQUE, /* ex: CMD-2026-001, LOT-01 */
            client_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'EN_ATTENTE', /* EN_ATTENTE, RESERVEE, DESTOCKED, ANNULEE */
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 10. Articles de commande
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            order_number TEXT NOT NULL,
            variant_id INTEGER NOT NULL,
            product_reference TEXT NOT NULL,
            product_name TEXT NOT NULL,
            color TEXT NOT NULL,
            quantity_reserved REAL NOT NULL DEFAULT 0,
            quantity_destocked REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'RESERVED',
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE
        )
    """)

    # 11. Sessions & Comptages d'Inventaire Croisé (Double comptage 2 personnes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL UNIQUE,
            product_reference TEXT NOT NULL,
            color TEXT NOT NULL,
            person1_name TEXT DEFAULT 'Personne 1',
            count1 REAL,
            person2_name TEXT DEFAULT 'Personne 2',
            count2 REAL,
            expected_quantity REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING', /* PENDING, CONFORME, DISCREPANCY, RECOUNT_NEEDED, ADJUSTED */
            is_selected INTEGER DEFAULT 0,
            inventory_date TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE
        )
    """)

    # 12. Historique des Anomalies d'Inventaire post-mise à niveau
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL,
            product_reference TEXT NOT NULL,
            designation TEXT NOT NULL,
            color TEXT NOT NULL,
            real_quantity_before REAL NOT NULL,
            counted_quantity REAL NOT NULL,
            discrepancy_quantity REAL NOT NULL,
            pmp_at_adjustment REAL NOT NULL DEFAULT 0,
            financial_impact REAL NOT NULL DEFAULT 0,
            person1_name TEXT,
            count1 REAL,
            person2_name TEXT,
            count2 REAL,
            reason TEXT NOT NULL, /* Motif obligatoire de l'anomalie */
            notes TEXT,
            adjusted_by TEXT DEFAULT 'Admin',
            created_at TEXT NOT NULL,
            FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE
        )
    """)

    # Indexation haute performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_var_ref_col ON variants(product_reference, color)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mvt_action_order ON movements(action_type, order_number, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ord_itm_var ON order_items(order_number, variant_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_cnt_var ON inventory_counts(variant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_anom_ref ON inventory_anomalies(product_reference, color, created_at)")

    # Migration automatique des colonnes manquantes (compatibilité schéma)
    cursor.execute("PRAGMA table_info(variants)")
    variant_cols = [c["name"] for c in cursor.fetchall()]
    if "ral_code" not in variant_cols:
        cursor.execute("ALTER TABLE variants ADD COLUMN ral_code TEXT")
    if "last_inventory_date" not in variant_cols:
        cursor.execute("ALTER TABLE variants ADD COLUMN last_inventory_date TEXT")

    cursor.execute("PRAGMA table_info(movements)")
    mvt_cols = [c["name"] for c in cursor.fetchall()]
    if "operator" not in mvt_cols:
        cursor.execute("ALTER TABLE movements ADD COLUMN operator TEXT DEFAULT 'Atelier'")
    if "is_anonyme" not in mvt_cols:
        cursor.execute("ALTER TABLE movements ADD COLUMN is_anonyme INTEGER DEFAULT 0")

    # Peuplement workshop_cases si vide
    cursor.execute("SELECT COUNT(*) as cnt FROM workshop_cases")
    if cursor.fetchone()["cnt"] == 0:
        cases = [
            ("PROFILE", "P-01", "Rack Vertical Profilés Dormants"),
            ("PROFILE", "P-02", "Rack Vertical Profilés Ouvrants"),
            ("PROFILE", "P-03", "Casier Horizontal Barres 6m"),
            ("PROFILE", "P-04", "Casier Coulissants 70mm"),
            ("PROFILE", "P-05", "Rack Lames Extrudées"),
            ("ACCESSOIRE", "A-01", "Bac Équerres & Quincaillerie"),
            ("ACCESSOIRE", "A-02", "Étagère Crémones & Poignées"),
            ("ACCESSOIRE", "A-03", "Bac Joints Brosse & EPDM"),
            ("ACCESSOIRE", "A-04", "Casier Coulisses VR 45mm")
        ]
        cursor.executemany("INSERT OR IGNORE INTO workshop_cases (type, code, description) VALUES (?, ?, ?)", cases)

    # Peuplement Nuancier / Couleurs si vide (défaut : RAL 7024 en tête)
    cursor.execute("SELECT COUNT(*) as cnt FROM colors")
    if cursor.fetchone()["cnt"] == 0:
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
        cursor.executemany("INSERT OR IGNORE INTO colors (name, ral_code, hex_code) VALUES (?, ?, ?)", default_colors)

    # Migration : Mise à niveau des variantes 'Standard' vers 'RAL 7024'
    cursor.execute("UPDATE variants SET color = 'RAL 7024', ral_code = 'RAL 7024', color_hex = '#474a51' WHERE color = 'Standard' OR color = 'standard'")
    cursor.execute("UPDATE movements SET color = 'RAL 7024' WHERE color = 'Standard' OR color = 'standard'")
    cursor.execute("UPDATE order_items SET color = 'RAL 7024' WHERE color = 'Standard' OR color = 'standard'")

    conn.commit()
    seed_data(cursor, conn)
    conn.close()

def seed_data(cursor, conn):
    """Données de départ avec Cases P-xx/A-xx, Nuances RAL et Commandes/Lots simples."""
    cursor.execute("SELECT COUNT(*) as cnt FROM categories")
    if cursor.fetchone()["cnt"] > 0:
        return
    cursor.execute("SELECT COUNT(*) as cnt FROM products")
    if cursor.fetchone()["cnt"] > 0:
        return

    # Catégories
    categories = [
        ("Profilés Aluminium", "Profilés dormants et ouvrants pour fenêtres et portes"),
        ("Volets Roulants", "Lames de volet alu, coulisses, lames finales et coffres"),
        ("Accessoires & Quincaillerie", "Poignées, crémones, équerres d'assemblage et paumelles"),
        ("Joints & Étanchéité", "Joints brosse, joints EPDM de vitrage et bavettes")
    ]
    cursor.executemany("INSERT INTO categories (name, description) VALUES (?, ?)", categories)

    # Gammes / Séries
    gammes = [
        ("Série RPT 55mm", "Rupture de pont thermique haute isolation"),
        ("Série Coulissant 70mm", "Profilés aluminium pour baies coulissantes"),
        ("Lames Extrudées Renforcées", "Aluminium extrudé double paroi"),
        ("Lames Thermo-Phoniques", "Aluminium injecté mousse polyuréthane")
    ]
    cursor.executemany("INSERT INTO gammes (name, description) VALUES (?, ?)", gammes)

    # Unités
    units = [
        ("Barre (6.00m)", "barre"),
        ("Mètre Linéaire", "m"),
        ("Pièce", "pcs"),
        ("Carton / Paquet", "ctn")
    ]
    cursor.executemany("INSERT INTO units (name, symbol) VALUES (?, ?)", units)

    # CASES ATELIER : P-N° (Profilés) et A-N° (Accessoires)
    cases = [
        ("PROFILE", "P-01", "Rack Vertical Profilés Dormants"),
        ("PROFILE", "P-02", "Rack Vertical Profilés Ouvrants"),
        ("PROFILE", "P-03", "Casier Horizontal Barres 6m"),
        ("PROFILE", "P-04", "Casier Coulissants 70mm"),
        ("PROFILE", "P-05", "Rack Lames Extrudées"),
        ("ACCESSOIRE", "A-01", "Bac Équerres & Quincaillerie"),
        ("ACCESSOIRE", "A-02", "Étagère Crémones & Poignées"),
        ("ACCESSOIRE", "A-03", "Bac Joints Brosse & EPDM"),
        ("ACCESSOIRE", "A-04", "Casier Coulisses VR 45mm")
    ]
    cursor.executemany("INSERT OR IGNORE INTO workshop_cases (type, code, description) VALUES (?, ?, ?)", cases)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Commandes / Lots simples (comme au début : CMD et LOT)
    orders = [
        ("CMD-2026-001", "Client Résidence Delmar", "RESERVEE", "Lot fenêtres et volets alu séjour", now, now),
        ("CMD-2026-002", "Projet Résidence Sibawi", "DESTOCKED", "Commande profilés débités", "2026-10-28 10:00:00", "2026-10-28 14:30:00"),
        ("LOT-03", "Lot Menuiseries Tour Gaea", "DESTOCKED", "Sortie barres coulissants", "2026-10-29 09:00:00", "2026-10-29 11:15:00"),
        ("CMD-2026-004", "Villa Dely Brahim", "EN_ATTENTE", "En attente mesures métreur", now, now)
    ]
    cursor.executemany("""
        INSERT INTO orders (order_number, client_name, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, orders)

    # Produits Catalogue Maître
    products = [
        ("HPS-40", "Profilé Dormant Alu 40mm RPT", "Profilés Aluminium", "Série RPT 55mm", "barre",
         "https://images.unsplash.com/photo-1504917599217-d4dc5ebe6122?w=150&auto=format&fit=crop&q=80", 15, "AluMaghreb Profils", "P-01", now),
        ("EX-2001", "Lame Finale Volet Roulant Extrudé", "Volets Roulants", "Lames Extrudées Renforcées", "barre",
         "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=150&auto=format&fit=crop&q=80", 20, "TechnoVolet Algérie", "P-05", now),
        ("OUV-ALU-55", "Profilé Ouvrant Fenêtre Frappe 55mm", "Profilés Aluminium", "Série RPT 55mm", "barre",
         "https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=150&auto=format&fit=crop&q=80", 12, "AluMaghreb Profils", "P-02", now),
        ("GLIS-VR-45", "Coulisse Volet Roulant avec Joint Brosse", "Volets Roulants", "Lames Extrudées Renforcées", "barre",
         "https://images.unsplash.com/photo-1534398079543-7ae6d016b86a?w=150&auto=format&fit=crop&q=80", 18, "TechnoVolet Algérie", "A-04", now)
    ]
    cursor.executemany("""
        INSERT INTO products (reference, designation, category, gamme, unit, image_url, threshold, supplier, location, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, products)

    # Variantes avec codes RAL (Blanc 9010, Gris 7016, Noir 2100 Sablé, Argent 9006, etc.)
    # Format: (ref, color, ral_code, hex, barcode, q_init, q_real, q_res, thresh, curr_p, pmp, supp, loc)
    variants = [
        ("HPS-40", "Blanc Pur RAL 9010", "RAL 9010", "#f8fafc", "BAR-HPS40-RAL9010", 100, 100, 40, 15, 8200.0, 8200.0, "AluMaghreb Profils", "P-01"),
        ("HPS-40", "Gris Anthracite RAL 7016", "RAL 7016", "#334155", "BAR-HPS40-RAL7016", 60, 45, 0, 15, 8600.0, 8600.0, "AluMaghreb Profils", "P-01"),
        ("HPS-40", "Noir Sablé RAL 2100", "RAL 2100", "#0f172a", "BAR-HPS40-RAL2100", 50, 14, 0, 15, 8900.0, 8900.0, "AluMaghreb Profils", "P-01"), # Stock bas

        ("EX-2001", "Blanc Pur RAL 9010", "RAL 9010", "#f8fafc", "BAR-EX2001-RAL9010", 80, 65, 10, 20, 3200.0, 3200.0, "TechnoVolet Algérie", "P-05"),
        ("EX-2001", "Gris Anthracite RAL 7016", "RAL 7016", "#334155", "BAR-EX2001-RAL7016", 50, 12, 0, 20, 3400.0, 3400.0, "TechnoVolet Algérie", "P-05"), # Stock bas
        ("EX-2001", "Aluminium Blanc RAL 9006", "RAL 9006", "#94a3b8", "BAR-EX2001-RAL9006", 40, 35, 0, 15, 3600.0, 3600.0, "TechnoVolet Algérie", "A-04"),

        ("OUV-ALU-55", "Blanc Pur RAL 9010", "RAL 9010", "#f8fafc", "BAR-OUV55-RAL9010", 70, 52, 12, 15, 9400.0, 9400.0, "AluMaghreb Profils", "P-02"),
        ("OUV-ALU-55", "Gris Anthracite RAL 7016", "RAL 7016", "#334155", "BAR-OUV55-RAL7016", 45, 38, 0, 12, 9800.0, 9800.0, "AluMaghreb Profils", "P-02"),
        ("OUV-ALU-55", "Noir Sablé RAL 2100", "RAL 2100", "#0f172a", "BAR-OUV55-RAL2100", 30, 4, 0, 10, 10200.0, 10200.0, "AluMaghreb Profils", "P-02"), # Stock bas

        ("GLIS-VR-45", "Blanc Pur RAL 9010", "RAL 9010", "#f8fafc", "BAR-GLIS45-RAL9010", 120, 95, 20, 25, 2100.0, 2100.0, "TechnoVolet Algérie", "A-04"),
        ("GLIS-VR-45", "Gris Anthracite RAL 7016", "RAL 7016", "#334155", "BAR-GLIS45-RAL7016", 60, 48, 5, 20, 2250.0, 2250.0, "TechnoVolet Algérie", "A-04")
    ]

    for item in variants:
        ref, color, ral_c, hex_v, bcode, q_init, q_real, q_res, thresh, curr_p, pmp_v, supp, loc = item
        cursor.execute("""
            INSERT INTO variants (product_reference, color, ral_code, color_hex, barcode, initial_quantity, real_quantity, reserved_quantity,
                                  threshold, current_price, previous_price, pmp, supplier, location, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ref, color, ral_c, hex_v, bcode, q_init, q_real, q_res, thresh, curr_p, curr_p, pmp_v, supp, loc, now))
        var_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO price_history (variant_id, product_reference, price, pmp_after, quantity, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (var_id, ref, curr_p, pmp_v, q_init, now))

    # Récupérer IDs commandes
    cursor.execute("SELECT id, order_number FROM orders")
    orders_map = {row["order_number"]: row["id"] for row in cursor.fetchall()}

    cursor.execute("SELECT id, product_reference, color, current_price, pmp FROM variants")
    v_map = {(r["product_reference"], r["color"]): (r["id"], r["current_price"], r["pmp"]) for r in cursor.fetchall()}

    # Réservation CMD-2026-001
    v_id1, p1, pmp1 = v_map[("HPS-40", "Blanc Pur RAL 9010")]
    cursor.execute("""
        INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color, quantity_reserved, quantity_destocked, unit_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (orders_map["CMD-2026-001"], "CMD-2026-001", v_id1, "HPS-40", "Profilé Dormant Alu 40mm RPT", "Blanc Pur RAL 9010", 40, 0, p1, "RESERVED"))

    # Déstockages passés pour CMD-2026-002 et LOT-03
    v_id3, p3, pmp3 = v_map[("OUV-ALU-55", "Blanc Pur RAL 9010")]
    cursor.execute("""
        INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color, quantity_reserved, quantity_destocked, unit_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (orders_map["CMD-2026-002"], "CMD-2026-002", v_id3, "OUV-ALU-55", "Profilé Ouvrant Fenêtre Frappe 55mm", "Blanc Pur RAL 9010", 0, 18, p3, "DESTOCKED"))

    v_id4, p4, pmp4 = v_map[("GLIS-VR-45", "Gris Anthracite RAL 7016")]
    cursor.execute("""
        INSERT INTO order_items (order_id, order_number, variant_id, product_reference, product_name, color, quantity_reserved, quantity_destocked, unit_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (orders_map["LOT-03"], "LOT-03", v_id4, "GLIS-VR-45", "Coulisse Volet Roulant avec Joint Brosse", "Gris Anthracite RAL 7016", 0, 12, p4, "DESTOCKED"))

    # Mouvements de départ
    movements = [
        ("2026-10-20 08:30:00", "STOCKAGE", "HPS-40", "Profilé Dormant Alu 40mm RPT", "Blanc Pur RAL 9010", 100, 8200.0, 8200.0, 820000.0, None, "Atelier", "Entrée usine extrusion"),
        ("2026-10-20 09:00:00", "STOCKAGE", "HPS-40", "Profilé Dormant Alu 40mm RPT", "Gris Anthracite RAL 7016", 60, 8600.0, 8600.0, 516000.0, None, "Atelier", "Réception palette laquage Gris 7016"),
        ("2026-10-21 10:00:00", "STOCKAGE", "EX-2001", "Lame Finale Volet Roulant Extrudé", "Blanc Pur RAL 9010", 80, 3200.0, 3200.0, 256000.0, None, "Atelier", "Réception lot TechnoVolet"),
        ("2026-10-28 14:30:00", "DESTOCKAGE", "OUV-ALU-55", "Profilé Ouvrant Fenêtre Frappe 55mm", "Blanc Pur RAL 9010", 18, 9400.0, 9400.0, 169200.0, "CMD-2026-002", "Atelier", "Débit profilés fenêtres"),
        ("2026-10-29 11:15:00", "DESTOCKAGE", "GLIS-VR-45", "Coulisse Volet Roulant avec Joint Brosse", "Gris Anthracite RAL 7016", 12, 2250.0, 2250.0, 27000.0, "LOT-03", "Atelier", "Sortie coulisses"),
        ("2026-10-30 16:00:00", "DESTOCKAGE", "HPS-40", "Profilé Dormant Alu 40mm RPT", "Gris Anthracite RAL 7016", 15, 8600.0, 8600.0, 129000.0, "Non assigné (Débit libre)", "Atelier", "Chutes & fabrication cadre expo"),
        ("2026-10-31 09:30:00", "RESERVATION", "HPS-40", "Profilé Dormant Alu 40mm RPT", "Blanc Pur RAL 9010", 40, 8200.0, 8200.0, 328000.0, "CMD-2026-001", "Atelier", "Réservation barres pour commande")
    ]
    cursor.executemany("""
        INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, movements)

    conn.commit()
