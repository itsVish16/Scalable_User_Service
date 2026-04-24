import json

from redis.asyncio import Redis

PROFILE_CACHE_TTL_SECONDS = 300
RESET_TOKEN_TTL_SECONDS = 900
EMAIL_VERIFICATION_TTL_SECONDS = 900
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
LOGIN_ATTEMPTS_PREFIX = "login:attempts:"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 900


def user_profile_cache_key(user_id: int) -> str:
    return f"user:profile:{user_id}"


def password_reset_cache_key(email: str) -> str:
    return f"user:password-reset:{email}"


def email_verification_cache_key(email: str) -> str:
    return f"user:email-verification:{email}"


# --- User Profile Cache ---


async def get_cached_user_profile(redis: Redis, user_id: int) -> dict | None:
    key = user_profile_cache_key(user_id)
    cached_value = await redis.get(key)
    if cached_value is None:
        return None
    return json.loads(cached_value)


async def set_cached_user_profile(redis: Redis, user_id: int, profile_data: dict) -> None:
    key = user_profile_cache_key(user_id)
    await redis.set(key, json.dumps(profile_data), ex=PROFILE_CACHE_TTL_SECONDS)


async def delete_cached_user_profile(redis: Redis, user_id: int) -> None:
    key = user_profile_cache_key(user_id)
    await redis.delete(key)


# --- Password Reset ---


async def set_password_reset_token(redis: Redis, email: str, token: str) -> None:
    key = password_reset_cache_key(email)
    await redis.set(key, token, ex=RESET_TOKEN_TTL_SECONDS)


async def get_password_reset_token(redis: Redis, email: str) -> str | None:
    key = password_reset_cache_key(email)
    return await redis.get(key)


async def delete_password_reset_token(redis: Redis, email: str) -> None:
    key = password_reset_cache_key(email)
    await redis.delete(key)


# --- Email Verification ---


async def set_email_verification_token(redis: Redis, email: str, token: str) -> None:
    key = email_verification_cache_key(email)
    await redis.set(key, token, ex=EMAIL_VERIFICATION_TTL_SECONDS)


async def get_email_verification_token(redis: Redis, email: str) -> str | None:
    key = email_verification_cache_key(email)
    return await redis.get(key)


async def delete_email_verification_token(redis: Redis, email: str) -> None:
    key = email_verification_cache_key(email)
    await redis.delete(key)


# --- Token Blacklist ---


async def blacklist_token(redis: Redis, jti: str, ttl_seconds: int) -> None:
    key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
    await redis.set(key, "1", ex=ttl_seconds)


async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    key = f"{TOKEN_BLACKLIST_PREFIX}{jti}"
    return await redis.get(key) is not None


# --- Login Attempt Tracking ---


async def increment_login_attempts(redis: Redis, email: str) -> int:
    key = f"{LOGIN_ATTEMPTS_PREFIX}{email}"
    count = await redis.get(key)
    new_count = int(count or 0) + 1
    await redis.set(key, str(new_count), ex=LOGIN_LOCKOUT_SECONDS)
    return new_count


async def get_login_attempts(redis: Redis, email: str) -> int:
    key = f"{LOGIN_ATTEMPTS_PREFIX}{email}"
    count = await redis.get(key)
    return int(count) if count else 0


async def reset_login_attempts(redis: Redis, email: str) -> None:
    key = f"{LOGIN_ATTEMPTS_PREFIX}{email}"
    await redis.delete(key)
