import hashlib, json, logging, os, secrets, time as time_module
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from uuid import uuid4
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError
from psycopg2 import IntegrityError
from .database import all_rows, db, one
from .schemas import *
from .security import (
    authenticated_user,
    current_user,
    decode_oidc_state,
    hash_password,
    oidc_state,
    token,
    verify_password,
)
from .services.whatsapp import verify_webhook_signature
from .services.whatsapp_worker import whatsapp_worker
from .services.email import (
    send_account_verification,
    send_appointment_confirmation,
    send_owner_notification,
    send_password_reset,
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
auth_hits = defaultdict(deque)
AUTH_RATE_LIMITS = {
    "/api/auth/register": (5, 600),
    "/api/auth/login": (10, 300),
    "/api/auth/reenviar-confirmacao": (5, 900),
    "/api/auth/esqueci-senha": (5, 900),
    "/api/auth/redefinir-senha": (10, 900),
    "/api/auth/confirmar-sessao": (10, 600),
}
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
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_login_token_hash VARCHAR(64)")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_login_expires_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_reset_token_hash VARCHAR(64)")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 1")
        cur.execute("""CREATE TABLE IF NOT EXISTS cadastros_pendentes (
            id SERIAL PRIMARY KEY,
            email VARCHAR(160) UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            nome VARCHAR(120) NOT NULL,
            telefone VARCHAR(30),
            barbearia_nome VARCHAR(160) NOT NULL,
            plano VARCHAR(24) NOT NULL,
            email_verificado BOOLEAN NOT NULL DEFAULT FALSE,
            email_verification_token_hash VARCHAR(64),
            email_verification_expires_at TIMESTAMPTZ,
            checkout_token_hash VARCHAR(64),
            checkout_token_expires_at TIMESTAMPTZ,
            stripe_checkout_session_id VARCHAR(160),
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            concluido_em TIMESTAMPTZ,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        cur.execute("""ALTER TABLE cadastros_pendentes
            ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending_email'""")
        cur.execute("""ALTER TABLE cadastros_pendentes
            ADD COLUMN IF NOT EXISTS checkout_idempotency_key VARCHAR(64)""")
        cur.execute("""CREATE INDEX IF NOT EXISTS idx_cadastros_pendentes_status
            ON cadastros_pendentes(status) WHERE usuario_id IS NULL""")
        cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_cadastros_pendentes_checkout_session
            ON cadastros_pendentes(stripe_checkout_session_id)
            WHERE stripe_checkout_session_id IS NOT NULL""")
        cur.execute("""CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id VARCHAR(255) PRIMARY KEY,
            event_type VARCHAR(120) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'processing',
            attempts INTEGER NOT NULL DEFAULT 1,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        cur.execute("""UPDATE cadastros_pendentes SET status=CASE
            WHEN usuario_id IS NOT NULL THEN 'paid'
            WHEN stripe_checkout_session_id IS NOT NULL THEN 'checkout_created'
            WHEN email_verificado THEN 'email_verified'
            ELSE 'pending_email' END
            WHERE status IS NULL OR status NOT IN (
                'pending_email','email_verified','checkout_created','paid',
                'payment_failed','checkout_expired'
            )""")
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
    now = time_module.time()
    bucket = hits[ip]
    while bucket and bucket[0] < now - 60: bucket.popleft()
    if len(bucket) >= 100:
        return JSONResponse(
            {"detail": "Limite de requisições excedido"},
            429,
            headers={"Retry-After": "60"},
        )
    bucket.append(now)
    auth_limit = AUTH_RATE_LIMITS.get(request.url.path)
    if auth_limit and request.method == "POST":
        limit, window = auth_limit
        auth_bucket = auth_hits[(ip, request.url.path)]
        while auth_bucket and auth_bucket[0] < now - window:
            auth_bucket.popleft()
        if len(auth_bucket) >= limit:
            retry_after = max(1, int(window - (now - auth_bucket[0])))
            return JSONResponse(
                {"detail": "Muitas tentativas. Aguarde antes de tentar novamente."},
                429,
                headers={"Retry-After": str(retry_after)},
            )
        auth_bucket.append(now)
    response = await call_next(request)
    sensitive_auth_response = (
        request.url.path in {
            "/api/auth/redefinir-senha",
            "/api/auth/verificar-email",
            "/api/auth/google/callback",
        }
        or "reset_password" in request.query_params
    )
    csp = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self' https://checkout.stripe.com; "
        "script-src 'self' https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com; "
        "frame-src https://accounts.google.com https://js.stripe.com https://hooks.stripe.com"
    )
    if is_vercel():
        csp += "; upgrade-insecure-requests"
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer" if sensitive_auth_response else "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": csp,
    })
    if sensitive_auth_response:
        response.headers["Cache-Control"] = "no-store"
    return response

