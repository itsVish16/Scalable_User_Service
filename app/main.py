import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.user import router as user_router
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.db.database import engine, get_db
from app.db.redis import close_redis, get_redis
from app.middleware.logging import RequestContextLogMiddleware
from app.middleware.metrics import MetricsMiddleware

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initializing connections")
    await get_redis()
    yield
    logger.info("Shutting down — cleaning up connections")
    await close_redis()
    await engine.dispose()
    logger.info("All connections closed")


app = FastAPI(
    title="Scalable User Service",
    description="Production-grade user authentication and management microservice",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextLogMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health/live")
async def get_health_live():
    return {"status": "alive"}


@app.get("/health/ready")
async def get_health_ready(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    health = {"status": "healthy", "dependencies": {}}

    try:
        await db.execute(text("SELECT 1"))
        health["dependencies"]["postgres"] = "up"
    except Exception:
        health["dependencies"]["postgres"] = "down"
        health["status"] = "degraded"

    try:
        await redis.ping()
        health["dependencies"]["redis"] = "up"
    except Exception:
        health["dependencies"]["redis"] = "down"
        health["status"] = "degraded"

    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
