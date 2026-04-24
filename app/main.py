import logging

from fastapi import FastAPI

from app.api.user import router as user_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Scalable User Service")

app.include_router(user_router)


@app.get("/health")
async def get_health():
    logger.info("Health check requested")
    return {"status": "healthy"}
