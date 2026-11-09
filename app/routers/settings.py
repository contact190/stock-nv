from fastapi import APIRouter, HTTPException
from typing import Optional
from app.models import CategoryModel, GammeModel, UnitModel, WorkshopCaseModel, ColorModel
from app.database import get_db
from app.supabase_sync import (
    is_supabase_enabled,
    sync_category_to_cloud,
    sync_gamme_to_cloud,
    sync_unit_to_cloud,
    sync_workshop_case_to_cloud,
    sync_color_to_cloud,
    pull_all_from_supabase_to_sqlite
)

router = APIRouter(prefix="/api/settings", tags=["Paramètres"])

@router.get("/cloud-status")
def get_cloud_status():
    """Vérifie l'état de la synchronisation Supabase Cloud."""
    enabled = is_supabase_enabled()
    return {
        "cloud_enabled": enabled,
        "provider": "Supabase PostgreSQL Cloud" if enabled else "Local SQLite Only",
        "status": "CONNECTÉ" if enabled else "DÉCONNECTÉ"
    }

@router.post("/cloud-pull")
def trigger_cloud_pull():
    """Force le rechargement des données depuis Supabase Cloud."""
    pull_all_from_supabase_to_sqlite()
    return {"success": True, "message": "Synchronisation cloud terminée avec succès."}

