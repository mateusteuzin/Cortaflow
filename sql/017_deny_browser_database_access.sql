-- The FastAPI backend authenticates tenants and uses a trusted database role.
-- Browser Supabase roles must not access these private tables directly.
-- Run using the table owner. Verify DATABASE_URL uses an owner/BYPASSRLS role
-- before applying: this does not introduce backend tenant RLS policies.
BEGIN;
DO $$
DECLARE
    table_name text;
    browser_role text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'usuarios', 'barbearias', 'cadastros_pendentes', 'stripe_webhook_events',
        'barbeiros', 'horarios_funcionamento', 'agendamentos', 'notificacoes_email',
        'clientes', 'produtos', 'servicos', 'vendas_produto', 'despesas',
        'fidelidade_cliente', 'pagamentos', 'push_subscriptions'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=browser_role) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', table_name, browser_role);
            END IF;
        END LOOP;
    END LOOP;
END $$;
COMMIT;
