"""OAuth callback integration tests (PR 4 of M4).

Closes:

- TC-I-AUTH-2: Callback with non-``symphony.is`` ``hd`` claim rejected
               (devlogic.eu included).
- TC-I-AUTH-3: Callback with ``hd=symphony.is`` but email not in
               ``users`` allowlist returns 403 + ``login_denied_allowlist``
               audit row.
- TC-I-AUTH-4: Allowlisted user receives a session cookie and reaches
               a protected route.
- TC-I-AUTH-8: Missing or ``email_verified=false`` is rejected.
- TC-E-2 (integration proxy): rejection UX for non-Symphony domain.
- TC-E-3 (integration proxy): rejection UX for allowlist miss.
- TC-I-AUD-1 (full): login_success audit row is written.
- TC-I-PRIV-1 (pos): no token/secret values leak into structured logs.

Network I/O is replaced by a ``FakeOIDCClient`` installed via FastAPI's
``dependency_overrides`` so no HTTP call reaches Google.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.auth.oauth import IdTokenClaims, get_oidc_client
from app.db.models import AuditLog
from app.db.models import Session as SessionRow

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    import httpx
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fake OIDC client
# ---------------------------------------------------------------------------


class FakeOIDCClient:
    """Scripted stand-in for :class:`~app.auth.oauth.GoogleOIDCClient`.

    ``script`` maps ``code`` values to either an ``IdTokenClaims`` dict
    (token exchange succeeds, verification returns these claims) or an
    ``OAuthError`` (raised on ``exchange_code``).
    """

    _SECRET_ID_TOKEN = "SECRET.ID.TOKEN"  # noqa: S105 — test fixture string
    _SECRET_ACCESS_TOKEN = "SECRET-ACCESS-TOKEN"  # noqa: S105 — test fixture string

    def __init__(self, claims: IdTokenClaims) -> None:
        self._claims = claims

    async def exchange_code(self, *, code: str, redirect_uri: str) -> str:
        _ = (code, redirect_uri)
        return self._SECRET_ID_TOKEN

    async def verify_id_token(self, id_token: str) -> IdTokenClaims:
        assert id_token == self._SECRET_ID_TOKEN
        return self._claims


def _install_fake_oidc(client: TestClient, claims: IdTokenClaims) -> None:
    client.app.dependency_overrides[get_oidc_client] = lambda: FakeOIDCClient(claims)


# ---------------------------------------------------------------------------
# Callback helper — drives through /login to set the state cookie
# ---------------------------------------------------------------------------


def _start_and_callback(client: TestClient, *, code: str = "fake-code") -> httpx.Response:
    """Walk the two-step flow: GET /login → extract state → GET /callback."""
    login = client.get("/api/auth/login", follow_redirects=False)
    assert login.status_code == 302
    state_cookie = login.cookies.get("ta_oauth_state")
    assert state_cookie, "login did not set state cookie"
    return client.get(
        "/api/auth/callback",
        params={"code": code, "state": state_cookie},
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# TC-I-AUTH-2 / TC-E-2 — domain rejection
# ---------------------------------------------------------------------------


async def test_tc_i_auth_2_rejects_non_symphony_hd(
    api_client: TestClient,
    owner_session: AsyncSession,
) -> None:
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "attacker@devlogic.eu",
            "email_verified": True,
            "hd": "devlogic.eu",
            "name": "Attacker",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403
    assert "symphony" in resp.text.lower()
    assert api_client.cookies.get(SESSION_COOKIE_NAME) is None

    rows = (await owner_session.execute(select(AuditLog))).scalars().all()
    actions = [r.action for r in rows]
    assert AuditAction.login_denied_domain in actions


async def test_rejects_missing_hd(api_client: TestClient) -> None:
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "gmail@gmail.com",
            "email_verified": True,
            "name": "Gmail User",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403
    assert api_client.cookies.get(SESSION_COOKIE_NAME) is None


# ---------------------------------------------------------------------------
# TC-I-AUTH-3 / TC-E-3 — allowlist rejection
# ---------------------------------------------------------------------------


async def test_tc_i_auth_3_rejects_symphony_user_not_in_allowlist(
    api_client: TestClient,
    owner_session: AsyncSession,
) -> None:
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "contractor@symphony.is",
            "email_verified": True,
            "hd": "symphony.is",
            "name": "New Contractor",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403
    assert "access denied" in resp.text.lower()

    rows = (await owner_session.execute(select(AuditLog))).scalars().all()
    actions = [r.action for r in rows]
    assert AuditAction.login_denied_allowlist in actions
    violation = next(r for r in rows if r.action == AuditAction.login_denied_allowlist)
    assert violation.actor_email == "contractor@symphony.is"


# ---------------------------------------------------------------------------
# TC-I-AUTH-4 / TC-I-AUD-1 — happy path
# ---------------------------------------------------------------------------


async def test_tc_i_auth_4_allowlisted_user_gets_session_and_audit_row(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    owner_session: AsyncSession,
) -> None:
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "viewer@symphony.is",
            "email_verified": True,
            "hd": "symphony.is",
            "name": "Real Viewer",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 302
    assert api_client.cookies.get(SESSION_COOKIE_NAME) is not None

    session_rows = (
        (await owner_session.execute(select(SessionRow).where(SessionRow.user_id == viewer_user)))
        .scalars()
        .all()
    )
    assert len(session_rows) == 1

    audit_rows = (await owner_session.execute(select(AuditLog))).scalars().all()
    actions = [r.action for r in audit_rows]
    assert actions == [AuditAction.login_success]
    assert audit_rows[0].actor_id == viewer_user

    me = api_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "viewer@symphony.is"


async def test_rejects_deactivated_allowlist_user(
    api_client: TestClient,
    create_user: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    await create_user(email="off@symphony.is", is_active=False)
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "off@symphony.is",
            "email_verified": True,
            "hd": "symphony.is",
            "name": "Deactivated",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403

    rows = (await owner_session.execute(select(AuditLog))).scalars().all()
    actions = [r.action for r in rows]
    assert AuditAction.login_denied_inactive in actions


# ---------------------------------------------------------------------------
# TC-I-AUTH-8 — email_verified missing / false
# ---------------------------------------------------------------------------


async def test_tc_i_auth_8_rejects_unverified_email(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    owner_session: AsyncSession,
) -> None:
    _ = viewer_user
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "viewer@symphony.is",
            "email_verified": False,
            "hd": "symphony.is",
            "name": "Real Viewer",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403

    rows = (await owner_session.execute(select(AuditLog))).scalars().all()
    actions = [r.action for r in rows]
    assert AuditAction.login_denied_email_unverified in actions


async def test_rejects_when_email_verified_is_missing(
    api_client: TestClient,
    viewer_user: uuid.UUID,
) -> None:
    _ = viewer_user
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "viewer@symphony.is",
            "hd": "symphony.is",
            "name": "Real Viewer",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CSRF on state parameter
# ---------------------------------------------------------------------------


async def test_state_mismatch_is_rejected(api_client: TestClient) -> None:
    _install_fake_oidc(
        api_client,
        {"sub": "1", "email": "a@symphony.is", "email_verified": True, "hd": "symphony.is"},
    )
    # Start flow to set the state cookie, then call /callback with the
    # wrong state value.  CSRF check must kick in before any token
    # exchange happens.
    login = api_client.get("/api/auth/login", follow_redirects=False)
    state = login.cookies.get("ta_oauth_state")
    assert state
    resp = api_client.get(
        "/api/auth/callback",
        params={"code": "anything", "state": state + "tampered"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid state"


# ---------------------------------------------------------------------------
# TC-I-PRIV-1 (positive) — no token / secret leaks into logs
# ---------------------------------------------------------------------------


async def test_tc_i_priv_1_positive_no_token_leakage_in_logs(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    caplog_json: Any,
) -> None:
    _ = viewer_user
    _install_fake_oidc(
        api_client,
        {
            "sub": "1",
            "email": "viewer@symphony.is",
            "email_verified": True,
            "hd": "symphony.is",
            "name": "Real Viewer",
        },
    )
    resp = _start_and_callback(api_client)
    assert resp.status_code == 302

    # TC-I-PRIV-1 is about secrets that would pivot into account takeover —
    # id_token, access_token, refresh_token, service-account JSON.  The raw
    # one-shot ``code`` is acceptable in HTTP access logs and is filtered
    # out of this assertion: httpx's test-side client emits it to its own
    # logger whether or not the app touches it.
    caplog_json.assert_no_secret_values(
        [
            FakeOIDCClient._SECRET_ID_TOKEN,
            FakeOIDCClient._SECRET_ACCESS_TOKEN,
        ]
    )
