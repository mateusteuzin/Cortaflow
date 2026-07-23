ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS email_login_token_hash VARCHAR(64),
  ADD COLUMN IF NOT EXISTS email_login_expires_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_login_token
  ON usuarios(email_login_token_hash)
  WHERE email_login_token_hash IS NOT NULL;
