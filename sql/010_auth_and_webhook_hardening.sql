ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE cadastros_pendentes
  ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending_email',
  ADD COLUMN IF NOT EXISTS checkout_idempotency_key VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_cadastros_pendentes_status
  ON cadastros_pendentes(status)
  WHERE usuario_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cadastros_pendentes_checkout_session
  ON cadastros_pendentes(stripe_checkout_session_id)
  WHERE stripe_checkout_session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  event_id VARCHAR(255) PRIMARY KEY,
  event_type VARCHAR(120) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'processing',
  attempts INTEGER NOT NULL DEFAULT 1,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

UPDATE cadastros_pendentes
SET status = CASE
  WHEN usuario_id IS NOT NULL THEN 'paid'
  WHEN stripe_checkout_session_id IS NOT NULL THEN 'checkout_created'
  WHEN email_verificado THEN 'email_verified'
  ELSE 'pending_email'
END
WHERE status IS NULL
   OR status NOT IN (
     'pending_email', 'email_verified', 'checkout_created', 'paid',
     'payment_failed', 'checkout_expired'
   );
