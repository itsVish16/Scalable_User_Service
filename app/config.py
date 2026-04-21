from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    debug: bool = False

    database_url: str

    redis_url: str


settings = Settings()


