from passlib.context import CryptContext
from jose import jwt
from app.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated = "auto")

def hash_password(password: str) -> str:
    return password_context.hash(password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)

def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes = settings.access_token_expire_minutes
    )
    payload = {"sub":subject, "type":"access", "exp": expire}
    return jwt.encode(payload.settings.secret_key, algorithm = settings.algorithm)

def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes = settings.refres_token_expire_minutes
    )
    payload = {"sub":subject, "type":"refresh", "exp": expire}
    return jwt.encode(payload,  settings.secret_key, algorigthm = settings.algorithm)
