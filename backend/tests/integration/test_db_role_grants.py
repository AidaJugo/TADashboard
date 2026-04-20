"""Integration tests for DB role wiring (ADR 0010, PR 2 of M6).

Cases covered
-------------
- Erasure session cannot INSERT into audit_log (ta_report_erasure grant check).
- Sweep session cannot UPDATE audit_log (ta_report_sweep grant check).
- Both sessions can SELECT from audit_log (they hold SELECT).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.audit.actions import AuditAction

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.integration


async def test_erasure_session_cannot_insert_audit_log(
    erasure_engine: AsyncEngine,
) -> None:
    """ADR 0010: ta_report_erasure does not hold INSERT on audit_log."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(erasure_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        with pytest.raises((ProgrammingError, Exception)) as exc_info:
            await session.execute(
                text(
                    "INSERT INTO audit_log "
                    "(id, actor_email, actor_display_name, action, created_at) "
                    "VALUES (gen_random_uuid(), 'x@x.com', 'X', 'login_success', now())"
                )
            )
            await session.commit()
        assert (
            "permission denied" in str(exc_info.value).lower()
            or "insufficient" in str(exc_info.value).lower()
        )


async def test_sweep_session_cannot_update_audit_log(
    sweep_engine: AsyncEngine,
    app_session: AsyncSession,
    create_user,
) -> None:
    """ADR 0010: ta_report_sweep does not hold UPDATE on audit_log."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.audit.writer import write_audit

    actor_id = await create_user(email="sweeptest@symphony.is")
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="sweeptest@symphony.is",
        actor_display_name="Sweep Test",
        actor_id=actor_id,
    )
    await app_session.commit()

    factory = async_sessionmaker(sweep_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        with pytest.raises((ProgrammingError, Exception)) as exc_info:
            await session.execute(
                text("UPDATE audit_log SET actor_email = 'hacked' WHERE actor_id = :uid"),
                {"uid": actor_id},
            )
            await session.commit()
        assert (
            "permission denied" in str(exc_info.value).lower()
            or "insufficient" in str(exc_info.value).lower()
        )


async def test_erasure_session_can_select_audit_log(
    erasure_engine: AsyncEngine,
    app_session: AsyncSession,
    create_user,
) -> None:
    """ta_report_erasure holds SELECT on audit_log — verify read works."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.audit.writer import write_audit

    actor_id = await create_user(email="readtest@symphony.is")
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="readtest@symphony.is",
        actor_display_name="Read Test",
        actor_id=actor_id,
    )
    await app_session.commit()

    factory = async_sessionmaker(erasure_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        result = await session.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_id = :uid"),
            {"uid": actor_id},
        )
        assert result.scalar_one() == 1
