"""Runtime configuration, env-driven via pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # The app connects as app_user (RLS-enforced).
    database_url: str = Field(
        default="postgresql+asyncpg://app_user:app_user_pw@localhost:55432/clinical_clarity",
        description="Async SQLAlchemy DSN for the runtime user (RLS-enforced).",
    )
    # Migrations and tests run as app_owner (BYPASSRLS).
    database_url_admin: str = Field(
        default="postgresql+asyncpg://app_owner:app_owner_pw@localhost:55432/clinical_clarity",
        description="Async SQLAlchemy DSN for the privileged owner role used by Alembic and test fixtures.",
    )

    session_secret: str = Field(
        default="dev-only-change-me-please",
        description="Signing secret for cookie sessions. MUST be overridden in production.",
    )
    session_cookie_name: str = "vfp_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    session_cookie_secure: bool = False  # set True in production
    session_cookie_domain: str | None = None

    cors_allow_origins: list[str] = ["http://localhost:5173"]

    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
