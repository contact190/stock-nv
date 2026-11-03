-- =============================================================================
-- STOCKMASTER ALU - SCHÉMA POSTGRESQL OPTIMISÉ POUR SUPABASE CLOUD
-- Conforme aux spécifications du skill : supabase-postgres-best-practices
-- Traçabilité Menuiserie Aluminium, PMP (DZD), RLS, Realtime & Sauvegardes
-- =============================================================================

-- Activation des extensions nécessaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Table des Catégories de Profilés & Accessoires
CREATE TABLE IF NOT EXISTS public.categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Table des Gammes / Séries (Série RPT 55mm, 40mm, Lames 45mm, etc.)
CREATE TABLE IF NOT EXISTS public.gammes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Table des Unités de Mesure
CREATE TABLE IF NOT EXISTS public.units (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Cases Atelier & Emplacements Physiques (P-xx profilés / A-xx accessoires)
CREATE TABLE IF NOT EXISTS public.workshop_cases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('PROFILE', 'ACCESSOIRE')),
    code TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Nuancier et Couleurs RAL Aluminium
CREATE TABLE IF NOT EXISTS public.colors (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    ral_code TEXT,
    hex_code TEXT DEFAULT '#474a51',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Catalogue Maître des Produits (Profilés & Volets)
CREATE TABLE IF NOT EXISTS public.products (
    reference TEXT PRIMARY KEY,
    designation TEXT NOT NULL,
    category TEXT NOT NULL,
    gamme TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'barre',
    image_url TEXT,
    threshold NUMERIC(12, 2) DEFAULT 10.00 NOT NULL,
    supplier TEXT DEFAULT '',
    location TEXT DEFAULT 'EN_ATTENTE_AFFECTATION' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 7. Variantes de Profilés par Teinte RAL avec Calcul PMP Strict
CREATE TABLE IF NOT EXISTS public.variants (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_reference TEXT NOT NULL REFERENCES public.products(reference) ON UPDATE CASCADE ON DELETE CASCADE,
    color TEXT NOT NULL,
    ral_code TEXT,
    color_hex TEXT DEFAULT '#64748b' NOT NULL,
    barcode TEXT,
    initial_quantity NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
    real_quantity NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
    reserved_quantity NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
    threshold NUMERIC(12, 2) DEFAULT 10.00 NOT NULL,
    current_price NUMERIC(14, 2) DEFAULT 0.00 NOT NULL,
    previous_price NUMERIC(14, 2) DEFAULT 0.00 NOT NULL,
    pmp NUMERIC(14, 2) DEFAULT 0.00 NOT NULL,
    supplier TEXT DEFAULT '',
    location TEXT DEFAULT 'EN_ATTENTE_AFFECTATION' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    -- Contrainte anti-doublon absolue [Référence + Couleur]
    CONSTRAINT unique_product_color UNIQUE (product_reference, color),
    -- Règle stricte anti-stock physique négatif
    CONSTRAINT check_real_qty_positive CHECK (real_quantity >= 0),
    CONSTRAINT check_reserved_qty_positive CHECK (reserved_quantity >= 0)
);

-- 8. Historique des Prix d'Achat & Calculs PMP
CREATE TABLE IF NOT EXISTS public.price_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    variant_id BIGINT NOT NULL REFERENCES public.variants(id) ON DELETE CASCADE,
    product_reference TEXT NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    pmp_after NUMERIC(14, 2) NOT NULL,
    quantity NUMERIC(12, 2) NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 9. Journal Chronologique des Mouvements (Traçabilité Totale)
CREATE TABLE IF NOT EXISTS public.movements (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('STOCKAGE', 'DESTOCKAGE', 'RESERVATION', 'LIBERATION')),
    product_reference TEXT NOT NULL,
    product_name TEXT NOT NULL,
    color TEXT NOT NULL,
    quantity NUMERIC(12, 2) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL,
    pmp_at_movement NUMERIC(14, 2) DEFAULT 0.00 NOT NULL,
    total_value NUMERIC(14, 2) NOT NULL,
    order_number TEXT DEFAULT 'STOCK_GENERAL',
    operator TEXT DEFAULT 'Atelier' NOT NULL,
    is_anonyme SMALLINT DEFAULT 0 NOT NULL,
    notes TEXT DEFAULT ''
);

-- 10. Commandes & Chantiers
CREATE TABLE IF NOT EXISTS public.orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number TEXT NOT NULL UNIQUE,
    client_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'EN_ATTENTE',
    notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 11. Articles Réservés / Déstockés par Commande
CREATE TABLE IF NOT EXISTS public.order_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    order_number TEXT NOT NULL,
    variant_id BIGINT NOT NULL REFERENCES public.variants(id) ON DELETE RESTRICT,
    product_reference TEXT NOT NULL,
    product_name TEXT NOT NULL,
    color TEXT NOT NULL,
    quantity_reserved NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
    quantity_destocked NUMERIC(12, 2) DEFAULT 0.00 NOT NULL,
    unit_price NUMERIC(14, 2) DEFAULT 0.00 NOT NULL,
    status TEXT DEFAULT 'RESERVED' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- =============================================================================
-- INDEX DE PERFORMANCE (selon les règles de supabase-postgres-best-practices)
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_variants_ref ON public.variants(product_reference);
CREATE INDEX IF NOT EXISTS idx_variants_location ON public.variants(location);
CREATE INDEX IF NOT EXISTS idx_variants_stock_alert ON public.variants(real_quantity, threshold);
CREATE INDEX IF NOT EXISTS idx_movements_timestamp ON public.movements(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_movements_order ON public.movements(order_number);
CREATE INDEX IF NOT EXISTS idx_movements_action ON public.movements(action_type);
CREATE INDEX IF NOT EXISTS idx_order_items_order_num ON public.order_items(order_number);
CREATE INDEX IF NOT EXISTS idx_order_items_variant ON public.order_items(variant_id);

-- =============================================================================
-- ACTIVATION DE SUPABASE REALTIME (Synchronisation instantanée multi-appareils)
-- Permet aux WebSockets de diffuser les changements aux PC, tablettes et téléphones
-- =============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE public.variants;
ALTER PUBLICATION supabase_realtime ADD TABLE public.movements;
ALTER PUBLICATION supabase_realtime ADD TABLE public.orders;
ALTER PUBLICATION supabase_realtime ADD TABLE public.order_items;

-- =============================================================================
-- POLITIQUES ROW-LEVEL SECURITY (RLS)
-- Protection des accès et exposition sécurisée à l'API Supabase
-- =============================================================================
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gammes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.units ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workshop_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.colors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;

-- Politiques d'accès complet pour l'application (anon & authenticated)
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('DROP POLICY IF EXISTS "Allow full access to %I" ON public.%I;', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow full access to %I" ON public.%I FOR ALL TO public USING (true) WITH CHECK (true);', tbl, tbl);
    END LOOP;
END
$$;

