-- Contas já existentes permanecem liberadas; somente novos cadastros exigem confirmação.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verificado BOOLEAN NOT NULL DEFAULT TRUE;
UPDATE usuarios SET email_verificado = TRUE WHERE email_verificado IS NULL;
ALTER TABLE usuarios ALTER COLUMN email_verificado SET DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verification_token_hash VARCHAR(64);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_verification_token_idx
  ON usuarios(email_verification_token_hash) WHERE email_verification_token_hash IS NOT NULL;
