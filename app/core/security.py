import secrets
import uuid
from datetime import UTC, datetime, timedelta

import anyio
from jose import jwt
from passlib.context import CryptContext

from app.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed bcrypt hash used for constant-time comparison when user doesn't exist.
# This prevents timing side-channel attacks that could enumerate valid emails.
DUMMY_HASH = password_context.hash("dummy-password-for-timing-normalization")

# Cap concurrent bcrypt operations per worker process.
# Prevents threadpool stampede: default anyio threadpool is 40 threads/worker,
# so 4 workers = 160 concurrent hashes fighting for 8 CPU cores.
# This limits it to cpu_count hashes per worker (e.g., 8 hashes on 8-core machine).
_bcrypt_limiter = anyio.CapacityLimiter(settings.bcrypt_concurrency)


def _hash_password_sync(password: str) -> str:
    return password_context.hash(password)


def _verify_password_sync(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hash_password_sync, password, limiter=_bcrypt_limiter)


async def verify_password(plain_password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(_verify_password_sync, plain_password, password_hash, limiter=_bcrypt_limiter)


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.refresh_token_expire_minutes)
    payload = {
        "sub": subject,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def generate_otp(length: int = 6) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))
