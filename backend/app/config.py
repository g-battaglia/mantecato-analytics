from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SESSION_SECRET: str = "mantecato-default-secret"
    CRON_SECRET: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:4180"]
    ENVIRONMENT: str = "development"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v  # type: ignore[return-value]

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()
