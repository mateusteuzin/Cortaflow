# Publicação do CortaFlow na Vercel

O projeto usa uma única aplicação FastAPI para o painel, agenda pública e API. O domínio
`cortaflow.com.br` atende todas as rotas; não é necessário comprar outros domínios.

## 1. Preparar o Supabase

1. No SQL Editor, execute `sql/schema.sql` se o banco ainda estiver vazio.
2. Execute `sql/002_anonymize_completed_appointments.sql`.
3. Execute `sql/003_supabase_storage.sql` para criar o bucket público de imagens.
4. Em **Project Settings > API**, copie a URL do projeto e a chave `service_role`.
5. Em **Connect**, use a URL do **Session Pooler**, porta 5432.

Nunca coloque a chave `service_role`, `DATABASE_URL` ou outras credenciais no JavaScript,
GitHub ou em variáveis prefixadas com `NEXT_PUBLIC_`/`VITE_`.

## 2. Importar o repositório

1. Envie o código a um repositório privado no GitHub. O `.env` já está ignorado.
2. Na Vercel, abra **Add New > Project** e importe o repositório.
3. Se o GitHub tiver a pasta externa e outra `barbershop-main` dentro, selecione a pasta
   que contém `index.py`, `requirements.txt` e `vercel.json` como **Root Directory**.
4. A Vercel detectará FastAPI pelo `index.py`; não defina Build Command nem Output Directory.

## 3. Variáveis de ambiente

Cadastre em **Settings > Environment Variables**, para Production e Preview:

```text
DATABASE_URL=postgresql://...session-pooler...:5432/postgres?sslmode=require
DB_POOL_MIN=1
DB_POOL_MAX=3
SECRET_KEY=GERAR_UMA_CHAVE_FORTE
ALLOWED_ORIGINS=https://cortaflow.com.br,https://www.cortaflow.com.br
RUN_DB_MIGRATIONS=false
ENABLE_BACKGROUND_WORKER=false
SUPABASE_URL=https://SEU_PROJETO.supabase.co
SUPABASE_SERVICE_ROLE_KEY=SUA_SERVICE_ROLE
SUPABASE_STORAGE_BUCKET=cortaflow-images
RESEND_API_KEY=SUA_CHAVE_RESEND
EMAIL_FROM=CortaFlow <nao-responda@cortaflow.com.br>
CRON_SECRET=OUTRA_CHAVE_FORTE
```

As variáveis `WHATSAPP_*` são opcionais até a integração da Meta estar pronta. Para gerar
segredos no PowerShell:

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
```

## 4. Primeiro deploy e domínio

1. Clique em **Deploy** e teste primeiro a URL `*.vercel.app`.
2. Confira `/api/health`, login, criação de barbearia, upload de foto e agenda pública.
3. Abra **Settings > Domains** e adicione `cortaflow.com.br` e `www.cortaflow.com.br`.
4. No registrador, crie exatamente os registros DNS mostrados pela Vercel.
5. Defina `cortaflow.com.br` como principal e redirecione `www` para ele.
6. Após o domínio ficar válido, faça novo deploy para aplicar `ALLOWED_ORIGINS`.

## 5. Resend

No Resend, verifique `cortaflow.com.br` e copie os registros DNS fornecidos. Esses registros
TXT/MX coexistem com os registros da Vercel. Depois use o remetente
`CortaFlow <nao-responda@cortaflow.com.br>`.

## 6. WhatsApp em ambiente serverless

O envio inicial é disparado junto à requisição de agendamento. Retentativas ficam no banco.
O endpoint abaixo processa até dez itens pendentes e exige `CRON_SECRET`:

```text
GET https://cortaflow.com.br/api/internal/whatsapp/processar
Authorization: Bearer SEU_CRON_SECRET
```

Configure um agendador compatível com sua conta Vercel para chamar o endpoint periodicamente.
Não exponha `CRON_SECRET`. A reserva continua salva se Meta ou Resend estiverem indisponíveis.

## Checklist

- [ ] `.env` não foi enviado ao GitHub
- [ ] SQL e bucket foram criados no Supabase
- [ ] `SECRET_KEY` e `CRON_SECRET` são diferentes e fortes
- [ ] `SUPABASE_SERVICE_ROLE_KEY` existe somente no backend da Vercel
- [ ] URL do Session Pooler usa SSL e porta 5432
- [ ] Domínio e `www` estão válidos na Vercel
- [ ] Domínio está verificado no Resend
- [ ] Upload de logo, barbeiro e serviço foi testado
- [ ] Cadastro, login e agendamento foram testados no celular
