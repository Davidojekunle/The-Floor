from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Taskroom API"
    api_v1_prefix: str = "/api/v1"

    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_days: int = 30
    refresh_cookie_secure: bool = True  # set false for plain-http local dev (Safari refuses Secure on http)
    refresh_reuse_grace_seconds: float = 30

    # email (L2)
    email_backend: str = "console"  # console | smtp
    email_from: str = "Taskroom <no-reply@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    frontend_url: str = "http://localhost:5173"
    email_sender_enabled: bool = True  # background sending loop (off in tests)
    email_send_interval_seconds: float = 5
    password_reset_minutes: int = 30
    public_api_url: str = "http://localhost:8000"  # where unsubscribe links in emails point
    notification_email_delay_seconds: int = 120  # notification emails are grouped within this window
    digest_hour: int = 8  # daily digest goes out at this hour, in each person's timezone
    notification_retention_days: int = 90

    # rate limiting (L2)
    rate_limit_enabled: bool = True
    trusted_proxies: str = ""  # comma-separated IPs whose X-Forwarded-For we believe
    bcrypt_rounds: int = 12  # lower only in tests
    ws_auth_timeout_seconds: float = 10
    temp_head_expiry_check_seconds: float = 30

    # Built frontend (frontend-v2/dist) to serve from this app, so site and API share one origin. Empty = API only.
    frontend_dist: str = ""

    # Comma-separated list, e.g. "http://localhost:5173,https://app.example.com"
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, v: str) -> str:
        """Hosts (Supabase, Render) hand out postgres:// or postgresql:// URLs; the installed driver is psycopg 3."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
