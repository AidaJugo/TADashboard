"""Integration tests for PII erasure on audit rows (TC-I-AUD-5, NFR-PRIV-5).

docs/testing.md §4.4:
    TC-I-AUD-5: Redacting an actor overwrites only ``actor_email`` and
                ``actor_display_name``.  id, action, target, timestamp, and
                actor_id FK are preserved.

docs/adr/0010-audit-log-grants.md:
    The ``ta_report_erasure`` role has UPDATE on those two columns only.
    Any other UPDATE or DELETE raises ``InsufficientPrivilege``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.audit.actions import AuditAction
from app.audit.erasure import ERASED_PLACEHOLDER, redact_actor
from app.audit.writer import write_audit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-I-AUD-5 — redaction preserves id / action / target / timestamp
# ---------------------------------------------------------------------------


async def test_tc_i_aud_5_redacts_pii_and_preserves_other_columns(
    app_session: AsyncSession,
    erasure_session: AsyncSession,
    create_user,
) -> None:
    """Erasure overwrites PII but preserves accountability fields."""
    actor_id = await create_user(email="alice@symphony.is", display_name="Alice Admin")

    # Seed an audit row via the app role
    row1 = await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="alice@symphony.is",
        actor_display_name="Alice Admin",
        actor_id=actor_id,
        target="hub:Sarajevo",
    )
    row2 = await write_audit(
        app_session,
        action=AuditAction.sheet_refresh,
        actor_email="alice@symphony.is",
        actor_display_name="Alice Admin",
        actor_id=actor_id,
        target=None,
    )
    await app_session.commit()

    # Capture pre-redaction snapshot of preserved columns
    result = await app_session.execute(
        text(
            "SELECT id, action, target, actor_id, created_at "
            "FROM audit_log WHERE actor_id = :aid ORDER BY id"
        ),
        {"aid": actor_id},
    )
    pre = sorted(result.all(), key=lambda r: str(r[0]))

    # Redact via the erasure role
    rowcount = await redact_actor(erasure_session, actor_id)
    await erasure_session.commit()
    assert rowcount == 2

    # Verify PII was replaced
    result = await app_session.execute(
        text("SELECT actor_email, actor_display_name FROM audit_log WHERE actor_id = :aid"),
        {"aid": actor_id},
    )
    for email, name in result.all():
        assert email == ERASED_PLACEHOLDER
        assert name == ERASED_PLACEHOLDER

    # And the accountability columns survived untouched
    result = await app_session.execute(
        text(
            "SELECT id, action, target, actor_id, created_at "
            "FROM audit_log WHERE actor_id = :aid ORDER BY id"
        ),
        {"aid": actor_id},
    )
    post = sorted(result.all(), key=lambda r: str(r[0]))
    assert [(r[0], r[1], r[2], r[3], r[4]) for r in post] == [
        (r[0], r[1], r[2], r[3], r[4]) for r in pre
    ]

    # Sanity: the two seeded rows are accounted for
    assert {str(row1.id), str(row2.id)} == {str(r[0]) for r in post}


async def test_redact_actor_is_idempotent(
    app_session: AsyncSession,
    erasure_session: AsyncSession,
    create_user,
) -> None:
    actor_id = await create_user(email="bob@symphony.is", display_name="Bob")
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="bob@symphony.is",
        actor_display_name="Bob",
        actor_id=actor_id,
    )
    await app_session.commit()

    first = await redact_actor(erasure_session, actor_id)
    await erasure_session.commit()
    second = await redact_actor(erasure_session, actor_id)
    await erasure_session.commit()

    assert first == 1
    # Second pass still updates 1 row, but both columns are already the placeholder.
    assert second == 1


async def test_redact_actor_touches_only_matching_rows(
    app_session: AsyncSession,
    erasure_session: AsyncSession,
    create_user,
) -> None:
    target_actor = await create_user(email="alice@symphony.is", display_name="Alice")
    other_actor = await create_user(email="bob@symphony.is", display_name="Bob")

    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="alice@symphony.is",
        actor_display_name="Alice",
        actor_id=target_actor,
    )
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="bob@symphony.is",
        actor_display_name="Bob",
        actor_id=other_actor,
    )
    await app_session.commit()

    await redact_actor(erasure_session, target_actor)
    await erasure_session.commit()

    result = await app_session.execute(
        text("SELECT actor_email, actor_display_name FROM audit_log WHERE actor_id = :aid"),
        {"aid": other_actor},
    )
    email, name = result.one()
    assert email == "bob@symphony.is"
    assert name == "Bob"
