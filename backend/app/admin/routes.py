"""Admin API (PR 3 + M4 review follow-up).

Endpoints:

- ``GET  /api/admin/ping``                            — role-guard smoke test.
- ``POST /api/admin/users/{user_id}/revoke-sessions`` — operator-assisted
  offboarding.  Closes every active session of ``user_id`` so the
  next request on any of them is rejected (ADR 0012, TC-I-AUTH-10).

Users CRUD / config CRUD land in M5.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — FastAPI introspects path-param annotations at runtime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

# Runtime imports required for FastAPI dependency introspection — see
# ``app/auth/deps.py`` for the full explanation.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.sessions import revoke_all_sessions_for
from app.authz.roles import CurrentUser, Role, require_role  # noqa: TC001
from app.db.session import get_db
from app.utils.http import client_ip

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/ping", dependencies=[Depends(require_role(Role.admin))])
async def admin_ping() -> dict[str, str]:
    """Return a trivial payload.  Admin-only (FR-AUTHZ-1)."""
    return {"status": "ok"}


@router.post(
    "/users/{user_id}/revoke-sessions",
    dependencies=[Depends(require_role(Role.admin))],
)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Revoke every active session of ``user_id`` (ADR 0012, TC-I-AUTH-10).

    The audit row names the admin actor; ``target`` names the user whose
    sessions were closed.  Audit write shares the caller's transaction so
    it either commits with the UPDATE or rolls back with it.
    """
    revoked = await revoke_all_sessions_for(db, user_id)
    await write_audit(
        db,
        action=AuditAction.admin_revoke_sessions,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"user:{user_id}",
        client_ip=client_ip(request),
    )
    return {"revoked": revoked}
