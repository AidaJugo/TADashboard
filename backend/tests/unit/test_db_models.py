"""Unit tests for ORM model structure.

These tests are pure-Python (no DB connection required). They verify that
the models have the expected columns, constraints, and relationships so that
schema drift between models.py and the migration is caught early.

PRD coverage: supports FR-AUTH-1..3, FR-AUTH-4/5 (sessions), FR-AUTHZ-1..3,
FR-AUDIT-1..3, FR-COMMENT-1..3, FR-CONFIG-1..3, FR-REPORT-2.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Enum as SAEnum

from app.db.models import (
    AuditLog,
    Base,
    BenchmarkNote,
    CityNote,
    ColumnMapping,
    Comment,
    ConfigKV,
    HubPair,
    RoleEnum,
    Session,
    SheetSnapshot,
    User,
    UserHubScope,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_columns(model: type) -> set[str]:
    return {col.name for col in model.__table__.columns}


def _table_constraints(model: type) -> list[str]:
    return [c.name for c in model.__table__.constraints if c.name]


# ---------------------------------------------------------------------------
# RoleEnum
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_role_enum_values() -> None:
    assert set(RoleEnum) == {RoleEnum.admin, RoleEnum.editor, RoleEnum.viewer}


@pytest.mark.unit
def test_role_enum_string_values() -> None:
    assert RoleEnum.admin == "admin"
    assert RoleEnum.editor == "editor"
    assert RoleEnum.viewer == "viewer"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_user_table_name() -> None:
    assert User.__tablename__ == "users"


@pytest.mark.unit
def test_user_required_columns() -> None:
    cols = _table_columns(User)
    assert {"id", "email", "display_name", "role", "is_active", "created_at", "updated_at"} <= cols


@pytest.mark.unit
def test_user_email_is_indexed_unique() -> None:
    index_names = {idx.name for idx in User.__table__.indexes}
    assert "ix_users_email" in index_names


@pytest.mark.unit
def test_user_default_role_is_viewer() -> None:
    """SQLAlchemy column-level default is viewer (applied on INSERT, not __init__)."""
    col = User.__table__.columns["role"]
    assert col.default.arg == RoleEnum.viewer  # type: ignore[union-attr]


@pytest.mark.unit
def test_user_default_is_active_true() -> None:
    """Column-level default for is_active is True."""
    col = User.__table__.columns["is_active"]
    assert col.default.arg is True  # type: ignore[union-attr]


@pytest.mark.unit
def test_user_id_column_uses_uuid_callable() -> None:
    """id column default is a callable that produces UUID values."""
    col = User.__table__.columns["id"]
    assert callable(col.default.arg)  # type: ignore[union-attr]
    assert col.default.is_callable  # type: ignore[union-attr]


@pytest.mark.unit
def test_user_role_column_uses_native_enum() -> None:
    """N1: users.role must use a DB-native Enum type, not a plain string (FR-AUTHZ-1)."""
    col = User.__table__.columns["role"]
    assert isinstance(col.type, SAEnum)
    assert col.type.name == "user_role"


# ---------------------------------------------------------------------------
# UserHubScope
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_user_hub_scope_table_name() -> None:
    assert UserHubScope.__tablename__ == "user_hub_scopes"


@pytest.mark.unit
def test_user_hub_scope_unique_constraint() -> None:
    constraints = _table_constraints(UserHubScope)
    assert "uq_user_hub" in constraints


@pytest.mark.unit
def test_user_hub_scope_columns() -> None:
    cols = _table_columns(UserHubScope)
    assert {"id", "user_id", "hub_name"} <= cols


# ---------------------------------------------------------------------------
# Session (B1, FR-AUTH-4/5, TC-I-AUTH-5/6/7/9)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_session_table_name() -> None:
    assert Session.__tablename__ == "sessions"


@pytest.mark.unit
def test_session_required_columns() -> None:
    """TC-I-AUTH-5/6: session must carry timing columns for idle + absolute timeout."""
    cols = _table_columns(Session)
    assert {
        "id",
        "user_id",
        "issued_at",
        "last_seen_at",
        "expires_at",
        "revoked_at",
        "client_ip",
        "user_agent",
    } <= cols


@pytest.mark.unit
def test_session_expires_at_is_indexed() -> None:
    """M4 auth middleware scans active sessions by expiry; needs an index."""
    index_names = {idx.name for idx in Session.__table__.indexes}
    assert "ix_sessions_expires_at" in index_names


@pytest.mark.unit
def test_session_user_id_is_indexed() -> None:
    index_names = {idx.name for idx in Session.__table__.indexes}
    assert "ix_sessions_user_id" in index_names


@pytest.mark.unit
def test_session_user_id_fk_cascade_delete() -> None:
    """Deleting a user must cascade to all their sessions (NFR-COMP-2)."""
    fks = list(Session.__table__.foreign_keys)
    user_id_fk = next(fk for fk in fks if fk.parent.name == "user_id")
    assert user_id_fk.ondelete == "CASCADE"


@pytest.mark.unit
def test_session_no_updated_at_column() -> None:
    """last_seen_at is the update-style column; there is no updated_at."""
    assert "updated_at" not in _table_columns(Session)


# ---------------------------------------------------------------------------
# ConfigKV
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_config_kv_table_name() -> None:
    assert ConfigKV.__tablename__ == "config_kv"


@pytest.mark.unit
def test_config_kv_string_primary_key() -> None:
    pk_cols = [c.name for c in ConfigKV.__table__.primary_key]
    assert pk_cols == ["key"]


@pytest.mark.unit
def test_config_kv_columns() -> None:
    cols = _table_columns(ConfigKV)
    assert {"key", "value", "updated_at", "updated_by_id"} <= cols


# ---------------------------------------------------------------------------
# ColumnMapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_column_mapping_table_name() -> None:
    assert ColumnMapping.__tablename__ == "column_mappings"


@pytest.mark.unit
def test_column_mapping_string_primary_key() -> None:
    pk_cols = [c.name for c in ColumnMapping.__table__.primary_key]
    assert pk_cols == ["logical_name"]


@pytest.mark.unit
def test_column_mapping_columns() -> None:
    cols = _table_columns(ColumnMapping)
    assert {"logical_name", "source_column", "updated_at", "updated_by_id"} <= cols


# ---------------------------------------------------------------------------
# Comment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_comment_table_name() -> None:
    assert Comment.__tablename__ == "comments"


@pytest.mark.unit
def test_comment_text_max_500_chars() -> None:
    text_col = Comment.__table__.columns["text"]
    assert text_col.type.length == 500


@pytest.mark.unit
def test_comment_composite_index_exists() -> None:
    index_names = {idx.name for idx in Comment.__table__.indexes}
    assert "ix_comments_key" in index_names


@pytest.mark.unit
def test_comment_hire_key_unique_constraint() -> None:
    """FR-COMMENT-1: exactly one comment per hire key tuple."""
    constraints = _table_constraints(Comment)
    assert "uq_comment_hire_key" in constraints


@pytest.mark.unit
def test_comment_columns() -> None:
    cols = _table_columns(Comment)
    assert {"id", "position", "seniority", "hub", "salary_eur", "text", "created_by_id"} <= cols


# ---------------------------------------------------------------------------
# BenchmarkNote
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_benchmark_note_table_name() -> None:
    assert BenchmarkNote.__tablename__ == "benchmark_notes"


@pytest.mark.unit
def test_benchmark_note_unique_constraint() -> None:
    constraints = _table_constraints(BenchmarkNote)
    assert "uq_benchmark_note_period_year" in constraints


@pytest.mark.unit
def test_benchmark_note_columns() -> None:
    cols = _table_columns(BenchmarkNote)
    assert {"id", "period", "year", "text", "created_by_id"} <= cols


# ---------------------------------------------------------------------------
# CityNote
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_city_note_table_name() -> None:
    assert CityNote.__tablename__ == "city_notes"


# ---------------------------------------------------------------------------
# HubPair
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hub_pair_table_name() -> None:
    assert HubPair.__tablename__ == "hub_pairs"


@pytest.mark.unit
def test_hub_pair_city_unique_constraint() -> None:
    constraints = _table_constraints(HubPair)
    assert "uq_hub_pair_city" in constraints


@pytest.mark.unit
def test_hub_pair_columns() -> None:
    cols = _table_columns(HubPair)
    assert {"id", "city_name", "hub_name", "created_by_id"} <= cols


# ---------------------------------------------------------------------------
# AuditLog — append-only (TC-I-AUD-3 structural check)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_audit_log_table_name() -> None:
    assert AuditLog.__tablename__ == "audit_log"


@pytest.mark.unit
def test_audit_log_required_columns() -> None:
    """TC-I-AUD-3: audit log must have actor, action, target, timestamp, IP."""
    cols = _table_columns(AuditLog)
    assert {
        "id",
        "actor_id",
        "actor_email",
        "actor_display_name",
        "action",
        "target",
        "client_ip",
        "created_at",
    } <= cols


@pytest.mark.unit
def test_audit_log_actor_fields_not_nullable() -> None:
    """B4: actor_email and actor_display_name must be NOT NULL.

    Right-to-erasure (NFR-PRIV-5) is implemented by overwriting them with
    "deleted user" rather than setting NULL.
    """
    assert not AuditLog.__table__.columns["actor_email"].nullable
    assert not AuditLog.__table__.columns["actor_display_name"].nullable


@pytest.mark.unit
def test_audit_log_no_updated_at_column() -> None:
    """TC-I-AUD-3: append-only — no updated_at means no in-place mutation."""
    cols = _table_columns(AuditLog)
    assert "updated_at" not in cols


@pytest.mark.unit
def test_audit_log_indexed_for_filtering() -> None:
    """TC-I-AUD-4: audit log must support filtering by actor, action, date."""
    index_names = {idx.name for idx in AuditLog.__table__.indexes}
    assert "ix_audit_log_actor_id" in index_names
    assert "ix_audit_log_created_at" in index_names


@pytest.mark.unit
def test_audit_log_composite_action_date_index() -> None:
    """N2/FR-AUDIT-3: composite (action, created_at) index for filtered queries."""
    index_names = {idx.name for idx in AuditLog.__table__.indexes}
    assert "ix_audit_log_action_created_at" in index_names


# ---------------------------------------------------------------------------
# SheetSnapshot
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sheet_snapshot_table_name() -> None:
    assert SheetSnapshot.__tablename__ == "sheet_snapshot"


@pytest.mark.unit
def test_sheet_snapshot_columns() -> None:
    """N4: raw column is now raw_rows (JSONB), not raw_json (TEXT)."""
    cols = _table_columns(SheetSnapshot)
    assert {"id", "raw_rows", "fetched_at", "column_hash"} <= cols
    assert "raw_json" not in cols


@pytest.mark.unit
def test_sheet_snapshot_single_row_check_constraint() -> None:
    """N3: CHECK (id = 1) enforces single-row invariant at the DB layer."""
    constraints = _table_constraints(SheetSnapshot)
    assert "ck_sheet_snapshot_single_row" in constraints


# ---------------------------------------------------------------------------
# Base metadata completeness
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_tables_registered_in_metadata() -> None:
    expected = {
        "users",
        "user_hub_scopes",
        "sessions",
        "config_kv",
        "column_mappings",
        "comments",
        "benchmark_notes",
        "city_notes",
        "hub_pairs",
        "audit_log",
        "sheet_snapshot",
    }
    assert expected <= set(Base.metadata.tables.keys())
