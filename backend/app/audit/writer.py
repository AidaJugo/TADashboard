"""Same-transaction audit log writer (FR-AUDIT-1, FR-AUDIT-2).

Every mutation handler must call :func:`write_audit` on the **same**
:class:`AsyncSession` that owns the mutation.  The writer issues an ``INSERT``
but does **not** commit.  Whichever handler owns the unit of work commits once
at the end, so the mutation and its audit row land (or roll back) together.

Rule (.cursor/rules/auth-and-authz.mdc):
    - No separate sessions for audit writes.
    - No writes after the handler has committed.
    - Never catch-and-swallow a DB error around the audit write.

Login-flow calls (before a session is minted) share the cookie-flow's
``AsyncSession`` so the login attempt and its audit row commit together.
A failed login rolls both back; we log the failure and let the client retry.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.audit.actions import ALL_AUDIT_ACTIONS
from app.db.models import AuditLog
from app.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class AuditValidationError(ValueError):
    """Raised when an audit call is given an unknown action name."""


async def write_audit(  # noqa: PLR0913 — keyword-only + closed vocabulary
    db: AsyncSession,
    *,
    action: str,
    actor_email: str,
    actor_display_name: str,
    actor_id: uuid.UUID | None = None,
    target: str | None = None,
    client_ip: str | None = None,
) -> AuditLog:
    """Append one row to ``audit_log`` using the caller's session.

    Parameters
    ----------
    db:
        The caller's :class:`AsyncSession`.  The INSERT runs inside whatever
        transaction the caller has open; no commit is performed here.
    action:
        One of :data:`app.audit.actions.ALL_AUDIT_ACTIONS`.  Unknown strings
        are rejected with :class:`AuditValidationError`.
    actor_email, actor_display_name:
        The user taking the action.  For login-denied audit rows the user row
        does not exist yet, so ``actor_id`` is ``None`` but the email from the
        ID token is captured here (ADR 0004).
    actor_id:
        The FK into ``users``.  ``None`` for unauthenticated flows.
    target:
        Free-form, optional.  Example: ``"user:<uuid>"``, ``"hub:Sarajevo"``.
    client_ip:
        The request's client IP.  Must come from the trusted FastAPI request
        after reverse-proxy header handling; never from user-controlled input.

    Returns
    -------
    AuditLog
        The ORM instance that was added to the session (and flushed so the
        generated id is populated).
    """
    if action not in ALL_AUDIT_ACTIONS:
        raise AuditValidationError(
            f"unknown audit action: {action!r}; add it to app.audit.actions.AuditAction"
        )

    row = AuditLog(
        id=uuid.uuid4(),
        actor_id=actor_id,
        actor_email=actor_email,
        actor_display_name=actor_display_name,
        action=action,
        target=target,
        client_ip=client_ip,
    )
    db.add(row)
    # Flush populates id/created_at from the DB side without committing the
    # caller's transaction.  If the handler rolls back later, this row
    # disappears with it — that's the same-tx guarantee in action.
    await db.flush()

    # Observability only. Target/client_ip/email are deliberately not logged;
    # ``audit_log`` is the accountability record and ``target`` may carry
    # caller-controlled data that we do not want reflected into stdout.
    log.info(
        "audit_write",
        extra={
            "audit_action": action,
            "actor_id": str(actor_id) if actor_id else None,
        },
    )
    return row
