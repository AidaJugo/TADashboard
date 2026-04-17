"""Integration tests for the same-transaction audit writer (FR-AUDIT-1, FR-AUDIT-2).

docs/testing.md §4.4:
    TC-I-AUD-1: Every mutation emits an audit row.  (PR 2 asserts the writer
                primitive; PR 4 asserts the login_success end-to-end flow.)

Invariants asserted here:
    1. Happy path: ``write_audit`` inserts a row via the caller's session.
    2. Same-transaction semantics: if the caller rolls back, the audit row
       disappears with it (no separate session, no swallowed commit).
    3. Unknown action names are rejected at the Python layer before any SQL
       is issued — guards against typos silently creating rows.
    4. Closed vocabulary: ``ALL_AUDIT_ACTIONS`` matches the ``AuditAction``
       attributes exactly (no drift between the class and the set used by
       the writer for validation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.audit.actions import ALL_AUDIT_ACTIONS, AuditAction
from app.audit.writer import AuditValidationError, write_audit

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TC-I-AUD-1 — happy-path insert through the app-role session
# ---------------------------------------------------------------------------


async def test_tc_i_aud_1_write_audit_inserts_row(
    app_session: AsyncSession,
    admin_user: uuid.UUID,
) -> None:
    """A successful write_audit persists the row and it's visible in the table."""
    row = await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="alice@symphony.is",
        actor_display_name="Alice Admin",
        actor_id=admin_user,
        target="user:alice",
        client_ip="203.0.113.1",
    )
    await app_session.commit()

    result = await app_session.execute(
        text("SELECT action, actor_email, target FROM audit_log WHERE id = :id"),
        {"id": row.id},
    )
    got = result.one()
    assert got[0] == "login_success"
    assert got[1] == "alice@symphony.is"
    assert got[2] == "user:alice"


# ---------------------------------------------------------------------------
# Same-transaction rollback semantics
# ---------------------------------------------------------------------------


async def test_write_audit_rolls_back_with_caller(app_session: AsyncSession) -> None:
    """If the handler raises, the audit row must roll back with the mutation.

    This is the core of same-transaction auditing: the audit call does not
    commit on its own.  A rollback on the caller's session removes both the
    mutation and the audit row.
    """
    row_id: uuid.UUID | None = None
    try:
        row = await write_audit(
            app_session,
            action=AuditAction.login_denied_domain,
            actor_email="intruder@devlogic.eu",
            actor_display_name="intruder",
        )
        row_id = row.id
        raise RuntimeError("handler failure after audit write")
    except RuntimeError:
        await app_session.rollback()

    assert row_id is not None
    result = await app_session.execute(
        text("SELECT count(*) FROM audit_log WHERE id = :id"),
        {"id": row_id},
    )
    assert result.scalar_one() == 0


async def test_write_audit_does_not_commit_by_itself(
    app_session: AsyncSession,
    editor_user: uuid.UUID,
) -> None:
    """A second session must not see the row until the caller commits."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    row = await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="bob@symphony.is",
        actor_display_name="Bob",
        actor_id=editor_user,
    )

    # Start a second, independent connection sharing the same engine.  Because
    # the caller has not committed, the row must not be visible there
    # (READ COMMITTED isolation, default).
    engine = app_session.bind
    assert engine is not None
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as other:
        result = await other.execute(
            text("SELECT count(*) FROM audit_log WHERE id = :id"),
            {"id": row.id},
        )
        assert result.scalar_one() == 0

    await app_session.commit()


# ---------------------------------------------------------------------------
# Unknown action rejected at Python layer
# ---------------------------------------------------------------------------


async def test_write_audit_rejects_unknown_action(app_session: AsyncSession) -> None:
    with pytest.raises(AuditValidationError, match="unknown audit action"):
        await write_audit(
            app_session,
            action="totally_made_up_event",
            actor_email="a@symphony.is",
            actor_display_name="A",
        )


# ---------------------------------------------------------------------------
# Closed-vocabulary invariant
# ---------------------------------------------------------------------------


def test_all_audit_actions_matches_audit_action_attributes() -> None:
    """``ALL_AUDIT_ACTIONS`` must stay in sync with the ``AuditAction`` class."""
    exposed = {
        v for k, v in vars(AuditAction).items() if not k.startswith("_") and isinstance(v, str)
    }
    assert exposed == ALL_AUDIT_ACTIONS


def test_audit_action_keys_match_values() -> None:
    """Every class attribute's name equals its string value (no typos)."""
    for k, v in vars(AuditAction).items():
        if k.startswith("_") or not isinstance(v, str):
            continue
        assert k == v, f"AuditAction attribute {k!r} does not match value {v!r}"
