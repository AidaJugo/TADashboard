"""PII erasure for audit rows (NFR-PRIV-5, ADR 0010, TC-I-AUD-5).

Audit rows are append-only for the application role (``ta_report_app``).
When a user exercises their right to erasure, we do not delete audit rows —
that would break accountability — but we overwrite the two PII columns
(``actor_email`` and ``actor_display_name``) with a fixed placeholder.  The
rest of the row (id, action, target, timestamp, actor_id link) is preserved.

The ``UPDATE`` grant on these two columns is held **only** by the
``ta_report_erasure`` role (see ``backend/grants.sql``).  Callers must
therefore use an :class:`AsyncSession` bound to that role's engine.  The
session factory for this role is provisioned at app boot (M4 PR 3 wires it
into a dedicated dependency); tests use the ``erasure_engine`` fixture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import update

from app.db.models import AuditLog
from app.logging import get_logger

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

#: Replacement value written to the two PII columns.  Deliberately human-
#: readable so an auditor reading the row immediately recognises erasure.
ERASED_PLACEHOLDER: Final[str] = "deleted user"


async def redact_actor(erasure_db: AsyncSession, actor_id: uuid.UUID) -> int:
    """Redact every audit row that references ``actor_id``.

    Must be called against a session bound to the ``ta_report_erasure`` role.
    Returns the number of rows updated.  The caller is responsible for
    committing the erasure-session transaction.

    Parameters
    ----------
    erasure_db:
        AsyncSession bound to ``ta_report_erasure``.  Any other role will
        fail with ``InsufficientPrivilege`` at the database layer.
    actor_id:
        The deactivated user's id.  The ``users`` row itself is handled
        separately by the admin deactivation flow (M5).
    """
    stmt = (
        update(AuditLog)
        .where(AuditLog.actor_id == actor_id)
        .values(
            actor_email=ERASED_PLACEHOLDER,
            actor_display_name=ERASED_PLACEHOLDER,
        )
    )
    result = await erasure_db.execute(stmt)
    # ``CursorResult.rowcount`` is defined on UPDATE/DELETE results but not on
    # the base ``Result`` typing shape.  Cast via ``getattr`` to stay strict-mypy-clean.
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    log.info(
        "audit_actor_redacted",
        extra={"actor_id": str(actor_id), "rowcount": rowcount},
    )
    return rowcount
