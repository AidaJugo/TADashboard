"""Shared pytest fixtures for the TA Hiring Report Platform.

Scope
-----
Unit tests (``-m unit``) do not need the database.  Integration tests
(``-m integration``) that touch the database opt in by depending on one of
the fixtures in this module.

Database topology (PR 1 of M4 — docs/adr/0010-audit-log-grants.md)
-----------------------------------------------------------------
Tests run against a real Postgres.  We exercise the three-role grants model
from ``backend/grants.sql``:

- ``superuser_engine``: the owner role; used only for seeding and cleanup.
- ``app_engine``: connects as ``ta_report_app``.  Route handlers run through
  this engine so that TC-I-AUD-3 actually trips the grant model
  (``InsufficientPrivilege`` on ``UPDATE`` / ``DELETE`` of ``audit_log``).
- ``erasure_engine``: connects as ``ta_report_erasure``.  Used by the NFR-PRIV-5
  redaction path and its integration test (TC-I-AUD-5).
- ``sweep_engine``: connects as ``ta_report_sweep``.  Used by the retention
  sweep test (TC-I-AUD-6, landed later).

The session-scoped setup fixture:

1. Connects to the ``postgres`` admin DB as the superuser.
2. Drops and recreates a dedicated test database (``ta_report_test`` by
   default; override via ``TEST_DATABASE_URL``).
3. Runs ``alembic upgrade head`` against it.
4. Applies ``backend/grants.sql``.
5. Sets passwords on the three role logins so password-authenticated
   connections work.

If Postgres is unreachable (local dev without ``docker-compose up db``), all
DB-dependent integration tests are skipped with a clear message.

Log capture (TC-I-PRIV-2 backbone)
----------------------------------
``caplog_json`` returns a list of JSON log records captured during the test,
each asserted to have the required structured-log fields (``timestamp``,
``level``, ``request_id``, ``event``).  PRs 2-4 reuse this for TC-I-PRIV-1.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import uuid
from collections.abc import AsyncGenerator, Callable, Generator, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import RoleEnum, User, UserHubScope

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Admin URL used to create/drop the test database.  Defaults to the dev
#: DATABASE_URL but targeting the ``postgres`` maintenance database.
_ADMIN_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)

#: Async URL for the test database.  Owner role only (superuser/postgres).
_DEFAULT_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/ta_report_test",
)

#: Password set on the three application roles at fixture setup time so
#: password-authenticated connections (CI default) work.  Not a secret.
_TEST_ROLE_PASSWORD = "ta_report_test"  # noqa: S105 — test-only, never used in prod


# ---------------------------------------------------------------------------
# Helpers (sync, used during session setup only)
# ---------------------------------------------------------------------------


def _to_sync_url(async_url: str) -> str:
    """Strip ``+psycopg_async`` so synchronous psycopg can use the URL."""
    return re.sub(r"\+psycopg_async\b", "+psycopg", async_url)


def _to_async_url(sync_url: str) -> str:
    """Force the ``+psycopg_async`` dialect for the async engine."""
    if "+psycopg_async" in sync_url:
        return sync_url
    return re.sub(r"\+psycopg\b", "+psycopg_async", sync_url)


def _psycopg_conn_str(url: str) -> str:
    """Convert a SQLAlchemy URL into a raw psycopg connection string."""
    sync = _to_sync_url(url)
    parsed = urlparse(sync)
    # scheme like "postgresql+psycopg" — strip the driver part
    scheme = parsed.scheme.split("+", 1)[0]
    return urlunparse(parsed._replace(scheme=scheme))


def _db_name_from(url: str) -> str:
    parsed = urlparse(_to_sync_url(url))
    return parsed.path.lstrip("/")


def _swap_role(url: str, role: str, password: str) -> str:
    """Return a copy of ``url`` with the role + password replaced.

    The test role connections use the same host/port/database as the owner
    URL, differing only in the credential pair.
    """
    parsed = urlparse(url)
    netloc = f"{role}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _postgres_reachable(admin_conn_str: str) -> tuple[bool, str]:
    try:
        import psycopg  # local import so unit-only runs don't need it

        with psycopg.connect(admin_conn_str, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True, ""
    except Exception as exc:  # noqa: BLE001 — fixture probe, surface all errors
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Session-scoped DB setup
# ---------------------------------------------------------------------------


class _TestDatabase:
    """Holds the URLs and engines produced by the session fixture."""

    def __init__(
        self,
        owner_url: str,
        app_url: str,
        erasure_url: str,
        sweep_url: str,
    ) -> None:
        self.owner_url = owner_url
        self.app_url = app_url
        self.erasure_url = erasure_url
        self.sweep_url = sweep_url


def _run_alembic_upgrade(sync_url: str) -> None:
    """Run ``alembic upgrade head`` against the test database."""
    env = os.environ.copy()
    env["DATABASE_URL"] = sync_url
    backend_dir = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        check=True,
        capture_output=True,
    )


def _apply_grants_sql(admin_conn_str: str) -> None:
    """Apply ``backend/grants.sql`` against the test database.

    Also sets passwords on the three application roles so password-
    authenticated connections work (CI + local docker both use md5).
    """
    import psycopg

    grants_path = Path(__file__).resolve().parents[1] / "grants.sql"
    grants_sql = grants_path.read_text(encoding="utf-8")

    # Passwords are escaped by single-quote doubling because ALTER ROLE
    # does not accept parameter placeholders for the PASSWORD clause.
    escaped_pw = _TEST_ROLE_PASSWORD.replace("'", "''")
    with psycopg.connect(admin_conn_str, autocommit=True) as conn:
        conn.execute(grants_sql)
        for role in ("ta_report_app", "ta_report_erasure", "ta_report_sweep"):
            conn.execute(f"ALTER ROLE {role} WITH PASSWORD '{escaped_pw}'")  # noqa: S608


def _drop_and_create_test_db(admin_url: str, test_db: str) -> None:
    import psycopg

    admin_conn_str = _psycopg_conn_str(admin_url)
    with psycopg.connect(admin_conn_str, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (test_db,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
        conn.execute(f'CREATE DATABASE "{test_db}"')


@pytest.fixture(scope="session")
def test_database() -> Iterator[_TestDatabase]:
    """Spin up a fresh test DB with alembic + grants, yield URLs, drop at end.

    Skips the session if Postgres is unreachable.
    """
    reachable, reason = _postgres_reachable(_psycopg_conn_str(_ADMIN_URL))
    if not reachable:
        pytest.skip(f"Postgres not reachable for integration tests: {reason}")

    test_db = _db_name_from(_DEFAULT_TEST_URL)
    _drop_and_create_test_db(_ADMIN_URL, test_db)

    owner_url = _DEFAULT_TEST_URL
    _run_alembic_upgrade(_to_sync_url(owner_url))

    owner_conn_str = _psycopg_conn_str(owner_url)
    _apply_grants_sql(owner_conn_str)

    app_url = _swap_role(owner_url, "ta_report_app", _TEST_ROLE_PASSWORD)
    erasure_url = _swap_role(owner_url, "ta_report_erasure", _TEST_ROLE_PASSWORD)
    sweep_url = _swap_role(owner_url, "ta_report_sweep", _TEST_ROLE_PASSWORD)

    yield _TestDatabase(
        owner_url=owner_url,
        app_url=app_url,
        erasure_url=erasure_url,
        sweep_url=sweep_url,
    )

    # Teardown: drop the test DB so the next run starts clean.
    try:
        import psycopg

        with psycopg.connect(_psycopg_conn_str(_ADMIN_URL), autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (test_db,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
    except Exception:  # noqa: BLE001 — best-effort teardown
        pass


# ---------------------------------------------------------------------------
# Engine fixtures (session-scoped)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def superuser_engine(test_database: _TestDatabase) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(_to_async_url(test_database.owner_url), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def app_engine(test_database: _TestDatabase) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(_to_async_url(test_database.app_url), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def erasure_engine(test_database: _TestDatabase) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(_to_async_url(test_database.erasure_url), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def sweep_engine(test_database: _TestDatabase) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(_to_async_url(test_database.sweep_url), pool_pre_ping=True)
    yield engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# Per-test cleanup: TRUNCATE all app tables between tests
# ---------------------------------------------------------------------------

#: Order matters only for readability; TRUNCATE ... CASCADE handles FKs.
_TRUNCATE_TABLES = (
    "audit_log",
    "sessions",
    "user_hub_scopes",
    "comments",
    "benchmark_notes",
    "city_notes",
    "hub_pairs",
    "column_mappings",
    "config_kv",
    "sheet_snapshot",
    "users",
)


@pytest_asyncio.fixture(autouse=False)
async def clean_db(superuser_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """TRUNCATE every application table before the test runs.

    Opt in by naming ``clean_db`` in the test signature, or rely on any of the
    higher-level fixtures (``owner_session``, ``app_session``, user seeds) that
    depend on it transitively.
    """
    from sqlalchemy import text

    table_list = ", ".join(_TRUNCATE_TABLES)
    async with superuser_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))
    yield


# ---------------------------------------------------------------------------
# AsyncSession fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def owner_session(
    superuser_engine: AsyncEngine,
    clean_db: None,
) -> AsyncGenerator[AsyncSession, None]:
    """AsyncSession bound to the superuser engine.  Use for seeding."""
    factory = async_sessionmaker(superuser_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def app_session(
    app_engine: AsyncEngine,
    clean_db: None,
) -> AsyncGenerator[AsyncSession, None]:
    """AsyncSession bound to ``ta_report_app``.

    Route handlers and their audit writes run through this session in tests,
    so the audit-log grant model is exercised end-to-end.
    """
    factory = async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def erasure_session(
    erasure_engine: AsyncEngine,
    clean_db: None,
) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(erasure_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed helpers and role fixtures
# ---------------------------------------------------------------------------


CreateUserFn = Callable[..., "uuid.UUID"]


@pytest_asyncio.fixture
async def create_user(owner_session: AsyncSession) -> CreateUserFn:
    """Factory fixture that seeds a ``User`` (and optional hub scopes).

    Usage::

        user_id = await create_user(role="admin", email="a@symphony.is")
    """

    async def _create(
        *,
        email: str | None = None,
        display_name: str | None = None,
        role: RoleEnum | str = RoleEnum.viewer,
        allowed_hubs: list[str] | None = None,
        is_active: bool = True,
    ) -> uuid.UUID:
        role_enum = RoleEnum(role) if isinstance(role, str) else role
        uid = uuid.uuid4()
        email = email or f"user-{uid.hex[:8]}@symphony.is"
        display_name = display_name or f"Test {role_enum.value.title()}"

        user = User(
            id=uid,
            email=email,
            display_name=display_name,
            role=role_enum,
            is_active=is_active,
        )
        owner_session.add(user)
        await owner_session.flush()

        for hub in allowed_hubs or []:
            owner_session.add(UserHubScope(user_id=uid, hub_name=hub))

        await owner_session.commit()
        return uid

    return _create


@pytest_asyncio.fixture
async def admin_user(create_user: CreateUserFn) -> uuid.UUID:
    return await create_user(role=RoleEnum.admin, email="admin@symphony.is")


@pytest_asyncio.fixture
async def editor_user(create_user: CreateUserFn) -> uuid.UUID:
    return await create_user(role=RoleEnum.editor, email="editor@symphony.is")


@pytest_asyncio.fixture
async def viewer_user(create_user: CreateUserFn) -> uuid.UUID:
    return await create_user(role=RoleEnum.viewer, email="viewer@symphony.is")


@pytest_asyncio.fixture
async def hub_scoped_viewer(create_user: CreateUserFn) -> uuid.UUID:
    """Viewer scoped to Sarajevo + Skopje.  Drives TC-E-4 in M5 and TC-I-API-6."""
    return await create_user(
        role=RoleEnum.viewer,
        email="scoped@symphony.is",
        allowed_hubs=["Sarajevo", "Skopje"],
    )


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Kept for back-compat with existing unit tests that don't need DB."""
    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Auth-aware TestClient wired to the test DB (PR 3)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_client(
    app_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    clean_db: None,
) -> AsyncGenerator[TestClient, None]:
    """FastAPI TestClient whose ``get_db`` yields sessions bound to ``ta_report_app``.

    This is how route-level integration tests exercise the production
    dependency graph (cookie verify → session row load → ``last_seen_at``
    bump → handler → audit write → commit) against the grants-aware DB.

    Sets ``SESSION_COOKIE_INSECURE=1`` so the signed cookie can ride over
    HTTP under the TestClient; the production cookie is still Secure.
    """
    from app.config import get_settings
    from app.db.session import get_db
    from app.main import app

    monkeypatch.setenv("SESSION_COOKIE_INSECURE", "1")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-secret-key-change-me")
    # Settings are lru_cached; clear so the above env vars take effect.
    get_settings.cache_clear()

    factory = async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def seed_session(
    owner_session: AsyncSession,
) -> Callable[..., Any]:
    """Factory that seeds a ``Session`` row for a user and returns ``(id, cookie)``.

    Lets integration tests simulate the state a real Google callback would
    have left behind, without calling the OAuth flow (PR 4).  Supports
    overriding timestamps so TC-I-AUTH-5 and TC-I-AUTH-6 can drive
    idle-/absolute-timeout assertions.
    """
    from datetime import UTC, datetime, timedelta

    from app.auth.cookies import sign_session_id
    from app.config import get_settings
    from app.db.models import Session as SessionRow

    async def _seed(
        user_id: uuid.UUID,
        *,
        last_seen_at: datetime | None = None,
        expires_at: datetime | None = None,
        revoked_at: datetime | None = None,
    ) -> tuple[uuid.UUID, str]:
        settings = get_settings()
        now = datetime.now(UTC)
        absolute = timedelta(minutes=settings.session_absolute_timeout_minutes)
        sid = uuid.uuid4()
        row = SessionRow(
            id=sid,
            user_id=user_id,
            issued_at=now,
            last_seen_at=last_seen_at or now,
            expires_at=expires_at or (now + absolute),
            revoked_at=revoked_at,
        )
        owner_session.add(row)
        await owner_session.commit()
        return sid, sign_session_id(sid)

    return _seed  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# CSRF helper for POST integration tests (PR B of M4 review follow-up)
