ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS google_subject VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_google_subject
  ON usuarios(google_subject)
  WHERE google_subject IS NOT NULL;

ALTER TABLE cadastros_pendentes
  ADD COLUMN IF NOT EXISTS google_subject VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cadastros_pendentes_google_subject
  ON cadastros_pendentes(google_subject)
  WHERE google_subject IS NOT NULL AND usuario_id IS NULL;
