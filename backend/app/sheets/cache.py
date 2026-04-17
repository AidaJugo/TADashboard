"""In-process TTL cache with last-known-good snapshot fallback.

Design
------
- One cache entry: the latest Sheet fetch result.
- TTL is configurable (default 60 s, FR-REPORT-1).
- ``invalidate()`` forces the next call to re-fetch (FR-REPORT-7, manual refresh).
- ``get()`` returns the cached value if fresh, else calls the fetcher.
- On fetcher failure, the cache falls back to the last-good snapshot if one
  exists, setting ``stale=True`` on the result (FR-REPORT-2, TC-I-SH-3).

No locks: at our ~10-user scale a stampede of concurrent refreshes is
acceptable.  This can be upgraded to asyncio.Lock if needed.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.sheets.models import SheetFetchResult


class SheetFetcher(Protocol):
    """Callable that fetches live Sheet data.  Must be async."""

    def __call__(self) -> Awaitable[SheetFetchResult]: ...


class SheetCache:
    """Single-entry async-aware TTL cache for Sheet fetch results."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._cached: SheetFetchResult | None = None
        self._cached_at: float = 0.0
        self._last_good: SheetFetchResult | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """Force the next ``get()`` to bypass the cache (FR-REPORT-7)."""
        self._cached_at = 0.0

    @property
    def last_good(self) -> SheetFetchResult | None:
        """Expose the last-known-good result (used by tests and health checks)."""
        return self._last_good

    async def get(
        self,
        fetcher: Callable[[], Awaitable[SheetFetchResult]],
    ) -> SheetFetchResult:
        """Return a fresh or cached result.

        Sequence:
        1. Cache hit within TTL → return cached value (TC-I-SH-4).
        2. Cache miss / invalidated → call fetcher.
           a. Success → update cache + last_good, return live result (TC-I-SH-5).
           b. Failure → return last_good with stale=True (TC-I-SH-3).
              If no last_good exists, re-raise the fetcher exception.
        """
        if self._is_fresh():
            return self._cached  # type: ignore[return-value]

        try:
            result = await fetcher()
        except Exception:
            if self._last_good is not None:
                return self._stale_copy(self._last_good)
            raise

        self._cached = result
        self._cached_at = time.monotonic()
        if not result.stale:
            self._last_good = result
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_fresh(self) -> bool:
        return self._cached is not None and (time.monotonic() - self._cached_at) < self._ttl

    @staticmethod
    def _stale_copy(result: SheetFetchResult) -> SheetFetchResult:
        return result.model_copy(update={"stale": True})
