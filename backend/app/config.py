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

    log_level: str = Field(default="INFO")
    cors_allowed_origins: str = Field(default="http://localhost:5173")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
