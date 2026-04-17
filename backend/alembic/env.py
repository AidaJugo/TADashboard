"""Alembic env for the TA Hiring Report Platform.

Migrations are forward-only. Never rewrite a migration that has shipped.
See .cursor/rules/migrations.mdc.

We use a synchronous psycopg URL here (stripping the +asyncpg or keeping
+psycopg as-is) because Alembic's built-in runner is synchronous.
The async engine in app.db.session uses the same URL; both drivers speak the
same Postgres wire protocol so there is no mismatch at the schema level.
"""

from __future__ import annotations

import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """Strip +asyncpg driver suffix so the sync engine can connect."""
    return re.sub(r"\+asyncpg", "", url)


settings = get_settings()
config.set_main_option("sqlalchemy.url", _sync_url(settings.database_url))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
