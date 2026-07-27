CREATE TABLE IF NOT EXISTS cadastros_pendentes (
  id SERIAL PRIMARY KEY,
  email VARCHAR(160) UNIQUE NOT NULL,
  senha_hash TEXT NOT NULL,
  nome VARCHAR(120) NOT NULL,
  telefone VARCHAR(30),
  barbearia_nome VARCHAR(160) NOT NULL,
  plano VARCHAR(24) NOT NULL CHECK (plano IN ('essencial', 'profissional', 'premium')),
  email_verificado BOOLEAN NOT NULL DEFAULT FALSE,
  email_verification_token_hash VARCHAR(64),
  email_verification_expires_at TIMESTAMPTZ,
  checkout_token_hash VARCHAR(64),
  checkout_token_expires_at TIMESTAMPTZ,
  stripe_checkout_session_id VARCHAR(160),
  usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
  concluido_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cadastros_pendentes_email_token
  ON cadastros_pendentes(email_verification_token_hash)
  WHERE email_verification_token_hash IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cadastros_pendentes_checkout_token
  ON cadastros_pendentes(checkout_token_hash)
  WHERE checkout_token_hash IS NOT NULL;
