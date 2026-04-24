import logging

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from app.core.rate_limit import limiter

from app.api.user import router as user_router

logger = logging.getLogger(__name__)




app = FastAPI(title="Scalable User Service")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(user_router)


@app.get("/health")
async def get_health():
    logger.info("Health check requested")
    return {"status": "healthy"}
