import os
from datetime import datetime, timedelta, timezone
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .database import one

DEFAULT_SECRET = "desenvolvimento-local-troque-em-producao"
SECRET = os.getenv("SECRET_KEY", DEFAULT_SECRET)
if os.getenv("VERCEL") == "1" and SECRET == DEFAULT_SECRET:
    raise RuntimeError("SECRET_KEY precisa ser configurada na Vercel")
bearer = HTTPBearer(auto_error=False)

def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

def verify_password(value: str, hashed: str) -> bool:
    return bcrypt.checkpw(value.encode(), hashed.encode())

def token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET, algorithm="HS256")

def current_user(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not auth:
        raise HTTPException(401, "Autenticação necessária")
    try:
        user_id = int(jwt.decode(auth.credentials, SECRET, algorithms=["HS256"])["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Token inválido ou expirado")
    user = one("SELECT u.id, u.email, u.nome, b.id barbearia_id FROM usuarios u JOIN barbearias b ON b.usuario_id=u.id WHERE u.id=%s", (user_id,))
    if not user:
        raise HTTPException(401, "Usuário não encontrado")
    return user
