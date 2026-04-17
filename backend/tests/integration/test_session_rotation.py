"""Session rotation on a fresh OAuth login (M4 review follow-up).

Closes the should-fix item: a successful OAuth callback must revoke any
prior live sessions for the same user before minting the new one.
Otherwise a leaked or stolen cookie can outlive a re-authentication —
the user's only mitigation is the 24h absolute timeout.

Walked here:

1. Seed an existing live session for the viewer via ``seed_session``.
2. Drive a real OAuth callback with the same email through the
   ``FakeOIDCClient`` from ``test_oauth_callback`` (kept duplication
   minimal by importing).
3. Assert the **old** session row has ``revoked_at`` populated, the
   new session row exists, and the old cookie is now rejected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.auth.oauth import get_oidc_client
from app.db.models import AuditLog
from app.db.models import Session as SessionRow

from .test_oauth_callback import FakeOIDCClient, _start_and_callback

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


def _install_fake_oidc(client: TestClient, email: str) -> None:
    client.app.dependency_overrides[get_oidc_client] = lambda: FakeOIDCClient(
        {
            "sub": "1",
            "email": email,
            "email_verified": True,
            "hd": "symphony.is",
            "name": "Real Viewer",
        }
    )


async def test_login_revokes_prior_live_sessions(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    # Two prior live sessions (e.g. an old browser tab and a phone).
    old_sid_1, old_cookie_1 = await seed_session(viewer_user)
    old_sid_2, _old_cookie_2 = await seed_session(viewer_user)

    _install_fake_oidc(api_client, "viewer@symphony.is")
    resp = _start_and_callback(api_client)
    assert resp.status_code == 302

    rows = (
        (await owner_session.execute(select(SessionRow).where(SessionRow.user_id == viewer_user)))
        .scalars()
        .all()
    )
    # Three rows total: two seeded + one freshly created.
    assert len(rows) == 3
    by_id = {row.id: row for row in rows}
    assert by_id[old_sid_1].revoked_at is not None
    assert by_id[old_sid_2].revoked_at is not None

    new_rows = [r for r in rows if r.id not in {old_sid_1, old_sid_2}]
    assert len(new_rows) == 1
    assert new_rows[0].revoked_at is None

    # The old cookie is now rejected on the next request.
    api_client.cookies.set(SESSION_COOKIE_NAME, old_cookie_1)
    me = api_client.get("/api/auth/me")
    assert me.status_code == 401
    assert me.json()["detail"] == "session revoked"


async def test_login_with_no_prior_sessions_still_audits_login_success(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    owner_session: AsyncSession,
) -> None:
    """Negative control: rotation is a no-op when there's nothing to revoke."""
    _ = viewer_user
    _install_fake_oidc(api_client, "viewer@symphony.is")
    resp = _start_and_callback(api_client)
    assert resp.status_code == 302

    audit_actions = [
        r.action for r in (await owner_session.execute(select(AuditLog))).scalars().all()
    ]
    assert AuditAction.login_success in audit_actions
