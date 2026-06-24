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

    # --- S3 / object storage (Phase 5) ---------------------------------
    # The same boto3 / aiobotocore client serves prod (AWS S3) and dev (MinIO);
    # only the endpoint URL changes. Leave s3_endpoint_url empty to use AWS's
    # default endpoint.
    s3_endpoint_url: str | None = Field(
        default="http://localhost:9000",
        description="S3 endpoint URL. None = AWS default; set to MinIO URL in dev.",
    )
    s3_region: str = Field(default="us-east-1")
    s3_access_key_id: str = Field(default="vfp_dev_access")
    s3_secret_access_key: str = Field(default="vfp_dev_secret")
    s3_bucket: str = Field(
        default="vfp-documents",
        description="Bucket name. Same bucket for all orgs; objects are keyed by org_id/...",
    )

    # --- Anthropic / Claude (Phase 5) ----------------------------------
    anthropic_api_key: str | None = Field(
        default=None,
        description="Live API key for Claude SoA parsing. Tests inject a mock client; only the manual smoke needs a real key.",
    )
    anthropic_model_id: str = Field(default="claude-opus-4-7")

    # --- Background worker (Phase 5) -----------------------------------
    redis_url: str = Field(default="redis://localhost:6379")


@lru_cache
def get_settings() -> Settings:
    return Settings()
