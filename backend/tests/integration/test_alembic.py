"""Migration sanity tests via ``pytest-alembic`` (M4 review should-fix #5).

The library re-exports four black-box checks; we run all four:

- ``test_single_head_revision``     — exactly one head exists (no
                                       accidental branch).
- ``test_upgrade``                   — every revision applies cleanly
                                       from ``base`` to ``head``.
- ``test_up_down_consistency``       — for every revision: ``upgrade``,
                                       then ``downgrade`` to the prior
                                       revision, then ``upgrade`` again
                                       still works.
- ``test_model_definitions_match_ddl`` — the SQLAlchemy ORM models and
                                       the DDL produced by ``head`` are
                                       identical (no model↔migration
                                       drift).

Each test runs against a **dedicated test database** (default
``ta_report_alembic_test``) so it can freely upgrade/downgrade without
touching the grants-aware fixture used by the rest of the integration
suite.  The DB is created fresh per test session and torn down at the
end.

Re-running locally::

    uv run pytest tests/integration/test_alembic.py -v
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# pytest-alembic re-exports its black-box tests as plain functions; importing
# them at module scope registers them with pytest.
from pytest_alembic.tests import (  # noqa: F401 — collected by pytest
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import create_engine

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Configuration — keep aligned with conftest's main test-DB plumbing.
# ---------------------------------------------------------------------------


_ALEMBIC_TEST_DB = os.environ.get("TEST_ALEMBIC_DB_NAME", "ta_report_alembic_test")
_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)


def _admin_psycopg_conn_str() -> str:
    """Convert the SQLAlchemy URL to a psycopg conn string for DB DDL."""
    from urllib.parse import urlparse

    p = urlparse(_ADMIN_URL.replace("postgresql+psycopg", "postgresql"))
    user = p.username or ""
    password = f":{p.password}" if p.password else ""
    host = p.hostname or "localhost"
    port = f":{p.port}" if p.port else ""
    return f"postgresql://{user}{password}@{host}{port}/{p.path.lstrip('/')}"


def _drop_and_create(db_name: str) -> None:
    import psycopg

    with psycopg.connect(_admin_psycopg_conn_str(), autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (db_name,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        conn.execute(f'CREATE DATABASE "{db_name}"')


def _drop(db_name: str) -> None:
    try:
        import psycopg

        with psycopg.connect(_admin_psycopg_conn_str(), autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    except Exception:  # noqa: BLE001 — best-effort teardown
        pass


def _alembic_test_db_url() -> str:
    """Sync URL to the dedicated alembic test DB.  pytest-alembic uses sync."""
    return f"postgresql+psycopg://postgres:postgres@localhost:5432/{_ALEMBIC_TEST_DB}"


# ---------------------------------------------------------------------------
# pytest-alembic fixtures — see https://pytest-alembic.readthedocs.io
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _alembic_db() -> Iterator[None]:
    """Create the alembic test DB once per session, drop it at the end."""
    import psycopg

    try:
        with psycopg.connect(_admin_psycopg_conn_str(), autocommit=True):
            pass
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres not reachable for pytest-alembic suite: {exc}")

    _drop_and_create(_ALEMBIC_TEST_DB)
    try:
        yield
    finally:
        _drop(_ALEMBIC_TEST_DB)


@pytest.fixture
def alembic_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Point pytest-alembic at the in-tree alembic.ini.

    We use ``ALEMBIC_DATABASE_URL`` (read by ``alembic/env.py``) to
    redirect at the dedicated test DB.  Setting ``sqlalchemy.url`` on
    the alembic Config alone is not enough because ``env.py`` overrides
    it from application settings on every run.
    """
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", _alembic_test_db_url())
    backend_dir = Path(__file__).resolve().parents[2]
    return {
        "file": str(backend_dir / "alembic.ini"),
        "script_location": str(backend_dir / "alembic"),
        # We intentionally raise NotImplementedError in every
        # ``downgrade()`` (forward-only policy, see migrations.mdc).
        # Tell pytest-alembic where to stop the down/up consistency
        # check so it doesn't warn for every revision below the floor.
        "minimum_downgrade_revision": "20260417_0001",
    }


@pytest.fixture
def alembic_engine(
    _alembic_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> Engine:
    """Sync engine bound to the dedicated alembic test DB.

    pytest-alembic drives upgrade/downgrade cycles synchronously, so we
    return a vanilla sync engine here (the rest of the test suite uses
    async engines).  ``ALEMBIC_DATABASE_URL`` is also set on the
    `alembic_config` fixture, but pytest-alembic invokes both fixtures
    in any order; setting it again here is cheap and avoids order
    coupling.
    """
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", _alembic_test_db_url())
    return create_engine(_alembic_test_db_url(), pool_pre_ping=True)
