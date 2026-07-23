import hashlib, json, logging, os, secrets, time as time_module
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg2 import IntegrityError
from .database import all_rows, db, one
from .schemas import *
from .security import authenticated_user, current_user, hash_password, token, verify_password
from .services.whatsapp import verify_webhook_signature
from .services.whatsapp_worker import whatsapp_worker
from .services.email import (
    send_account_verification,
    send_appointment_confirmation,
    send_owner_notification,
    send_subscription_confirmation,
)
from .services.storage import StorageConfigurationError, StorageUploadError, image_storage
from .services.slugs import unique_shop_slug
from .runtime import is_vercel, should_run_migrations, should_start_worker
from .services.appointments import (
    AppointmentNotFoundError,
    InvalidAppointmentStatusError,
    complete_appointment,
)

app = FastAPI(title="CortaFlow API", version="1.0.0", docs_url="/api/docs")
origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
hits = defaultdict(deque)
static = Path(__file__).parent/'static'
uploads = static/'uploads'
if not is_vercel():
    uploads.mkdir(exist_ok=True)
image_types = {
    'image/jpeg': ('.jpg', (b'\xff\xd8\xff',)),
    'image/png': ('.png', (b'\x89PNG\r\n\x1a\n',)),
    'image/webp': ('.webp', (b'RIFF',)),
}

