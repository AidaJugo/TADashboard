"""Single-source hub scoping filter (FR-AUTHZ-3, FR-AUTHZ-4, FR-AUTHZ-5).

This module is the **only** place in the codebase that decides whether a hub
is visible to a given user.  The M5 report pipeline and every admin / API
handler that touches hub-scoped data must import its primitives from here.
A lint-style test in ``tests/unit/test_authz_hub_scope.py`` asserts the
single-source invariant.

Semantics (PRD FR-AUTHZ-3):
    - A user with **no** rows in ``user_hub_scopes`` sees every hub.
    - A user with one or more hub scope rows sees only those hubs.

The primitives here are pure (no I/O, no SQLAlchemy).  The report layer
resolves ``city -> hub`` via ``HubPair`` before calling into this module, so
this module does not need the raw ``HireRow`` type or the DB.

Hub comparisons are case-sensitive by convention.  Admin UIs normalise hub
names at write time (stripped, as stored).  If you need case-insensitive
matching, add a helper here; do not add a second hub check elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, true

from app.db.models import UserHubScope

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Iterable

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession


def is_hub_allowed(hub: str, allowed_hubs: list[str]) -> bool:
    """Return True when ``hub`` is visible to a user scoped to ``allowed_hubs``.

    An empty ``allowed_hubs`` means "all hubs" (FR-AUTHZ-3).
    """
    if not allowed_hubs:
        return True
    return hub in allowed_hubs


def filter_hub_names(hubs: Iterable[str], allowed_hubs: list[str]) -> list[str]:
    """Filter an iterable of hub names against a user's hub scope.

    Preserves input order.  Pure: does not mutate ``hubs`` or ``allowed_hubs``.
    """
    if not allowed_hubs:
        return list(hubs)
    allowed_set = set(allowed_hubs)
    return [h for h in hubs if h in allowed_set]


def filter_by_hub[
    T
](items: Iterable[T], key: Callable[[T], str], allowed_hubs: list[str],) -> list[T]:
    """Filter arbitrary items where ``key(item)`` returns the item's hub.

    Usage example (M5 report aggregation)::

        from app.authz.hub_scope import filter_by_hub

        scoped = filter_by_hub(
            rows,
            key=lambda row: city_to_hub[row.city],
            allowed_hubs=user.allowed_hubs,
        )

    The input iterable is not mutated.  The returned list is always a new list.
    """
    if not allowed_hubs:
        return list(items)
    allowed_set = set(allowed_hubs)
    return [item for item in items if key(item) in allowed_set]


async def load_allowed_hubs(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Return the list of hubs the user is scoped to.

    An empty list means *all* hubs (FR-AUTHZ-3).  This is the single DB
    read used by every request path that needs to know a user's scope.
    """
    stmt = select(UserHubScope.hub_name).where(UserHubScope.user_id == user_id)
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


def hub_scope_clause(column: ColumnElement[str], allowed_hubs: list[str]) -> ColumnElement[bool]:
    """Build a SQL WHERE-clause fragment enforcing hub scope at query time.

    - Empty ``allowed_hubs`` returns a constant ``true`` (all hubs visible).
    - Non-empty returns ``column IN (...)``.

    Rejecting a hub explicitly (for example a ``hub`` query param that is not
    in the user's scope) is the caller's job.  This helper only narrows a
    data query; it does not produce a deny-decision on its own.
    """
    if not allowed_hubs:
        return true()
    return column.in_(allowed_hubs)
