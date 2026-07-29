import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .database import one


DEFAULT_SECRET = "desenvolvimento-local-troque-em-producao"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "cortaflow")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "cortaflow-web")
OIDC_STATE_AUDIENCE = "cortaflow-google-oauth"
SECRET = os.getenv("SECRET_KEY", DEFAULT_SECRET)


def _access_token_minutes() -> int:
    try:
        configured = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "480"))
    except ValueError:
        configured = 480
    return min(max(configured, 15), 10_080)


def _validate_production_secret() -> None:
    if os.getenv("VERCEL") != "1":
        return
    placeholder = any(marker in SECRET.lower() for marker in ("troque", "change-me", "..."))
    if SECRET == DEFAULT_SECRET or placeholder or len(SECRET.encode("utf-8")) < 32:
        raise RuntimeError(
            "SECRET_KEY precisa ter pelo menos 32 bytes e ser configurada na Vercel"
        )


_validate_production_secret()
bearer = HTTPBearer(auto_error=False)


def hash_password(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("A senha não pode ultrapassar 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(value: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(value.encode("utf-8"), hashed.encode("ascii"))
    except (TypeError, ValueError):
        return False


def token(user_id: int, auth_version: int = 1) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=_access_token_minutes())
    claims = {
        "sub": str(user_id),
        "ver": int(auth_version),
        "type": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    return jwt.encode(claims, SECRET, algorithm=JWT_ALGORITHM)


def oidc_state(nonce: str, mode: str = "login", plan: str = "") -> str:
    if mode not in {"login", "register"}:
        raise ValueError("Modo OAuth invalido")
    if plan and plan not in {"essencial", "profissional", "premium"}:
        raise ValueError("Plano OAuth invalido")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": "oidc_state",
            "nonce": nonce,
            "mode": mode,
            "plan": plan,
            "iss": JWT_ISSUER,
            "aud": OIDC_STATE_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=10),
            "jti": uuid4().hex,
        },
        SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_oidc_state(value: str) -> dict:
    claims = jwt.decode(
        value,
        SECRET,
        algorithms=[JWT_ALGORITHM],
        audience=OIDC_STATE_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"require_exp": True, "require_iat": True},
    )
    if not secrets.compare_digest(str(claims.get("type", "")), "oidc_state"):
        raise JWTError("Tipo de state inválido")
    if not claims.get("nonce"):
        raise JWTError("Nonce ausente")
    if claims.get("mode", "login") not in {"login", "register"}:
        raise JWTError("Modo OAuth invalido")
    if claims.get("plan") and claims["plan"] not in {"essencial", "profissional", "premium"}:
        raise JWTError("Plano OAuth invalido")
    return claims


def _decode_access_token(credentials: str) -> tuple[int, int]:
    claims = jwt.decode(
        credentials,
        SECRET,
        algorithms=[JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={"require_exp": True, "require_sub": True},
    )
    if not secrets.compare_digest(str(claims.get("type", "")), "access"):
        raise JWTError("Tipo de token inválido")
    return int(claims["sub"]), int(claims.get("ver", 1))


def _authenticated_user(auth: HTTPAuthorizationCredentials | None):
    if not auth:
        raise HTTPException(401, "Autenticação necessária")
    try:
        user_id, auth_version = _decode_access_token(auth.credentials)
    except (JWTError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "Token inválido ou expirado")
    user = one(
        """SELECT u.id,u.email,u.nome,u.email_verificado,u.auth_version,b.id barbearia_id,
        b.plano_ativo,b.subscription_plan,b.subscription_status,
        b.subscription_current_period_end,b.subscription_cancel_at_period_end
        FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id WHERE u.id=%s""",
        (user_id,),
    )
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    if int(user.get("auth_version") or 1) != auth_version:
        raise HTTPException(401, "Sessão revogada. Entre novamente.")
    if not user["email_verificado"]:
        raise HTTPException(403, "Confirme seu e-mail para acessar o painel")
    partner_emails = {
        value.strip().lower()
        for value in os.getenv("PARTNER_PRO_EMAILS", "ma2664223@gmail.com").split(",")
        if value.strip()
    }
    if str(user.get("email") or "").strip().lower() in partner_emails:
        user["plano_ativo"] = True
        user["subscription_plan"] = "profissional"
        user["subscription_status"] = "active"
    return user


def authenticated_user(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    return _authenticated_user(auth)


def current_user(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    user = _authenticated_user(auth)
    if not user.get("plano_ativo"):
        raise HTTPException(402, "Escolha uma assinatura para liberar o painel")
    return user
