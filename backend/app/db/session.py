"""SQLAlchemy async session factory and engine.

Usage
-----
Depend on ``get_db`` in FastAPI route handlers::

    @router.get("/example")
    async def example(db: AsyncSession = Depends(get_db)) -> ...:
        ...

The engine reads DATABASE_URL from the Settings singleton (ADR 0008).
Connection pooling is intentionally minimal for our ~10-user scale.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

log = get_logger(__name__)


def _async_url(url: str) -> str:
    """Ensure the URL uses the async psycopg driver.

    Settings stores a psycopg (sync) URL by default; SQLAlchemy async engine
    requires the ``+psycopg_async`` dialect suffix.
    """
    if "+psycopg_async" in url:
        return url
    return re.sub(r"\+psycopg\b", "+psycopg_async", url)


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        _async_url(settings.database_url),
        echo=settings.app_env == "dev",
        pool_size=5,
        max_overflow=10,
    )


def _build_role_engine(url: str, fallback_url: str, role_name: str) -> AsyncEngine:
    """Build an engine for a restricted DB role (erasure or sweep).

    If ``url`` is empty the engine falls back to ``fallback_url`` so the app
    starts in dev/test without separate role credentials.  In that case DB-level
    grants are NOT enforced — the production startup check in ``app.main``
    catches this before any request is served in ``app_env=prod``.

    The ``role_name`` parameter is only used for the startup log line
    (``engine_role_resolved``) so operators can verify which credential is
    actually in use.
    """
    effective = url.strip() if url.strip() else fallback_url
    log.info("db_role_engine_built", extra={"role": role_name, "using_role_url": bool(url.strip())})
    return create_async_engine(
        _async_url(effective),
        echo=False,
        pool_size=2,
        max_overflow=2,
    )


class _LazyEngineState:
    """Holds module-level singletons without requiring global statements."""

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None
    _erasure_engine: AsyncEngine | None = None
    _erasure_factory: async_sessionmaker[AsyncSession] | None = None
    _sweep_engine: AsyncEngine | None = None
    _sweep_factory: async_sessionmaker[AsyncSession] | None = None

    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = _build_engine()
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                self.engine(),
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    def erasure_engine(self) -> AsyncEngine:
        if self._erasure_engine is None:
            settings = get_settings()
            self._erasure_engine = _build_role_engine(
                settings.database_url_erasure, settings.database_url, "ta_report_erasure"
            )
        return self._erasure_engine

    def erasure_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._erasure_factory is None:
            self._erasure_factory = async_sessionmaker(
                self.erasure_engine(),
                expire_on_commit=False,
                autoflush=False,
            )
        return self._erasure_factory

    def sweep_engine(self) -> AsyncEngine:
        if self._sweep_engine is None:
            settings = get_settings()
            self._sweep_engine = _build_role_engine(
                settings.database_url_sweep, settings.database_url, "ta_report_sweep"
            )
        return self._sweep_engine

    def sweep_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._sweep_factory is None:
            self._sweep_factory = async_sessionmaker(
                self.sweep_engine(),
                expire_on_commit=False,
                autoflush=False,
            )
        return self._sweep_factory

    def reset(self) -> None:
        """Reset singletons (used in tests to swap in a test engine)."""
        self._engine = None
        self._session_factory = None
        self._erasure_engine = None
        self._erasure_factory = None
        self._sweep_engine = None
        self._sweep_factory = None


_state = _LazyEngineState()


def get_engine() -> AsyncEngine:
    return _state.engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return _state.session_factory()


def get_erasure_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to ``ta_report_erasure`` (ADR 0010)."""
    return _state.erasure_factory()


def get_sweep_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to ``ta_report_sweep`` (ADR 0010)."""
    return _state.sweep_factory()


async def get_sweep_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request sweep session (ta_report_sweep)."""
    async with get_sweep_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request DB session."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
