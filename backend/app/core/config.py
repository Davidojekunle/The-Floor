from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Taskroom API"
    api_v1_prefix: str = "/api/v1"

    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 60
    bcrypt_rounds: int = 12  # lower only in tests

    # Comma-separated list, e.g. "http://localhost:5173,https://app.example.com"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
