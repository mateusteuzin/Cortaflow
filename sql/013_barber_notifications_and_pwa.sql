ALTER TABLE barbeiros
  ADD COLUMN IF NOT EXISTS notification_email VARCHAR(254),
  ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(30) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS cargo VARCHAR(80) NOT NULL DEFAULT 'Barbeiro',
  ADD COLUMN IF NOT EXISTS usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_barbeiros_usuario
  ON barbeiros(usuario_id) WHERE usuario_id IS NOT NULL;

ALTER TABLE agendamentos
  ADD COLUMN IF NOT EXISTS observacoes VARCHAR(500) NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS notificacoes_email (
  id BIGSERIAL PRIMARY KEY,
  agendamento_id INTEGER NOT NULL REFERENCES agendamentos(id) ON DELETE CASCADE,
  barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
  barbeiro_id INTEGER REFERENCES barbeiros(id) ON DELETE SET NULL,
  evento VARCHAR(24) NOT NULL CHECK(evento IN ('novo','reagendado','cancelado')),
  event_key VARCHAR(80) NOT NULL,
  destinatario VARCHAR(254) NOT NULL,
  origem_destinatario VARCHAR(20) NOT NULL CHECK(origem_destinatario IN ('barbeiro','administrativo')),
  status VARCHAR(20) NOT NULL DEFAULT 'processando'
    CHECK(status IN ('processando','enviado','erro')),
  resend_message_id TEXT,
  erro VARCHAR(500),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  enviado_em TIMESTAMPTZ,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(agendamento_id, evento, event_key, destinatario)
);

CREATE INDEX IF NOT EXISTS idx_notificacoes_email_agendamento
  ON notificacoes_email(agendamento_id, criado_em DESC);
