"""Integration tests for ``POST /api/admin/users/{user_id}/revoke-sessions``.

Closes:

- TC-I-AUTH-10 — Admin revokes another user's active sessions; the next
  request from any of those sessions is rejected (NFR-COMP-2, ADR 0012).

The endpoint is the operator-assisted offboarding path: when IT has
deactivated a user in Google Workspace and we cannot wait up to 24h for
the absolute session timeout to take effect.

Asserted invariants:

1. Admin caller, two prior live sessions for the target → both
   ``sessions.revoked_at`` populated, response body reports
   ``{"revoked": 2}``.
2. The target user's old cookie now hits 401 ``session revoked`` on the
   very next request (load_session enforces ``revoked_at IS NOT NULL``).
3. Exactly one ``admin_revoke_sessions`` audit row is written, with
   ``actor_id`` = admin and ``target = "user:<uid>"``.
4. Non-admin callers (viewer/editor) get 403 + ``access_denied`` audit row
   (covered indirectly by ``test_admin_guard.py``; we assert the negative
   here too so the endpoint can never silently downgrade its guard).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import Session as SessionRow

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-I-AUTH-10 — happy path
# ---------------------------------------------------------------------------


async def test_tc_i_auth_10_admin_revokes_targets_active_sessions(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    viewer_sid_1, viewer_cookie_1 = await seed_session(viewer_user)
    viewer_sid_2, _viewer_cookie_2 = await seed_session(viewer_user)

    _admin_sid, admin_cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)
    csrf_headers = attach_csrf(api_client)

    response = api_client.post(
        f"/api/admin/users/{viewer_user}/revoke-sessions",
        headers=csrf_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"revoked": 2}

    # Both viewer sessions are revoked at the DB layer.
    rows = (
        (await owner_session.execute(select(SessionRow).where(SessionRow.user_id == viewer_user)))
        .scalars()
        .all()
    )
    assert len(rows) == 2
    for row in rows:
        assert row.revoked_at is not None
    assert {row.id for row in rows} == {viewer_sid_1, viewer_sid_2}

    # Reusing the viewer cookie now hits 401 with the documented detail.
    api_client.cookies.set(SESSION_COOKIE_NAME, viewer_cookie_1)
    me_resp = api_client.get("/api/auth/me")
    assert me_resp.status_code == 401
    assert me_resp.json()["detail"] == "session revoked"

    # Exactly one audit row, naming the admin as actor and the viewer as target.
    audit_rows = (
        await owner_session.execute(
            text(
                "SELECT actor_id, target FROM audit_log "
                "WHERE action = :action ORDER BY created_at DESC"
            ),
            {"action": AuditAction.admin_revoke_sessions},
        )
    ).all()
    assert len(audit_rows) == 1
    actor_id, target = audit_rows[0]
    assert actor_id == admin_user
    assert target == f"user:{viewer_user}"


# ---------------------------------------------------------------------------
# Idempotency — calling twice is safe; second call reports 0 revoked.
# ---------------------------------------------------------------------------


async def test_revoke_is_idempotent(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    await seed_session(viewer_user)
    _admin_sid, admin_cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)
    csrf_headers = attach_csrf(api_client)

    first = api_client.post(f"/api/admin/users/{viewer_user}/revoke-sessions", headers=csrf_headers)
    assert first.status_code == 200
    assert first.json() == {"revoked": 1}

    second = api_client.post(
        f"/api/admin/users/{viewer_user}/revoke-sessions", headers=csrf_headers
    )
    assert second.status_code == 200
    assert second.json() == {"revoked": 0}


# ---------------------------------------------------------------------------
# Authz — non-admin callers must hit 403, not 200, even with no rows to revoke.
# ---------------------------------------------------------------------------


async def test_viewer_cannot_revoke(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    """Even with a valid CSRF token, a viewer must hit the role guard."""
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    csrf_headers = attach_csrf(api_client)

    response = api_client.post(
        f"/api/admin/users/{viewer_user}/revoke-sessions", headers=csrf_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient role"


async def test_editor_cannot_revoke(
    api_client: TestClient,
    editor_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    csrf_headers = attach_csrf(api_client)

    response = api_client.post(
        f"/api/admin/users/{viewer_user}/revoke-sessions", headers=csrf_headers
    )
    assert response.status_code == 403


async def test_unauthenticated_revoke_returns_403_csrf_first(
    api_client: TestClient,
    viewer_user: uuid.UUID,
) -> None:
    """CSRF dep runs before authn — no cookie/header → 403 csrf, not 401."""
    response = api_client.post(f"/api/admin/users/{viewer_user}/revoke-sessions")
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf token missing or invalid"


async def test_unauthenticated_with_csrf_revoke_returns_401(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    """With a valid CSRF token but no session, authn rejects with 401."""
    csrf_headers = attach_csrf(api_client)
    response = api_client.post(
        f"/api/admin/users/{viewer_user}/revoke-sessions", headers=csrf_headers
    )
    assert response.status_code == 401