@router.get("/all")
def get_all_settings():
    """Récupère l'ensemble des listes de paramètres (catégories, gammes, unités, cases atelier, couleurs)."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, description FROM categories ORDER BY name ASC")
    categories = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name, description FROM gammes ORDER BY name ASC")
    gammes = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name, symbol FROM units ORDER BY name ASC")
    units = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, type, code, description FROM workshop_cases ORDER BY type DESC, code ASC")
    cases = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name, ral_code, hex_code FROM colors ORDER BY id ASC")
    colors = [dict(r) for r in cursor.fetchall()]

    # Emplacements et fournisseurs distincts
    cursor.execute("SELECT DISTINCT location FROM variants WHERE location IS NOT NULL AND location != '' UNION SELECT DISTINCT location FROM products")
    locations = [r[0] for r in cursor.fetchall() if r[0]]

    cursor.execute("SELECT DISTINCT supplier FROM variants WHERE supplier IS NOT NULL AND supplier != '' UNION SELECT DISTINCT supplier FROM products")
    suppliers = [r[0] for r in cursor.fetchall() if r[0]]

    conn.close()
    return {
        "categories": categories,
        "gammes": gammes,
        "units": units,
        "cases": cases,
        "colors": colors,
        "locations": locations,
        "suppliers": suppliers
    }

# --- Cases Atelier (P-N° profilés et A-N° accessoires) ---
@router.get("/cases")
def list_workshop_cases():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, code, description FROM workshop_cases ORDER BY type DESC, code ASC")
    cases = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return cases

@router.post("/cases")
def add_workshop_case(data: WorkshopCaseModel):
    conn = get_db()
    cursor = conn.cursor()
    clean_type = data.type.strip().upper()
    if clean_type not in ("PROFILE", "ACCESSOIRE"):
        conn.close()
        raise HTTPException(status_code=400, detail="Type invalide. Choisissez 'PROFILE' ou 'ACCESSOIRE'.")

    raw_num = data.number.strip().upper()
    if clean_type == "PROFILE":
        code = raw_num if raw_num.startswith("P-") else f"P-{raw_num}"
    else:
        code = raw_num if raw_num.startswith("A-") else f"A-{raw_num}"

    try:
        cursor.execute("INSERT INTO workshop_cases (type, code, description) VALUES (?, ?, ?)",
                       (clean_type, code, data.description.strip() if data.description else None))
        case_id = cursor.lastrowid
        conn.commit()
        conn.close()
        try:
            sync_workshop_case_to_cloud(clean_type, code, data.description.strip() if data.description else "")
        except Exception:
            pass
        return {"success": True, "id": case_id, "type": clean_type, "code": code}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail=f"La case '{code}' existe déjà.")

@router.delete("/cases/{case_id}")
def delete_workshop_case(case_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM workshop_cases WHERE id = ?", (case_id,))
    row = cursor.fetchone()
    case_code = row["code"] if row else None

    cursor.execute("DELETE FROM workshop_cases WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

    if case_code:
        try:
            sync_workshop_case_to_cloud("", case_code, delete=True)
        except Exception:
            pass
    return {"success": True, "message": "Case atelier supprimée"}


# --- Catégories ---
@router.post("/categories")
def add_category(data: CategoryModel):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (data.name.strip(), data.description))
        cat_id = cursor.lastrowid
        conn.commit()
        conn.close()
        try:
            sync_category_to_cloud(data.name.strip(), data.description or "")
        except Exception:
            pass
        return {"success": True, "id": cat_id, "name": data.name}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Cette catégorie existe déjà.")

@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
    row = cursor.fetchone()
    cat_name = row["name"] if row else None

    cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()

    if cat_name:
        try:
            sync_category_to_cloud(cat_name, delete=True)
        except Exception:
            pass
    return {"success": True, "message": "Catégorie supprimée"}

# --- Gammes ---
@router.post("/gammes")
def add_gamme(data: GammeModel):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO gammes (name, description) VALUES (?, ?)", (data.name.strip(), data.description))
        g_id = cursor.lastrowid
        conn.commit()
        conn.close()
        try:
            sync_gamme_to_cloud(data.name.strip(), data.description or "")
        except Exception:
            pass
        return {"success": True, "id": g_id, "name": data.name}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Cette gamme existe déjà.")

@router.delete("/gammes/{gamme_id}")
def delete_gamme(gamme_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM gammes WHERE id = ?", (gamme_id,))
    row = cursor.fetchone()
    gamme_name = row["name"] if row else None

    cursor.execute("DELETE FROM gammes WHERE id = ?", (gamme_id,))
    conn.commit()
    conn.close()

    if gamme_name:
        try:
            sync_gamme_to_cloud(gamme_name, delete=True)
        except Exception:
            pass
    return {"success": True, "message": "Gamme supprimée"}

# --- Unités ---
@router.post("/units")
def add_unit(data: UnitModel):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO units (name, symbol) VALUES (?, ?)", (data.name.strip(), data.symbol.strip()))
        u_id = cursor.lastrowid
        conn.commit()
        conn.close()
        try:
            sync_unit_to_cloud(data.name.strip(), data.symbol.strip())
        except Exception:
            pass
        return {"success": True, "id": u_id, "name": data.name, "symbol": data.symbol}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Cette unité existe déjà.")

@router.delete("/units/{unit_id}")
def delete_unit(unit_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM units WHERE id = ?", (unit_id,))
    row = cursor.fetchone()
    unit_name = row["name"] if row else None

    cursor.execute("DELETE FROM units WHERE id = ?", (unit_id,))
    conn.commit()
    conn.close()

    if unit_name:
        try:
            sync_unit_to_cloud(unit_name, delete=True)
        except Exception:
            pass
    return {"success": True, "message": "Unité supprimée"}

# --- Nuancier & Couleurs RAL ---
@router.get("/colors")
def list_colors():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, ral_code, hex_code FROM colors ORDER BY id ASC")
    colors = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return colors

@router.post("/colors")
def add_color(data: ColorModel):
    conn = get_db()
    cursor = conn.cursor()
    clean_name = data.name.strip()
    clean_ral = data.ral_code.strip() if data.ral_code else ""
    clean_hex = data.hex_code.strip() if data.hex_code else "#474a51"
    try:
        cursor.execute("INSERT INTO colors (name, ral_code, hex_code) VALUES (?, ?, ?)",
                       (clean_name, clean_ral, clean_hex))
        c_id = cursor.lastrowid
        conn.commit()
        conn.close()
        try:
            sync_color_to_cloud(clean_name, clean_ral, clean_hex)
        except Exception:
            pass
        return {"success": True, "id": c_id, "name": clean_name, "ral_code": clean_ral, "hex_code": clean_hex}
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail=f"La couleur '{clean_name}' existe déjà.")

@router.delete("/colors/{color_id}")
def delete_color(color_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM colors WHERE id = ?", (color_id,))
    row = cursor.fetchone()
    color_name = row["name"] if row else None

    cursor.execute("DELETE FROM colors WHERE id = ?", (color_id,))
    conn.commit()
    conn.close()

    if color_name:
        try:
            sync_color_to_cloud(color_name, delete=True)
        except Exception:
            pass
    return {"success": True, "message": "Couleur supprimée"}

# --- Réinitialisation Démo ---
@router.post("/reset-demo")
def reset_demo_data():
    from app.database import init_db
    init_db()
    return {"success": True, "message": "Base de données réinitialisée aux données menuiserie aluminium / volets avec succès."}

