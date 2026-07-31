-- Impede reutilização do session_id de Checkout como credencial de bootstrap.
ALTER TABLE cadastros_pendentes
  ADD COLUMN IF NOT EXISTS checkout_login_consumed_at TIMESTAMPTZ;
