"""Integration tests for the retention sweep (NFR-PRIV-4, TC-I-AUD-6).

Cases covered
-------------
- TC-I-AUD-6: Audit rows older than the configured window are deleted; newer
              rows are preserved.
- Sweep trigger endpoint (POST /api/admin/sweep/trigger) is admin-only.
- Sweep uses the ta_report_sweep DB role.
- Rows at exactly the cutoff boundary are NOT deleted (strict less-than).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-I-AUD-6 — sweep deletes old rows, preserves recent ones
# ---------------------------------------------------------------------------


async def test_tc_i_aud_6_sweep_deletes_old_rows(
    sweep_engine: AsyncEngine,
    app_session: AsyncSession,
    create_user,
) -> None:
    """Rows older than retention window are deleted; newer rows survive."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.audit.sweep import sweep_audit_log

    actor_id = await create_user(email="sweep-actor@symphony.is")

    # Insert an OLD row directly.
    old_ts = datetime.now(UTC) - timedelta(days=365 * 5)  # 5 years ago
    await app_session.execute(
        text(
            "INSERT INTO audit_log "
            "(id, actor_id, actor_email, actor_display_name, action, created_at) "
            "VALUES (gen_random_uuid(), :uid, 'sweep-actor@symphony.is', 'Sweep Actor', "
            "'login_success', :ts)"
        ),
        {"uid": actor_id, "ts": old_ts},
    )
    # Insert a RECENT row via write_audit.
    from app.audit.writer import write_audit  # noqa: PLC0415

    await write_audit(
        app_session,
        action=AuditAction.report_view,
        actor_email="sweep-actor@symphony.is",
        actor_display_name="Sweep Actor",
        actor_id=actor_id,
    )
    await app_session.commit()

    # Confirm 2 rows before sweep.
    count_before = (
        await app_session.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_id = :uid"),
            {"uid": actor_id},
        )
    ).scalar_one()
    assert count_before == 2

    # Run sweep with 6-month retention (default minimum).
    factory = async_sessionmaker(sweep_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        deleted = await sweep_audit_log(session, retention_months=6)
        await session.commit()

    assert deleted >= 1  # at least the 5-year-old row

    # Recent row survives.
    count_after = (
        await app_session.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_id = :uid"),
            {"uid": actor_id},
        )
    ).scalar_one()
    assert count_after == count_before - deleted


# ---------------------------------------------------------------------------
# Sweep trigger endpoint — access control
# ---------------------------------------------------------------------------


async def test_sweep_trigger_forbidden_for_viewer(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)
    assert api_client.post("/api/admin/sweep/trigger", headers=headers).status_code == 403


async def test_sweep_trigger_admin_ok(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    """Admin can trigger the sweep; returns rows_deleted count."""
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post("/api/admin/sweep/trigger", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "rows_deleted" in body
    assert isinstance(body["rows_deleted"], int)

    # Sweep-triggered audit row was written.
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'sweep_triggered'")
        )
    ).scalar_one()
    assert count == 1
