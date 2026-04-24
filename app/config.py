from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    debug: bool = False
    database_url: str
    redis_url: str

    secret_key: str
    algirithm: str = "HSA256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 10080

settings = Settings()


