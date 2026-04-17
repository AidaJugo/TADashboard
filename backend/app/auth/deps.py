"""Request-scoped authentication dependencies.

FastAPI dependency tree for authenticated endpoints::

    get_db           ──▶ yields an AsyncSession (per-request, auto-commit)
        └─ get_current_user  ──▶ validates cookie + session row, returns User

Every authenticated request therefore goes through this chain exactly once
and "bumps" :attr:`Session.last_seen_at` as a side effect (FR-AUTH-4).

Tests can bypass the full flow by using
``app.dependency_overrides[get_current_user] = lambda: fake_user``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

# NOTE: ``AsyncSession`` and ``User`` are imported at runtime (not under
# TYPE_CHECKING) because FastAPI evaluates the ``Annotated`` type hints of
# this dependency via ``get_type_hints()`` to decide how to resolve the
# ``db`` parameter.  If either name is only a forward reference, FastAPI
# mis-identifies ``db`` as a query parameter and every protected route
# responds 422.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.auth.cookies import SESSION_COOKIE_NAME, InvalidCookieError, verify_cookie
from app.auth.sessions import SessionInvalidError, bump_last_seen, load_session
from app.db.models import User  # noqa: TC001
from app.db.session import get_db
from app.logging import get_logger

log = get_logger(__name__)


def _unauthenticated(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Cookie"},
    )


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Return the current user or raise 401.

    Steps:

    1. Read the signed ``ta_sid`` cookie.
    2. Verify signature + absolute-age (:func:`verify_cookie`).
    3. Load the session row + owning user (:func:`load_session`).  This
       enforces idle timeout, absolute timeout, revocation and
       ``user.is_active``.
    4. Bump :attr:`Session.last_seen_at`.
    5. Return the user.  ``db.commit`` is owned by :func:`get_db` and flushes
       both the bump and any handler writes in one transaction.
    """
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        raise _unauthenticated("missing session cookie")

    try:
        session_id = verify_cookie(raw)
    except InvalidCookieError as exc:
        log.info("auth_cookie_rejected", extra={"reason": str(exc)})
        raise _unauthenticated("invalid session cookie") from exc

    try:
        _session_row, user = await load_session(db, session_id)
    except SessionInvalidError as exc:
        log.info(
            "auth_session_rejected",
            extra={"session_id": str(session_id), "reason": exc.reason},
        )
        raise _unauthenticated(exc.reason) from exc

    await bump_last_seen(db, session_id)
    return user
