BEGIN;

CREATE EXTENSION IF NOT EXISTS unaccent;

ALTER TABLE barbearias
  ADD COLUMN IF NOT EXISTS slug VARCHAR(160),
  ADD COLUMN IF NOT EXISTS public_booking_enabled BOOLEAN NOT NULL DEFAULT TRUE;

DO $$
DECLARE
  shop RECORD;
  base_slug TEXT;
  candidate TEXT;
  suffix INTEGER;
BEGIN
  FOR shop IN SELECT id, nome FROM barbearias WHERE slug IS NULL OR btrim(slug) = '' ORDER BY id LOOP
    base_slug := trim(BOTH '-' FROM regexp_replace(lower(unaccent(shop.nome)), '[^a-z0-9]+', '-', 'g'));
    IF base_slug = '' THEN base_slug := 'barbearia'; END IF;
    base_slug := left(base_slug, 140);
    candidate := base_slug;
    suffix := 2;
    WHILE EXISTS (SELECT 1 FROM barbearias WHERE slug = candidate AND id <> shop.id) LOOP
      candidate := left(base_slug, 140 - length(suffix::text) - 1) || '-' || suffix;
      suffix := suffix + 1;
    END LOOP;
    UPDATE barbearias SET slug = candidate WHERE id = shop.id;
  END LOOP;
END $$;

ALTER TABLE barbearias ALTER COLUMN slug SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS barbearias_slug_unique ON barbearias(slug);

COMMIT;
