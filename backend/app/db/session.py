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

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


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


class _LazyEngineState:
    """Holds module-level singletons without requiring global statements."""

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

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

    def reset(self) -> None:
        """Reset singletons (used in tests to swap in a test engine)."""
        self._engine = None
        self._session_factory = None


_state = _LazyEngineState()


def get_engine() -> AsyncEngine:
    return _state.engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return _state.session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request DB session."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
