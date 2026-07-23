ALTER TABLE barbearias
  ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(24),
  ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(24) NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(120),
  ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(120),
  ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_barbearias_stripe_customer
  ON barbearias(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_barbearias_stripe_subscription
  ON barbearias(stripe_subscription_id)
  WHERE stripe_subscription_id IS NOT NULL;

UPDATE barbearias
SET subscription_status = CASE WHEN plano_ativo THEN 'active' ELSE 'inactive' END
WHERE subscription_status IS NULL OR subscription_status = '';
