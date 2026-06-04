from datetime import datetime, timedelta
import re

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuditLog, User


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
rate_buckets: dict[str, list[datetime]] = {}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=8),
    }
    return jwt.encode(payload, settings.app_secret, algorithm="HS256")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.app_secret, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or missing user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def validate_question(question: str) -> str:
    clean = question.strip()
    if not clean or len(clean) > 1500:
        raise HTTPException(status_code=400, detail="Question must be between 1 and 1500 characters")
    blocked = ["ignore previous instructions", "reveal system prompt", "show api key", "developer message"]
    if any(term in clean.lower() for term in blocked):
        raise HTTPException(status_code=400, detail="Prompt injection pattern detected")
    return clean


def mask_sensitive(text: str) -> str:
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[masked-email]", text)
    text = re.sub(r"\b\d{10,16}\b", "[masked-number]", text)
    return text


async def rate_limit(request: Request):
    if request.method in {"OPTIONS", "HEAD"} or request.url.path == "/health":
        return

    forwarded_for = request.headers.get("x-forwarded-for")
    key = forwarded_for.split(",", 1)[0].strip() if forwarded_for else None
    if not key:
        key = request.client.host if request.client else "unknown"

    now = datetime.utcnow()
    bucket = [t for t in rate_buckets.get(key, []) if now - t < timedelta(minutes=1)]
    if len(bucket) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
    bucket.append(now)
    rate_buckets[key] = bucket


def audit(db: Session, user_id: int | None, action: str, detail: str):
    db.add(AuditLog(user_id=user_id, action=action, detail=mask_sensitive(detail)))
    db.commit()
