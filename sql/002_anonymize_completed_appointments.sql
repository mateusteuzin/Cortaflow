BEGIN;

ALTER TABLE agendamentos
  ALTER COLUMN cliente_telefone DROP NOT NULL;

ALTER TABLE fidelidade_cliente
  ALTER COLUMN cliente_telefone DROP NOT NULL;

ALTER TABLE agendamentos
  ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS concluido_em TIMESTAMPTZ;

ALTER TABLE agendamentos
  DROP CONSTRAINT IF EXISTS agendamentos_status_check;

ALTER TABLE agendamentos
  ADD CONSTRAINT agendamentos_status_check
  CHECK(status IN (
    'agendado','confirmado','em_andamento','concluido',
    'realizado','cancelado','nao_compareceu'
  ));

COMMIT;
