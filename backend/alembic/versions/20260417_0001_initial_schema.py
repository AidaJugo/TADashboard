"""Initial schema: all application tables for the TA Hiring Report Platform.

What: Creates users, user_hub_scopes, config_kv, column_mappings, comments,
      benchmark_notes, city_notes, hub_pairs, audit_log, and sheet_snapshot.
Why:  M3 — data model milestone. All auxiliary data (users, config, comments,
      audit log, snapshot) lives in Postgres from day one per ADR 0002.
Rollback: No automated downgrade. If production forces a rollback, drop all
      tables listed in downgrade() manually after confirming data is backed up.
      See docs/adr/0002-sheet-as-source-of-truth.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260417_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_hub_scopes",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("hub_name", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hub_name", name="uq_user_hub"),
    )

    op.create_table(
        "config_kv",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "column_mappings",
        sa.Column("logical_name", sa.String(50), nullable=False),
        sa.Column("source_column", sa.String(200), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("logical_name"),
    )

    op.create_table(
        "comments",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.String(200), nullable=False),
        sa.Column("seniority", sa.String(100), nullable=False),
        sa.Column("hub", sa.String(100), nullable=False),
        sa.Column("salary_eur", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("created_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_comments_key", "comments", ["position", "seniority", "hub", "salary_eur"]
    )

    op.create_table(
        "benchmark_notes",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period", "year", name="uq_benchmark_note_period_year"),
    )

    op.create_table(
        "city_notes",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("city_name", sa.String(100), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city_name"),
    )

    op.create_table(
        "hub_pairs",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("city_name", sa.String(100), nullable=False),
        sa.Column("hub_name", sa.String(100), nullable=False),
        sa.Column("created_by_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city_name", name="uq_hub_pair_city"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("actor_display_name", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.create_table(
        "sheet_snapshot",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("raw_json", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("column_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "forward-only migration (see .cursor/rules/migrations.mdc). "
        "To roll back manually: drop tables audit_log, sheet_snapshot, hub_pairs, "
        "city_notes, benchmark_notes, comments, column_mappings, config_kv, "
        "user_hub_scopes, users in that order."
    )