@app.on_event("startup")
def ensure_current_schema():
    if not should_run_migrations():
        if should_start_worker():
            whatsapp_worker.start()
        return
    with db() as cur:
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verificado BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute("ALTER TABLE usuarios ALTER COLUMN email_verificado SET DEFAULT FALSE")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verification_token_hash VARCHAR(64)")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS logo_url TEXT")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS email_notificacoes VARCHAR(254)")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS notificar_novos_agendamentos BOOLEAN NOT NULL DEFAULT TRUE")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS subscription_plan VARCHAR(24)")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(24) NOT NULL DEFAULT 'active'")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(120)")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(120)")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMPTZ")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS subscription_cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE barbearias ADD COLUMN IF NOT EXISTS subscription_confirmation_email_sent_at TIMESTAMPTZ")
        cur.execute("""UPDATE barbearias b SET email_notificacoes=u.email FROM usuarios u
            WHERE b.usuario_id=u.id AND (b.email_notificacoes IS NULL OR b.email_notificacoes='')""")
        cur.execute("ALTER TABLE barbeiros ADD COLUMN IF NOT EXISTS foto_url TEXT")
        cur.execute("""CREATE TABLE IF NOT EXISTS servicos (
          id SERIAL PRIMARY KEY, barbearia_id INTEGER NOT NULL REFERENCES barbearias(id) ON DELETE CASCADE,
          nome VARCHAR(120) NOT NULL, descricao VARCHAR(240),
          duracao_minutos INTEGER NOT NULL DEFAULT 30 CHECK(duracao_minutos BETWEEN 10 AND 480),
          preco NUMERIC(10,2) NOT NULL CHECK(preco >= 0), ativo BOOLEAN DEFAULT TRUE,
          criado_em TIMESTAMPTZ DEFAULT NOW())""")
        cur.execute("ALTER TABLE servicos ADD COLUMN IF NOT EXISTS imagem_url TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_autorizado BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_enviado BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_enviado_em TIMESTAMPTZ")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_message_id TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_status VARCHAR(20) NOT NULL DEFAULT 'PENDENTE'")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_erro TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_tentativas INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_proxima_tentativa TIMESTAMPTZ DEFAULT NOW()")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS whatsapp_telefone VARCHAR(20)")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS cliente_email VARCHAR(254)")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_enviado BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_enviado_em TIMESTAMPTZ")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_message_id TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_erro TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_dono_enviado BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_dono_message_id TEXT")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS email_dono_erro TEXT")
        cur.execute("ALTER TABLE agendamentos ALTER COLUMN cliente_telefone DROP NOT NULL")
        cur.execute("ALTER TABLE fidelidade_cliente ALTER COLUMN cliente_telefone DROP NOT NULL")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS concluido_em TIMESTAMPTZ")
        cur.execute("ALTER TABLE agendamentos ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ DEFAULT NOW()")
        cur.execute("ALTER TABLE agendamentos DROP CONSTRAINT IF EXISTS agendamentos_status_check")
        cur.execute("""ALTER TABLE agendamentos ADD CONSTRAINT agendamentos_status_check
          CHECK(status IN ('agendado','confirmado','em_andamento','concluido','realizado','cancelado','nao_compareceu'))""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_agenda_whatsapp_fila ON agendamentos(whatsapp_status,whatsapp_proxima_tentativa) WHERE whatsapp_autorizado AND NOT whatsapp_enviado")
    if should_start_worker():
        whatsapp_worker.start()

@app.on_event("shutdown")
def stop_workers():
    if should_start_worker():
        whatsapp_worker.stop()


def dispatch_whatsapp(background_tasks: BackgroundTasks | None = None):
    """Executa na resposta serverless ou acorda o worker persistente local."""
    if should_start_worker():
        whatsapp_worker.notify()
    elif background_tasks is not None:
        background_tasks.add_task(whatsapp_worker.process_next)

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time_module.time(); bucket = hits[ip]
    while bucket and bucket[0] < now - 60: bucket.popleft()
    if len(bucket) >= 100: return JSONResponse({"detail": "Limite de requisições excedido"}, 429)
    bucket.append(now)
    response = await call_next(request)
    response.headers.update({"X-Content-Type-Options":"nosniff", "X-Frame-Options":"DENY", "Referrer-Policy":"strict-origin-when-cross-origin", "Permissions-Policy":"camera=(), microphone=(), geolocation=()"})
    return response

@app.get("/api/health")
def health(): return {"status":"ok"}

STRIPE_PLANS = {
    "essencial": {"name": "CortaFlow Essencial", "amount": 3000},
    "profissional": {"name": "CortaFlow Profissional", "amount": 4490},
    "premium": {"name": "CortaFlow Premium", "amount": 6490},
}

@app.post("/api/billing/checkout")
def create_checkout(data: dict, request: Request, user=Depends(authenticated_user)):
    """Cria um Checkout recorrente sem misturar preços dos modos teste e produção."""
    plan = str(data.get("plan", "")).lower()
    plan_data = STRIPE_PLANS.get(plan)
    if not plan_data:
        raise HTTPException(422, "Plano inválido.")
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret or not secret.startswith(("sk_test_", "sk_live_")):
        raise HTTPException(503, "Stripe ainda não está configurada. Preencha a chave secreta no ambiente.")
    try:
        import stripe
    except ImportError as error:
        raise HTTPException(503, "Dependência Stripe não instalada no servidor.") from error
    stripe.api_key = secret
    site_url = str(request.base_url).rstrip("/")
    shop = one("""SELECT id,nome,stripe_customer_id,stripe_subscription_id,plano_ativo
        FROM barbearias WHERE id=%s""", (user["barbearia_id"],))
    if shop["plano_ativo"] and shop["stripe_subscription_id"]:
        raise HTTPException(409, "Sua assinatura já está ativa. Use Minha assinatura para alterar o plano.")
    try:
        customer_id = shop["stripe_customer_id"]
        if not customer_id:
            customer = stripe.Customer.create(
                email=user["email"],
                name=shop["nome"],
                metadata={"barbearia_id": str(shop["id"]), "usuario_id": str(user["id"])},
            )
            customer_id = customer.id
            one("UPDATE barbearias SET stripe_customer_id=%s WHERE id=%s RETURNING id",
                (customer_id, shop["id"]))
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user["id"]),
            line_items=[{
                "price_data": {
                    "currency": "brl",
                    "unit_amount": plan_data["amount"],
                    "recurring": {"interval": "month"},
                    "product_data": {"name": plan_data["name"]},
                },
                "quantity": 1,
            }],
            success_url=f"{site_url}/painel?checkout=sucesso&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{site_url}/painel?checkout=cancelado",
            allow_promotion_codes=True,
            metadata={"plan": plan, "barbearia_id": str(shop["id"]), "usuario_id": str(user["id"])},
            subscription_data={"metadata": {"plan": plan, "barbearia_id": str(shop["id"])}},
        )
    except stripe.error.StripeError as error:
        logging.exception("Stripe checkout error")
        raise HTTPException(502, "Não foi possível abrir o checkout agora.") from error
    return {"url": session.url}

def _stripe_client():
    try:
        import stripe
    except ImportError as error:
        raise HTTPException(503, "Dependência Stripe não instalada no servidor.") from error
    secret = os.getenv("STRIPE_SECRET_KEY")
    if not secret or not secret.startswith(("sk_test_", "sk_live_")):
        raise HTTPException(503, "Stripe ainda não está configurada.")
    stripe.api_key = secret
    return stripe

def _timestamp(value):
    return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None

def _metadata_shop_id(metadata) -> int:
    try:
        return int((metadata or {}).get("barbearia_id") or 0)
    except (TypeError, ValueError):
        return 0

def _save_stripe_subscription(shop_id: int, subscription, plan: str | None = None):
    status = str(subscription.get("status") or "inactive")
    active = status in {"active", "trialing"}
    metadata = subscription.get("metadata") or {}
    selected_plan = plan or metadata.get("plan")
    return one("""UPDATE barbearias SET plano_ativo=%s,subscription_plan=COALESCE(%s,subscription_plan),
        subscription_status=%s,stripe_subscription_id=%s,
        subscription_current_period_end=%s,subscription_cancel_at_period_end=%s,
        data_assinatura=CASE WHEN %s THEN CURRENT_DATE ELSE data_assinatura END
        WHERE id=%s RETURNING id""",
        (active, selected_plan, status, subscription.get("id"),
         _timestamp(subscription.get("current_period_end")),
         bool(subscription.get("cancel_at_period_end")), active, shop_id))

def _send_subscription_email_once(shop_id: int, plan: str | None, period_end=None):
    plan_data = STRIPE_PLANS.get(plan or "")
    if not plan_data:
        return
    item = one("""UPDATE barbearias b SET subscription_confirmation_email_sent_at=NOW()
        FROM usuarios u WHERE b.usuario_id=u.id AND b.id=%s
        AND b.subscription_confirmation_email_sent_at IS NULL RETURNING u.email,u.nome""", (shop_id,))
    if not item:
        return
    sent = send_subscription_confirmation(
        item["email"], item["nome"], plan_data["name"], plan_data["amount"], _timestamp(period_end)
    )
    if not sent:
        one("""UPDATE barbearias SET subscription_confirmation_email_sent_at=NULL
            WHERE id=%s RETURNING id""", (shop_id,))

@app.get("/api/billing/subscription")
def subscription_details(user=Depends(authenticated_user)):
    shop = one("""SELECT subscription_plan,subscription_status,plano_ativo,
        subscription_current_period_end,subscription_cancel_at_period_end,
        stripe_customer_id,stripe_subscription_id FROM barbearias WHERE id=%s""",
        (user["barbearia_id"],))
    return {
        "active": bool(shop["plano_ativo"]),
        "plan": shop["subscription_plan"],
        "status": shop["subscription_status"] or ("active" if shop["plano_ativo"] else "inactive"),
        "current_period_end": shop["subscription_current_period_end"],
        "cancel_at_period_end": bool(shop["subscription_cancel_at_period_end"]),
        "managed_by_stripe": bool(shop["stripe_customer_id"] and shop["stripe_subscription_id"]),
    }

@app.post("/api/billing/confirm")
def confirm_checkout(data: dict, user=Depends(authenticated_user)):
    session_id = str(data.get("session_id", ""))
    if not session_id.startswith("cs_"):
        raise HTTPException(422, "Sessão de checkout inválida.")
    stripe = _stripe_client()
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except stripe.error.StripeError as error:
        raise HTTPException(502, "Não foi possível confirmar a assinatura.") from error
    metadata = session.get("metadata") or {}
    if str(session.get("client_reference_id")) != str(user["id"]) or str(metadata.get("barbearia_id")) != str(user["barbearia_id"]):
        raise HTTPException(403, "Esta assinatura não pertence à sua conta.")
    if session.get("payment_status") not in {"paid", "no_payment_required"}:
        raise HTTPException(409, "O pagamento ainda não foi confirmado.")
    subscription = session.get("subscription")
    if not subscription:
        raise HTTPException(409, "A assinatura ainda não foi criada pela Stripe.")
    if isinstance(subscription, str):
        subscription = stripe.Subscription.retrieve(subscription)
    _save_stripe_subscription(user["barbearia_id"], subscription, metadata.get("plan"))
    _send_subscription_email_once(
        user["barbearia_id"], metadata.get("plan"), subscription.get("current_period_end")
    )
    return {"active": True, "plan": metadata.get("plan")}

@app.post("/api/billing/portal")
def billing_portal(request: Request, user=Depends(authenticated_user)):
    stripe = _stripe_client()
    shop = one("SELECT stripe_customer_id FROM barbearias WHERE id=%s", (user["barbearia_id"],))
    if not shop["stripe_customer_id"]:
        raise HTTPException(422, "Conclua sua primeira assinatura antes de gerenciá-la.")
    try:
        session = stripe.billing_portal.Session.create(
            customer=shop["stripe_customer_id"],
            return_url=f"{str(request.base_url).rstrip('/')}/painel",
        )
    except stripe.error.StripeError as error:
        raise HTTPException(502, "Não foi possível abrir o portal da assinatura.") from error
    return {"url": session.url}

@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    stripe = _stripe_client()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(503, "Webhook da Stripe não configurado.")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, request.headers.get("stripe-signature", ""), webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise HTTPException(400, "Assinatura do webhook inválida.") from error
    obj = event["data"]["object"]
    event_type = event["type"]
    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata") or {}
        shop_id = _metadata_shop_id(metadata)
        subscription_id = obj.get("subscription")
        if shop_id and subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            _save_stripe_subscription(shop_id, subscription, metadata.get("plan"))
            _send_subscription_email_once(shop_id, metadata.get("plan"), subscription.get("current_period_end"))
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        metadata = obj.get("metadata") or {}
        shop_id = _metadata_shop_id(metadata)
        if shop_id:
            _save_stripe_subscription(shop_id, obj)
    elif event_type == "invoice.payment_failed":
        customer_id = obj.get("customer")
        one("""UPDATE barbearias SET plano_ativo=FALSE,subscription_status='past_due'
            WHERE stripe_customer_id=%s RETURNING id""", (customer_id,))
    return {"received": True}

@app.post("/api/uploads/imagem", status_code=201)
async def upload_image(arquivo: UploadFile = File(...), user=Depends(current_user)):
    image_type = image_types.get(arquivo.content_type or '')
    if not image_type:
        raise HTTPException(415, "Use uma imagem JPG, PNG ou WebP")
    content = await arquivo.read(5 * 1024 * 1024 + 1)
    await arquivo.close()
    if not content:
        raise HTTPException(400, "A imagem enviada está vazia")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "A imagem deve ter no máximo 5 MB")
    extension, signatures = image_type
    valid_signature = any(content.startswith(signature) for signature in signatures)
    if arquivo.content_type == 'image/webp':
        valid_signature = valid_signature and len(content) >= 12 and content[8:12] == b'WEBP'
    if not valid_signature:
        raise HTTPException(400, "O arquivo não contém uma imagem válida")
    filename = f"{user['barbearia_id']}-{uuid4().hex}{extension}"
    try:
        stored = image_storage.upload(
            content=content,
            content_type=arquivo.content_type,
            object_path=f"barbearias/{user['barbearia_id']}/{filename}",
            local_directory=uploads,
        )
    except StorageConfigurationError as error:
        raise HTTPException(503, str(error)) from error
    except StorageUploadError as error:
        raise HTTPException(502, str(error)) from error
    return {"url": stored.public_url}

def _new_email_verification() -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash, datetime.now().astimezone() + timedelta(hours=24)


@app.post("/api/auth/register", status_code=201)
def register(data: Register):
    raw_token, token_hash, expires_at = _new_email_verification()
    try:
        with db() as cur:
            cur.execute("""INSERT INTO usuarios(email,senha_hash,nome,telefone,email_verificado,
                email_verification_token_hash,email_verification_expires_at)
                VALUES(%s,%s,%s,%s,FALSE,%s,%s) RETURNING id""",
                (data.email.lower(),hash_password(data.senha),data.nome,data.telefone,token_hash,expires_at)); uid=cur.fetchone()["id"]
            shop_slug=unique_shop_slug(cur,data.barbearia_nome)
            cur.execute("""INSERT INTO barbearias(usuario_id,nome,slug,telefone,plano_ativo,
                subscription_status,subscription_plan)
                VALUES(%s,%s,%s,%s,FALSE,'inactive',%s) RETURNING id""",
                (uid,data.barbearia_nome,shop_slug,data.telefone,data.plano)); sid=cur.fetchone()["id"]
            cur.execute("INSERT INTO horarios_funcionamento(barbearia_id,dia_semana,hora_inicio,hora_fim) SELECT %s,d,'09:00','19:00' FROM generate_series(0,5) d", (sid,))
            cur.execute("""INSERT INTO servicos(barbearia_id,nome,descricao,duracao_minutos,preco,imagem_url) VALUES
              (%s,'Corte Degradê','Degradê com acabamento completo',40,30,'/assets/service-degrade.webp'),
              (%s,'Corte Social','Corte clássico com acabamento',30,25,'/assets/service-social.webp'),
              (%s,'Corte + Barba','Corte completo e barba alinhada',60,50,'/assets/service-combo.webp'),
              (%s,'Sobrancelha','Design e acabamento de sobrancelha',15,10,'/assets/service-sobrancelha.webp')""", (sid,sid,sid,sid))
        sent = send_account_verification(data.email.lower(), data.nome, raw_token)
        return {"requires_email_verification":True,"email_sent":sent,"plan":data.plano,
            "message":"Enviamos um link de confirmação para seu Gmail." if sent else "Conta criada. Use reenviar link para confirmar seu e-mail."}
    except IntegrityError: raise HTTPException(409,"E-mail já cadastrado")

@app.post("/api/auth/login")
def login(data: Login):
    user=one("""SELECT u.*,b.plano_ativo,b.subscription_plan,b.subscription_status
        FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id WHERE u.email=%s""",(data.email.lower(),))
    if not user or not verify_password(data.senha,user["senha_hash"]): raise HTTPException(401,"E-mail ou senha inválidos")
    if not user.get("email_verificado"):
        raise HTTPException(403,"Confirme seu e-mail antes de entrar. Confira também a caixa de spam.")
    return {"access_token":token(user["id"]),"token_type":"bearer","nome":user["nome"],
        "subscription_required":not bool(user["plano_ativo"]),
        "subscription_plan":user["subscription_plan"],
        "subscription_status":user["subscription_status"]}


@app.post("/api/auth/reenviar-confirmacao")
def resend_email_verification(data: ResendVerification):
    user = one("SELECT id,email,nome,email_verificado FROM usuarios WHERE email=%s", (data.email.lower(),))
    if user and not user["email_verificado"]:
        raw_token, token_hash, expires_at = _new_email_verification()
        one("""UPDATE usuarios SET email_verification_token_hash=%s,email_verification_expires_at=%s
            WHERE id=%s RETURNING id""", (token_hash, expires_at, user["id"]))
        send_account_verification(user["email"], user["nome"], raw_token)
    return {"message":"Se existir uma conta pendente, enviaremos um novo link de confirmação."}


@app.get("/api/auth/verificar-email")
def verify_account_email(token: str = Query(min_length=20, max_length=200)):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = one("""UPDATE usuarios SET email_verificado=TRUE,email_verification_token_hash=NULL,
        email_verification_expires_at=NULL WHERE email_verification_token_hash=%s
        AND email_verification_expires_at>NOW() AND NOT email_verificado RETURNING id,email""", (token_hash,))
    status = "sucesso" if user else "invalido"
    email = f"&email={quote(user['email'])}" if user else ""
    return RedirectResponse(url=f"/?email_confirmado={status}{email}", status_code=303)

@app.get("/api/barbearia/perfil")
def profile(user=Depends(current_user)): return one("SELECT * FROM barbearias WHERE id=%s",(user["barbearia_id"],))

@app.post("/api/barbearia/atualizar")
def update_shop(data: ShopUpdate,user=Depends(current_user)):
    return one("""UPDATE barbearias SET nome=%s,telefone=%s,endereco=%s,cnpj=%s,logo_url=%s,
        email_notificacoes=%s,notificar_novos_agendamentos=%s,public_booking_enabled=%s WHERE id=%s RETURNING *""",
        (data.nome,data.telefone,data.endereco,data.cnpj,data.logo_url,data.email_notificacoes,
         data.notificar_novos_agendamentos,data.public_booking_enabled,user["barbearia_id"]))

@app.get("/api/barbearia/horarios-funcionamento")
def business_hours(user=Depends(current_user)):
    rows = all_rows("""SELECT dia_semana,hora_inicio,hora_fim FROM horarios_funcionamento
        WHERE barbearia_id=%s ORDER BY dia_semana""", (user["barbearia_id"],))
    configured = {row["dia_semana"]: row for row in rows}
    return [{"dia_semana": day, "ativo": day in configured,
        "hora_inicio": configured[day]["hora_inicio"] if day in configured else None,
        "hora_fim": configured[day]["hora_fim"] if day in configured else None} for day in range(7)]

@app.put("/api/barbearia/horarios-funcionamento")
def update_business_hours(items: list[BusinessHour], user=Depends(current_user)):
    if len(items) != 7 or {item.dia_semana for item in items} != set(range(7)):
        raise HTTPException(422, "Informe os sete dias da semana uma única vez")
    active = []
    for item in items:
        if not item.ativo:
            continue
        if item.hora_inicio is None or item.hora_fim is None:
            raise HTTPException(422, "Informe abertura e fechamento nos dias de atendimento")
        if item.hora_inicio >= item.hora_fim:
            raise HTTPException(422, "O horário de fechamento deve ser posterior à abertura")
        active.append(item)
    if not active:
        raise HTTPException(422, "Mantenha pelo menos um dia de atendimento ativo")
    with db() as cur:
        cur.execute("DELETE FROM horarios_funcionamento WHERE barbearia_id=%s", (user["barbearia_id"],))
        cur.executemany("""INSERT INTO horarios_funcionamento(barbearia_id,dia_semana,hora_inicio,hora_fim)
            VALUES(%s,%s,%s,%s)""", [(user["barbearia_id"], item.dia_semana,
                item.hora_inicio, item.hora_fim) for item in active])
    return {"message":"Horários de atendimento atualizados","horarios":business_hours(user)}

@app.get("/api/barbearia/barbeiros")
def barbers(user=Depends(current_user)): return all_rows("SELECT * FROM barbeiros WHERE barbearia_id=%s ORDER BY ativo DESC,nome",(user["barbearia_id"],))

def resolve_public_shop(slug:str):
    shop=one("""SELECT id,nome,slug,telefone,endereco,logo_url,plano_ativo,public_booking_enabled
        FROM barbearias WHERE slug=%s""",(slug.lower(),))
    if not shop: raise HTTPException(404,"Barbearia não encontrada. Verifique se o link está correto.")
    if not shop["plano_ativo"] or not shop["public_booking_enabled"]:
        raise HTTPException(403,"Esta barbearia não está recebendo agendamentos no momento.")
    return shop

@app.get("/api/cliente/barbearias")
def public_shops():
    raise HTTPException(410,"A listagem pública de barbearias não está disponível. Use o link exclusivo do estabelecimento.")

@app.get("/api/public/barbearias/{slug}/profissionais")
def public_barbers(slug:str):
    shop=resolve_public_shop(slug)
    return all_rows("SELECT id,nome,foto_url FROM barbeiros WHERE barbearia_id=%s AND ativo ORDER BY nome",(shop["id"],))

@app.get("/api/public/barbearias/{slug}")
def public_shop(slug:str):
    shop=resolve_public_shop(slug)
    logo=shop["logo_url"] or ""
    if not (logo.startswith("https://") or logo.startswith("/assets/")):
        logo=""
    return {"nome":shop["nome"],"slug":shop["slug"],"telefone":shop["telefone"],
        "endereco":shop["endereco"],"logo_url":logo}

@app.get("/api/public/barbearias/{slug}/servicos")
def public_services(slug:str):
    shop=resolve_public_shop(slug)
    return all_rows("SELECT id,nome,descricao,duracao_minutos,preco,imagem_url FROM servicos WHERE barbearia_id=%s AND ativo ORDER BY nome",(shop["id"],))

@app.post("/api/barbearia/barbeiros",status_code=201)
def create_barber(data: Barber,user=Depends(current_user)):
    limit = {"essencial": 1, "profissional": 2}.get(user.get("subscription_plan"))
    if limit is not None:
        total = one("SELECT COUNT(*) total FROM barbeiros WHERE barbearia_id=%s AND ativo",
            (user["barbearia_id"],))["total"]
        if total >= limit:
            raise HTTPException(403, f"Seu plano permite até {limit} profissional(is). Altere o plano para ampliar a equipe.")
    return one("""INSERT INTO barbeiros(barbearia_id,nome,telefone,comissao_percentual,foto_url)
        VALUES(%s,%s,%s,%s,%s) RETURNING *""",
        (user["barbearia_id"],data.nome,data.telefone,data.comissao_percentual,data.foto_url))

@app.put("/api/barbearia/barbeiros/{barber_id}")
def update_barber(barber_id:int,data:Barber,user=Depends(current_user)):
    row=one("""UPDATE barbeiros SET nome=%s,telefone=%s,comissao_percentual=%s,foto_url=%s
      WHERE id=%s AND barbearia_id=%s AND ativo RETURNING *""",
      (data.nome,data.telefone,data.comissao_percentual,data.foto_url,barber_id,user["barbearia_id"]))
    if not row: raise HTTPException(404,"Barbeiro não encontrado")
    return row

@app.delete("/api/barbearia/barbeiros/{barber_id}")
def delete_barber(barber_id:int,user=Depends(current_user)):
    row=one("UPDATE barbeiros SET ativo=false WHERE id=%s AND barbearia_id=%s RETURNING id",(barber_id,user["barbearia_id"]))
    if not row: raise HTTPException(404,"Barbeiro não encontrado")
    return {"ok":True}

@app.get("/api/servicos")
def services(user=Depends(current_user)):
    return all_rows("SELECT * FROM servicos WHERE barbearia_id=%s AND ativo ORDER BY nome",(user["barbearia_id"],))

@app.post("/api/servicos",status_code=201)
def create_service(data:Service,user=Depends(current_user)):
    return one("INSERT INTO servicos(barbearia_id,nome,descricao,duracao_minutos,preco,imagem_url) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",(user["barbearia_id"],data.nome,data.descricao,data.duracao_minutos,data.preco,data.imagem_url))

@app.put("/api/servicos/{service_id}")
def update_service(service_id:int,data:Service,user=Depends(current_user)):
    row=one("UPDATE servicos SET nome=%s,descricao=%s,duracao_minutos=%s,preco=%s,imagem_url=%s WHERE id=%s AND barbearia_id=%s AND ativo RETURNING *",(data.nome,data.descricao,data.duracao_minutos,data.preco,data.imagem_url,service_id,user["barbearia_id"]))
    if not row: raise HTTPException(404,"Serviço não encontrado")
    return row

@app.delete("/api/servicos/{service_id}")
def delete_service(service_id:int,user=Depends(current_user)):
    row=one("UPDATE servicos SET ativo=false WHERE id=%s AND barbearia_id=%s RETURNING id",(service_id,user["barbearia_id"]))
    if not row: raise HTTPException(404,"Serviço não encontrado")
    return {"ok":True}

def insert_appointment(data, shop_id):
    service=one("""SELECT id,nome,duracao_minutos,preco FROM servicos
      WHERE barbearia_id=%s AND ativo AND (id=%s OR (%s::int IS NULL AND nome=%s))
      ORDER BY CASE WHEN id=%s THEN 0 ELSE 1 END LIMIT 1""",(shop_id,data.servico_id,data.servico_id,data.servico,data.servico_id))
    if not service: raise HTTPException(404,"Serviço não encontrado")
    try:
        return one("""INSERT INTO agendamentos(
          barbearia_id,barbeiro_id,servico_id,cliente_nome,cliente_telefone,cliente_email,data_hora,duracao_minutos,servico,preco,whatsapp_autorizado)
          SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
          WHERE EXISTS(SELECT 1 FROM barbeiros WHERE id=%s AND barbearia_id=%s AND ativo)
          RETURNING *""",(shop_id,data.barbeiro_id,service["id"],data.cliente_nome,data.cliente_telefone,data.cliente_email,data.data_hora,service["duracao_minutos"],service["nome"],service["preco"],data.whatsapp_autorizado,data.barbeiro_id,shop_id))
    except IntegrityError: raise HTTPException(409,"Este horário acabou de ser ocupado")

@app.get("/api/agendamentos")
def appointments(data:date|None=None,barbeiro_id:int|None=None,user=Depends(current_user)):
    return all_rows("SELECT a.*,b.nome barbeiro_nome FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id WHERE a.barbearia_id=%s AND (%s::date IS NULL OR a.data_hora::date=%s) AND (%s::int IS NULL OR a.barbeiro_id=%s) ORDER BY a.data_hora",(user["barbearia_id"],data,data,barbeiro_id,barbeiro_id))

@app.post("/api/agendamentos",status_code=201)
def create_appointment(data: Appointment,background_tasks:BackgroundTasks,user=Depends(current_user)):
    row=insert_appointment(data,user["barbearia_id"])
    if not row: raise HTTPException(404,"Barbeiro não encontrado")
    dispatch_whatsapp(background_tasks)
    return row

@app.put("/api/agendamentos/{appointment_id}")
def update_appointment(appointment_id:int,data:AppointmentUpdate,user=Depends(current_user)):
    if data.status in ('concluido','realizado'):
        try:
            return complete_appointment(appointment_id,user["barbearia_id"])
        except AppointmentNotFoundError:
            raise HTTPException(404,"Agendamento não encontrado")
        except InvalidAppointmentStatusError:
            raise HTTPException(409,"Agendamento cancelado não pode ser concluído")
    current=one("SELECT * FROM agendamentos WHERE id=%s AND barbearia_id=%s",(appointment_id,user["barbearia_id"]))
    if not current: raise HTTPException(404,"Agendamento não encontrado")
    values=data.model_dump(exclude_none=True)
    if data.status and data.status not in ('agendado','confirmado','em_andamento','cancelado','nao_compareceu'): raise HTTPException(422,"Status inválido")
    for key,value in values.items(): current=one(f"UPDATE agendamentos SET {key}=%s WHERE id=%s RETURNING *",(value,appointment_id))
    return current

@app.patch("/api/agendamentos/{appointment_id}/concluir")
def conclude_appointment(appointment_id:int,user=Depends(current_user)):
    try:
        appointment=complete_appointment(appointment_id,user["barbearia_id"])
    except AppointmentNotFoundError:
        raise HTTPException(404,"Agendamento não encontrado")
    except InvalidAppointmentStatusError:
        raise HTTPException(409,"Agendamento cancelado não pode ser concluído")
    return {
        "message":"Agendamento concluído e dados de contato removidos com sucesso.",
        "agendamento":appointment,
    }

@app.delete("/api/agendamentos/{appointment_id}")
def cancel(appointment_id:int,user=Depends(current_user)):
    row=one("UPDATE agendamentos SET status='cancelado' WHERE id=%s AND barbearia_id=%s RETURNING id",(appointment_id,user["barbearia_id"]))
    if not row: raise HTTPException(404,"Agendamento não encontrado")
    return {"ok":True}

@app.delete("/api/agendamentos/{appointment_id}/remover")
def remove_cancelled_appointment(appointment_id:int,user=Depends(current_user)):
    with db() as cur:
        cur.execute("SELECT id FROM agendamentos WHERE id=%s AND barbearia_id=%s AND status='cancelado'",(appointment_id,user["barbearia_id"]))
        if not cur.fetchone(): raise HTTPException(409,"Somente agendamentos cancelados podem ser apagados")
        cur.execute("DELETE FROM pagamentos WHERE agendamento_id=%s",(appointment_id,))
        cur.execute("DELETE FROM vendas_produto WHERE agendamento_id=%s",(appointment_id,))
        cur.execute("DELETE FROM agendamentos WHERE id=%s",(appointment_id,))
    return {"ok":True}

def available(shop_id:int, day:date, barber_id:int|None, duration:int=30):
    weekday=day.weekday(); hours=one("SELECT hora_inicio,hora_fim FROM horarios_funcionamento WHERE barbearia_id=%s AND dia_semana=%s",(shop_id,weekday))
    if not hours:return []
    busy=all_rows("SELECT data_hora,duracao_minutos FROM agendamentos WHERE barbearia_id=%s AND data_hora::date=%s AND status<>'cancelado' AND (%s::int IS NULL OR barbeiro_id=%s)",(shop_id,day,barber_id,barber_id))
    cursor=datetime.combine(day,hours["hora_inicio"]); end=datetime.combine(day,hours["hora_fim"]); slots=[]
    while cursor+timedelta(minutes=duration)<=end:
        candidate_end=cursor+timedelta(minutes=duration)
        free=all(candidate_end<=item["data_hora"] or cursor>=item["data_hora"]+timedelta(minutes=item["duracao_minutos"]) for item in busy)
        if free and cursor>datetime.now(): slots.append(cursor.strftime('%H:%M'))
        cursor+=timedelta(minutes=30)
    return slots

@app.get("/api/agendamentos/horarios-disponiveis")
def owner_slots(data:date,barbeiro_id:int|None=None,user=Depends(current_user)): return {"horarios":available(user["barbearia_id"],data,barbeiro_id)}

def validate_public_selection(shop_id:int,barbeiro_id:int,servico_id:int):
    barber=one("SELECT id FROM barbeiros WHERE id=%s AND barbearia_id=%s AND ativo",(barbeiro_id,shop_id))
    if not barber: raise HTTPException(404,"Profissional não encontrado para esta barbearia")
    service=one("SELECT duracao_minutos FROM servicos WHERE id=%s AND barbearia_id=%s AND ativo",(servico_id,shop_id))
    if not service: raise HTTPException(404,"Serviço não encontrado para esta barbearia")
    return service

@app.get("/api/public/barbearias/{slug}/horarios")
def public_slots(slug:str,data:date,barbeiro_id:int,servico_id:int):
    shop=resolve_public_shop(slug)
    service=validate_public_selection(shop["id"],barbeiro_id,servico_id)
    return {"horarios":available(shop["id"],data,barbeiro_id,service["duracao_minutos"])}
@app.post("/api/public/barbearias/{slug}/agendamentos",status_code=201)
def public_create(slug:str,data:PublicAppointment,background_tasks:BackgroundTasks):
    shop=resolve_public_shop(slug)
    service=validate_public_selection(shop["id"],data.barbeiro_id,data.servico_id)
    slots=available(shop["id"],data.data_hora.date(),data.barbeiro_id,service["duracao_minutos"])
    if data.data_hora.strftime("%H:%M") not in slots:
        raise HTTPException(409,"Este horário não está mais disponível")
    row=insert_appointment(data,shop["id"])
    if not row: raise HTTPException(404,"Barbeiro não encontrado")
    dispatch_whatsapp(background_tasks)
    background_tasks.add_task(send_appointment_confirmation,row["id"])
    background_tasks.add_task(send_owner_notification,row["id"])
    return row
@app.get("/api/public/barbearias/{slug}/reservas/{telefone}")
def my_appointment(slug:str,telefone:str):
    shop=resolve_public_shop(slug)
    digits=''.join(character for character in telefone if character.isdigit())
    if len(digits)<10: raise HTTPException(422,"Informe um WhatsApp válido")
    return all_rows("""SELECT a.id,a.data_hora,a.servico,a.status,b.nome barbeiro_nome
      FROM agendamentos a JOIN barbeiros b ON b.id=a.barbeiro_id
      WHERE a.barbearia_id=%s
        AND RIGHT(regexp_replace(a.cliente_telefone,'\\D','','g'),11)=RIGHT(%s,11)
        AND a.data_hora>=NOW()-INTERVAL '30 days' AND a.status<>'cancelado'
      ORDER BY (a.data_hora>=NOW()) DESC,a.data_hora DESC LIMIT 10""",(shop["id"],digits))
@app.post("/api/cliente/confirmar")
def confirm(data:ConfirmRequest):
    raise HTTPException(410,"Esta confirmação pública foi desativada")

@app.get("/api/produtos")
def products(user=Depends(current_user)): return all_rows("SELECT * FROM produtos WHERE barbearia_id=%s ORDER BY nome",(user["barbearia_id"],))
@app.post("/api/produtos",status_code=201)
def create_product(data:Product,user=Depends(current_user)): return one("INSERT INTO produtos(barbearia_id,nome,preco,quantidade_estoque) VALUES(%s,%s,%s,%s) RETURNING *",(user["barbearia_id"],data.nome,data.preco,data.quantidade_estoque))
@app.put("/api/produtos/{product_id}")
def update_product(product_id:int,data:Product,user=Depends(current_user)): return one("UPDATE produtos SET nome=%s,preco=%s,quantidade_estoque=%s WHERE id=%s AND barbearia_id=%s RETURNING *",(data.nome,data.preco,data.quantidade_estoque,product_id,user["barbearia_id"]))
@app.delete("/api/produtos/{product_id}")
def delete_product(product_id:int,user=Depends(current_user)):
    if not one("DELETE FROM produtos WHERE id=%s AND barbearia_id=%s RETURNING id",(product_id,user["barbearia_id"])): raise HTTPException(404,"Produto não encontrado")
    return {"ok":True}
@app.post("/api/agendamentos/{appointment_id}/adicionar-produto")
def sell_product(appointment_id:int,data:ProductSale,user=Depends(current_user)):
    with db() as cur:
        cur.execute("UPDATE produtos SET quantidade_estoque=quantidade_estoque-%s WHERE id=%s AND barbearia_id=%s AND quantidade_estoque>=%s RETURNING preco",(data.quantidade,data.produto_id,user["barbearia_id"],data.quantidade)); p=cur.fetchone()
        if not p: raise HTTPException(409,"Estoque insuficiente")
        cur.execute("INSERT INTO vendas_produto(agendamento_id,produto_id,quantidade,preco_unitario) VALUES(%s,%s,%s,%s) RETURNING *",(appointment_id,data.produto_id,data.quantidade,p["preco"])); return cur.fetchone()
@app.get("/api/agendamentos/{appointment_id}/produtos")
def appointment_products(appointment_id:int,user=Depends(current_user)): return all_rows("SELECT v.*,p.nome FROM vendas_produto v JOIN produtos p ON p.id=v.produto_id JOIN agendamentos a ON a.id=v.agendamento_id WHERE v.agendamento_id=%s AND a.barbearia_id=%s",(appointment_id,user["barbearia_id"]))

@app.get("/api/relatorios/dia")
def daily(data:date,user=Depends(current_user)): return {"data":data,"total":one("SELECT COALESCE(SUM(preco),0) total,COUNT(*) cortes FROM agendamentos WHERE barbearia_id=%s AND data_hora::date=%s AND status IN ('concluido','realizado')",(user["barbearia_id"],data)),"por_barbeiro":all_rows("SELECT b.nome,COUNT(a.id) cortes,COALESCE(SUM(a.preco),0) faturamento FROM barbeiros b LEFT JOIN agendamentos a ON a.barbeiro_id=b.id AND a.data_hora::date=%s AND a.status IN ('concluido','realizado') WHERE b.barbearia_id=%s GROUP BY b.id ORDER BY faturamento DESC",(data,user["barbearia_id"]))}
@app.get("/api/relatorios/mes")
def monthly(mes:int,ano:int,user=Depends(current_user)): return all_rows("SELECT data_hora::date data,COALESCE(SUM(preco),0) total FROM agendamentos WHERE barbearia_id=%s AND EXTRACT(MONTH FROM data_hora)=%s AND EXTRACT(YEAR FROM data_hora)=%s AND status IN ('concluido','realizado') GROUP BY 1 ORDER BY 1",(user["barbearia_id"],mes,ano))
@app.get("/api/relatorios/periodo")
def period_report(periodo:str=Query("mensal",pattern="^(mensal|anual)$"),mes:int=Query(1,ge=1,le=12),ano:int=Query(...,ge=2020,le=2100),user=Depends(current_user)):
    inicio=date(ano,mes,1) if periodo=="mensal" else date(ano,1,1)
    fim=(date(ano+1,1,1) if mes==12 else date(ano,mes+1,1)) if periodo=="mensal" else date(ano+1,1,1)
    bucket="day" if periodo=="mensal" else "month"
    pontos=all_rows(f"""SELECT date_trunc('{bucket}',data_hora)::date periodo,
        COUNT(*) atendimentos,COALESCE(SUM(preco),0) faturamento
        FROM agendamentos WHERE barbearia_id=%s AND data_hora>=%s AND data_hora<%s
        AND status IN ('concluido','realizado') GROUP BY 1 ORDER BY 1""",(user["barbearia_id"],inicio,fim))
    total=one("""SELECT COUNT(*) atendimentos,COALESCE(SUM(preco),0) faturamento,
        COALESCE(AVG(preco),0) ticket_medio FROM agendamentos
        WHERE barbearia_id=%s AND data_hora>=%s AND data_hora<%s
        AND status IN ('concluido','realizado')""",(user["barbearia_id"],inicio,fim))
    por_barbeiro=all_rows("""SELECT b.nome,COUNT(a.id) cortes,COALESCE(SUM(a.preco),0) faturamento
        FROM barbeiros b LEFT JOIN agendamentos a ON a.barbeiro_id=b.id AND a.data_hora>=%s
        AND a.data_hora<%s AND a.status IN ('concluido','realizado')
        WHERE b.barbearia_id=%s GROUP BY b.id ORDER BY faturamento DESC,b.nome""",(inicio,fim,user["barbearia_id"]))
    melhor=max(pontos,key=lambda item:item["atendimentos"],default=None)
    return {"periodo":periodo,"inicio":inicio,"fim":fim,"total":total,"pontos":pontos,
        "melhor_periodo":melhor,"por_barbeiro":por_barbeiro}
@app.get("/api/relatorios/barbeiro/{barber_id}")
def barber_report(barber_id:int,user=Depends(current_user)): return one("SELECT b.nome,b.comissao_percentual,COUNT(a.id) cortes,COALESCE(SUM(a.preco),0) faturamento,COALESCE(SUM(a.preco)*b.comissao_percentual/100,0) comissao FROM barbeiros b LEFT JOIN agendamentos a ON a.barbeiro_id=b.id AND a.status IN ('concluido','realizado') WHERE b.id=%s AND b.barbearia_id=%s GROUP BY b.id",(barber_id,user["barbearia_id"]))
@app.get("/api/relatorios/fidelidade")
def loyalty_report(user=Depends(current_user)): return all_rows("SELECT *,10-(total_cortes%%10) cortes_para_premio FROM fidelidade_cliente WHERE barbearia_id=%s ORDER BY total_cortes DESC",(user["barbearia_id"],))
@app.get("/api/fidelidade/{telefone}")
def loyalty(telefone:str,barbearia_id:int=1): return one("SELECT *,total_cortes%%10 saldo,10-(total_cortes%%10) cortes_para_premio FROM fidelidade_cliente WHERE barbearia_id=%s AND cliente_telefone=%s",(barbearia_id,telefone)) or {"total_cortes":0,"saldo":0,"cortes_para_premio":10}
@app.post("/api/fidelidade/registrar-corte")
def add_cut(data:Cut,user=Depends(current_user)): return one("INSERT INTO fidelidade_cliente(barbearia_id,cliente_telefone,cliente_nome,total_cortes) VALUES(%s,%s,%s,1) ON CONFLICT(barbearia_id,cliente_telefone) DO UPDATE SET total_cortes=fidelidade_cliente.total_cortes+1,cliente_nome=EXCLUDED.cliente_nome RETURNING *",(user["barbearia_id"],data.cliente_telefone,data.cliente_nome))

@app.post("/api/whatsapp/enviar-lembranca")
def whatsapp_reminder(agendamento_id:int,background_tasks:BackgroundTasks,user=Depends(current_user)):
    a=one("""UPDATE agendamentos SET whatsapp_autorizado=true,whatsapp_enviado=false,
        whatsapp_status='PENDENTE',whatsapp_erro=NULL,whatsapp_proxima_tentativa=NOW()
        WHERE id=%s AND barbearia_id=%s AND NOT whatsapp_enviado RETURNING id""",(agendamento_id,user['barbearia_id']))
    if not a: raise HTTPException(404,"Agendamento não encontrado")
    dispatch_whatsapp(background_tasks)
    return {"enfileirado":True,"agendamento_id":agendamento_id}

@app.get("/api/internal/whatsapp/processar",include_in_schema=False)
def process_whatsapp_queue(request:Request):
    expected=os.getenv("CRON_SECRET","").strip()
    provided=request.headers.get("authorization","")
    if not expected or provided != f"Bearer {expected}":
        raise HTTPException(401,"Acesso recusado")
    processed=0
    while processed < 10 and whatsapp_worker.process_next():
        processed+=1
    return {"processados":processed}

@app.get("/api/whatsapp/webhook")
def verify_whatsapp_webhook(
    mode: str = Query(default="", alias="hub.mode"),
    verify_token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge"),
):
    expected=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN","")
    if mode != "subscribe" or not expected or verify_token != expected:
        raise HTTPException(401,"Verificação do webhook recusada")
    return Response(content=challenge,media_type="text/plain")

@app.post("/api/whatsapp/webhook")
async def whatsapp_webhook(request:Request):
    body=await request.body()
    signature=request.headers.get("x-hub-signature-256","")
    if not verify_webhook_signature(body,signature,os.getenv("WHATSAPP_APP_SECRET","")):
        raise HTTPException(401,"Assinatura do webhook inválida")
    try: payload=json.loads(body)
    except json.JSONDecodeError: raise HTTPException(400,"Payload inválido")
    status_map={"sent":"ENVIADO","delivered":"ENTREGUE","read":"LIDO","failed":"FALHOU"}
    updated=0
    for entry in payload.get("entry",[]):
        for change in entry.get("changes",[]):
            for item in change.get("value",{}).get("statuses",[]):
                message_id=item.get("id"); status=status_map.get(item.get("status"))
                if not message_id or not status: continue
                error_title=((item.get("errors") or [{}])[0].get("title") or "")[:300] or None
                row=one("""UPDATE agendamentos SET whatsapp_status=%s,whatsapp_erro=%s
                    WHERE whatsapp_message_id=%s RETURNING id""",(status,error_title,message_id))
                updated+=bool(row)
    return {"recebido":True,"atualizados":updated}

@app.get("/agendar/{slug}",include_in_schema=False)
def booking_page(slug:str):
    return FileResponse(static/'cliente.html')

@app.get("/",include_in_schema=False)
def landing_page():
    return FileResponse(static/'landing.html')

@app.get("/painel",include_in_schema=False)
def dashboard_page():
    return FileResponse(static/'index.html')

app.mount('/',StaticFiles(directory=static,html=True),name='frontend')
