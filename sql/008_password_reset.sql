ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS password_reset_token_hash VARCHAR(64),
  ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_password_reset_token
  ON usuarios(password_reset_token_hash)
  WHERE password_reset_token_hash IS NOT NULL;
