"""Report API (PR 3 slice).

The full pipeline lands in M5.  In PR 3 we only need the ``hub`` query
param path through :func:`app.authz.hub_scope.is_hub_allowed` so we can
close TC-I-API-6 (hub-scoped viewer requesting an out-of-scope hub must
get 403 + audit row).

For scope-permitted or scope-less calls we return a minimal placeholder
body.  M5 replaces the body; the **guard** does not change.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

# Runtime imports required for FastAPI dependency introspection — see
# ``app/auth/deps.py`` for the full explanation.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.csrf import require_csrf
from app.authz.hub_scope import filter_hub_names, is_hub_allowed, load_allowed_hubs
from app.authz.roles import CurrentUser, Role, require_role  # noqa: TC001
from app.db.session import get_db
from app.utils.http import client_ip

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("")
async def get_report(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    hub: str | None = None,
) -> dict[str, object]:
    """Return report data, filtered to the caller's hub scope.

    - No ``hub`` param: respond with the caller's allowed hubs list (or
      ``null`` when the user has no row in ``user_hub_scopes``, meaning
      all hubs).
    - ``hub`` param that is **not** in scope: 403 + audit row
      (TC-I-API-6).
    - ``hub`` param that **is** in scope: trivial ok payload (M5 replaces
      the body).
    """
    allowed = await load_allowed_hubs(db, user.id)

    if hub is not None and not is_hub_allowed(hub, allowed):
        await write_audit(
            db,
            action=AuditAction.hub_scope_violation,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"hub={hub}",
            client_ip=client_ip(request),
        )
        # Persist the audit row before raising — HTTPException triggers a
        # rollback in the get_db dependency.  The audit row is the whole
        # point of this code path (FR-AUDIT-1 for denied access).
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="hub not in scope",
        )

    return {
        "hub": hub,
        "allowed_hubs": allowed if allowed else None,
        "hubs": filter_hub_names([hub] if hub else [], allowed),
    }


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_csrf), Depends(require_role(Role.admin, Role.editor))],
)
async def refresh_report(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Kick off a Google Sheets refresh (FR-REPORT-7, TC-I-AUD-7).

    The actual fetch + snapshot write lands with the M5 report pipeline.
    What PR 4 needs here is the **audit row**: every refresh (successful
    or not) must leave a ``sheet_refresh`` entry.
    """
    await write_audit(
        db,
        action=AuditAction.sheet_refresh,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        client_ip=client_ip(request),
    )
    return {"status": "accepted"}
