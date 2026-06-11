from functools import cached_property
from os import cpu_count

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = False
    database_url: str = "postgresql+asyncpg://userservice:userservice@localhost:5432/userservice"
    redis_url: str = "redis://localhost:6379/0"
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout: int = 10
    redis_max_connections: int = 100

    enable_rate_limiting: bool = True
    rate_limit_trust_proxy_headers: bool = False
    rate_limit_signup: str = "5/minute"
    rate_limit_login: str = "10/minute"
    rate_limit_refresh: str = "10/minute"
    rate_limit_forgot_password: str = "5/minute"
    rate_limit_reset_password: str = "5/minute"
    rate_limit_verify_email: str = "5/minute"
    rate_limit_resend_verification: str = "5/minute"

    profile_cache_ttl_seconds: int = 300
    otp_ttl_seconds: int = 900
    max_login_attempts: int = 5
    login_lockout_seconds: int = 900

    # Cap concurrent bcrypt operations per worker process.
    # Default = CPU count. Prevents threadpool stampede when many logins hit simultaneously.
    # With 4 workers on 8 cores: each worker gets 2 concurrent hashes max (8 total).
    bcrypt_concurrency: int = cpu_count() or 4

    secret_key: str = "dev-secret-key-change-me"
    algorithm: str = "HS256"
    jwt_issuer: str = "scalable-user-service"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    resend_api_key: str = ""
    email_from: str = "noreply@example.com"
    frontend_base_url: str = "http://localhost:3000"
    email_delivery_enabled: bool = False
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    )

    @cached_property
    def cors_allowed_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:3000"]


settings = Settings()
