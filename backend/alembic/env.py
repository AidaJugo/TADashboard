"""Alembic env for the TA Hiring Report Platform.

Migrations are forward-only. Never rewrite a migration that has shipped.
See .cursor/rules/migrations.mdc.

We use a synchronous psycopg URL here (stripping the +asyncpg or keeping
+psycopg as-is) because Alembic's built-in runner is synchronous.
The async engine in app.db.session uses the same URL; both drivers speak the
same Postgres wire protocol so there is no mismatch at the schema level.
"""

from __future__ import annotations

import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import get_settings
from app.db.models import Base

config = context.config
# Skip alembic's own logging config when running under pytest: pytest
# (and ``configure_logging``) own the root logger config in that
# context, and ``fileConfig`` would replace the root handlers — which
# silently drops pytest's caplog handler and breaks structured-log
# assertions in the rest of the suite.  ``ALEMBIC_DATABASE_URL`` is
# only set by the test fixture, so it doubles as the "in-tests" hint.
if config.config_file_name is not None and not os.environ.get("ALEMBIC_DATABASE_URL"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(url: str) -> str:
    """Strip +asyncpg driver suffix so the sync engine can connect."""
    return re.sub(r"\+asyncpg", "", url)


# URL precedence:
#   1. ``ALEMBIC_DATABASE_URL`` env var — used by pytest-alembic in
#      ``tests/integration/test_alembic.py`` to point the runner at a
#      dedicated test DB without touching alembic.ini.
#   2. ``Settings.database_url`` from app config (the deployment URL).
# This keeps ``alembic upgrade head`` working out of the box from the
# CLI while letting the test suite redirect at will.
_override_url = os.environ.get("ALEMBIC_DATABASE_URL")
if _override_url:
    config.set_main_option("sqlalchemy.url", _sync_url(_override_url))
else:
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
