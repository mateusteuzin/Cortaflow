BEGIN;

-- Relatorios financeiros percorrem somente atendimentos finalizados no periodo.
CREATE INDEX IF NOT EXISTS idx_agenda_relatorios_finalizados
  ON agendamentos(barbearia_id, data_hora)
  INCLUDE (barbeiro_id, preco)
  WHERE status IN ('concluido', 'realizado');

-- A tela de clientes procura o proximo horario por telefone para cada cliente.
CREATE INDEX IF NOT EXISTS idx_agenda_cliente_proximo
  ON agendamentos(barbearia_id, cliente_telefone, data_hora)
  INCLUDE (barbeiro_id, servico, whatsapp_status)
  WHERE status IN ('agendado', 'confirmado', 'em_andamento');

CREATE INDEX IF NOT EXISTS idx_produtos_barbearia_nome
  ON produtos(barbearia_id, nome);

CREATE INDEX IF NOT EXISTS idx_fidelidade_barbearia_total
  ON fidelidade_cliente(barbearia_id, total_cortes DESC);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_usuario_ativo
  ON push_subscriptions(usuario_id, barbearia_id)
  WHERE ativo;

-- Atualiza as estatisticas usadas pelo planejador depois de criar os indices.
ANALYZE agendamentos;
ANALYZE clientes;
ANALYZE produtos;
ANALYZE fidelidade_cliente;
ANALYZE push_subscriptions;

COMMIT;
