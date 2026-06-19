import json
from datetime import UTC, datetime

import structlog

from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

USER_EVENTS_CHANNEL = "user_events"


async def publish_user_event(redis: Redis, event_type: str, data: dict) -> None:
    """Publishes a user microservice event to the Redis Pub/Sub channel."""
    payload = {
        "event": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }

    try:
        subscribers = await redis.publish(USER_EVENTS_CHANNEL, json.dumps(payload))
        logger.info("event_published", event_type=event_type, subscribers=subscribers)
    except Exception as exc:
        # Event publishing shouldn't crash the request, so we log the error
        logger.error("event_publication_failed", event_type=event_type, error=str(exc))
