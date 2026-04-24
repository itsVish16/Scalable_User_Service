import secrets
import uuid
from datetime import UTC, datetime, timedelta

import anyio
from jose import jwt
from passlib.context import CryptContext

from app.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password_sync(password: str) -> str:
    return password_context.hash(password)


def _verify_password_sync(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hash_password_sync, password)


async def verify_password(plain_password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(_verify_password_sync, plain_password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.refresh_token_expire_minutes)
    payload = {
        "sub": subject,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def generate_otp(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))
