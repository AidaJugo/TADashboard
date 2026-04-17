"""Integration tests for the session-cookie auth flow.

Closes:

- TC-I-AUTH-1: Unauthenticated request to a protected route returns 401.
- TC-I-AUTH-5: Idle timeout rejects a session with a stale ``last_seen_at``.
- TC-I-AUTH-6: Absolute timeout rejects a session past ``expires_at``.
- TC-I-AUTH-7: Logout revokes the session server-side; reuse of the old
               cookie is rejected on the next request.

Each test seeds a :class:`~app.db.models.Session` row directly via the
``seed_session`` fixture so we can control ``last_seen_at`` and
``expires_at`` without going through the OAuth callback (that lands in
PR 4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import Session as SessionRow

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-I-AUTH-1 — unauthenticated request returns 401
# ---------------------------------------------------------------------------


async def test_tc_i_auth_1_unauthenticated_request_returns_401(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "missing session cookie"


async def test_unauthenticated_bad_cookie_returns_401(api_client: TestClient) -> None:
    api_client.cookies.set(SESSION_COOKIE_NAME, "not-a-valid-signed-cookie")
    response = api_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid session cookie"


# ---------------------------------------------------------------------------
# Happy path — signed-in user can read /me
# ---------------------------------------------------------------------------


async def test_authenticated_me_returns_user_identity(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/auth/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(viewer_user)
    assert body["role"] == "viewer"
    assert body["email"] == "viewer@symphony.is"


# ---------------------------------------------------------------------------
# TC-I-AUTH-5 — idle timeout
# ---------------------------------------------------------------------------


async def test_tc_i_auth_5_idle_timeout_rejects_stale_session(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    """Session that has been idle for > 4 hours + 1 minute is rejected."""
    idle_cutoff = datetime.now(UTC) - timedelta(hours=4, minutes=1)
    _session_id, cookie = await seed_session(viewer_user, last_seen_at=idle_cutoff)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "session idle timeout exceeded"


# ---------------------------------------------------------------------------
# TC-I-AUTH-6 — absolute timeout
# ---------------------------------------------------------------------------


async def test_tc_i_auth_6_absolute_timeout_rejects_old_session(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    """Session past ``expires_at`` is rejected even if ``last_seen_at`` is fresh."""
    now = datetime.now(UTC)
    _session_id, cookie = await seed_session(
        viewer_user,
        last_seen_at=now,
        expires_at=now - timedelta(minutes=1),
    )
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "session absolute timeout exceeded"


# ---------------------------------------------------------------------------
# TC-I-AUTH-7 — logout revokes server-side
# ---------------------------------------------------------------------------


async def test_tc_i_auth_7_logout_revokes_session_and_rejects_old_cookie(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    logout_response = api_client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    # The TestClient keeps cookies across calls.  Server-side the session
    # is revoked, so reusing the cookie now returns 401 regardless.
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    reuse_response = api_client.get("/api/auth/me")
    assert reuse_response.status_code == 401
    assert reuse_response.json()["detail"] == "session revoked"

    # revoked_at is set on the DB row.
    row = (
        await owner_session.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one()
    assert row.revoked_at is not None


async def test_user_deactivated_is_rejected(
    api_client: TestClient,
    create_user: Callable[..., object],
    seed_session: Callable[..., object],
) -> None:
    """NFR-COMP-2 / FR-AUTH-5: deactivated user's session is rejected."""
    user_id = await create_user(is_active=False, email="deactivated@symphony.is")
    _session_id, cookie = await seed_session(user_id)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "user deactivated"
