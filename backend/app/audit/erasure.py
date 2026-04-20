"""PII erasure for audit rows (NFR-PRIV-5, ADR 0010, TC-I-AUD-5).

Audit rows are append-only for the application role (``ta_report_app``).
When a user exercises their right to erasure, we do not delete audit rows —
that would break accountability — but we overwrite the two PII columns
(``actor_email`` and ``actor_display_name``) with a fixed placeholder.  The
rest of the row (id, action, target, timestamp, actor_id link) is preserved.

The ``UPDATE`` grant on these two columns is held **only** by the
``ta_report_erasure`` role (see ``backend/grants.sql``).  Callers must
therefore use an :class:`AsyncSession` bound to that role's engine.  The
session factory for this role is :func:`app.db.session.get_erasure_session_factory`.

Order of operations on user deactivation (M6 spec):
1–4. App transaction: guard check, set is_active=False, revoke sessions,
     write deactivation audit row (real actor identity preserved).
5.   Commit app transaction.
6.   ``redact_actor(erasure_db, actor_id, before_ts=deactivation_ts)``
     — only rows created BEFORE the deactivation timestamp are redacted.
     This deliberately excludes the step-4 audit row so the deactivation
     event retains its real actor identity (TC-I-AUD-5 variant).
7.   Commit erasure transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import update

from app.db.models import AuditLog
from app.logging import get_logger

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

#: Replacement value written to the two PII columns.  Deliberately human-
#: readable so an auditor reading the row immediately recognises erasure.
ERASED_PLACEHOLDER: Final[str] = "deleted user"


async def redact_actor(
    erasure_db: AsyncSession,
    actor_id: uuid.UUID,
    *,
    before_ts: datetime | None = None,
) -> int:
    """Redact audit rows that reference ``actor_id``.

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
        separately by the admin deactivation flow.
    before_ts:
        When provided, only rows with ``created_at < before_ts`` are
        redacted.  This protects the deactivation audit row itself (written
        at ``before_ts``) from having its actor PII erased — preserving
        the record of WHO deactivated the user (M6 spec, NFR-PRIV-5).
    """
    stmt = (
        update(AuditLog)
        .where(AuditLog.actor_id == actor_id)
        .values(
            actor_email=ERASED_PLACEHOLDER,
            actor_display_name=ERASED_PLACEHOLDER,
        )
    )
    if before_ts is not None:
        stmt = stmt.where(AuditLog.created_at < before_ts)

    result = await erasure_db.execute(stmt)
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    log.info(
        "audit_actor_redacted",
        extra={"actor_id": str(actor_id), "rowcount": rowcount},
    )
    return rowcount
