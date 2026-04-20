"""Pydantic request/response models for the admin API (M6).

All request models perform server-side validation before any DB write.
Retention bounds are imported from config constants so TC-I-API-13 reads
from the same source the route handler enforces.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — Pydantic resolves at runtime
from datetime import datetime  # noqa: TC003 — Pydantic resolves at runtime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.config import (
    RETENTION_AUDIT_MONTHS_MAX,
    RETENTION_AUDIT_MONTHS_MIN,
    RETENTION_BACKUP_DAYS_MAX,
    RETENTION_BACKUP_DAYS_MIN,
)
from app.db.models import RoleEnum

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Public representation of a user (no secrets, no session data)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: RoleEnum
    is_active: bool
    allowed_hubs: list[str]
    created_at: datetime
    updated_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(max_length=255)
    role: RoleEnum = RoleEnum.viewer
    allowed_hubs: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    """All fields optional; only supplied fields are updated."""

    display_name: str | None = Field(default=None, max_length=255)
    role: RoleEnum | None = None
    allowed_hubs: list[str] | None = None


# ---------------------------------------------------------------------------
# Config (spreadsheet + column mappings)
# ---------------------------------------------------------------------------


class ConfigResponse(BaseModel):
    spreadsheet_id: str
    spreadsheet_tab_name: str
    audit_retention_months: int
    backup_retention_days: int
    column_mappings: dict[str, str]


class ConfigUpdateRequest(BaseModel):
    """Update spreadsheet identity and/or column mappings.

    If column_mappings is supplied, it replaces the full mapping (no partial
    patch).  Validation of the spreadsheet happens server-side before save
    (FR-CONFIG-4).
    """

    spreadsheet_id: str | None = Field(default=None, max_length=500)
    spreadsheet_tab_name: str | None = Field(default=None, max_length=255)
    column_mappings: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Retention windows
# ---------------------------------------------------------------------------


class RetentionUpdateRequest(BaseModel):
    """Update one or both retention windows.

    Both bounds are server-enforced (TC-I-API-13).  The UI may pre-validate
    using the same min/max, but the server is the source of truth.
    """

    audit_retention_months: int | None = Field(
        default=None,
        ge=RETENTION_AUDIT_MONTHS_MIN,
        le=RETENTION_AUDIT_MONTHS_MAX,
        description=(
            f"Audit log retention in months "
            f"({RETENTION_AUDIT_MONTHS_MIN}–{RETENTION_AUDIT_MONTHS_MAX})"
        ),
    )
    backup_retention_days: int | None = Field(
        default=None,
        ge=RETENTION_BACKUP_DAYS_MIN,
        le=RETENTION_BACKUP_DAYS_MAX,
        description=(
            f"Backup retention in days "
            f"({RETENTION_BACKUP_DAYS_MIN}–{RETENTION_BACKUP_DAYS_MAX})"
        ),
    )


# ---------------------------------------------------------------------------
# Hub pairs
# ---------------------------------------------------------------------------


class HubPairResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    city_name: str
    hub_name: str


class HubPairCreateRequest(BaseModel):
    city_name: str = Field(max_length=100)
    hub_name: str = Field(max_length=100)


class HubPairUpdateRequest(BaseModel):
    city_name: str | None = Field(default=None, max_length=100)
    hub_name: str | None = Field(default=None, max_length=100)
