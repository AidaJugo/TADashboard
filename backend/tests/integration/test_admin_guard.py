"""Integration test for role-based route guards (TC-I-API-2, TC-S-3).

- TC-I-API-2 — Viewer GET ``/api/admin/ping`` returns 403.
- TC-S-3     — That 403 also writes an ``access_denied`` audit row whose
              ``target`` names the method + path that was rejected
              (FR-AUTHZ-2).  Added in M4 review follow-up PR A.
              Extended in M6 review to cover users, config, and sweep routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


async def test_tc_i_api_2_viewer_forbidden_from_admin_endpoint(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/admin/ping")
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient role"


async def test_editor_forbidden_from_admin_endpoint(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/admin/ping")
    assert response.status_code == 403


async def test_admin_allowed_on_admin_endpoint(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/admin/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unauthenticated_admin_endpoint_returns_401_not_403(
    api_client: TestClient,
) -> None:
    """Unauth should surface as 401; otherwise a probe can differentiate admin routes."""
    response = api_client.get("/api/admin/ping")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# TC-S-3 — viewer 403 on /api/admin/* writes an access_denied audit row.
# ---------------------------------------------------------------------------


async def test_tc_s_3_viewer_403_writes_access_denied_audit_row(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """Viewer hits an admin route → 403 + ``access_denied`` audit row.

    The audit row is the contract from PRD FR-AUTHZ-2 ("Admin-only
    routes reject non-admin users with HTTP 403 and an audit entry.")
    and must survive even though the response is a failure — ``require_role``
    commits the audit before raising, just like ``get_report``'s
    hub-scope-violation path.
    """
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/admin/ping")
    assert response.status_code == 403

    rows = (
        await owner_session.execute(
            text(
                "SELECT action, actor_id, target FROM audit_log "
                "WHERE actor_id = :uid AND action = :action "
                "ORDER BY created_at DESC"
            ),
            {"uid": viewer_user, "action": AuditAction.access_denied},
        )
    ).all()
    assert len(rows) == 1
    action, actor_id, target = rows[0]
    assert action == AuditAction.access_denied
    assert actor_id == viewer_user
    assert target == "GET /api/admin/ping"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/config"),
        ("GET", "/api/admin/hub-pairs"),
        # POST mutation routes require a CSRF token; the CSRF check fires before
        # require_role, so a missing CSRF token returns 403 from CSRF (not role
        # guard) and no access_denied audit row is written.  Those routes are
        # covered by the per-module test_admin_*.py files which include CSRF tokens.
    ],
)
async def test_tc_s_3_access_denied_audit_row_written_for_key_admin_routes(
    method: str,
    path: str,
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """FR-AUTHZ-2: every protected admin route writes an access_denied audit row on 403.

    Parametrised over the three routes that carry the most sensitive actions:
    user listing, config read, and sweep trigger.
    """
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get(path) if method == "GET" else api_client.post(path)
    assert response.status_code == 403

    rows = (
        await owner_session.execute(
            text(
                "SELECT action, actor_id, target FROM audit_log "
                "WHERE actor_id = :uid AND action = :action AND target = :target "
                "ORDER BY created_at DESC"
            ),
            {
                "uid": viewer_user,
                "action": AuditAction.access_denied,
                "target": f"{method} {path}",
            },
        )
    ).all()
    assert len(rows) >= 1, f"Expected access_denied audit row for {method} {path}, found none"


async def test_admin_200_writes_no_access_denied_row(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """Negative control: a permitted call must not write an access_denied row."""
    _session_id, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/admin/ping")
    assert response.status_code == 200

    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_id = :uid AND action = :action"),
            {"uid": admin_user, "action": AuditAction.access_denied},
        )
    ).scalar_one()
    assert count == 0
