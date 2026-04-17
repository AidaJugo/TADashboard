"""TC-I-AUD-3 and related grants-model tests.

docs/testing.md §4.4:
    TC-I-AUD-3: Audit log is append-only. No update or delete endpoint exists.
                The DB role used by the app has no ``UPDATE`` or ``DELETE``
                grant on ``audit_log``.

docs/adr/0010-audit-log-grants.md defines three roles:

- ``ta_report_app``     — SELECT + INSERT on ``audit_log``; no UPDATE/DELETE.
- ``ta_report_erasure`` — UPDATE only on ``actor_email`` + ``actor_display_name``.
- ``ta_report_sweep``   — DELETE only.

We exercise each bound on every role so a future grant regression surfaces as
a failing test instead of a silent privilege escalation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import psycopg
import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_audit_row_as_owner(
    superuser_engine: AsyncEngine,
    *,
    action: str = "login_success",
    actor_email: str = "a@symphony.is",
    actor_display_name: str = "Alice Admin",
) -> uuid.UUID:
    """Insert an audit row via the superuser for tests that need one in place."""
    row_id = uuid.uuid4()
    async with superuser_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO audit_log "
                "(id, actor_id, actor_email, actor_display_name, action, target, client_ip) "
                "VALUES (:id, NULL, :email, :name, :action, NULL, NULL)"
            ),
            {
                "id": row_id,
                "email": actor_email,
                "name": actor_display_name,
                "action": action,
            },
        )
    return row_id


# ---------------------------------------------------------------------------
# TC-I-AUD-3: the app role cannot UPDATE or DELETE audit_log
# ---------------------------------------------------------------------------


async def test_tc_i_aud_3_app_role_cannot_update_audit_log(
    superuser_engine: AsyncEngine,
    app_engine: AsyncEngine,
    clean_db: None,
) -> None:
    """TC-I-AUD-3: ``UPDATE audit_log`` as ``ta_report_app`` raises InsufficientPrivilege."""
    await _insert_audit_row_as_owner(superuser_engine)

    with pytest.raises((psycopg.errors.InsufficientPrivilege, Exception)) as excinfo:
        async with app_engine.begin() as conn:
            await conn.execute(text("UPDATE audit_log SET action = 'tampered'"))

    assert _is_insufficient_privilege(excinfo.value)


async def test_tc_i_aud_3_app_role_cannot_delete_audit_log(
    superuser_engine: AsyncEngine,
    app_engine: AsyncEngine,
    clean_db: None,
) -> None:
    """TC-I-AUD-3: ``DELETE FROM audit_log`` as ``ta_report_app`` is rejected."""
    await _insert_audit_row_as_owner(superuser_engine)

    with pytest.raises(Exception) as excinfo:
        async with app_engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log"))

    assert _is_insufficient_privilege(excinfo.value)


async def test_app_role_can_select_and_insert_audit_log(
    app_engine: AsyncEngine,
    clean_db: None,
) -> None:
    """Positive side of TC-I-AUD-3: the app role *can* INSERT + SELECT."""
    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO audit_log "
                "(id, actor_id, actor_email, actor_display_name, action, target, client_ip) "
                "VALUES (gen_random_uuid(), NULL, :e, :n, :a, NULL, NULL)"
            ),
            {"e": "a@symphony.is", "n": "Alice", "a": "login_success"},
        )
        result = await conn.execute(text("SELECT count(*) FROM audit_log"))
        assert result.scalar_one() == 1


# ---------------------------------------------------------------------------
# Erasure role: UPDATE only on PII columns; no UPDATE elsewhere, no DELETE
# ---------------------------------------------------------------------------


async def test_erasure_role_can_update_pii_columns(
    superuser_engine: AsyncEngine,
    erasure_engine: AsyncEngine,
    clean_db: None,
) -> None:
    row_id = await _insert_audit_row_as_owner(superuser_engine)

    async with erasure_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE audit_log SET actor_email = 'deleted user', "
                "actor_display_name = 'deleted user' WHERE id = :id"
            ),
            {"id": row_id},
        )
        result = await conn.execute(
            text("SELECT actor_email, actor_display_name FROM audit_log WHERE id = :id"),
            {"id": row_id},
        )
        row = result.one()
        assert row[0] == "deleted user"
        assert row[1] == "deleted user"


async def test_erasure_role_cannot_update_non_pii_columns(
    superuser_engine: AsyncEngine,
    erasure_engine: AsyncEngine,
    clean_db: None,
) -> None:
    await _insert_audit_row_as_owner(superuser_engine)

    with pytest.raises(Exception) as excinfo:
        async with erasure_engine.begin() as conn:
            await conn.execute(text("UPDATE audit_log SET action = 'tampered'"))

    assert _is_insufficient_privilege(excinfo.value)


async def test_erasure_role_cannot_delete(
    superuser_engine: AsyncEngine,
    erasure_engine: AsyncEngine,
    clean_db: None,
) -> None:
    await _insert_audit_row_as_owner(superuser_engine)

    with pytest.raises(Exception) as excinfo:
        async with erasure_engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log"))

    assert _is_insufficient_privilege(excinfo.value)


# ---------------------------------------------------------------------------
# Sweep role: DELETE only; no UPDATE, no INSERT
# ---------------------------------------------------------------------------


async def test_sweep_role_can_delete(
    superuser_engine: AsyncEngine,
    sweep_engine: AsyncEngine,
    clean_db: None,
) -> None:
    await _insert_audit_row_as_owner(superuser_engine)

    async with sweep_engine.begin() as conn:
        await conn.execute(text("DELETE FROM audit_log"))
        result = await conn.execute(text("SELECT count(*) FROM audit_log"))
        assert result.scalar_one() == 0


async def test_sweep_role_cannot_insert(
    sweep_engine: AsyncEngine,
    clean_db: None,
) -> None:
    with pytest.raises(Exception) as excinfo:
        async with sweep_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_log "
                    "(id, actor_id, actor_email, actor_display_name, action) "
                    "VALUES (gen_random_uuid(), NULL, 'x@symphony.is', 'X', 'login_success')"
                )
            )

    assert _is_insufficient_privilege(excinfo.value)


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _is_insufficient_privilege(exc: BaseException) -> bool:
    """Return True when the error chain contains a Postgres InsufficientPrivilege.

    SQLAlchemy wraps the psycopg error, so we walk ``__cause__`` / ``__context__``.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, psycopg.errors.InsufficientPrivilege):
            return True
        msg = str(current).lower()
        if "permission denied" in msg or "insufficientprivilege" in msg:
            return True
        current = current.__cause__ or current.__context__
    return False
