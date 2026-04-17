"""TC-I-AUD-7 — ``POST /api/report/refresh`` writes a ``sheet_refresh`` audit row.

Also pins the role guard: a viewer must not be able to trigger a
refresh (FR-AUTHZ-1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import AuditLog

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


async def test_tc_i_aud_7_editor_refresh_writes_audit(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    csrf_headers = attach_csrf(api_client)

    resp = api_client.post("/api/report/refresh", headers=csrf_headers)
    assert resp.status_code == 202

    rows = (
        (await owner_session.execute(select(AuditLog).where(AuditLog.actor_id == editor_user)))
        .scalars()
        .all()
    )
    actions = [r.action for r in rows]
    assert actions == [AuditAction.sheet_refresh]


async def test_viewer_refresh_forbidden(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    """Even with a valid CSRF token, a viewer must be rejected by ``require_role``."""
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    csrf_headers = attach_csrf(api_client)

    resp = api_client.post("/api/report/refresh", headers=csrf_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "insufficient role"

    rows = (
        (
            await owner_session.execute(
                select(AuditLog).where(AuditLog.action == AuditAction.sheet_refresh)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []
