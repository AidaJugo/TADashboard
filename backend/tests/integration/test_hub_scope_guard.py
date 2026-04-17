"""Integration test for the hub-scope guard on ``/api/report`` (TC-I-API-6).

TC-I-API-6 — Hub-scoped viewer GET ``/api/report?hub=Belgrade`` where
Belgrade is not in their scope returns 403 **and** writes an audit entry
(``hub_scope_violation``).
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


async def test_tc_i_api_6_hub_scope_violation_returns_403_and_audit_row(
    api_client: TestClient,
    hub_scoped_viewer: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    _session_id, cookie = await seed_session(hub_scoped_viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/report", params={"hub": "Belgrade"})
    assert response.status_code == 403
    assert response.json()["detail"] == "hub not in scope"

    rows = (
        (
            await owner_session.execute(
                select(AuditLog).where(AuditLog.actor_id == hub_scoped_viewer)
            )
        )
        .scalars()
        .all()
    )
    actions = [r.action for r in rows]
    assert AuditAction.hub_scope_violation in actions
    violation = next(r for r in rows if r.action == AuditAction.hub_scope_violation)
    assert violation.target == "hub=Belgrade"


async def test_hub_in_scope_is_allowed(
    api_client: TestClient,
    hub_scoped_viewer: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(hub_scoped_viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/report", params={"hub": "Sarajevo"})
    assert response.status_code == 200
    assert response.json()["hub"] == "Sarajevo"


async def test_unscoped_viewer_can_read_any_hub(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """A viewer with no hub scope rows sees every hub (FR-AUTHZ-3)."""
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/report", params={"hub": "Belgrade"})
    assert response.status_code == 200

    # No hub_scope_violation row should have been written.
    rows = (
        (
            await owner_session.execute(
                select(AuditLog).where(AuditLog.action == AuditAction.hub_scope_violation)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []
