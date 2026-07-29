CREATE TABLE IF NOT EXISTS push_subscriptions (
  id BIGSERIAL PRIMARY KEY,
  barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  barbeiro_id INTEGER REFERENCES barbeiros(id) ON DELETE CASCADE,
  endpoint TEXT UNIQUE NOT NULL,
  p256dh VARCHAR(512) NOT NULL,
  auth VARCHAR(256) NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ultimo_envio_em TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_destino
  ON push_subscriptions(barbearia_id,barbeiro_id) WHERE ativo;
