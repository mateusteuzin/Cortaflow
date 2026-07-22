# CortaFlow

Sistema web de gestão para barbearia com FastAPI, PostgreSQL e frontend HTML/CSS/JavaScript puro. Inclui autenticação JWT, agenda com bloqueio de conflito, barbeiros, produtos/estoque, relatórios, fidelidade e WhatsApp.

## Rodar com Docker (recomendado)

```powershell
docker compose up --build
```

Depois acesse:

- Painel do proprietário: http://localhost:8000
- Agendamento público: http://localhost:8000/cliente.html
- Documentação da API: http://localhost:8000/api/docs

No primeiro acesso, clique em **Crie sua conta**. A página pública encontra automaticamente a primeira barbearia ativa; em instalações com várias empresas, use `?barbearia=ID` para abrir uma agenda específica.

## Banco compartilhado com Supabase

O backend usa um projeto Supabase compartilhado. Para configurá-lo, siga o guia em [`docs/SUPABASE.md`](docs/SUPABASE.md). A `DATABASE_URL` fica apenas no backend e nunca deve ser adicionada ao Git.

## Rodar sem Docker

Configure primeiro o projeto Supabase conforme `docs/SUPABASE.md` e então:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
$env:DATABASE_URL='COLE_A_URL_DO_SESSION_POOLER_DO_SUPABASE'
$env:SECRET_KEY='uma-chave-local-segura'
uvicorn app.main:app --reload
```

## Confirmação automática por WhatsApp

O sistema usa exclusivamente a **WhatsApp Business Cloud API oficial da Meta**. O agendamento é confirmado no banco antes do envio; uma falha na Meta nunca desfaz a reserva.

1. Crie e aprove na Meta o template `confirmacao_agendamento`, idioma `pt_BR`, com seis variáveis no corpo: nome, serviço, data, horário, profissional e código.
2. Preencha no `.env` as variáveis `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN` e `WHATSAPP_APP_SECRET`.
3. Cadastre na Meta o callback HTTPS `https://SEU-DOMINIO/api/whatsapp/webhook` e use o mesmo token de verificação configurado no ambiente.
4. Reinicie o FastAPI. O worker busca mensagens pendentes e tenta novamente após 1, 5 e 15 minutos somente em falhas temporárias.

Os resultados ficam nos campos `whatsapp_status`, `whatsapp_message_id`, `whatsapp_enviado_em`, `whatsapp_tentativas` e `whatsapp_erro` do agendamento. Tokens e payloads sensíveis não são registrados.

## Confirmação por e-mail

Defina `RESEND_API_KEY` e `EMAIL_FROM` no `.env`. A página pública solicita um e-mail válido e envia a confirmação pelo Resend em segundo plano. A reserva permanece salva mesmo quando o provedor rejeita ou não consegue entregar a mensagem. Com `onboarding@resend.dev`, use no teste o mesmo e-mail cadastrado na conta Resend; para destinatários externos, configure um domínio verificado.

Para executar os testes sem enviar mensagens reais:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Produção na Vercel

O projeto possui entrada FastAPI para a Vercel, armazenamento persistente de imagens no
Supabase Storage e modo serverless para as notificações. Siga o checklist completo em
[`docs/VERCEL.md`](docs/VERCEL.md). Não envie `.env` ao GitHub e não exponha a chave
`SUPABASE_SERVICE_ROLE_KEY` no frontend.

## Principais rotas

Todas as rotas solicitadas estão documentadas interativamente em `/api/docs`. Rotas administrativas exigem `Authorization: Bearer <token>`.
