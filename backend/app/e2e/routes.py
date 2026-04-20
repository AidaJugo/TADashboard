"""E2E test fixture endpoint — only active when APP_ENV=test.

Provides ``POST /api/e2e/seed-session`` which:
1. Upserts a synthetic user with the given role and hub scope.
2. Creates a live session row.
3. Returns the signed session cookie value so Playwright can inject it.

This endpoint MUST NOT exist in production.  Two independent guards prevent
accidental exposure:

1. ``app/main.py`` only registers this router when ``APP_ENV == "test"``.  In
   production the symbols are never imported and no route is registered.
2. ``require_e2e_env`` (FastAPI ``Depends``) checks strict equality at request
   time and returns 404 if the guard somehow reaches a non-test process.
3. The route handler itself repeats the check as a third line of defence.

All three checks use **strict equality** (``app_env == "test"``), not ``in``,
not ``startswith``, and not a case-folded comparison.

No credentials are mocked here: the real auth middleware reads the real session
table, so the E2E session is as valid as one produced by the OAuth flow.  The
Sheet data is mocked at the network level by Playwright's ``page.route()``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.auth.cookies import SESSION_COOKIE_NAME, sign_session_id
from app.config import get_settings
from app.db.models import RoleEnum, User, UserHubScope
from app.db.models import Session as SessionRow
from app.db.session import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


def require_e2e_env() -> None:
    """FastAPI dependency: block the endpoint in non-test environments.

    Returns 404 (not 403) to avoid confirming the endpoint's existence.
    Uses strict equality — not ``in``, not ``startswith``, no lowercasing.
    """
    if get_settings().app_env != "test":
        raise HTTPException(status_code=404)


class SeedSessionRequest(BaseModel):
    email: str = "e2e-viewer@symphony.is"
    role: RoleEnum = RoleEnum.viewer
    allowed_hubs: list[str] = []
    display_name: str = "E2E Test User"


class SeedSessionResponse(BaseModel):
    session_id: str
    cookie_name: str
    cookie_value: str


@router.post(
    "/seed-session",
    response_model=SeedSessionResponse,
    dependencies=[Depends(require_e2e_env)],
)
async def seed_session(
    body: SeedSessionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SeedSessionResponse:
    """Seed a user + session and return the signed cookie for Playwright.

    Idempotent on email: if the user already exists, the existing row is reused
    and a new session is issued.
    """
    # Defense-in-depth: inline guard mirrors require_e2e_env.  Strict equality.
    if get_settings().app_env != "test":
        raise HTTPException(status_code=404)

    settings = get_settings()

    # --- Upsert user --------------------------------------------------------
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()

    if existing is None:
        user = User(
            id=uuid.uuid4(),
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    else:
        user = existing

    # --- Hub scopes ---------------------------------------------------------
    # Delete all existing scopes before re-adding so repeated calls with a
    # narrower scope don't accumulate rows and widen the effective scope.
    await db.execute(delete(UserHubScope).where(UserHubScope.user_id == user.id))
    for hub in body.allowed_hubs:
        db.add(UserHubScope(user_id=user.id, hub_name=hub))

    # --- Session row --------------------------------------------------------
    now = datetime.now(UTC)
    absolute = timedelta(minutes=settings.session_absolute_timeout_minutes)
    sid = uuid.uuid4()
    session = SessionRow(
        id=sid,
        user_id=user.id,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + absolute,
    )
    db.add(session)
    await db.commit()

    return SeedSessionResponse(
        session_id=str(sid),
        cookie_name=SESSION_COOKIE_NAME,
        cookie_value=sign_session_id(sid),
    )
