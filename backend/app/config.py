from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SESSION_SECRET: str = "mantecato-default-secret"
    CRON_SECRET: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:4180"]
    ENVIRONMENT: str = "development"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()