# ---------------------------------------------------------------------------


@pytest.fixture
def attach_csrf() -> Callable[[TestClient], dict[str, str]]:
    """Set the ``ta_csrf`` cookie on ``client`` and return matching headers.

    State-changing routes (``POST /api/auth/logout``, ``POST /api/report/refresh``,
    ``POST /api/admin/users/{id}/revoke-sessions``) require a double-submit
    CSRF check (``app.auth.csrf``).  Tests call::

        headers = attach_csrf(api_client)
        api_client.post("/api/auth/logout", headers=headers)

    The fixture deliberately picks a fixed token value so test failures
    surface as "got 403 csrf" rather than as flaky randomness.
    """
    from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

    def _attach(client: TestClient) -> dict[str, str]:
        token = "test-csrf-token-fixed-for-determinism"  # noqa: S105 — test fixture
        client.cookies.set(CSRF_COOKIE_NAME, token)
        return {CSRF_HEADER_NAME: token}

    return _attach


# ---------------------------------------------------------------------------
# Sheets client mock (prevents tests from hitting real Google API)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_sheets_client() -> Generator[Any, None, None]:
    """Patch ``get_sheets_client`` with a mock that returns an empty fetch result.

    Tests that call any endpoint touching the Sheets layer must apply this
    fixture (or supply their own patch) so CI runs without real credentials.
    """
    from datetime import UTC, datetime
    from unittest.mock import MagicMock, patch

    from app.sheets.models import SheetFetchResult

    empty_result = SheetFetchResult(
        rows=[], stale=False, fetched_at=datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    )

    async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
        return empty_result

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = _get_rows
        mock_client.invalidate = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


