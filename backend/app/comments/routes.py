"""Comments CRUD API (FR-COMMENT-1..4, M6).

Endpoints
---------
POST   /api/comments           — create comment (editor + admin, TC-I-API-3).
GET    /api/comments           — list comments (editor + admin).
PATCH  /api/comments/{id}      — update comment text (editor + admin).
DELETE /api/comments/{id}      — delete comment (editor + admin).

Security notes
--------------
- Requires editor or admin role (FR-COMMENT-1).
- Every mutation writes an audit row in the same DB transaction (FR-COMMENT-4).
- Duplicate hire key returns 409 (uq_comment_hire_key DB constraint).
  The route handler catches IntegrityError and surfaces a clear detail message.
- The GET endpoint is here for admin/editor management UIs; the report endpoint
  already serves comments to all roles as part of the aggregated ReportAux.
"""

from __future__ import annotations

import uuid as uuid_module  # noqa: TC003 — FastAPI resolves path params at runtime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.csrf import require_csrf
from app.authz.roles import CurrentUser, Role, require_role  # noqa: TC001
from app.comments.schemas import CommentCreateRequest, CommentResponse, CommentUpdateRequest
from app.db.models import Comment
from app.db.session import get_db
from app.utils.http import client_ip

router = APIRouter(prefix="/api/comments", tags=["comments"])

_EDITOR_OR_ADMIN = Depends(require_role(Role.editor, Role.admin))


# ---------------------------------------------------------------------------
# Create (TC-I-API-3)
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentResponse,
    dependencies=[Depends(require_csrf), _EDITOR_OR_ADMIN],
)
async def create_comment(
    body: CommentCreateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommentResponse:
    """Create a comment keyed by (position, seniority, hub, salary_eur).

    Returns 409 if a comment for this hire key already exists
    (uq_comment_hire_key, FR-COMMENT-1).
    """
    comment = Comment(
        position=body.position,
        seniority=body.seniority,
        hub=body.hub,
        salary_eur=body.salary_eur,
        text=body.text,
        created_by_id=user.id,
    )
    db.add(comment)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A comment for position={body.position!r} seniority={body.seniority!r} "
                f"hub={body.hub!r} salary_eur={body.salary_eur} already exists."
            ),
        ) from exc

    await write_audit(
        db,
        action=AuditAction.comment_created,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"comment:{comment.id} hub:{body.hub!r} position:{body.position!r}",
        client_ip=client_ip(request),
    )
    return CommentResponse.model_validate(comment)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[CommentResponse],
    dependencies=[_EDITOR_OR_ADMIN],
)
async def list_comments(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CommentResponse]:
    comments = (
        (await db.execute(select(Comment).order_by(Comment.hub, Comment.position))).scalars().all()
    )
    return [CommentResponse.model_validate(c) for c in comments]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.patch(
    "/{comment_id}",
    response_model=CommentResponse,
    dependencies=[Depends(require_csrf), _EDITOR_OR_ADMIN],
)
async def update_comment(
    comment_id: uuid_module.UUID,
    body: CommentUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommentResponse:
    comment = (
        await db.execute(select(Comment).where(Comment.id == comment_id))
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")

    before = comment.text
    if before == body.text:
        return CommentResponse.model_validate(comment)

    comment.text = body.text

    await write_audit(
        db,
        action=AuditAction.comment_updated,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"comment:{comment_id} before:{before[:50]!r}→after:{body.text[:50]!r}",
        client_ip=client_ip(request),
    )
    await db.flush()
    # Refresh to populate server-computed updated_at (onupdate=func.now()).
    await db.refresh(comment)
    return CommentResponse.model_validate(comment)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf), _EDITOR_OR_ADMIN],
)
async def delete_comment(
    comment_id: uuid_module.UUID,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    comment = (
        await db.execute(select(Comment).where(Comment.id == comment_id))
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")

    hub = comment.hub
    position = comment.position
    await db.delete(comment)

    await write_audit(
        db,
        action=AuditAction.comment_deleted,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"comment:{comment_id} hub:{hub!r} position:{position!r}",
        client_ip=client_ip(request),
    )
