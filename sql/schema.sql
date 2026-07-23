CREATE TABLE IF NOT EXISTS usuarios (
 id SERIAL PRIMARY KEY, email VARCHAR(160) UNIQUE NOT NULL, senha_hash TEXT NOT NULL,
 nome VARCHAR(120) NOT NULL, telefone VARCHAR(30), email_verificado BOOLEAN NOT NULL DEFAULT FALSE,
 email_verification_token_hash VARCHAR(64), email_verification_expires_at TIMESTAMPTZ,
 criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS barbearias (
 id SERIAL PRIMARY KEY, usuario_id INTEGER UNIQUE NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
 nome VARCHAR(160) NOT NULL, slug VARCHAR(160) UNIQUE NOT NULL, telefone VARCHAR(30), endereco TEXT, cnpj VARCHAR(24), logo_url TEXT,
 email_notificacoes VARCHAR(254), notificar_novos_agendamentos BOOLEAN NOT NULL DEFAULT TRUE,
 public_booking_enabled BOOLEAN NOT NULL DEFAULT TRUE,
 plano_ativo BOOLEAN DEFAULT TRUE, data_assinatura DATE DEFAULT CURRENT_DATE,
 subscription_plan VARCHAR(24), subscription_status VARCHAR(24) NOT NULL DEFAULT 'active',
 stripe_customer_id VARCHAR(120), stripe_subscription_id VARCHAR(120),
 subscription_current_period_end TIMESTAMPTZ,
 subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
 criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS barbeiros (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 nome VARCHAR(120) NOT NULL, telefone VARCHAR(30), comissao_percentual NUMERIC(5,2) DEFAULT 40,
 foto_url TEXT, ativo BOOLEAN DEFAULT TRUE, criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS horarios_funcionamento (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6), hora_inicio TIME NOT NULL, hora_fim TIME NOT NULL,
 UNIQUE(barbearia_id, dia_semana));
CREATE TABLE IF NOT EXISTS agendamentos (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 barbeiro_id INTEGER NOT NULL REFERENCES barbeiros(id), servico_id INTEGER, cliente_nome VARCHAR(120) NOT NULL,
 cliente_telefone VARCHAR(30), cliente_email VARCHAR(254), data_hora TIMESTAMP NOT NULL, duracao_minutos INTEGER DEFAULT 30,
 servico VARCHAR(100) DEFAULT 'Corte', preco NUMERIC(10,2) NOT NULL DEFAULT 45,
 status VARCHAR(20) DEFAULT 'agendado' CHECK(status IN ('agendado','confirmado','em_andamento','concluido','realizado','cancelado','nao_compareceu')),
 pago_em TIMESTAMPTZ, criado_em TIMESTAMPTZ DEFAULT NOW(), atualizado_em TIMESTAMPTZ DEFAULT NOW(), concluido_em TIMESTAMPTZ,
 whatsapp_autorizado BOOLEAN NOT NULL DEFAULT FALSE,
 whatsapp_enviado BOOLEAN NOT NULL DEFAULT FALSE,
 whatsapp_enviado_em TIMESTAMPTZ, whatsapp_message_id TEXT,
 whatsapp_status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE', whatsapp_erro TEXT,
 whatsapp_tentativas INTEGER NOT NULL DEFAULT 0,
 whatsapp_proxima_tentativa TIMESTAMPTZ DEFAULT NOW(), whatsapp_telefone VARCHAR(20),
 email_enviado BOOLEAN NOT NULL DEFAULT FALSE, email_enviado_em TIMESTAMPTZ,
 email_message_id TEXT, email_erro TEXT, email_dono_enviado BOOLEAN NOT NULL DEFAULT FALSE,
 email_dono_message_id TEXT, email_dono_erro TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS agenda_slot_ativo ON agendamentos(barbeiro_id, data_hora) WHERE status <> 'cancelado';
CREATE INDEX IF NOT EXISTS idx_agenda_whatsapp_fila ON agendamentos(whatsapp_status,whatsapp_proxima_tentativa) WHERE whatsapp_autorizado AND NOT whatsapp_enviado;
CREATE TABLE IF NOT EXISTS produtos (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 nome VARCHAR(120) NOT NULL, preco NUMERIC(10,2) NOT NULL, quantidade_estoque INTEGER DEFAULT 0, criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS servicos (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 nome VARCHAR(120) NOT NULL, descricao VARCHAR(240), duracao_minutos INTEGER NOT NULL DEFAULT 30 CHECK(duracao_minutos BETWEEN 10 AND 480),
 preco NUMERIC(10,2) NOT NULL CHECK(preco >= 0), imagem_url TEXT,
 ativo BOOLEAN DEFAULT TRUE, criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS vendas_produto (
 id SERIAL PRIMARY KEY, agendamento_id INTEGER NOT NULL REFERENCES agendamentos(id), produto_id INTEGER NOT NULL REFERENCES produtos(id),
 quantidade INTEGER NOT NULL CHECK(quantidade > 0), preco_unitario NUMERIC(10,2) NOT NULL, criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS fidelidade_cliente (
 id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
 cliente_telefone VARCHAR(30), cliente_nome VARCHAR(120), total_cortes INTEGER DEFAULT 0, criado_em TIMESTAMPTZ DEFAULT NOW(),
 UNIQUE(barbearia_id, cliente_telefone));
CREATE TABLE IF NOT EXISTS pagamentos (
 id SERIAL PRIMARY KEY, agendamento_id INTEGER NOT NULL REFERENCES agendamentos(id), valor NUMERIC(10,2) NOT NULL,
 status VARCHAR(20) DEFAULT 'pendente', chave_pix VARCHAR(160), referencia VARCHAR(80) UNIQUE NOT NULL, criado_em TIMESTAMPTZ DEFAULT NOW());
CREATE INDEX IF NOT EXISTS idx_agenda_data ON agendamentos(barbearia_id, data_hora);
