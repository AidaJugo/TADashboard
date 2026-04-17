"""Follow-up schema additions: sessions table, users.role ENUM, audit_log composite
index, sheet_snapshot CHECK + JSONB, comments UNIQUE hire-key constraint.

What:
  1. Add `sessions` table for server-side session storage (FR-AUTH-4/5).
  2. Convert `users.role` from VARCHAR(20) to a native Postgres ENUM `user_role`.
  3. Add composite index `ix_audit_log_action_created_at` on `(action, created_at)`
     to support FR-AUDIT-3 filtered queries.
  4. Add `CHECK (id = 1)` constraint to `sheet_snapshot` to enforce the single-row
     invariant at the DB layer.
  5. Rename `sheet_snapshot.raw_json` (TEXT) to `raw_rows` (JSONB) for structured
     storage and future partial reads.
  6. Add UNIQUE constraint `uq_comment_hire_key` on
     `comments(position, seniority, hub, salary_eur)` per FR-COMMENT-1.

Why: four blockers from the M3 review (B1, B3 schema side, N1-N4) needed before M4
can build auth on top of a complete, correct schema.

Rollback: forward-only (see .cursor/rules/migrations.mdc). Manual steps if needed:
  - DROP TABLE sessions;
  - ALTER TABLE users ALTER COLUMN role TYPE varchar(20) USING role::text;
  - DROP TYPE user_role;
  - DROP INDEX ix_audit_log_action_created_at;
  - ALTER TABLE sheet_snapshot DROP CONSTRAINT ck_sheet_snapshot_single_row;
  - ALTER TABLE sheet_snapshot RENAME COLUMN raw_rows TO raw_json;
  - ALTER TABLE sheet_snapshot ALTER COLUMN raw_json TYPE text USING raw_json::text;
  - ALTER TABLE comments DROP CONSTRAINT uq_comment_hire_key;
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260417_0002"
down_revision = "20260417_0001"
branch_labels = None
depends_on = None

# Postgres ENUM type for users.role
_USER_ROLE_ENUM = postgresql.ENUM("admin", "editor", "viewer", name="user_role", create_type=False)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create the `user_role` ENUM type, then alter users.role
    # ------------------------------------------------------------------
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'editor', 'viewer')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE user_role USING role::user_role")

    # ------------------------------------------------------------------
    # 2. Add `sessions` table
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    # ------------------------------------------------------------------
    # 3. Composite index on audit_log (action, created_at) — FR-AUDIT-3
    # ------------------------------------------------------------------
    op.create_index(
        "ix_audit_log_action_created_at",
        "audit_log",
        ["action", "created_at"],
    )

    # ------------------------------------------------------------------
    # 4. CHECK (id = 1) on sheet_snapshot
    # ------------------------------------------------------------------
    op.create_check_constraint(
        "ck_sheet_snapshot_single_row",
        "sheet_snapshot",
        "id = 1",
    )

    # ------------------------------------------------------------------
    # 5. Rename raw_json (TEXT) → raw_rows (JSONB)
    # ------------------------------------------------------------------
    op.alter_column(
        "sheet_snapshot",
        "raw_json",
        new_column_name="raw_rows",
        type_=postgresql.JSONB(),
        postgresql_using="raw_json::jsonb",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    # ------------------------------------------------------------------
    # 6. UNIQUE constraint on comments hire key
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_comment_hire_key",
        "comments",
        ["position", "seniority", "hub", "salary_eur"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "forward-only migration (see .cursor/rules/migrations.mdc). "
        "Manual rollback steps are in this file's module docstring."
    )