# ---------------------------------------------------------------------------
# APP_ENV override helper (get_settings LRU cache aware)
# ---------------------------------------------------------------------------


@pytest.fixture
def override_app_env(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Callable[[str], None], None, None]:
    """Yield a callable that sets APP_ENV and clears the get_settings LRU cache.

    Usage::

        def test_something(override_app_env):
            override_app_env("prod")
            # get_settings() now returns settings with app_env == "prod"

    The cache is cleared both on call and unconditionally at fixture teardown
    so sibling tests are never exposed to the patched value.  Both steps are
    necessary: the call-time clear makes the new value visible; the teardown
    clear prevents cross-test contamination when the next test reads
    get_settings() before monkeypatch has fully unset the env var.
    """
    from app.config import get_settings

    def _set(env: str) -> None:
        monkeypatch.setenv("APP_ENV", env)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


class _JsonLogCapture:
    """Captures log records emitted during a test and exposes them parsed.

    Holds a reference to the pytest ``caplog`` fixture rather than its
    ``records`` list, because the list reference can change between fixture
    setup and test body; re-reading ``caplog.records`` on every access is
    the safe path.

    Each record is asserted to have the structured-log required keys
    (``timestamp``, ``level``) the first time ``assert_structured()`` is
    called.  This is TC-I-PRIV-2.
    """

    REQUIRED_KEYS = ("timestamp", "level")

    def __init__(self, caplog: pytest.LogCaptureFixture) -> None:
        self._caplog = caplog

    @staticmethod
    def _record_to_dict(record: logging.LogRecord) -> dict[str, Any]:
        """Render a ``LogRecord`` through the app's RedactingFormatter and parse it."""
        from app.logging import RedactingFormatter

        fmt = RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        return json.loads(fmt.format(record))

    @property
    def records(self) -> list[dict[str, Any]]:
        return [self._record_to_dict(r) for r in self._caplog.records]

    def assert_structured(self) -> None:
        for rec in self.records:
            for key in self.REQUIRED_KEYS:
                assert key in rec, f"log record missing required key {key!r}: {rec}"

    def events(self) -> list[str]:
        """Return the ``event`` field of each record, defaulting to message."""
        return [r.get("event") or r.get("message", "") for r in self.records]

    def find(self, event: str) -> dict[str, Any] | None:
        for rec in self.records:
            if rec.get("event") == event or rec.get("message") == event:
                return rec
        return None

    def assert_no_secret_values(self, values: list[str]) -> None:
        """Assert none of the given literal secret values appear anywhere in the logs.

        Used by TC-I-PRIV-1 (no cookies, tokens, or service account JSON in
        application logs).  Checks the rendered JSON so redaction bugs are
        caught too.
        """
        rendered = json.dumps(self.records)
        for value in values:
            if not value:
                continue
            assert value not in rendered, (
                f"secret value leaked into logs: matched {value[:6]}... "
                "(full value redacted in assertion message)"
            )


@pytest.fixture
def caplog_json(caplog: pytest.LogCaptureFixture) -> Generator[_JsonLogCapture, None, None]:
    """Capture log records during the test and expose them as parsed JSON.

    Uses pytest's ``caplog`` to grab ``LogRecord`` objects, then re-renders
    each through the app's ``RedactingFormatter`` so redaction rules apply.
    """
    caplog.set_level(logging.DEBUG)
    yield _JsonLogCapture(caplog)
