# Configuração do Supabase

O projeto usa o PostgreSQL do Supabase por meio do FastAPI e `psycopg2`, permitindo que os colaboradores trabalhem com os mesmos dados. Não é necessário instalar ou executar PostgreSQL localmente.

## Responsável pela implementação

Uma pessoa deve criar e administrar o projeto no Supabase. Os demais colaboradores recebem acesso ao projeto pelo painel do Supabase; a senha do banco não deve ser enviada em mensagens ou adicionada ao GitHub.

## 1. Criar o projeto

1. Crie um projeto no Supabase.
2. Convide o colaborador em **Project Settings > Team**.
3. Abra **SQL Editor**, cole todo o conteúdo de `sql/schema.sql` e execute uma vez.

## 2. Configurar a conexão

1. No painel, clique em **Connect**.
2. Escolha **Session pooler**, porta `5432`.
3. Copie `.env.example` para `.env`.
4. Substitua `DATABASE_URL` pela conexão copiada e mantenha `sslmode=require`.
5. Troque `SECRET_KEY` por uma chave longa e aleatória.

Exemplo apenas estrutural:

```env
DATABASE_URL=postgresql://postgres.PROJECT_REF:SENHA@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
DB_POOL_MIN=1
DB_POOL_MAX=5
SECRET_KEY=CHAVE_LOCAL_COM_PELO_MENOS_32_CARACTERES
```

Se a senha tiver caracteres especiais, use a URL fornecida pelo próprio painel ou codifique esses caracteres na URL.

## 3. Executar

```powershell
Copy-Item .env.example .env
# Preencha o .env antes de continuar.
docker compose up --build
```

O Compose inicia somente a API. A inicialização será interrompida se `DATABASE_URL` não estiver preenchida no `.env`.

## 4. Divisão do trabalho

- Administrador do Supabase: criar projeto, executar `sql/schema.sql`, convidar colaboradores e configurar backups.
- Backend: manter alterações de estrutura como novos scripts SQL versionados no repositório.
- Frontend: consumir somente as rotas `/api`; nunca usar a senha do banco nem a `DATABASE_URL` no JavaScript.
- Todos: usar branches próprias e pull requests; não versionar `.env`.

## Validação

Execute também `sql/004_database_performance.sql` no SQL Editor. A migração é idempotente
e adiciona índices para agenda, clientes, profissionais, serviços, vendas e pagamentos sem
alterar os dados existentes.

Depois de iniciar a API, abra `http://localhost:8000/api/health`. Em seguida, crie uma conta pelo painel. Se os dois computadores estiverem usando a mesma `DATABASE_URL`, ambos verão os mesmos cadastros e agendamentos.
