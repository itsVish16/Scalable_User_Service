import logging

from redis.asyncio import ConnectionPool, Redis
from app.config import settings

logger = getLogging(__name__)

_pool: ConnectionPool | None = None
_client: Redis | None = None

async def get_redis() -> Redis:
    global _client, _pool
    if _client is None:
        _pool = ConnectionPool.from_url(
            ettings.redis_url,
            decoce_reponse = True,
            max_connections = 20,

        )

        _client = Redis(connection_pool = _pool)
        logger.info("Redis connectuin pool created")
    return _client


async def close_redis():
    global _pool, _client
    if _client:
        await _client.close()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None


