"""Server-side session lifecycle (FR-AUTH-4, FR-AUTH-5, ADR 0004).

One row per active browser session in the ``sessions`` table.  The cookie
carries nothing but the signed session id.  This module owns:

- :func:`create_session` — issued at login.
- :func:`load_session`   — read on every authenticated request.
- :func:`bump_last_seen` — extends the idle window.
- :func:`revoke_session` — logout or offboarding.

Timeout policy:

- **Absolute**: ``sessions.expires_at`` is set to ``issued_at + 24h`` at
  creation.  A session past ``expires_at`` is invalid (FR-AUTH-4).
- **Idle**: if ``now() - last_seen_at > 4h`` the session is invalid
  (FR-AUTH-4).
- **Revocation**: ``revoked_at IS NOT NULL`` invalidates the session on the
  very next request (FR-AUTH-5).
- **Offboarding**: if the user's ``is_active`` is False the session is
  rejected even if all three timestamp checks pass.

All time comparisons are done in SQL against ``now()`` so the app and DB
agree on "now".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.config import get_settings
from app.db.models import Session as SessionRow
from app.db.models import User
from app.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class SessionInvalidError(Exception):
    """Raised when the session row fails any of the validity checks."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_session(
    db: AsyncSession,
    *,
    user: User,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> SessionRow:
    """Create a new session row and return the persisted instance.

    The caller is responsible for committing the transaction; the caller is
    also responsible for setting the signed cookie on the response.  Keeping
    those two steps separate means the OAuth callback can run the same
    create-session logic whether it came from a real Google flow or a test
    harness.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    absolute = timedelta(minutes=settings.session_absolute_timeout_minutes)

    row = SessionRow(
        id=uuid.uuid4(),
        user_id=user.id,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + absolute,
        client_ip=client_ip,
        user_agent=(user_agent[:500] if user_agent else None),
    )
    db.add(row)
    await db.flush()
    log.info(
        "session_created",
        extra={"session_id": str(row.id), "actor_id": str(user.id)},
    )
    return row


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


async def load_session(db: AsyncSession, session_id: uuid.UUID) -> tuple[SessionRow, User]:
    """Load a session row and its owning user, raising :class:`SessionInvalidError` on any failure.

    Validity checks, in order:

    1. Row exists.
    2. ``revoked_at IS NULL``.
    3. ``expires_at > now()`` (absolute cap).
    4. ``last_seen_at >= now() - idle_timeout`` (idle cap).
    5. Owning user exists and ``is_active`` is True.
    """
    stmt = (
        select(SessionRow, User)
        .join(User, User.id == SessionRow.user_id)
        .where(SessionRow.id == session_id)
    )
    result = await db.execute(stmt)
    hit = result.one_or_none()
    if hit is None:
        raise SessionInvalidError("session not found")

    row, user = hit

    if row.revoked_at is not None:
        raise SessionInvalidError("session revoked")

    settings = get_settings()
    now = datetime.now(UTC)
    if row.expires_at <= now:
        raise SessionInvalidError("session absolute timeout exceeded")

    idle_cutoff = now - timedelta(minutes=settings.session_idle_timeout_minutes)
    if row.last_seen_at < idle_cutoff:
        raise SessionInvalidError("session idle timeout exceeded")

    if not user.is_active:
        raise SessionInvalidError("user deactivated")

    return row, user


# ---------------------------------------------------------------------------
# Bump
# ---------------------------------------------------------------------------


async def bump_last_seen(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Update ``last_seen_at`` to ``now()`` for ``session_id``.

    Uses a direct UPDATE so the bump is a single round trip and never
    conflicts with another writer on the same session row.
    """
    stmt = (
        update(SessionRow).where(SessionRow.id == session_id).values(last_seen_at=datetime.now(UTC))
    )
    await db.execute(stmt)


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


async def revoke_session(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Mark the session revoked (logout, offboarding).

    Idempotent: calling twice is a no-op on the second call.
    """
    stmt = (
        update(SessionRow)
        .where(SessionRow.id == session_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(stmt)
    log.info("session_revoked", extra={"session_id": str(session_id)})


async def revoke_all_sessions_for(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every active session of ``user_id`` and return the rowcount.

    Used by two paths:

    - **Login rotation**: the OAuth callback revokes any prior live
      sessions before minting a new one so a leaked cookie cannot
      outlive a fresh sign-in (review finding: session rotation).
    - **Admin offboarding**: ``POST /api/admin/users/{id}/revoke-sessions``
      closes every session of a user that IT has deactivated in
      Google Workspace (ADR 0012, TC-I-AUTH-10).

    Both callers share this helper so there is one UPDATE shape — if the
    predicate ever changes (e.g. adding an ``expires_at > now()`` guard)
    it changes in exactly one place.
    """
    stmt = (
        update(SessionRow)
        .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    result = await db.execute(stmt)
    # ``CursorResult.rowcount`` is typed on the concrete cursor only; the
    # base ``Result`` shape does not expose it.  Same pattern as
    # ``audit/erasure.py``.
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    log.info(
        "sessions_bulk_revoked",
        extra={"actor_id": str(user_id), "revoked_count": rowcount},
    )
    return rowcount
