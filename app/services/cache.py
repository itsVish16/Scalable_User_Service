import json
from redis.asyncio import Redis

PROFILE_CACHE_TTL_SECONDS = 300

def user_profile_cache_key(user_id:int) -> str:
    return f"user:profile:{user_id}"

async def get_cached_user_profile(redis: Redis, user_id:int) -> dict | None:
    key = user_profile_cache_key(user_id)
    cached_value = await redis.get(key)

    if cached_value is None:
        return None
    return json.loads(cached_value)

async def set_cached_user_profiles(redis: Redis, user_id: int, profile_data: dict) -> None:
    key =user_profile_cache_key(user_id)
    await redis.set(ey, json.dumps(profile_data), ex = PROFILE_CACHE_TTL_SECONDS)

async def delete_cached_user_profiles(redis: Redis, user_id:int) -> None:
    key = user_profile_cache_key(user_id)
    await redis.delete(key)

