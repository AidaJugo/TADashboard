"""CSRF (double-submit cookie) tests — TC-S-1.

docs/testing.md §6:
    TC-S-1: CSRF token missing on a POST request returns 403.

The token is a 32-byte URL-safe value issued at OAuth callback time
(``app.auth.csrf.set_csrf_cookie``).  Browsers send it in the
``ta_csrf`` cookie; the SPA reads that cookie via JS and echoes it as
``X-CSRF-Token``.  Both must match byte-for-byte (``secrets.compare_digest``).

This test file pins the contract from three angles:

1. POST without any CSRF cookie/header → 403, ``detail == "csrf token
   missing or invalid"``, **and the underlying state change does not
   happen** (session is still alive).  This is the security invariant.
2. POST with a header value that does not match the cookie → 403.
3. POST with matching cookie + header → endpoint runs as before
   (the rest of the auth/authz stack is unchanged).
4. The dependency is a no-op for safe methods (GET ``/api/auth/me``
   passes without any CSRF state).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.auth.cookies import SESSION_COOKIE_NAME
from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.db.models import Session as SessionRow

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-S-1 — POST /api/auth/logout without CSRF
# ---------------------------------------------------------------------------


async def test_tc_s_1_post_logout_without_csrf_returns_403(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """The state change must not happen when CSRF is missing."""
    session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"

    # Critical: the session must still be alive.  If the dependency
    # ordering were wrong, the handler could partially run before the
    # CSRF check rejected.
    row = (
        await owner_session.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one()
    assert row.revoked_at is None


async def test_post_logout_with_mismatched_csrf_returns_403(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    api_client.cookies.set(CSRF_COOKIE_NAME, "cookie-side-token")

    response = api_client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: "header-side-token-different"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"


async def test_post_logout_with_matching_csrf_succeeds(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    attach_csrf: Callable[[TestClient], dict[str, str]],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    response = api_client.post("/api/auth/logout", headers=headers)
    assert response.status_code == 204


async def test_post_logout_with_only_cookie_returns_403(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    """An attacker who can write the cookie but cannot read it (no XSS)
    still cannot forge the header."""
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    api_client.cookies.set(CSRF_COOKIE_NAME, "only-cookie-no-header")

    response = api_client.post("/api/auth/logout")
    assert response.status_code == 403


async def test_post_logout_with_only_header_returns_403(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.post(
        "/api/auth/logout",
        headers={CSRF_HEADER_NAME: "header-without-cookie"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Safe methods are exempt
# ---------------------------------------------------------------------------


async def test_get_me_does_not_require_csrf(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    """The ``require_csrf`` dependency must skip safe methods entirely.

    ``/api/auth/me`` doesn't depend on require_csrf today, but this
    pins the broader semantic: GETs never need the token, even if a
    future route adds it as a dependency by mistake.
    """
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/auth/me")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Same shape on the other CSRF-guarded routes
# ---------------------------------------------------------------------------


async def test_post_report_refresh_without_csrf_returns_403(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.post("/api/report/refresh")
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"


async def test_post_admin_revoke_without_csrf_returns_403(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _admin_sid, admin_cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)

    response = api_client.post(f"/api/admin/users/{viewer_user}/revoke-sessions")
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"


# ---------------------------------------------------------------------------
# CSRF check fires before authn — an unauthenticated POST should still
# get a 403 csrf, not a 401.  This matters because otherwise an attacker
# learns "this route exists" before being filtered out.
# ---------------------------------------------------------------------------


async def test_post_logout_unauthenticated_without_csrf_still_403(
    api_client: TestClient,
) -> None:
    response = api_client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"
