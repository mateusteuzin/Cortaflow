# CortaFlow

Sistema web de gestão para barbearia com FastAPI, PostgreSQL e frontend HTML/CSS/JavaScript puro. Inclui autenticação JWT, agenda com bloqueio de conflito, barbeiros, produtos/estoque, relatórios, fidelidade e WhatsApp.

## Rodar com Docker (recomendado)

```powershell
docker compose up --build
```

Depois acesse:

- Painel do proprietário: http://localhost:8000
- Agendamento público: `http://localhost:8000/agendar/slug-da-barbearia` (copie o endereço em **Minha conta**)
- Documentação da API: http://localhost:8000/api/docs

No primeiro acesso, clique em **Crie sua conta**. Cada barbearia recebe automaticamente um slug único e um link exclusivo. Não existe listagem pública de estabelecimentos nem agendamento por ID numérico.

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

Defina `RESEND_API_KEY`, `EMAIL_FROM` e `PUBLIC_BASE_URL` no `.env`. A página pública envia a confirmação ao cliente em segundo plano. Cada profissional pode ter seu próprio e-mail de notificação e recebe somente eventos dos agendamentos pelos quais é responsável: novo, reagendado e cancelado. Se o profissional estiver sem e-mail, o sistema usa o e-mail administrativo da barbearia e registra essa contingência no log.

Em produção, verifique o domínio no Resend e use um remetente como `CortaFlow <nao-responda@cortaflow.com.br>`. A tabela `notificacoes_email` impede duplicidade por agendamento, evento, versão do evento e destinatário, além de registrar a situação e o ID retornado pelo Resend. A reserva permanece salva mesmo quando o provedor rejeita ou não consegue entregar a mensagem.

Para liberar o acesso individual, marque **Convidar para acessar o painel** no cadastro do profissional. O convite permite que ele crie uma senha e altere apenas nome, cargo, foto, telefone, WhatsApp e o próprio e-mail de avisos.

Para executar os testes sem enviar mensagens reais:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Login com Google

O fluxo OAuth 2.0/OpenID Connect já está implementado. Para ativá-lo:

1. Crie um cliente OAuth do tipo **Aplicativo da Web** no Google Cloud.
2. Cadastre `https://cortaflow.com.br/api/auth/google/callback` como URI de redirecionamento autorizada.
3. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI` na Vercel.
4. Faça um novo deploy. O botão Google é habilitado automaticamente quando a configuração estiver completa.

O login Google utiliza apenas `openid email profile` e atende contas CortaFlow que já concluíram a assinatura.

## Stripe

Produção exige `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` e os três IDs `STRIPE_PRICE_*`.
O endpoint `/api/config/status` informa apenas se a integração está pronta, sem revelar credenciais.
O webhook deve ouvir `checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted` e `invoice.payment_failed`.

## Produção na Vercel

O projeto possui entrada FastAPI para a Vercel, armazenamento persistente de imagens no
Supabase Storage e modo serverless para as notificações. Siga o checklist completo em
[`docs/VERCEL.md`](docs/VERCEL.md). Não envie `.env` ao GitHub e não exponha a chave
`SUPABASE_SERVICE_ROLE_KEY` no frontend.

## Principais rotas

Todas as rotas solicitadas estão documentadas interativamente em `/api/docs`. Rotas administrativas exigem `Authorization: Bearer <token>`.
