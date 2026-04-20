"""Integration tests for day-one admin bootstrap (FR-AUTH-3, TC-I-AUTH-11).

Covers
------
- TC-I-AUTH-11-a: seed_admin creates a user row with admin role + writes
  an admin_seeded audit row.
- TC-I-AUTH-11-b: seed_admin is idempotent — running twice leaves exactly
  one user with admin role; a second audit row is written for traceability.
- TC-I-AUTH-11-c: re-activation — seeding a deactivated user restores
  is_active=True and promotes to admin.
- TC-I-AUTH-11-d: the seeded admin completes the full OAuth login flow
  (mocked OIDC) and receives a valid session cookie.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from app.admin.bootstrap import seed_admin
from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.auth.oauth import get_oidc_client
from app.config import get_settings
from app.db.models import RoleEnum, User

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_ADMIN_EMAIL = "bootstrap-admin@symphony.is"
_ADMIN_NAME = "Bootstrap Admin"


# ---------------------------------------------------------------------------
# Fake OIDC client — scripted claims, no network calls
# ---------------------------------------------------------------------------


class _FakeOIDC:
    """Minimal fake that returns pre-canned claims."""

    def __init__(self, claims: dict) -> None:  # type: ignore[type-arg]
        self._claims = claims

    async def exchange_code(self, *, code: str, redirect_uri: str) -> str:
        return "fake-id-token"

    async def verify_id_token(self, id_token: str) -> dict:  # type: ignore[type-arg]
        return self._claims


# ---------------------------------------------------------------------------
# TC-I-AUTH-11-a: seed_admin creates user + audit row
# ---------------------------------------------------------------------------


async def test_tc_i_auth_11a_seed_creates_admin(
    owner_session: AsyncSession,
) -> None:
    created, promoted = await seed_admin(
        owner_session, email=_ADMIN_EMAIL, display_name=_ADMIN_NAME
    )
    await owner_session.commit()

    assert created is True
    assert promoted is False  # new insert, not a promotion

    user = (
        await owner_session.execute(select(User).where(User.email == _ADMIN_EMAIL))
    ).scalar_one()
    assert user.role == RoleEnum.admin
    assert user.is_active is True
    assert user.display_name == _ADMIN_NAME

    audit_rows = (
        await owner_session.execute(
            text(
                "SELECT action, actor_email, target FROM audit_log "
                "WHERE action = :action ORDER BY created_at DESC"
            ),
            {"action": AuditAction.admin_seeded},
        )
    ).all()
    assert len(audit_rows) == 1
    assert audit_rows[0][1] == "system"
    assert _ADMIN_EMAIL in audit_rows[0][2]
    assert "created" in audit_rows[0][2]


# ---------------------------------------------------------------------------
# TC-I-AUTH-11-b: idempotent — running twice, one user, two audit rows
# ---------------------------------------------------------------------------


async def test_tc_i_auth_11b_seed_is_idempotent(
    owner_session: AsyncSession,
) -> None:
    await seed_admin(owner_session, email=_ADMIN_EMAIL, display_name=_ADMIN_NAME)
    await owner_session.commit()

    # Second call — same email
    created2, promoted2 = await seed_admin(
        owner_session, email=_ADMIN_EMAIL, display_name=_ADMIN_NAME
    )
    await owner_session.commit()

    assert created2 is False  # already existed

    users = (
        (await owner_session.execute(select(User).where(User.email == _ADMIN_EMAIL)))
        .scalars()
        .all()
    )
    assert len(users) == 1
    assert users[0].role == RoleEnum.admin

    # Both calls write audit rows (traceability).
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = :a"),
            {"a": AuditAction.admin_seeded},
        )
    ).scalar_one()
    assert count == 2


# ---------------------------------------------------------------------------
# TC-I-AUTH-11-c: re-activation — seeding a deactivated viewer promotes + re-activates
# ---------------------------------------------------------------------------


async def test_tc_i_auth_11c_seed_reactivates_deactivated_user(
    owner_session: AsyncSession,
) -> None:
    # Pre-existing deactivated viewer row
    owner_session.add(
        User(
            email=_ADMIN_EMAIL,
            display_name="Old Viewer",
            role=RoleEnum.viewer,
            is_active=False,
        )
    )
    await owner_session.commit()

    created, promoted = await seed_admin(
        owner_session, email=_ADMIN_EMAIL, display_name=_ADMIN_NAME
    )
    await owner_session.commit()

    assert created is False  # row already existed
    assert promoted is True  # role was not admin before

    user = (
        await owner_session.execute(select(User).where(User.email == _ADMIN_EMAIL))
    ).scalar_one()
    assert user.role == RoleEnum.admin
    assert user.is_active is True
    assert user.display_name == _ADMIN_NAME


# ---------------------------------------------------------------------------
# TC-I-AUTH-11-d: seeded admin completes the OAuth callback and gets a session
# ---------------------------------------------------------------------------


async def test_tc_i_auth_11d_seeded_admin_completes_login(
    api_client: TestClient,
    owner_session: AsyncSession,
) -> None:
    """Bootstrap an admin, then simulate the Google OAuth callback.

    Uses a fake OIDC client injected via FastAPI dependency_overrides so
    no real Google call is made.  Asserts that the callback:
    1. Returns HTTP 302 → app root.
    2. Sets a valid session cookie.
    3. /me reports the correct role and email.
    """
    # Seed the admin before the OAuth flow.
    await seed_admin(owner_session, email=_ADMIN_EMAIL, display_name=_ADMIN_NAME)
    await owner_session.commit()

    settings = get_settings()

    # Build scripted OIDC claims matching the seeded email.
    claims = {
        "sub": "google-uid-bootstrap",
        "email": _ADMIN_EMAIL,
        "email_verified": True,
        "hd": settings.allowed_hd,
        "name": _ADMIN_NAME,
    }
    fake_oidc = _FakeOIDC(claims)

    from app.main import app  # noqa: PLC0415

    app.dependency_overrides[get_oidc_client] = lambda: fake_oidc
    try:
        # Plant the OAuth state cookie on the test client (mimics /login step).
        state = secrets.token_urlsafe(16)
        api_client.cookies.set("ta_oauth_state", state)

        resp = api_client.get(
            f"/api/auth/callback?code=fake-code&state={state}",
            follow_redirects=False,
        )

        # Callback must redirect to the app root.
        assert resp.status_code == 302, resp.text
        assert SESSION_COOKIE_NAME in resp.cookies

        # Replay the session cookie and assert /me returns admin.
        api_client.cookies.set(SESSION_COOKIE_NAME, resp.cookies[SESSION_COOKIE_NAME])
        me = api_client.get("/api/auth/me")
        assert me.status_code == 200
        data = me.json()
        assert data["email"] == _ADMIN_EMAIL
        assert data["role"] == "admin"
    finally:
        app.dependency_overrides.pop(get_oidc_client, None)
