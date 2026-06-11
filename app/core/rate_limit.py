from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def _get_client_ip(request: Request) -> str:
    if settings.rate_limit_trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request) or "unknown"


limiter = Limiter(key_func=_get_client_ip, enabled=settings.enable_rate_limiting)
