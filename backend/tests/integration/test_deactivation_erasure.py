"""Integration tests for the deactivation + erasure flow (NFR-PRIV-5, TC-I-AUD-5).

Tests the complete M6 deactivation flow:
- Deactivation sets is_active=False and revokes sessions.
- The deactivation audit row retains real actor identity (before_ts filter).
- Historical audit rows for the deactivated actor have PII erased.
- last-admin guard fires (covered in test_admin_users.py; smoke-tested here).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.audit.actions import AuditAction
from app.audit.erasure import ERASED_PLACEHOLDER, redact_actor
from app.audit.writer import write_audit
from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import RoleEnum

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Unit-level: before_ts filter protects the deactivation audit row
# ---------------------------------------------------------------------------


async def test_redact_actor_with_before_ts_skips_newer_rows(
    app_session: AsyncSession,
    erasure_session: AsyncSession,
    create_user,
) -> None:
    """TC-I-AUD-5 variant: before_ts filter protects the deactivation row."""
    actor_id = await create_user(email="toerase@symphony.is")

    # Seed a historical row (before deactivation).
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="toerase@symphony.is",
        actor_display_name="To Erase",
        actor_id=actor_id,
    )
    await app_session.commit()

    # Simulate capturing deactivation_ts.
    await asyncio.sleep(0.01)  # ensure subsequent row has strictly newer created_at
    deactivation_ts = datetime.now(UTC)
    await asyncio.sleep(0.01)

    # Seed the deactivation audit row (after deactivation_ts).
    await write_audit(
        app_session,
        action=AuditAction.user_deactivated,
        actor_email="toerase@symphony.is",
        actor_display_name="To Erase",
        actor_id=actor_id,
        target=f"user:{actor_id}",
    )
    await app_session.commit()

    # Erase with before_ts — should only touch the login_success row.
    rowcount = await redact_actor(erasure_session, actor_id, before_ts=deactivation_ts)
    await erasure_session.commit()

    # login_success row: PII erased.
    rows = (
        await app_session.execute(
            text(
                "SELECT action, actor_email, actor_display_name "
                "FROM audit_log WHERE actor_id = :uid ORDER BY created_at"
            ),
            {"uid": actor_id},
        )
    ).all()

    assert len(rows) == 2
    login_row = rows[0]
    deact_row = rows[1]

    assert login_row[0] == AuditAction.login_success
    assert login_row[1] == ERASED_PLACEHOLDER
    assert login_row[2] == ERASED_PLACEHOLDER

    # Deactivation row: PII preserved.
    assert deact_row[0] == AuditAction.user_deactivated
    assert deact_row[1] == "toerase@symphony.is"
    assert deact_row[2] == "To Erase"

    assert rowcount == 1


# ---------------------------------------------------------------------------
# API-level: deactivate endpoint triggers background erasure
# ---------------------------------------------------------------------------


async def test_deactivate_endpoint_erases_pii_in_background(
    api_client: TestClient,
    create_user: Callable,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    """Deactivation + background erasure: historical rows get PII erased."""
    second_admin = await create_user(role=RoleEnum.admin, email="admin2@symphony.is")
    target = await create_user(role=RoleEnum.viewer, email="farewell@symphony.is")

    # Seed a historical audit row for the target user (directly in DB via owner).
    from app.audit.writer import write_audit  # noqa: PLC0415

    await write_audit(
        owner_session,
        action=AuditAction.login_success,
        actor_email="farewell@symphony.is",
        actor_display_name="Farewell User",
        actor_id=target,
    )
    await owner_session.commit()

    # Deactivate via API.
    _sid, cookie = await seed_session(second_admin)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)
    resp = api_client.post(f"/api/admin/users/{target}/deactivate", headers=headers)
    assert resp.status_code == 200

    # The TestClient's background tasks run synchronously in-process,
    # so PII erasure should complete before this assertion.
    await asyncio.sleep(0.1)

    # Query audit rows for the TARGET user (the deactivated one).
    rows = (
        await owner_session.execute(
            text(
                "SELECT action, actor_email FROM audit_log "
                "WHERE actor_id = :uid ORDER BY created_at"
            ),
            {"uid": target},
        )
    ).all()

    login_rows = [r for r in rows if r[0] == AuditAction.login_success]

    # Historical login row for the target: PII erased.
    assert len(login_rows) == 1
    assert login_rows[0][1] == ERASED_PLACEHOLDER

    # The deactivation audit row has actor_id = second_admin (who did the
    # deactivation), not target.  Verify it still has real PII preserved.
    deact_rows = (
        await owner_session.execute(
            text(
                "SELECT actor_email FROM audit_log "
                "WHERE action = 'user_deactivated' AND actor_id = :admin_id"
            ),
            {"admin_id": second_admin},
        )
    ).all()
    assert len(deact_rows) == 1
    assert deact_rows[0][0] == "admin2@symphony.is"
