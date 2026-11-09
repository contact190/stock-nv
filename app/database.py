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
    """
    Initialisation système : la base reste entièrement vierge de tout produit ou commande de démo.
    Les utilisateurs peuvent saisir leurs articles manuellement ou via import.
    """
    pass
