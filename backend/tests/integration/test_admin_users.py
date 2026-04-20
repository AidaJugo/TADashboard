"""Integration tests for admin user management (FR-USER-1..3).

Cases covered
-------------
- TC-I-API-10: Deactivating the last admin returns 409 (FR-USER-3).
- TC-I-API-11: Demoting the last admin returns 409 (FR-USER-3).
- TC-S-3 (partial): viewer/editor on admin endpoint returns 403.
- Happy paths: create, list, get, update, deactivate.
- Deactivation revokes sessions and marks user inactive.
- Create duplicate email returns 409.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import RoleEnum

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_cookie(api_client, admin_id, seed_session):
    """Return (cookie_str, headers) for an admin user."""
    return seed_session(admin_id)


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------


async def test_list_users_returns_all_users(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    resp = api_client.get("/api/admin/users")
    assert resp.status_code == 200
    ids = {u["id"] for u in resp.json()}
    assert str(admin_user) in ids
    assert str(viewer_user) in ids


async def test_list_users_forbidden_for_viewer(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert api_client.get("/api/admin/users").status_code == 403


# ---------------------------------------------------------------------------
# Create user
# ---------------------------------------------------------------------------


async def test_create_user_happy_path(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post(
        "/api/admin/users",
        json={"email": "new@symphony.is", "display_name": "New User", "role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new@symphony.is"
    assert body["role"] == "viewer"
    assert body["is_active"] is True

    # Audit row written
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'user_created'")
        )
    ).scalar_one()
    assert count == 1


async def test_create_user_duplicate_email_returns_409(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    # viewer_user fixture already created viewer@symphony.is
    resp = api_client.post(
        "/api/admin/users",
        json={"email": "viewer@symphony.is", "display_name": "Dup", "role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# TC-I-API-10 — last-admin guard on deactivate
# ---------------------------------------------------------------------------


async def test_tc_i_api_10_deactivate_last_admin_returns_409(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    """Deactivating the sole admin returns 409; user stays active (FR-USER-3)."""
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post(f"/api/admin/users/{admin_user}/deactivate", headers=headers)
    assert resp.status_code == 409
    assert "last admin" in resp.json()["detail"].lower()

    # User must still be active
    user_resp = api_client.get(f"/api/admin/users/{admin_user}")
    assert user_resp.status_code == 200
    assert user_resp.json()["is_active"] is True


async def test_deactivate_admin_succeeds_when_another_admin_exists(
    api_client: TestClient,
    admin_user: uuid.UUID,
    create_user: Callable,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    second_admin = await create_user(role=RoleEnum.admin, email="admin2@symphony.is")
    _sid, cookie = await seed_session(second_admin)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post(f"/api/admin/users/{admin_user}/deactivate", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"

    # User now inactive
    user_resp = api_client.get(f"/api/admin/users/{admin_user}")
    assert user_resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# TC-I-API-11 — last-admin guard on role demote
# ---------------------------------------------------------------------------


async def test_tc_i_api_11_demote_last_admin_returns_409(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    """Demoting the sole admin to viewer returns 409 (FR-USER-3)."""
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.patch(
        f"/api/admin/users/{admin_user}",
        json={"role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert "last admin" in resp.json()["detail"].lower()

    # Role unchanged
    user_resp = api_client.get(f"/api/admin/users/{admin_user}")
    assert user_resp.json()["role"] == "admin"


async def test_demote_admin_succeeds_when_another_admin_exists(
    api_client: TestClient,
    admin_user: uuid.UUID,
    create_user: Callable,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    second_admin = await create_user(role=RoleEnum.admin, email="admin2@symphony.is")
    _sid, cookie = await seed_session(second_admin)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.patch(
        f"/api/admin/users/{admin_user}",
        json={"role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"


# ---------------------------------------------------------------------------
# Update hubs — audit written
# ---------------------------------------------------------------------------


async def test_update_user_hubs_writes_audit_row(
    api_client: TestClient,
    admin_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.patch(
        f"/api/admin/users/{viewer_user}",
        json={"allowed_hubs": ["Sarajevo", "Belgrade"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert set(resp.json()["allowed_hubs"]) == {"Sarajevo", "Belgrade"}

    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'hub_scope_change'")
        )
    ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# Deactivate — session revocation
# ---------------------------------------------------------------------------


async def test_deactivate_revokes_sessions(
    api_client: TestClient,
    create_user: Callable,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    """After deactivation, previous sessions of the deactivated user are revoked."""
    second_admin = await create_user(role=RoleEnum.admin, email="admin2@symphony.is")
    target = await create_user(role=RoleEnum.viewer, email="target@symphony.is")
    _target_sid, _target_cookie = await seed_session(target)

    _sid, cookie = await seed_session(second_admin)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post(f"/api/admin/users/{target}/deactivate", headers=headers)
    assert resp.status_code == 200
    assert int(resp.json()["sessions_revoked"]) >= 1

    # Confirm the session row is revoked
    row = (
        await owner_session.execute(
            text("SELECT revoked_at FROM sessions WHERE user_id = :uid"),
            {"uid": target},
        )
    ).one_or_none()
    assert row is not None
    assert row[0] is not None  # revoked_at is set
