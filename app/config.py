from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    debug: bool = False
    database_url: str
    redis_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080

    celery_broker_url: str
    celery_result_backend: str
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    resend_api_key: str
    email_from: str
    frontend_base_url: str


settings = Settings()
