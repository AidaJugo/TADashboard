"""Role-based authorization dependency (FR-AUTHZ-1, FR-AUTHZ-2).

Usage::

    from fastapi import Depends
    from app.authz.roles import require_role, Role

    @app.get("/api/admin/ping", dependencies=[Depends(require_role(Role.admin))])
    async def admin_ping() -> dict[str, str]:
        ...

Or, when the handler needs the user::

    @app.get("/api/report")
    async def report(user: User = Depends(require_role(Role.admin, Role.editor, Role.viewer))):
        ...

Notes
-----
- ``require_role`` is a dependency **factory** — call it with the allowed
  roles, then use the returned callable in ``Depends(...)``.
- Role comparison uses the ``RoleEnum`` values.  We accept either the enum
  or bare string names at the factory call site for ergonomics; internally
  we always coerce to ``RoleEnum``.
- A 403 from here **writes** an ``access_denied`` audit row before
  raising (FR-AUTHZ-2, TC-S-3).  We commit the audit row in the same
  session so ``get_db``'s rollback on ``HTTPException`` cannot drop it —
  same pattern as the hub-scope violation path in
  ``app.report.routes.get_report``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, HTTPException, Request, status

# Runtime imports required for FastAPI dependency introspection — see
# ``app/auth/deps.py`` for the full explanation.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.deps import get_current_user
from app.db.models import RoleEnum, User
from app.db.session import get_db
from app.utils.http import client_ip

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

#: Public alias — downstream code imports ``Role`` rather than ``RoleEnum``.
Role = RoleEnum


#: Typed alias for handler signatures: ``user: CurrentUser``.  Uses FastAPI's
#: ``Annotated[..., Depends(...)]`` pattern (ruff B008-safe).  Route
#: handlers declare ``user: CurrentUser`` and FastAPI resolves the
#: dependency without a function-call default.
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(
    *allowed: Role | str,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Build a FastAPI dependency that enforces ``allowed`` roles.

    An empty ``allowed`` is a programming error (no one would be allowed in).
    We reject it at factory time so the mistake surfaces at import / app-
    startup rather than at request time.
    """
    if not allowed:
        raise ValueError("require_role() called with no allowed roles — would deny all callers")
    allowed_set: frozenset[Role] = frozenset(Role(r) if isinstance(r, str) else r for r in allowed)

    async def _dep(
        request: Request,
        user: CurrentUser,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if user.role not in allowed_set:
            await write_audit(
                db,
                action=AuditAction.access_denied,
                actor_id=user.id,
                actor_email=user.email,
                actor_display_name=user.display_name,
                target=f"{request.method} {request.url.path}",
                client_ip=client_ip(request),
            )
            # Persist the audit row before raising — HTTPException triggers a
            # rollback in the ``get_db`` dependency.  See
            # ``app.report.routes.get_report`` for the sibling pattern.
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient role",
            )
        return user

    return _dep
