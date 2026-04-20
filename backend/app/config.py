"""Application configuration.

All settings come from environment variables (see .env.example at the repo root
and ADR 0008). Never read secrets from files in the repo.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    app_env: str = Field(default="dev", description="dev | test | staging | prod")
    app_base_url: str = Field(default="http://localhost:8000")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ta_report",
    )

    session_secret_key: str = Field(
        default="change-me-in-env",
        description="Server-side session signing key. Rotate every 90 days.",
    )
    session_idle_timeout_minutes: int = 240
    session_absolute_timeout_minutes: int = 1440

    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8000/auth/callback",
    )
    allowed_hd: str = Field(
        default="symphony.is",
        description="Only Google Workspace accounts on this domain may log in.",
    )

    google_service_account_json_path: str = Field(
        default="",
        description="Path to the service account key file. See ADR 0003.",
    )
    spreadsheet_id: str = Field(default="")
    spreadsheet_tab_name: str = Field(default="Report Template")

    # Three-role DB connections (ADR 0010).
    # In prod, both must be non-empty and must differ from database_url.
    # In dev/test, leave empty to fall back to database_url (grants not enforced).
    database_url_erasure: str = Field(
        default="",
        description="DSN for ta_report_erasure role — NFR-PRIV-5 PII redaction (ADR 0010).",
    )
    database_url_sweep: str = Field(
        default="",
        description="DSN for ta_report_sweep role — NFR-PRIV-4 retention sweep (ADR 0010).",
    )

    log_level: str = Field(default="INFO")
    cors_allowed_origins: str = Field(default="http://localhost:5173")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


# ---------------------------------------------------------------------------
# Retention bounds (PRD NFR-PRIV-2, NFR-PRIV-4, TC-I-API-13)
# ---------------------------------------------------------------------------
# These are the server-enforced hard limits.  Admin UI may pre-validate, but
# the server returns 422 if the submitted value is outside the range.

RETENTION_AUDIT_MONTHS_MIN: int = 6
RETENTION_AUDIT_MONTHS_MAX: int = 60

RETENTION_BACKUP_DAYS_MIN: int = 7
RETENTION_BACKUP_DAYS_MAX: int = 90

#: Defaults stored in config_kv when no override has been set.
RETENTION_AUDIT_MONTHS_DEFAULT: int = 18
RETENTION_BACKUP_DAYS_DEFAULT: int = 30


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
