# StockMaster Alu — Gestion de Stock Menuiserie Aluminium & Volets (DZD)

Solution Full-Stack industrielle de gestion de stock pour la menuiserie aluminium et volets roulants, conçue avec **FastAPI (Python)**, **SQLite optimisé** et une interface **Mobile-First** (Tailwind CSS, JsBarcode, Chart.js, Lucide).

---

## 🚫 Règles Métier & Directives Négatives Implémentées

1. **Interdiction des Références Doublons :**
   - Clé unique `[Référence + Couleur]` en base.
   - Toute tentative de créer un profilé déjà existant au Catalogue Maître est formellement bloquée avec un message d'erreur clair.
2. **Interdiction des Mouvements Orphelins :**
   - L'entrée en stock se fait obligatoirement par sélection sur un article existant du Catalogue Maître.
3. **Traçabilité & Alerte Stock Anonyme :**
   - Menus déroulants pour **Chantier / Projet** et **Opérateur / Poseur**.
   - Si une sortie est effectuée sans chantier ni poseur, elle n'est pas bloquée mais déclenche une **bannière d'alerte visuelle**, est enregistrée sous le libellé `STOCK_GENERAL` et tracée avec un flag d'alerte dans le journal.
4. **Interdiction du Stock Négatif Non Contrôlé :**
   - Déstockage strictement plafonné à la Quantité Réelle physiquement présente en atelier.
5. **Méthode Obligatoire du PMP (Prix Moyen Pondéré) :**
   - Remplacement de la moyenne arithmétique simple et du prix médian par la formule stricte du PMP :
     $$\text{Nouveau PMP} = \frac{(\text{Stock Existant} \times \text{PMP Actuel}) + (\text{Qté Entrante} \times \text{Prix d'Achat})}{\text{Stock Existant} + \text{Qté Entrante}}$$
6. **Optimisation & Indexation SQL ($\le 200\text{ ms}$) :**
   - Index composites sur `[product_reference, color]`, `[action_type, order_number, timestamp]`, etc.

---

## 🌟 Les 4 Évolutions Appliquées

1. **Emplacement par Défaut (`EN_ATTENTE_AFFECTATION`) :**
   - Si aucun casier n'est renseigné lors de l'entrée ou de la création, l'article reçoit automatiquement `'EN_ATTENTE_AFFECTATION'` et lève une alerte d'inventaire dans le Dashboard.
2. **Contrôle du Prix d'Achat à 0 DZD :**
   - Si le prix d'achat est égal à 0 ou non renseigné, l'application demande une confirmation explicite pour autoriser le don ou coût nul.
3. **Spécificités Menuiserie Aluminium / Volets & Devise DZD :**
   - Profilés alu RPT (`HPS-40`, `OUV-ALU-55`), lames de volets extrudées (`EX-2001`, `LAM-VR-55`), coulisses (`GLIS-VR-45`).
   - Prix et valorisations exprimés en **DZD (Dinars Algériens)**.
4. **Code-Barres Local (JsBarcode) :**
   - Génération locale et autonome d'étiquettes code-barres (Code 128) pour chaque profilé, avec visualisation et impression sans dépendance à une API externe.
5. **Inventaire Physique Croisé (Double Comptage 2 Personnes & Anomalies) :**
   - Déclinaison complète de chaque référence par couleur (`[Référence + Couleur]`).
   - Saisie séparée pour deux opérateurs (Personne 1 et Personne 2) avec barre de recherche et sélection ciblée.
   - Mise en **rouge vif** automatique en cas de désaccord entre les deux personnes OU d'écart avec le stock réel.
   - Intégration Dashboard pour **refaire l'inventaire (recomptage)** ou **mettre à niveau le stock**.
   - **Sous-onglet Anomalies** archivant tous les écarts régularisés avec motif obligatoire (casse, chute non déclarée, perte) et impact financier en DZD.

---

## 🧪 Exécution de la Suite de Tests QA Automatisée

Pour lancer l'ensemble des 21 tests unitaires et scénarios limites :
```bash
python -m unittest tests/test_qa_scenarios.py
```

### Scénarios validés :
- `Test 1.1` : Contrôle du prix à 0 DZD.
- `Test 1.2` : Rejet des doublons `[Ref + Couleur]` au catalogue.
- `Test 1.3` : Attribution et alerte de l'emplacement `EN_ATTENTE_AFFECTATION`.
- `Test 2.1` : Cycle Réservation (Physique 100 / Dispo 60) puis Déstockage (Physique 60).
- `Test 2.2` : Blocage strict du stock négatif.
- `Test 2.3` : Alerte traçabilité pour sortie en Stock Général.
- `Test 3.1` : Filtre combiné par chantiers (SIBAWI + GAEA) calculé au centime près.
- `Test 3.2` : Déclenchement instantané des alertes de seuil (14 barres pour seuil de 15).
- `Test 4.1` : Précision mathématique de la formule du PMP.
- `Test 5.1 à 5.7` : Déstockage/réservation par lot et en batch.
- `Test 6.1` : Double comptage conforme (Pers 1 == Pers 2 == Réel).
- `Test 6.2` : Détection immédiate du désaccord (Pers 1 != Pers 2) -> Alerte Rouge.
- `Test 6.3` : Détection de l'écart avec le stock réel -> Alerte Rouge & Dashboard.
- `Test 6.4` : Réinitialisation et demande de recomptage (Refaire l'inventaire).
- `Test 6.5` : Mise à niveau vers quantité d'inventaire avec motif obligatoire et archivage au sous-onglet Anomalies.

---

## 🚀 Démarrage de l'Application

Double-cliquez sur **`run.bat`** ou exécutez :
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Puis accédez à : **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
