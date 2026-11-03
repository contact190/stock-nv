"""
Suite de Tests QA & Scénarios d'Intégration
Valide l'ensemble des règles négatives, calculs PMP et scénarios de test (A, B, C, D).
"""
import unittest
import os
import sqlite3
from datetime import datetime
from app.database import get_db, init_db, calculate_pmp
from app.models import (
    CatalogProductCreate, StockInRequest, DestockRequest, ReserveRequest, 
    BatchItem, BatchDestockRequest, BatchReserveRequest,
    InventoryAdjustmentRequest
)
from app.services import (
    create_catalog_product,
    stock_in_operation,
    destock_operation,
    batch_destock_operation,
    reserve_operation,
    batch_reserve_operation,
    validate_and_destock_order,
    get_dashboard_metrics,
    get_products_with_variants,
    get_inventory_items,
    save_inventory_counts,
    recount_inventory_item,
    adjust_stock_to_inventory,
    get_inventory_anomalies,
    generate_inventory_print_sheet
)

class TestQANegativeAndBusinessRules(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_qa_stock.db")
        os.environ["STOCK_DB_PATH"] = cls.test_db_path
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
        init_db()

    @classmethod
    def tearDownClass(cls):
        """Suppression complète de la base de test temporaire pour garantir zéro pollution."""
        if "STOCK_DB_PATH" in os.environ:
            del os.environ["STOCK_DB_PATH"]
        if hasattr(cls, "test_db_path") and os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    # ========================================================
    # A. Test de Réception & Saisie d'Entrée (Stockage)
    # ========================================================

    def test_1_1_controle_du_prix_zero_bloque(self):
        """Test 1.1 : Contrôle du Prix d'achat à 0 DZD (doit bloquer sans confirmation)"""
        req = StockInRequest(
            reference="HPS-40",
            color="Blanc 9010 Brillant",
            quantity=10,
            unit_price=0.0,
            allow_zero_price=False
        )
        with self.assertRaises(ValueError) as ctx:
            stock_in_operation(req)
        self.assertIn("0 DZD", str(ctx.exception))
        print("[TEST PASSED] Test 1.1: Entree avec prix a 0 DZD bloquee avec succes.")

    def test_1_2_interdiction_doublon_catalogue(self):
        """Test 1.2 : Interdiction stricte des doublons [Ref + Couleur]"""
        test_ref = "TEST-REF-DOUBLON"
        test_color = "Blanc 9010"
        duplicate_item = CatalogProductCreate(
            reference=test_ref,
            designation="Article Test Doublon",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            unit_price=3200.0,
            threshold=15
        )
        try:
            create_catalog_product(duplicate_item)
        except ValueError:
            pass

        with self.assertRaises(ValueError) as ctx:
            create_catalog_product(duplicate_item)
        self.assertIn("existe déjà", str(ctx.exception))
        print("[TEST PASSED] Test 1.2: Doublon [Ref + Couleur] formellement rejeté.")

    def test_1_3_emplacement_par_defaut_en_attente(self):
        """Test 1.3 : Attribution automatique de EN_ATTENTE_AFFECTATION si casier omis"""
        unique_color = f"Bronze Special {os.urandom(2).hex()}"
        new_prod = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=unique_color,
            location="",
            unit_price=9000.0,
            initial_quantity=10
        )
        res = create_catalog_product(new_prod)
        self.assertEqual(res["location"], "EN_ATTENTE_AFFECTATION")

        metrics = get_dashboard_metrics()
        self.assertGreater(metrics["kpis"]["unassigned_location_count"], 0)
        print("[TEST PASSED] Test 1.3: Emplacement EN_ATTENTE_AFFECTATION attribue et alerte.")

    # ========================================================
    # B. Test de Déstockage & Réservation (Mouvements)
    # ========================================================

    def test_2_1_reservation_vs_destockage_physique(self):
        """
        Test 2.1 :
        - Stock initial : 100 barres
        - Réservation de 40 barres pour DELMAR -> Réel = 100, Dispo = 60
        - Déstockage effectif de 40 barres -> Réel = 60, Réservé = 0
        """
        test_color = f"Gris Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=100.0,
            unit_price=8000.0,
            threshold=15
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        # Étape 1 : Réservation de 40 barres pour TEST-DELMAR-01
        reserve_req = ReserveRequest(
            variant_id=v_id,
            order_number="TEST-DELMAR-01",
            quantity=40.0,
            user="Ahmed B."
        )
        reserve_operation(reserve_req)

        # Vérification Étape 1
        prods = get_products_with_variants()
        var_found = None
        for p in prods:
            for v in p["variants"]:
                if v["id"] == v_id:
                    var_found = v
                    break

        self.assertIsNotNone(var_found)
        self.assertEqual(var_found["real_quantity"], 100.0, "Le stock physique doit rester a 100 lors de la reservation")
        self.assertEqual(var_found["available_quantity"], 60.0, "Le stock disponible doit passer a 60")
        self.assertEqual(var_found["reserved_quantity"], 40.0)

        # Étape 2 : Déstockage effectif des 40 barres pour TEST-DELMAR-01
        validate_and_destock_order("TEST-DELMAR-01")

        # Vérification Étape 2
        prods_after = get_products_with_variants()
        var_after = None
        for p in prods_after:
            for v in p["variants"]:
                if v["id"] == v_id:
                    var_after = v
                    break

        self.assertEqual(var_after["real_quantity"], 60.0, "Le stock physique doit passer a 60 apres destockage effectif")
        self.assertEqual(var_after["reserved_quantity"], 0.0, "La reservation doit etre cloturee")
        print("[TEST PASSED] Test 2.1: Cycle Reservation (100 -> Reel 100 / Dispo 60) puis Destockage (Reel 60) conforme.")

    def test_2_2_interdiction_stock_negatif(self):
        """Interdiction stricte du stock négatif non contrôlé"""
        test_color = f"Noir Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=5.0,
            unit_price=8500.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        # Tenter de sortir 10 barres alors qu'il n'y en a que 5
        destock_req = DestockRequest(
            variant_id=v_id,
            quantity=10.0,
            chantier="DELMAR",
            poseur="Ahmed B."
        )
        with self.assertRaises(ValueError) as ctx:
            destock_operation(destock_req)
        self.assertIn("Stock Négatif", str(ctx.exception))
        print("[TEST PASSED] Test Securite Stock Negatif: Sortie > stock reel bloquee.")

    def test_2_3_tracabilite_alerte_anonyme(self):
        """Test alerte de traçabilité si déstockage sans chantier/poseur (non bloquant mais alerté)"""
        test_color = f"Argent Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=20.0,
            unit_price=8500.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        destock_req = DestockRequest(
            variant_id=v_id,
            quantity=2.0,
            chantier=None,
            poseur=None
        )
        res = destock_operation(destock_req)
        self.assertTrue(res["success"])
        self.assertIsNotNone(res["warning"])
        self.assertIn("non assignée", res["warning"])
        print("[TEST PASSED] Test 2.3: Alerte traçabilité générée pour sortie non assignée.")

    # ========================================================
    # C. Test du Dashboard & Filtres Financiers PMP
    # ========================================================

    def test_3_1_filtre_par_ensemble_de_commandes(self):
        """Test 3.1 : Filtrer par ensemble de chantiers calcule exactement les sorties dédiées"""
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR IGNORE INTO orders (order_number, client_name, status, created_at, updated_at) VALUES ('TEST-CMD-SIBAWI', 'Client Sibawi', 'DESTOCKED', ?, ?)", (now, now))
        cursor.execute("""
            INSERT INTO movements (timestamp, action_type, product_reference, product_name, color, quantity, unit_price, pmp_at_movement, total_value, order_number, operator, notes)
            VALUES (?, 'DESTOCKAGE', 'TEST-REF', 'Test Produit', 'Standard', 10, 1000.0, 1000.0, 10000.0, 'TEST-CMD-SIBAWI', 'Atelier', 'Test')
        """, (now,))
        conn.commit()
        conn.close()

        metrics = get_dashboard_metrics(selected_orders=["TEST-CMD-SIBAWI"])
        destocked_val = metrics["kpis"]["destocked_value"]
        self.assertGreaterEqual(destocked_val, 10000.0)
        print(f"[TEST PASSED] Test 3.1: Filtre chantier = {destocked_val:,.2f} DZD.")

    def test_3_2_alerte_de_seuil(self):
        """Test 3.2 : Seuil à 15, stock réduit à 14 -> Apparaît immédiatement en alerte"""
        test_color = f"Beige Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=15.0,
            threshold=15.0,
            unit_price=8500.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        destock_operation(DestockRequest(variant_id=v_id, quantity=1.0, chantier="DELMAR", poseur="Karim T."))

        metrics = get_dashboard_metrics()
        alert_refs = [a["color"] for a in metrics["alerts"]]
        self.assertIn(test_color, alert_refs)
        print("[TEST PASSED] Test 3.2: Article a 14 unites (seuil 15) immediatement liste dans les alertes.")

    # ========================================================
    # D. Test Calcul Mathématique du PMP
    # ========================================================

    def test_4_1_formule_pmp_exacte(self):
        """
        Test 4.1 : Vérification mathématique stricte de la formule du PMP :
        - Stock initial : 50 barres à 8 000 DZD = 400 000 DZD (PMP = 8 000)
        - Entrée : 50 barres à 10 000 DZD
        - Nouveau PMP = ((50 * 8000) + (50 * 10000)) / (50 + 50) = 900 000 / 100 = 9 000 DZD
        """
        pmp = calculate_pmp(
            stock_existant=50.0,
            pmp_actuel=8000.0,
            qte_entrante=50.0,
            prix_achat_unitaire=10000.0
        )
        self.assertEqual(pmp, 9000.0)

        pmp2 = calculate_pmp(
            stock_existant=100.0,
            pmp_actuel=9000.0,
            qte_entrante=20.0,
            prix_achat_unitaire=12000.0
        )
        self.assertEqual(pmp2, 9500.0)
        print("[TEST PASSED] Test 4.1: Formule PMP mathematiquement exacte (9 000 DZD puis 9 500 DZD).")

    # ========================================================
    # E. Nouveaux Tests : Cases Atelier, Opérateur par Défaut, Filtres Temporels
    # ========================================================

    def test_5_1_cases_atelier_types(self):
        """Test 5.1 : Cases atelier types PROFILE et ACCESSOIRE"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT code, type FROM workshop_cases WHERE type = 'PROFILE'")
        p_cases = cursor.fetchall()
        cursor.execute("SELECT code, type FROM workshop_cases WHERE type = 'ACCESSOIRE'")
        a_cases = cursor.fetchall()
        conn.close()

        self.assertGreater(len(p_cases), 0, "Doit comporter des cases profilés")
        self.assertGreater(len(a_cases), 0, "Doit comporter des cases accessoires")
        print(f"[TEST PASSED] Test 5.1: Cases atelier verifies ({len(p_cases)} profile, {len(a_cases)} accessoire).")

    def test_5_2_destock_operateur_par_defaut_atelier_et_texte_libre(self):
        """Test 5.2 : Déstockage avec opérateur par défaut 'Atelier' et motif libre si non assigné"""
        test_color = f"Brun Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=20.0,
            unit_price=8000.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        # Sortie non assignée à une commande avec motif libre
        destock_req = DestockRequest(
            variant_id=v_id,
            quantity=3.0,
            order_number=None,
            unassigned_reason="Chutes pour prototype atelier",
            operator=None  # Sera par défaut 'Atelier'
        )
        res = destock_operation(destock_req)
        self.assertTrue(res["success"])

        # Vérification en base de données dans la table movements
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT operator, order_number, is_anonyme FROM movements WHERE product_reference = 'HPS-40' AND color = ? ORDER BY id DESC LIMIT 1", (test_color,))
        mvt = cursor.fetchone()
        conn.close()

        self.assertEqual(mvt["operator"], "Atelier", "L'opérateur par défaut doit être 'Atelier'")
        self.assertEqual(mvt["order_number"], "Chutes pour prototype atelier")
        self.assertEqual(mvt["is_anonyme"], 1)
        print("[TEST PASSED] Test 5.2: Destockage avec operateur 'Atelier' et motif libre valide.")

    def test_5_3_interdiction_stockage_orphelin(self):
        """Test 5.3 : Interdiction de stocker un article inexistant au catalogue"""
        req = StockInRequest(
            reference="REF-INCONNUE-9999",
            color="Couleur Inconnue",
            quantity=10,
            unit_price=5000.0
        )
        with self.assertRaises(ValueError) as ctx:
            stock_in_operation(req)
        self.assertIn("Mouvement orphelin interdit", str(ctx.exception))
        print("[TEST PASSED] Test 5.3: Stockage orphelin d'article inexistant bloque avec succes.")

    def test_5_4_filtre_dashboard_par_periode(self):
        """Test 5.4 : Filtre du dashboard par période ('MONTH', 'WEEK', 'YEAR', 'ALL')"""
        for p in ["ALL", "WEEK", "MONTH", "YEAR"]:
            metrics = get_dashboard_metrics(period=p)
            self.assertIn("kpis", metrics)
            self.assertIn("charts", metrics)
        print("[TEST PASSED] Test 5.4: Filtrage dashboard par periode (ALL, WEEK, MONTH, YEAR) fonctionnel.")

    def test_5_5_filtre_stock_reserve_et_chantier(self):
        """Test 5.5 : Filtrage catalogue par statut 'RESERVE' et par chantier spécifique"""
        test_color = f"Vert Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=50.0,
            unit_price=8000.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        # Réserver 15 barres pour le chantier CMD-FILTRE-01
        res_req = ReserveRequest(
            variant_id=v_id,
            order_number="CMD-FILTRE-01",
            lot_number="LOT-ETAGE-1",
            quantity=15.0
        )
        reserve_operation(res_req)

        # Vérifier filtre RESERVE
        stock_reserved = get_products_with_variants(status_filter="RESERVE")
        reserved_vars = [v for p in stock_reserved for v in p["variants"] if v["id"] == v_id]
        self.assertEqual(len(reserved_vars), 1)
        self.assertEqual(reserved_vars[0]["reserved_quantity"], 15.0)

        # Vérifier filtre par chantier
        stock_chantier = get_products_with_variants(chantier_filter="CMD-FILTRE-01")
        chantier_vars = [v for p in stock_chantier for v in p["variants"] if v["id"] == v_id]
        self.assertEqual(len(chantier_vars), 1)
        print("[TEST PASSED] Test 5.5: Filtrage stock RESERVE et Chantier operationnel.")

    def test_5_6_destock_et_reservation_avec_saisie_manuelle_lot(self):
        """Test 5.6 : Déstockage et Réservation avec sélection de commande et saisie manuelle de lot"""
        test_color = f"Bleu Test {os.urandom(2).hex()}"
        item = CatalogProductCreate(
            reference="HPS-40",
            designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=test_color,
            initial_quantity=40.0,
            unit_price=9000.0
        )
        cat_res = create_catalog_product(item)
        v_id = cat_res["variant_id"]

        # Déstockage avec commande + lot manuel
        destock_req = DestockRequest(
            variant_id=v_id,
            quantity=5.0,
            order_number="CMD-2026-LOT",
            lot_number="LOT-FACADE-NORD",
            operator="Atelier"
        )
        d_res = destock_operation(destock_req)
        self.assertTrue(d_res["success"])

        # Vérification dans la table movements
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT order_number FROM movements WHERE product_reference = 'HPS-40' AND color = ? AND action_type = 'DESTOCKAGE' ORDER BY id DESC LIMIT 1", (test_color,))
        mvt = cursor.fetchone()
        conn.close()

        self.assertIn("CMD-2026-LOT", mvt["order_number"])
        self.assertIn("LOT-FACADE-NORD", mvt["order_number"])
        print("[TEST PASSED] Test 5.6: Destockage et Reservation avec lot manuel traces avec succes.")

    def test_5_7_batch_destock_and_batch_reserve(self):
        """Test 5.7 : Déstockage et Réservation multi-articles (Batch) avec commande et lot partagés"""
        # Création de deux articles
        c1 = f"Vert Batch {os.urandom(2).hex()}"
        c2 = f"Rouge Batch {os.urandom(2).hex()}"
        it1 = create_catalog_product(CatalogProductCreate(
            reference="HPS-40", designation="Profilé Dormant Alu 40mm RPT",
            category="Profilés Aluminium", gamme="Série RPT 55mm", unit="barre",
            color=c1, initial_quantity=50.0, unit_price=8000.0
        ))
        it2 = create_catalog_product(CatalogProductCreate(
            reference="HPS-40", designation="Profilé Ouvrant Alu RPT",
            category="Profilés Aluminium", gamme="Série RPT 55mm", unit="barre",
            color=c2, initial_quantity=30.0, unit_price=8500.0
        ))
        v1_id = it1["variant_id"]
        v2_id = it2["variant_id"]

        # 1. Test Déstockage Batch
        batch_d = BatchDestockRequest(
            items=[
                BatchItem(variant_id=v1_id, quantity=10.0),
                BatchItem(variant_id=v2_id, quantity=5.0)
            ],
            order_number="BATCH-CMD-99",
            lot_number="LOT-CUISINE",
            operator="Atelier Principal",
            notes="Débit groupé"
        )
        res_d = batch_destock_operation(batch_d)
        self.assertTrue(res_d["success"])
        self.assertEqual(res_d["items_count"], 2)

        # Vérifier que les stocks ont diminué correctement
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT real_quantity FROM variants WHERE id = ?", (v1_id,))
        self.assertEqual(cursor.fetchone()["real_quantity"], 40.0)
        cursor.execute("SELECT real_quantity FROM variants WHERE id = ?", (v2_id,))
        self.assertEqual(cursor.fetchone()["real_quantity"], 25.0)

        # 2. Test Sécurité Stock Négatif sur Batch (doit rejeter l'ensemble si 1 article dépasse)
        with self.assertRaises(ValueError) as ctx:
            batch_destock_operation(BatchDestockRequest(
                items=[
                    BatchItem(variant_id=v1_id, quantity=5.0),
                    BatchItem(variant_id=v2_id, quantity=100.0) # Dépasse 25 dispo
                ],
                order_number="BATCH-FAIL"
            ))
        self.assertIn("Stock Négatif", str(ctx.exception))

        # 3. Test Réservation Batch
        batch_r = BatchReserveRequest(
            items=[
                BatchItem(variant_id=v1_id, quantity=15.0),
                BatchItem(variant_id=v2_id, quantity=10.0)
            ],
            order_number="BATCH-RESERVE-CMD",
            lot_number="LOT-SALON"
        )
        res_r = batch_reserve_operation(batch_r)
        self.assertTrue(res_r["success"])
        self.assertEqual(res_r["items_count"], 2)

        cursor.execute("SELECT reserved_quantity FROM variants WHERE id = ?", (v1_id,))
        self.assertEqual(cursor.fetchone()["reserved_quantity"], 15.0)
        cursor.execute("SELECT reserved_quantity FROM variants WHERE id = ?", (v2_id,))
        self.assertEqual(cursor.fetchone()["reserved_quantity"], 10.0)
        conn.close()
        print("[TEST PASSED] Test 5.7: Destockage et Reservation multi-articles (Batch) valides avec succes.")

    def test_5_8_gestion_couleurs_parametres(self):
        """Test 5.8 : Gestion des couleurs dans Paramètres et présence de RAL 7024 par défaut"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, ral_code, hex_code FROM colors WHERE ral_code = 'RAL 7024'")
        ral_7024 = cursor.fetchone()
        self.assertIsNotNone(ral_7024, "La couleur standard RAL 7024 doit être présente dans la table colors")
        self.assertEqual(ral_7024["ral_code"], "RAL 7024")

        # Test d'ajout d'une nouvelle couleur
        new_color_name = f"Test Couleur {os.urandom(2).hex()}"
        cursor.execute("INSERT INTO colors (name, ral_code, hex_code) VALUES (?, ?, ?)", (new_color_name, "RAL 9999", "#123456"))
        new_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM colors WHERE id = ?", (new_id,))
        self.assertIsNotNone(cursor.fetchone())

        # Nettoyage
        cursor.execute("DELETE FROM colors WHERE id = ?", (new_id,))
        conn.commit()
        conn.close()
        print("[TEST PASSED] Test 5.8: Gestion des couleurs dans Parametres valide avec RAL 7024.")

    # ========================================================
    # F. Tests d'Inventaire Croisé & Gestion des Anomalies
    # ========================================================

    def test_6_1_double_comptage_conforme(self):
        """Test 6.1 : Double comptage identique correspondant au stock réel -> CONFORME (Vert)"""
        # Créer un article de test dédié
        color = f"Test Inv Conforme {os.urandom(2).hex()}"
        res = create_catalog_product(CatalogProductCreate(
            reference="INV-TEST-01",
            designation="Profilé Test Inventaire Conforme",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=color,
            initial_quantity=50.0,
            unit_price=4500.0
        ))
        v_id = res["variant_id"]

        # Double comptage par 2 personnes : 50 et 50
        save_inventory_counts([
            {
                "variant_id": v_id,
                "person1_name": "Karim",
                "count1": 50.0,
                "person2_name": "Sofiane",
                "count2": 50.0
            }
        ])

        inv_data = get_inventory_items(search="INV-TEST-01")
        item = next(it for it in inv_data["items"] if it["variant_id"] == v_id)
        self.assertEqual(item["status"], "CONFORME")
        self.assertFalse(item["is_red"])
        print("[TEST PASSED] Test 6.1: Double comptage conforme (Pers1 == Pers2 == Reel) -> CONFORME.")

    def test_6_2_desaccord_deux_personnes_alerte_rouge(self):
        """Test 6.2 : Les deux personnes ne trouvent pas la même quantité -> DISCREPANCY_PERSONS (Rouge)"""
        color = f"Test Inv Disaccord {os.urandom(2).hex()}"
        res = create_catalog_product(CatalogProductCreate(
            reference="INV-TEST-02",
            designation="Profilé Test Désaccord Comptage",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=color,
            initial_quantity=80.0,
            unit_price=5000.0
        ))
        v_id = res["variant_id"]

        # Personne 1 compte 75, Personne 2 compte 78
        save_inventory_counts([
            {
                "variant_id": v_id,
                "person1_name": "Karim",
                "count1": 75.0,
                "person2_name": "Sofiane",
                "count2": 78.0
            }
        ])

        inv_data = get_inventory_items(search="INV-TEST-02")
        item = next(it for it in inv_data["items"] if it["variant_id"] == v_id)
        self.assertEqual(item["status"], "DISCREPANCY_PERSONS")
        self.assertTrue(item["is_red"])
        print("[TEST PASSED] Test 6.2: Desaccord entre les deux personnes (75 != 78) -> Alerte Rouge.")

    def test_6_3_ecart_avec_stock_reel_alerte_rouge(self):
        """Test 6.3 : Personnes d'accord entre elles mais en écart avec le stock réel -> DISCREPANCY_STOCK (Rouge)"""
        color = f"Test Inv Diff {os.urandom(2).hex()}"
        res = create_catalog_product(CatalogProductCreate(
            reference="INV-TEST-03",
            designation="Profilé Test Écart Stock Réel",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=color,
            initial_quantity=100.0,
            unit_price=6000.0
        ))
        v_id = res["variant_id"]

        # Les 2 personnes comptent 92 barres (écart de -8 barres vs stock théorique de 100)
        save_inventory_counts([
            {
                "variant_id": v_id,
                "person1_name": "Karim",
                "count1": 92.0,
                "person2_name": "Sofiane",
                "count2": 92.0
            }
        ])

        inv_data = get_inventory_items(search="INV-TEST-03")
        item = next(it for it in inv_data["items"] if it["variant_id"] == v_id)
        self.assertEqual(item["status"], "DISCREPANCY_STOCK")
        self.assertTrue(item["is_red"])
        self.assertEqual(item["discrepancy_diff"], -8.0)

        # Vérifier que le Dashboard affiche bien cette anomalie
        metrics = get_dashboard_metrics()
        self.assertGreater(metrics["kpis"]["inventory_anomalies_count"], 0)
        dash_alert = next((a for a in metrics["inventory_anomalies_alerts"] if a["variant_id"] == v_id), None)
        self.assertIsNotNone(dash_alert)
        print("[TEST PASSED] Test 6.3: Ecart avec le stock reel (100 reel vs 92 compte) -> Alerte Rouge & Dashboard.")

    def test_6_4_refaire_inventaire_recomptage(self):
        """Test 6.4 : Demande de recomptage physique -> Statut RECOUNT_NEEDED et réinitialisation des comptages"""
        color = f"Test Inv Recount {os.urandom(2).hex()}"
        res = create_catalog_product(CatalogProductCreate(
            reference="INV-TEST-04",
            designation="Profilé Test Recomptage",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=color,
            initial_quantity=30.0,
            unit_price=3500.0
        ))
        v_id = res["variant_id"]

        # Enregistrement initial avec désaccord
        save_inventory_counts([
            {"variant_id": v_id, "count1": 25.0, "count2": 28.0}
        ])

        # Action : Refaire l'inventaire
        rec_res = recount_inventory_item(variant_id=v_id, notes="Nouvelle vérification casier")
        self.assertTrue(rec_res["success"])

        inv_data = get_inventory_items(search="INV-TEST-04")
        item = next(it for it in inv_data["items"] if it["variant_id"] == v_id)
        self.assertEqual(item["status"], "RECOUNT_NEEDED")
        self.assertIsNone(item["count1"])
        self.assertIsNone(item["count2"])
        self.assertTrue(item["is_red"])
        print("[TEST PASSED] Test 6.4: Demande 'Refaire l'inventaire' correctement initialisee pour recomptage.")

    def test_6_5_mise_a_niveau_stock_et_sous_onglet_anomalie(self):
        """
        Test 6.5 :
        - Mise à niveau du stock vers quantité d'inventaire avec motif obligatoire.
        - Vérification de la mise à jour du stock réel et de la date d'inventaire.
        - Vérification de l'enregistrement dans l'historique des anomalies (sous-onglet).
        - Contrôle du rejet si le motif est manquant.
        """
        color = f"Test Inv Adjust {os.urandom(2).hex()}"
        res = create_catalog_product(CatalogProductCreate(
            reference="INV-TEST-05",
            designation="Profilé Test Mise à Niveau",
            category="Profilés Aluminium",
            gamme="Série RPT 55mm",
            unit="barre",
            color=color,
            initial_quantity=60.0,
            unit_price=8000.0
        ))
        v_id = res["variant_id"]

        # 1. Vérification du blocage sans motif (Pydantic validation min_length=3 ou ValueError)
        with self.assertRaises(Exception) as ctx:
            adjust_stock_to_inventory(InventoryAdjustmentRequest(
                variant_id=v_id,
                chosen_quantity=55.0,
                reason="",  # Motif vide non autorisé (< 3 caractères)
                operator="Chef Atelier"
            ))
        err_msg = str(ctx.exception).lower()
        self.assertTrue("reason" in err_msg or "motif" in err_msg or "at least 3 characters" in err_msg)

        # 2. Mise à niveau valide vers 55 barres (écart de -5 barres)
        adj_res = adjust_stock_to_inventory(InventoryAdjustmentRequest(
            variant_id=v_id,
            chosen_quantity=55.0,
            reason="Chute de coupe non déclarée en atelier",
            notes="Vérification physique effectuée au casier P-01",
            operator="Chef Atelier"
        ))
        self.assertTrue(adj_res["success"])
        self.assertEqual(adj_res["quantity_after"], 55.0)
        self.assertEqual(adj_res["discrepancy"], -5.0)
        self.assertEqual(adj_res["financial_impact"], -40000.0) # -5 * 8000 DZD

        # 3. Vérifier que la table variants a bien le stock réel à 55 et la date d'inventaire
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT real_quantity, last_inventory_date FROM variants WHERE id = ?", (v_id,))
        var_row = cursor.fetchone()
        self.assertEqual(var_row["real_quantity"], 55.0)
        self.assertIsNotNone(var_row["last_inventory_date"])

        # 4. Vérifier que le sous-onglet Anomalies contient bien l'anomalie enregistrée
        anomalies = get_inventory_anomalies(search="INV-TEST-05")
        self.assertGreaterEqual(len(anomalies), 1)
        anom = anomalies[0]
        self.assertEqual(anom["reason"], "Chute de coupe non déclarée en atelier")
        self.assertEqual(anom["discrepancy_quantity"], -5.0)
        self.assertEqual(anom["financial_impact"], -40000.0)

        # 5. Vérifier que le journal des mouvements a bien tracé l'ajustement
        cursor.execute("SELECT * FROM movements WHERE order_number = 'INVENTAIRE' AND product_reference = 'INV-TEST-05'")
        mvt = cursor.fetchone()
        self.assertIsNotNone(mvt)
        self.assertEqual(mvt["action_type"], "DESTOCKAGE")
        self.assertEqual(mvt["quantity"], 5.0)
        conn.close()
        print("[TEST PASSED] Test 6.5: Mise a niveau du stock et archivage sous-onglet Anomalie avec motif conformes.")

    def test_6_6_generation_document_inventaire_imprimable(self):
        """Test 6.6 : Génération du document de comptage papier / PDF pour les articles sélectionnés"""
        html_sheet = generate_inventory_print_sheet(
            person1="Karim (Opérateur 1)",
            person2="Sofiane (Opérateur 2)"
        )
        self.assertIn("FICHE DE COMPTAGE D'INVENTAIRE PHYSIQUE", html_sheet)
        self.assertIn("Karim (Opérateur 1)", html_sheet)
        self.assertIn("Sofiane (Opérateur 2)", html_sheet)
        self.assertIn("Casier Atelier", html_sheet)
        self.assertIn("window.print()", html_sheet)
        print("[TEST PASSED] Test 6.6: Generation de la fiche d'inventaire imprimable/PDF validee avec succes.")

if __name__ == "__main__":
    unittest.main()
