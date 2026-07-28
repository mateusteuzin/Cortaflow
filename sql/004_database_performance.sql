BEGIN;

CREATE INDEX IF NOT EXISTS idx_agenda_barbearia_barbeiro_data_ativa
  ON agendamentos(barbearia_id, barbeiro_id, data_hora)
  WHERE status <> 'cancelado';

CREATE INDEX IF NOT EXISTS idx_agenda_barbearia_status_data
  ON agendamentos(barbearia_id, status, data_hora);

CREATE INDEX IF NOT EXISTS idx_clientes_barbearia_atualizado
  ON clientes(barbearia_id, atualizado_em DESC);

CREATE INDEX IF NOT EXISTS idx_barbeiros_barbearia_ativos
  ON barbeiros(barbearia_id, nome)
  WHERE ativo;

CREATE INDEX IF NOT EXISTS idx_servicos_barbearia_ativos
  ON servicos(barbearia_id, nome)
  WHERE ativo;

CREATE INDEX IF NOT EXISTS idx_vendas_produto_agendamento
  ON vendas_produto(agendamento_id);

CREATE INDEX IF NOT EXISTS idx_pagamentos_agendamento
  ON pagamentos(agendamento_id);

COMMIT;