def _env_configured(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _stripe_mode() -> str:
    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    valid = len(secret) >= 24 and "..." not in secret and not any(char.isspace() for char in secret)
    if valid and secret.startswith("sk_live_"):
        return "live"
    if valid and secret.startswith("sk_test_"):
        return "test"
    return "unconfigured"


def _google_oauth_settings() -> dict | None:
    settings = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", "").strip(),
    }
    if not all(settings.values()):
        return None
    if any("..." in value or "troque" in value.lower() for value in settings.values()):
        return None
    parsed = urlparse(settings["redirect_uri"])
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        not parsed.netloc
        or parsed.path != "/api/auth/google/callback"
        or parsed.query
        or parsed.fragment
        or (is_vercel() and parsed.scheme != "https")
        or (parsed.scheme != "https" and not local_http)
    ):
        return None
    public_base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base:
        public = urlparse(public_base)
        if (parsed.scheme, parsed.netloc) != (public.scheme, public.netloc):
            return None
    return settings


def _configuration_status() -> dict:
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    google_redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    google_redirect = urlparse(google_redirect_uri)
    google_public_base = urlparse(os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"))
    google_redirect_valid = (
        bool(google_redirect.netloc)
        and google_redirect.scheme == "https"
        and google_redirect.path == "/api/auth/google/callback"
        and not google_redirect.query
        and not google_redirect.fragment
    )
    google_public_base_matches = (
        not google_public_base.netloc
        or (google_redirect.scheme, google_redirect.netloc)
        == (google_public_base.scheme, google_public_base.netloc)
    )
    webhook_configured = (
        os.getenv("STRIPE_WEBHOOK_SECRET", "").strip().startswith("whsec_")
        and len(os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()) >= 16
        and "..." not in os.getenv("STRIPE_WEBHOOK_SECRET", "")
    )
    stripe_prices = {
        plan: (
            os.getenv(config["price_env"], "").strip().startswith("price_")
            and len(os.getenv(config["price_env"], "").strip()) >= 12
            and "..." not in os.getenv(config["price_env"], "")
        )
        for plan, config in STRIPE_PLANS.items()
    }
    return {
        "stripe": {
            "configured": (
                _stripe_mode() != "unconfigured"
                and webhook_configured
                and all(stripe_prices.values())
            ),
            "live_mode": _stripe_mode() == "live",
            "webhook_configured": webhook_configured,
            "prices_configured": stripe_prices,
        },
        "email": {
            "configured": (
                os.getenv("RESEND_API_KEY", "").strip().startswith("re_")
                and _env_configured("EMAIL_FROM")
            ),
        },
        "google_oauth": {
            "configured": _google_oauth_settings() is not None,
            "client_id_configured": bool(google_client_id),
            "client_secret_configured": bool(google_client_secret),
            "redirect_uri_configured": bool(google_redirect_uri),
            "redirect_uri_valid": google_redirect_valid,
            "redirect_scheme_valid": google_redirect.scheme == "https",
            "redirect_host_present": bool(google_redirect.netloc),
            "redirect_path_valid": google_redirect.path == "/api/auth/google/callback",
            "redirect_query_empty": not google_redirect.query,
            "redirect_fragment_empty": not google_redirect.fragment,
            "public_base_matches": google_public_base_matches,
        },
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/config/status")
def configuration_status():
    """Expõe somente prontidão operacional; nunca retorna valores de credenciais."""
    return _configuration_status()


GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_OIDC_SCOPES = "openid email profile"
GOOGLE_STATE_COOKIE = "cortaflow_oidc_state"


def _google_json_request(request: UrlRequest) -> dict:
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        logging.warning("Google OIDC request failed: %s", type(error).__name__)
        raise HTTPException(502, "Não foi possível validar o acesso com o Google.") from error


@app.get("/api/auth/google/iniciar")
def start_google_oidc():
    settings = _google_oauth_settings()
    if not settings:
        raise HTTPException(503, "Login com Google ainda não está configurado.")
    nonce = secrets.token_urlsafe(32)
    state = oidc_state(nonce)
    query = urlencode({
        "client_id": settings["client_id"],
        "redirect_uri": settings["redirect_uri"],
        "response_type": "code",
        "scope": GOOGLE_OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    })
    response = RedirectResponse(f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}", status_code=302)
    response.set_cookie(
        GOOGLE_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=urlparse(settings["redirect_uri"]).scheme == "https",
        samesite="lax",
        path="/api/auth/google",
    )
    return response


@app.get("/api/auth/google/callback")
def google_oidc_callback(
    request: Request,
    code: str = Query(min_length=8, max_length=2048),
    state: str = Query(min_length=20, max_length=4096),
):
    settings = _google_oauth_settings()
    if not settings:
        raise HTTPException(503, "Login com Google ainda não está configurado.")
    cookie_state = request.cookies.get(GOOGLE_STATE_COOKIE, "")
    if not cookie_state or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(400, "State OAuth inválido ou expirado.")
    try:
        state_claims = decode_oidc_state(state)
    except JWTError as error:
        raise HTTPException(400, "State OAuth inválido ou expirado.") from error
    token_request = UrlRequest(
        GOOGLE_TOKEN_ENDPOINT,
        data=urlencode({
            "code": code,
            "client_id": settings["client_id"],
            "client_secret": settings["client_secret"],
            "redirect_uri": settings["redirect_uri"],
            "grant_type": "authorization_code",
        }).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token_data = _google_json_request(token_request)
    id_token = str(token_data.get("id_token") or "")
    if not id_token:
        raise HTTPException(502, "O Google não retornou uma identidade válida.")
    identity_request = UrlRequest(
        f"{GOOGLE_TOKENINFO_ENDPOINT}?{urlencode({'id_token': id_token})}",
        headers={"Accept": "application/json"},
    )
    identity = _google_json_request(identity_request)
    try:
        identity_expires_at = int(identity.get("exp") or 0)
    except (TypeError, ValueError):
        identity_expires_at = 0
    valid_identity = all((
        identity.get("iss") in {"https://accounts.google.com", "accounts.google.com"},
        secrets.compare_digest(str(identity.get("aud") or ""), settings["client_id"]),
        secrets.compare_digest(str(identity.get("nonce") or ""), state_claims["nonce"]),
        str(identity.get("email_verified", "")).lower() == "true",
        identity_expires_at > int(time_module.time()),
    ))
    if not valid_identity:
        raise HTTPException(401, "Identidade Google inválida ou expirada.")
    email = str(identity.get("email") or "").strip().lower()
    user = one("""SELECT u.id,u.email,u.nome,b.subscription_plan
        FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id
        WHERE u.email=%s AND u.email_verificado""", (email,))
    if not user:
        response = RedirectResponse("/?google=conta_nao_encontrada", status_code=303)
        response.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth/google")
        return response
    login_code = secrets.token_urlsafe(32)
    login_hash = hashlib.sha256(login_code.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    one("""UPDATE usuarios SET email_login_token_hash=%s,email_login_expires_at=%s
        WHERE id=%s RETURNING id""", (login_hash, expires_at, user["id"]))
    query = urlencode({
        "email_confirmado": "sucesso",
        "email": user["email"],
        "plan": user["subscription_plan"] or "",
        "code": login_code,
    })
    response = RedirectResponse(f"/?{query}", status_code=303)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/api/auth/google")
    return response


STRIPE_PLANS = {
    "essencial": {"name": "CortaFlow Essencial", "amount": 2990, "price_env": "STRIPE_PRICE_ESSENCIAL"},
    "profissional": {"name": "CortaFlow Profissional", "amount": 4490, "price_env": "STRIPE_PRICE_PROFISSIONAL"},
    "premium": {"name": "CortaFlow Premium", "amount": 6490, "price_env": "STRIPE_PRICE_PREMIUM"},
}

def _public_site_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    site_url = configured or str(request.base_url).rstrip("/")
    parsed = urlparse(site_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(503, "PUBLIC_BASE_URL possui formato inválido.")
    if is_vercel() and parsed.scheme != "https":
        raise HTTPException(503, "PUBLIC_BASE_URL precisa usar HTTPS em produção.")
    return site_url


@app.post("/api/billing/checkout")
def create_checkout(data: CheckoutRequest, request: Request, user=Depends(authenticated_user)):
    """Cria um Checkout recorrente usando apenas preços cadastrados na Stripe."""
    plan = data.plan
    stripe = _stripe_client()
    site_url = _public_site_url(request)
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
                idempotency_key=f"shop-customer-{shop['id']}",
            )
            customer_id = customer.id
            one("UPDATE barbearias SET stripe_customer_id=%s WHERE id=%s RETURNING id",
                (customer_id, shop["id"]))
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user["id"]),
            line_items=[_stripe_line_item(plan)],
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
    secret = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if _stripe_mode() == "unconfigured":
        raise HTTPException(503, "Stripe ainda não está configurada.")
    stripe.api_key = secret
    return stripe

def _stripe_line_item(plan: str):
    plan_data = STRIPE_PLANS.get(plan)
    if not plan_data:
        raise HTTPException(422, "Plano inválido.")
    price_id = os.getenv(plan_data["price_env"], "").strip()
    if not price_id.startswith("price_") or len(price_id) < 12 or "..." in price_id:
        raise HTTPException(503, f"Preço do plano {plan} não configurado na Stripe.")
    return {"price": price_id, "quantity": 1}

def _create_pending_checkout(pending, request: Request):
    stripe = _stripe_client()
    plan = pending["plano"]
    site_url = _public_site_url(request)
    idempotency_key = pending.get("checkout_idempotency_key") or secrets.token_hex(24)
    if not pending.get("checkout_idempotency_key"):
        one("""UPDATE cadastros_pendentes SET checkout_idempotency_key=%s,atualizado_em=NOW()
            WHERE id=%s RETURNING id""", (idempotency_key, pending["id"]))
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=pending["email"],
            client_reference_id=f"pending:{pending['id']}",
            line_items=[_stripe_line_item(plan)],
            success_url=f"{site_url}/?checkout=sucesso&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{site_url}/?checkout=cancelado",
            allow_promotion_codes=True,
            metadata={"plan": plan, "pending_signup_id": str(pending["id"])},
            subscription_data={"metadata": {"plan": plan, "pending_signup_id": str(pending["id"])}},
            idempotency_key=f"pending-checkout-{pending['id']}-{idempotency_key}",
        )
    except stripe.error.StripeError as error:
        logging.exception("Stripe pending checkout error")
        raise HTTPException(502, "Não foi possível abrir o checkout agora.") from error
    one("""UPDATE cadastros_pendentes SET stripe_checkout_session_id=%s,
        status='checkout_created',atualizado_em=NOW()
        WHERE id=%s AND usuario_id IS NULL RETURNING id""", (session.id, pending["id"]))
    return session

def _timestamp(value):
    return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None

def _metadata_shop_id(metadata) -> int:
    try:
        return int((metadata or {}).get("barbearia_id") or 0)
    except (TypeError, ValueError):
        return 0

def _metadata_pending_id(metadata) -> int:
    try:
        return int((metadata or {}).get("pending_signup_id") or 0)
    except (TypeError, ValueError):
        return 0


def _checkout_matches_pending(pending, session, subscription) -> bool:
    metadata = session.get("metadata") or {}
    subscription_status = str(subscription.get("status") or "")
    return all((
        bool(pending.get("email_verificado")),
        str(pending.get("stripe_checkout_session_id") or "") == str(session.get("id") or ""),
        str(session.get("client_reference_id") or "") == f"pending:{pending['id']}",
        session.get("mode") == "subscription",
        session.get("payment_status") in {"paid", "no_payment_required"},
        _metadata_pending_id(metadata) == pending["id"],
        metadata.get("plan") == pending.get("plano"),
        subscription_status in {"active", "trialing"},
    ))


def _activate_pending_signup(pending_id: int, session, subscription):
    with db() as cur:
        cur.execute("SELECT * FROM cadastros_pendentes WHERE id=%s FOR UPDATE", (pending_id,))
        pending = cur.fetchone()
        if not pending:
            return None
        if not _checkout_matches_pending(pending, session, subscription):
            return None
        if pending["usuario_id"]:
            cur.execute("""SELECT u.id,u.email,u.nome,b.id barbearia_id
                FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id WHERE u.id=%s""",
                (pending["usuario_id"],))
            return cur.fetchone()
        status = str(subscription.get("status"))
        cur.execute("""INSERT INTO usuarios(email,senha_hash,nome,telefone,email_verificado)
            VALUES(%s,%s,%s,%s,TRUE) RETURNING id""",
            (pending["email"], pending["senha_hash"], pending["nome"], pending["telefone"]))
        user_id = cur.fetchone()["id"]
        shop_slug = unique_shop_slug(cur, pending["barbearia_nome"])
        cur.execute("""INSERT INTO barbearias(usuario_id,nome,slug,telefone,plano_ativo,
            subscription_status,subscription_plan,stripe_customer_id,stripe_subscription_id,
            subscription_current_period_end,subscription_cancel_at_period_end,data_assinatura)
            VALUES(%s,%s,%s,%s,TRUE,%s,%s,%s,%s,%s,%s,CURRENT_DATE) RETURNING id""",
            (user_id, pending["barbearia_nome"], shop_slug, pending["telefone"], status,
             pending["plano"], session.get("customer"), subscription.get("id"),
             _timestamp(subscription.get("current_period_end")),
             bool(subscription.get("cancel_at_period_end"))))
        shop_id = cur.fetchone()["id"]
        cur.execute("""INSERT INTO horarios_funcionamento(barbearia_id,dia_semana,hora_inicio,hora_fim)
            SELECT %s,d,'09:00','19:00' FROM generate_series(0,5) d""", (shop_id,))
        cur.execute("""INSERT INTO servicos(barbearia_id,nome,descricao,duracao_minutos,preco,imagem_url) VALUES
          (%s,'Corte Degradê','Degradê com acabamento completo',40,30,'/assets/service-degrade.webp'),
          (%s,'Corte Social','Corte clássico com acabamento',30,25,'/assets/service-social.webp'),
          (%s,'Corte + Barba','Corte completo e barba alinhada',60,50,'/assets/service-combo.webp'),
          (%s,'Sobrancelha','Design e acabamento de sobrancelha',15,10,'/assets/service-sobrancelha.webp')""",
          (shop_id, shop_id, shop_id, shop_id))
        cur.execute("""UPDATE cadastros_pendentes SET usuario_id=%s,concluido_em=NOW(),
            checkout_token_hash=NULL,checkout_token_expires_at=NULL,status='paid',atualizado_em=NOW()
            WHERE id=%s""", (user_id, pending_id))
        return {"id": user_id, "email": pending["email"], "nome": pending["nome"], "barbearia_id": shop_id}

def _link_stripe_metadata(stripe, session, subscription, created, plan: str):
    try:
        stripe.Subscription.modify(
            subscription.get("id"),
            metadata={"plan": plan, "barbearia_id": str(created["barbearia_id"])},
        )
        if session.get("customer"):
            stripe.Customer.modify(
                session.get("customer"),
                metadata={"barbearia_id": str(created["barbearia_id"]), "usuario_id": str(created["id"])},
            )
    except stripe.error.StripeError:
        logging.exception("Stripe metadata link failed for shop %s", created["barbearia_id"])

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
def confirm_checkout(data: CheckoutSessionRequest, user=Depends(authenticated_user)):
    session_id = data.session_id
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
    status = str(subscription.get("status") or "")
    if status not in {"active", "trialing"}:
        raise HTTPException(409, "A assinatura ainda não está ativa na Stripe.")
    _save_stripe_subscription(user["barbearia_id"], subscription, metadata.get("plan"))
    _send_subscription_email_once(
        user["barbearia_id"], metadata.get("plan"), subscription.get("current_period_end")
    )
    return {"active": True, "plan": metadata.get("plan"), "status": status}

@app.post("/api/billing/portal")
def billing_portal(request: Request, user=Depends(authenticated_user)):
    stripe = _stripe_client()
    shop = one("SELECT stripe_customer_id FROM barbearias WHERE id=%s", (user["barbearia_id"],))
    if not shop["stripe_customer_id"]:
        raise HTTPException(422, "Conclua sua primeira assinatura antes de gerenciá-la.")
    try:
        session = stripe.billing_portal.Session.create(
            customer=shop["stripe_customer_id"],
            return_url=f"{_public_site_url(request)}/painel",
        )
    except stripe.error.StripeError as error:
        raise HTTPException(502, "Não foi possível abrir o portal da assinatura.") from error
    return {"url": session.url}


def _claim_stripe_event(event_id: str, event_type: str) -> bool:
    with db() as cur:
        cur.execute("""INSERT INTO stripe_webhook_events(event_id,event_type)
            VALUES(%s,%s)
            ON CONFLICT(event_id) DO UPDATE SET
                status='processing',attempts=stripe_webhook_events.attempts+1,
                last_error=NULL,updated_at=NOW()
            WHERE stripe_webhook_events.status='failed'
               OR (stripe_webhook_events.status='processing'
                   AND stripe_webhook_events.updated_at < NOW() - INTERVAL '5 minutes')
            RETURNING event_id""", (event_id, event_type))
        return cur.fetchone() is not None


def _finish_stripe_event(event_id: str) -> None:
    one("""UPDATE stripe_webhook_events SET status='completed',processed_at=NOW(),
        last_error=NULL,updated_at=NOW() WHERE event_id=%s RETURNING event_id""", (event_id,))


def _fail_stripe_event(event_id: str, error: Exception) -> None:
    error_name = type(error).__name__[:120]
    one("""UPDATE stripe_webhook_events SET status='failed',last_error=%s,
        updated_at=NOW() WHERE event_id=%s RETURNING event_id""", (error_name, event_id))


def _process_stripe_event(stripe, event_type: str, obj) -> None:
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        if obj.get("mode") != "subscription":
            return
        if obj.get("payment_status") not in {"paid", "no_payment_required"}:
            return
        metadata = obj.get("metadata") or {}
        pending_id = _metadata_pending_id(metadata)
        shop_id = _metadata_shop_id(metadata)
        subscription_id = obj.get("subscription")
        if pending_id and subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            created = _activate_pending_signup(pending_id, obj, subscription)
            if created:
                _link_stripe_metadata(stripe, obj, subscription, created, metadata.get("plan", ""))
                _send_subscription_email_once(
                    created["barbearia_id"], metadata.get("plan"),
                    subscription.get("current_period_end"),
                )
        elif shop_id and subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            _save_stripe_subscription(shop_id, subscription, metadata.get("plan"))
            _send_subscription_email_once(
                shop_id, metadata.get("plan"), subscription.get("current_period_end")
            )
    elif event_type in {
        "checkout.session.expired",
        "checkout.session.async_payment_failed",
    }:
        pending_id = _metadata_pending_id(obj.get("metadata") or {})
        if pending_id:
            status = (
                "checkout_expired"
                if event_type == "checkout.session.expired"
                else "payment_failed"
            )
            one("""UPDATE cadastros_pendentes SET status=%s,atualizado_em=NOW()
                WHERE id=%s AND usuario_id IS NULL
                AND stripe_checkout_session_id=%s RETURNING id""",
                (status, pending_id, obj.get("id")))
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }:
        metadata = obj.get("metadata") or {}
        shop_id = _metadata_shop_id(metadata)
        if not shop_id:
            shop = one(
                "SELECT id FROM barbearias WHERE stripe_subscription_id=%s",
                (obj.get("id"),),
            )
            shop_id = shop["id"] if shop else 0
        if shop_id:
            _save_stripe_subscription(shop_id, obj)
    elif event_type in {"invoice.payment_failed", "invoice.payment_succeeded"}:
        subscription_id = obj.get("subscription")
        if subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            shop = one(
                "SELECT id FROM barbearias WHERE stripe_subscription_id=%s",
                (subscription_id,),
            )
            if shop:
                _save_stripe_subscription(shop["id"], subscription)
        elif event_type == "invoice.payment_failed":
            one("""UPDATE barbearias SET plano_ativo=FALSE,subscription_status='past_due'
                WHERE stripe_customer_id=%s RETURNING id""", (obj.get("customer"),))


@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    stripe = _stripe_client()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if (
        not webhook_secret
        or not webhook_secret.startswith("whsec_")
        or len(webhook_secret) < 16
        or "..." in webhook_secret
    ):
        raise HTTPException(503, "Webhook da Stripe não configurado.")
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, request.headers.get("stripe-signature", ""), webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as error:
        raise HTTPException(400, "Assinatura do webhook inválida.") from error
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id.startswith("evt_") or not event_type:
        raise HTTPException(400, "Evento Stripe inválido.")
    if not _claim_stripe_event(event_id, event_type):
        return {"received": True, "duplicate": True}
    try:
        _process_stripe_event(stripe, event_type, event["data"]["object"])
    except Exception as error:
        _fail_stripe_event(event_id, error)
        if isinstance(error, HTTPException):
            raise
        logging.exception("Stripe webhook processing failed event_id=%s type=%s", event_id, event_type)
        raise HTTPException(502, "Falha temporária ao processar evento Stripe.") from error
    _finish_stripe_event(event_id)
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

def _new_secure_token(ttl: timedelta) -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash, datetime.now(timezone.utc) + ttl


def _new_email_verification() -> tuple[str, str, datetime]:
    return _new_secure_token(timedelta(hours=24))


def _new_password_reset() -> tuple[str, str, datetime]:
    return _new_secure_token(timedelta(minutes=30))


@app.post("/api/auth/register", status_code=201)
def register(data: Register):
    if one("SELECT id FROM usuarios WHERE email=%s", (data.email.lower(),)):
        raise HTTPException(409, "Este e-mail já possui uma conta. Entre com sua senha para continuar.")
    raw_token, token_hash, expires_at = _new_email_verification()
    existing_pending = one("""SELECT id,email,nome,plano FROM cadastros_pendentes
        WHERE email=%s AND usuario_id IS NULL""", (data.email.lower(),))
    if existing_pending:
        one("""UPDATE cadastros_pendentes SET email_verificado=FALSE,
            email_verification_token_hash=%s,email_verification_expires_at=%s,
            checkout_token_hash=NULL,checkout_token_expires_at=NULL,
            status=CASE WHEN stripe_checkout_session_id IS NULL
                THEN 'pending_email' ELSE status END,atualizado_em=NOW()
            WHERE id=%s RETURNING id""", (token_hash, expires_at, existing_pending["id"]))
        sent = send_account_verification(
            existing_pending["email"], existing_pending["nome"], raw_token)
        return {
            "requires_email_verification": True,
            "email_sent": sent,
            "existing_pending_account": True,
            "plan": existing_pending["plano"],
            "message": "Seu cadastro ainda aguarda pagamento. Enviamos um novo link seguro.",
        }
    pending = one("""INSERT INTO cadastros_pendentes(
        email,senha_hash,nome,telefone,barbearia_nome,plano,email_verificado,
        email_verification_token_hash,email_verification_expires_at,status,atualizado_em)
        VALUES(%s,%s,%s,%s,%s,%s,FALSE,%s,%s,'pending_email',NOW()) RETURNING id""",
        (data.email.lower(), hash_password(data.senha), data.nome, data.telefone,
         data.barbearia_nome, data.plano, token_hash, expires_at))
    if not pending:
        raise HTTPException(409, "Este e-mail já concluiu um cadastro. Entre com sua senha.")
    sent = send_account_verification(data.email.lower(), data.nome, raw_token)
    return {
        "requires_email_verification": True,
        "email_sent": sent,
        "plan": data.plano,
        "message": "Enviamos um link de confirmação para seu Gmail."
            if sent else "Cadastro iniciado. Use reenviar para confirmar seu e-mail.",
    }

@app.post("/api/auth/login")
def login(data: Login):
    user=one("""SELECT u.*,b.plano_ativo,b.subscription_plan,b.subscription_status
        FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id WHERE u.email=%s""",(data.email.lower(),))
    if not user or not verify_password(data.senha,user["senha_hash"]): raise HTTPException(401,"E-mail ou senha inválidos")
    if not user.get("email_verificado"):
        raise HTTPException(403,"Confirme seu e-mail antes de entrar. Confira também a caixa de spam.")
    return {"access_token":token(user["id"], user.get("auth_version", 1)),"token_type":"bearer","nome":user["nome"],
        "subscription_required":not bool(user["plano_ativo"]),
        "subscription_plan":user["subscription_plan"],
        "subscription_status":user["subscription_status"]}


@app.post("/api/auth/reenviar-confirmacao")
def resend_email_verification(data: ResendVerification):
    pending = one("""SELECT id,email,nome,email_verificado FROM cadastros_pendentes
        WHERE email=%s AND usuario_id IS NULL""", (data.email.lower(),))
    if pending and not pending["email_verificado"]:
        raw_token, token_hash, expires_at = _new_email_verification()
        one("""UPDATE cadastros_pendentes SET email_verification_token_hash=%s,
            email_verification_expires_at=%s,
            status=CASE WHEN stripe_checkout_session_id IS NULL
                THEN 'pending_email' ELSE status END,atualizado_em=NOW()
            WHERE id=%s RETURNING id""", (token_hash, expires_at, pending["id"]))
        send_account_verification(pending["email"], pending["nome"], raw_token)
    else:
        user = one("SELECT id,email,nome,email_verificado FROM usuarios WHERE email=%s", (data.email.lower(),))
        if user and not user["email_verificado"]:
            raw_token, token_hash, expires_at = _new_email_verification()
            one("""UPDATE usuarios SET email_verification_token_hash=%s,email_verification_expires_at=%s
                WHERE id=%s RETURNING id""", (token_hash, expires_at, user["id"]))
            send_account_verification(user["email"], user["nome"], raw_token)
    return {"message":"Se existir uma conta pendente, enviaremos um novo link de confirmação."}


@app.post("/api/auth/esqueci-senha")
def forgot_password(data: ForgotPassword):
    user = one("SELECT id,email,nome,email_verificado FROM usuarios WHERE email=%s", (data.email.lower(),))
    if user and user["email_verificado"]:
        raw_token, token_hash, expires_at = _new_password_reset()
        one("""UPDATE usuarios SET password_reset_token_hash=%s,password_reset_expires_at=%s
            WHERE id=%s RETURNING id""", (token_hash, expires_at, user["id"]))
        send_password_reset(user["email"], user["nome"], raw_token)
    return {"message": "Se esse e-mail estiver cadastrado, enviaremos um link para criar uma nova senha."}


@app.get("/api/auth/redefinir-senha")
def password_reset_page(token: str = Query(min_length=20, max_length=200)):
    return RedirectResponse(url=f"/?reset_password={quote(token)}", status_code=303)


@app.post("/api/auth/redefinir-senha")
def reset_password(data: ResetPassword):
    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    user = one("""UPDATE usuarios SET senha_hash=%s,password_reset_token_hash=NULL,
        password_reset_expires_at=NULL,auth_version=auth_version+1
        WHERE password_reset_token_hash=%s
        AND password_reset_expires_at>NOW() RETURNING id,email""",
        (hash_password(data.senha), token_hash))
    if not user:
        raise HTTPException(400, "Este link de recuperação é inválido ou expirou.")
    return {"message": "Senha atualizada com sucesso. Você já pode entrar."}


@app.get("/api/auth/verificar-email")
def verify_account_email(token: str = Query(min_length=20, max_length=200)):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login_code = secrets.token_urlsafe(32)
    login_hash = hashlib.sha256(login_code.encode()).hexdigest()
    login_expires_at = datetime.now().astimezone() + timedelta(minutes=10)
    checkout_idempotency_key = secrets.token_hex(24)
    pending = one("""UPDATE cadastros_pendentes SET email_verificado=TRUE,
        email_verification_token_hash=NULL,email_verification_expires_at=NULL,
        checkout_token_hash=%s,checkout_token_expires_at=%s,status='email_verified',
        checkout_idempotency_key=COALESCE(checkout_idempotency_key,%s),atualizado_em=NOW()
        WHERE email_verification_token_hash=%s AND email_verification_expires_at>NOW()
        AND usuario_id IS NULL RETURNING id,email,plano""",
        (login_hash, login_expires_at, checkout_idempotency_key, token_hash))
    if pending:
        return RedirectResponse(
            url=f"/?email_confirmado=sucesso&email={quote(pending['email'])}"
                f"&plan={pending['plano']}&code={quote(login_code)}",
            status_code=303,
        )
    user = one("""UPDATE usuarios SET email_verificado=TRUE,email_verification_token_hash=NULL,
        email_verification_expires_at=NULL,email_login_token_hash=%s,email_login_expires_at=%s
        WHERE email_verification_token_hash=%s
        AND email_verification_expires_at>NOW() AND NOT email_verificado RETURNING id,email""",
        (login_hash, login_expires_at, token_hash))
    status = "sucesso" if user else "invalido"
    email = f"&email={quote(user['email'])}" if user else ""
    shop = one("SELECT subscription_plan FROM barbearias WHERE usuario_id=%s", (user["id"],)) if user else None
    selected_plan = shop["subscription_plan"] if shop and shop["subscription_plan"] in STRIPE_PLANS else ""
    plan = f"&plan={selected_plan}" if selected_plan else ""
    code = f"&code={quote(login_code)}" if user else ""
    return RedirectResponse(url=f"/?email_confirmado={status}{email}{plan}{code}", status_code=303)

@app.post("/api/auth/confirmar-sessao")
def confirm_verification_session(data: VerificationSession, request: Request):
    code_hash = hashlib.sha256(data.code.encode()).hexdigest()
    pending = one("""SELECT * FROM cadastros_pendentes
        WHERE checkout_token_hash=%s AND checkout_token_expires_at>NOW()
        AND email_verificado AND usuario_id IS NULL""", (code_hash,))
    if pending:
        session = _create_pending_checkout(pending, request)
        one("""UPDATE cadastros_pendentes SET checkout_token_hash=NULL,
            checkout_token_expires_at=NULL,atualizado_em=NOW()
            WHERE id=%s AND checkout_token_hash=%s RETURNING id""",
            (pending["id"], code_hash))
        return {"checkout_url": session.url, "subscription_plan": pending["plano"]}
    user = one("""UPDATE usuarios SET email_login_token_hash=NULL,email_login_expires_at=NULL
        WHERE email_login_token_hash=%s AND email_login_expires_at>NOW()
        RETURNING id,nome,auth_version""", (code_hash,))
    if not user:
        raise HTTPException(401, "Este acesso de confirmação expirou ou já foi utilizado.")
    shop = one("""SELECT plano_ativo,subscription_plan,subscription_status
        FROM barbearias WHERE usuario_id=%s""", (user["id"],))
    return {
        "access_token": token(user["id"], user.get("auth_version", 1)),
        "token_type": "bearer",
        "nome": user["nome"],
        "subscription_required": not bool(shop["plano_ativo"]),
        "subscription_plan": shop["subscription_plan"],
        "subscription_status": shop["subscription_status"],
    }

@app.post("/api/auth/concluir-pagamento")
def finish_paid_signup(data: CheckoutSessionRequest):
    session_id = data.session_id
    stripe = _stripe_client()
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except stripe.error.StripeError as error:
        raise HTTPException(502, "Não foi possível confirmar o pagamento agora.") from error
    metadata = session.get("metadata") or {}
    pending_id = _metadata_pending_id(metadata)
    if not pending_id or session.get("payment_status") not in {"paid", "no_payment_required"}:
        raise HTTPException(409, "O pagamento ainda não foi confirmado.")
    subscription = session.get("subscription")
    if not subscription:
        raise HTTPException(409, "A assinatura ainda está sendo processada.")
    if isinstance(subscription, str):
        subscription = stripe.Subscription.retrieve(subscription)
    created = _activate_pending_signup(pending_id, session, subscription)
    if not created:
        raise HTTPException(409, "A assinatura ainda está sendo processada.")
    _link_stripe_metadata(stripe, session, subscription, created, metadata.get("plan", ""))
    _send_subscription_email_once(
        created["barbearia_id"], metadata.get("plan"), subscription.get("current_period_end"))
    return {
        "access_token": token(created["id"]),
        "token_type": "bearer",
        "nome": created["nome"],
    }

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
