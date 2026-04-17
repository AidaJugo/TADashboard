"""SQLAlchemy ORM models for the TA Hiring Report Platform.

Tables:
  users              — allowlisted Symphony employees with an assigned role.
  user_hub_scopes    — hubs each user may view (empty rows = all hubs).
  config_kv          — admin-editable runtime configuration (spreadsheet ID, tab,
                       retention windows).
  column_mappings    — admin-editable mapping: logical column names → Sheet headers.
  comments           — free-text comments keyed by (position, seniority, hub, salary_eur).
  benchmark_notes    — free-text notes per period (Jan..Dec, Q1..Q4, H1, H2, Annual).
  city_notes         — free-text notes per city.
  hub_pairs          — admin-editable hub definitions (city → hub).
  audit_log          — append-only log of every sensitive action (ADR 0009, FR-AUDIT).
  sheet_snapshot     — last-successful raw JSON from Google Sheets (FR-REPORT-2).

All tables use UUIDs as primary keys except config_kv / column_mappings (string PKs)
and sheet_snapshot (single-row sentinel with integer PK).

The audit log has no updated_at column: the DB role used by the app must not have
UPDATE or DELETE grants on audit_log (TC-I-AUD-3).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime  # noqa: TC003  # SQLAlchemy resolves Mapped[datetime] at runtime

from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RoleEnum(enum.StrEnum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(Base):
    """Allowlisted Symphony employee.

    A Google SSO login only succeeds if the email is present here (FR-AUTH-3).
    Role is enforced server-side on every request (FR-AUTHZ-1).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(
        String(20),
        nullable=False,
        default=RoleEnum.viewer,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    hub_scopes: Mapped[list[UserHubScope]] = relationship(
        "UserHubScope", back_populates="user", cascade="all, delete-orphan"
    )
    audit_entries: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id"
    )


class UserHubScope(Base):
    """Per-user hub allowlist.

    Absence of rows for a user means all hubs are permitted (FR-AUTHZ-3).
    """

    __tablename__ = "user_hub_scopes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    hub_name: Mapped[str] = mapped_column(String(100), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="hub_scopes")

    __table_args__ = (UniqueConstraint("user_id", "hub_name", name="uq_user_hub"),)


# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------


class ConfigKV(Base):
    """Admin-editable key/value configuration store.

    Keys match the constants in app.config (spreadsheet_id, spreadsheet_tab_name,
    audit_retention_months, backup_retention_days, etc.). Values are always text;
    the application is responsible for parsing/validating on read.
    """

    __tablename__ = "config_kv"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ColumnMapping(Base):
    """Admin-editable mapping from logical column names to Sheet column headers.

    Logical names are fixed (see FR-CONFIG-2): Position, Seniority, City, Salary,
    Midpoint, Gap_EUR, Gap_PCT, Status, Month, Year, Type, Recruiter, Note.
    source_column is the actual header string in the Google Sheet.
    """

    __tablename__ = "column_mappings"

    logical_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_column: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# ---------------------------------------------------------------------------
# Comments and benchmark notes (editable by admin + editor, FR-COMMENT-1..3)
# ---------------------------------------------------------------------------


class Comment(Base):
    """Free-text comment keyed by (position, seniority, hub, salary_eur).

    Displayed next to above-midpoint hire rows in the report (FR-REPORT-5).
    Text is capped at 500 characters (PRD glossary: "Hire note").
    """

    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position: Mapped[str] = mapped_column(String(200), nullable=False)
    seniority: Mapped[str] = mapped_column(String(100), nullable=False)
    hub: Mapped[str] = mapped_column(String(100), nullable=False)
    salary_eur: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_comments_key", "position", "seniority", "hub", "salary_eur"),)


class BenchmarkNote(Base):
    """Free-text note per period (FR-COMMENT-2).

    Period values: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec,
    Q1, Q2, Q3, Q4, H1, H2, Annual. Validated at the API layer.
    """

    __tablename__ = "benchmark_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("period", "year", name="uq_benchmark_note_period_year"),)


class CityNote(Base):
    """Free-text note per city (FR-COMMENT-3)."""

    __tablename__ = "city_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class HubPair(Base):
    """Admin-managed city-to-hub mapping (FR-CONFIG-3).

    Maps a raw city name from the Sheet to a canonical hub name used in
    aggregation and scoping. Both names are free text; the list is editable
    without a redeploy.
    """

    __tablename__ = "hub_pairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hub_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("city_name", name="uq_hub_pair_city"),)


# ---------------------------------------------------------------------------
# Audit log (append-only, FR-AUDIT-1..3)
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Append-only audit log.

    The DB role used by the app must not have UPDATE or DELETE grants on this
    table (TC-I-AUD-3). Application code only ever INSERTs.

    actor_email and actor_display_name are nullable to support the right-to-erasure
    flow (NFR-PRIV-5): when a user is deleted, these fields are replaced with
    "deleted user" placeholders while actor_id, action, target, and created_at
    are preserved.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    actor: Mapped[User | None] = relationship(
        "User", back_populates="audit_entries", foreign_keys=[actor_id]
    )

    __table_args__ = (Index("ix_audit_log_actor_id", "actor_id"),)


# ---------------------------------------------------------------------------
# Sheet snapshot (last-known-good fallback, FR-REPORT-2)
# ---------------------------------------------------------------------------


class SheetSnapshot(Base):
    """Single-row table holding the last successfully fetched Sheet payload.

    raw_json is the full list of row dicts as a JSON string.
    fetched_at is UTC. column_hash is a SHA-256 of the sorted column headers,
    used to detect schema drift between fetches.
    """

    __tablename__ = "sheet_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    column_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
