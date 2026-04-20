"""Admin API — M6 expansion.

Endpoints
---------
GET  /api/admin/ping                             — role-guard smoke test.
POST /api/admin/users/{user_id}/revoke-sessions  — operator-assisted offboarding
                                                   (ADR 0012, TC-I-AUTH-10).

User management (FR-USER-1..3):
GET  /api/admin/users                            — list all users.
POST /api/admin/users                            — add user to allowlist.
GET  /api/admin/users/{user_id}                  — fetch single user.
PATCH /api/admin/users/{user_id}                 — edit role / hubs / display name.
POST /api/admin/users/{user_id}/deactivate       — soft-delete; revokes sessions
                                                   and writes deactivation audit row.

Config (FR-CONFIG-1..5):
GET  /api/admin/config                           — current spreadsheet + mapping config.
POST /api/admin/config                           — update spreadsheet / column mappings.
                                                   Validates reachability before save.
PATCH /api/admin/config/retention                — update retention windows.

Hub pairs (FR-CONFIG-3, TC-I-API-12):
GET   /api/admin/hub-pairs                       — list hub pairs.
POST  /api/admin/hub-pairs                       — create hub pair.
PATCH /api/admin/hub-pairs/{pair_id}             — update hub pair.
DELETE /api/admin/hub-pairs/{pair_id}            — delete hub pair.

Security notes
--------------
- All endpoints require admin role via ``require_role(Role.admin)`` at the
  router-dependency level; no role checks inside route bodies (TC-S-3).
- Every mutation writes an audit row in the same DB transaction as the change.
- Last-admin guard: deactivate and role-demote paths check that at least one
  other active admin would remain; 409 if not (TC-I-API-10, TC-I-API-11).
- Retention bounds validated by Pydantic (ge/le) + the server returns 422 on
  out-of-range values (TC-I-API-13).
- Spreadsheet validation is done before config is written; invalid spreadsheet
  returns 422 and leaves the existing config unchanged (TC-I-API-5).
"""

from __future__ import annotations

import asyncio
import uuid as uuid_module  # noqa: TC003 — FastAPI resolves path params at runtime
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002
from sqlalchemy.orm import selectinload

from app.admin.schemas import (
    ConfigResponse,
    ConfigUpdateRequest,
    HubPairCreateRequest,
    HubPairResponse,
    HubPairUpdateRequest,
    RetentionUpdateRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.csrf import require_csrf
from app.auth.sessions import revoke_all_sessions_for
from app.authz.roles import CurrentUser, Role, require_role  # noqa: TC001
from app.config import (
    RETENTION_AUDIT_MONTHS_DEFAULT,
    RETENTION_BACKUP_DAYS_DEFAULT,
    get_settings,
)
from app.db.models import (
    ColumnMapping,
    ConfigKV,
    HubPair,
    RoleEnum,
    User,
    UserHubScope,
)
from app.db.session import get_db, get_erasure_session_factory, get_sweep_db
from app.logging import get_logger
from app.sheets.column_mapping import ColumnMappingError, validate_column_mapping
from app.utils.http import client_ip

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
)

_ADMIN = Depends(require_role(Role.admin))

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config key names (matches config_kv.key column)
# ---------------------------------------------------------------------------

_KEY_SPREADSHEET_ID = "spreadsheet_id"
_KEY_SPREADSHEET_TAB = "spreadsheet_tab_name"
_KEY_AUDIT_RETENTION = "audit_retention_months"
_KEY_BACKUP_RETENTION = "backup_retention_days"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_other_active_admins(db: AsyncSession, exclude_user_id: uuid_module.UUID) -> int:
    """Return the number of active admins excluding ``exclude_user_id``."""
    result = await db.execute(
        select(func.count()).where(
            User.role == RoleEnum.admin,
            User.is_active.is_(True),
            User.id != exclude_user_id,
        )
    )
    return int(result.scalar_one())


def _last_admin_guard(remaining: int) -> None:
    """Raise 409 if there would be no admins left."""
    if remaining == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove or demote the last admin.",
        )


async def _erasure_background(
    actor_id: uuid_module.UUID,
    before_ts: datetime,
    factory: object | None = None,
) -> None:
    """Redact PII from audit rows for ``actor_id`` (NFR-PRIV-5, ADR 0010).

    Runs as a FastAPI BackgroundTask — after the app transaction commits,
    before the next request.  Uses the ``ta_report_erasure`` DB role.
    Errors are logged but not re-raised so a connectivity blip does not
    undo the already-committed deactivation.

    ``factory`` is injectable for tests; production code passes None and
    gets the module-level erasure session factory.
    """
    from app.audit.erasure import redact_actor  # noqa: PLC0415
    from app.db.session import get_erasure_session_factory  # noqa: PLC0415

    effective_factory = factory or get_erasure_session_factory()
    try:
        async with effective_factory() as session:
            rowcount = await redact_actor(session, actor_id, before_ts=before_ts)
            await session.commit()
            log.info(
                "erasure_background_complete",
                extra={"actor_id": str(actor_id), "rowcount": rowcount},
            )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "erasure_background_failed",
            extra={"actor_id": str(actor_id), "error": str(exc)},
        )


async def _user_or_404(db: AsyncSession, user_id: uuid_module.UUID) -> User:
    stmt = select(User).options(selectinload(User.hub_scopes)).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        allowed_hubs=[hs.hub_name for hs in user.hub_scopes],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _load_config_kv(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(ConfigKV))).scalars().all()
    return {row.key: row.value for row in rows}


async def _upsert_config_kv(
    db: AsyncSession,
    key: str,
    value: str,
    updated_by_id: uuid_module.UUID | None,
) -> None:
    existing = (await db.execute(select(ConfigKV).where(ConfigKV.key == key))).scalar_one_or_none()
    if existing is None:
        db.add(ConfigKV(key=key, value=value, updated_by_id=updated_by_id))
    else:
        existing.value = value
        existing.updated_by_id = updated_by_id


async def _validate_spreadsheet(
    spreadsheet_id: str,
    tab_name: str,
) -> str | None:
    """Return None if the spreadsheet is reachable, else a human-readable error.

    Wraps the synchronous gspread call in ``asyncio.to_thread`` so it does not
    block the event loop.  Catches all expected error shapes and returns a
    specific message so TC-I-API-5 (FR-CONFIG-5) can surface the right hint.

    Tests patch this function directly to inject failures.
    """
    settings = get_settings()
    if not settings.google_service_account_json_path:
        # In environments without a service account configured (dev, test),
        # skip the reachability check — structural validation already ran.
        # In prod, a missing SA path is a misconfiguration: fail hard so the
        # 422 contract from TC-I-API-5 (FR-CONFIG-4) is still enforced.
        if settings.app_env == "prod":
            return "Service account not configured; cannot validate spreadsheet in prod."
        return None

    def _check() -> str | None:
        try:
            from app.sheets.client import _build_gspread_client  # noqa: PLC0415

            gc = _build_gspread_client(settings.google_service_account_json_path)
            ss = gc.open_by_key(spreadsheet_id)
            ss.worksheet(tab_name)
            return None
        except Exception as exc:  # noqa: BLE001 — surface all errors to the caller
            return str(exc)

    return await asyncio.to_thread(_check)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


@router.get("/ping", dependencies=[_ADMIN])
async def admin_ping() -> dict[str, str]:
    """Return a trivial payload.  Admin-only (FR-AUTHZ-1)."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Users — list
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[UserResponse], dependencies=[_ADMIN])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserResponse]:
    """List all users (active and inactive)."""
    stmt = select(User).options(selectinload(User.hub_scopes)).order_by(User.created_at)
    users = (await db.execute(stmt)).scalars().all()
    return [_user_to_response(u) for u in users]


# ---------------------------------------------------------------------------
# Users — create
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def create_user(
    body: UserCreateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Add a user to the allowlist (FR-USER-1)."""
    existing = (
        await db.execute(select(User).where(User.email == str(body.email)))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {body.email!r} already exists.",
        )

    new_user = User(
        email=str(body.email),
        display_name=body.display_name,
        role=body.role,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    for hub in body.allowed_hubs:
        db.add(UserHubScope(user_id=new_user.id, hub_name=hub))

    await write_audit(
        db,
        action=AuditAction.user_created,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"user:{new_user.id} email:{new_user.email} role:{new_user.role}",
        client_ip=client_ip(request),
    )

    await db.refresh(new_user, ["hub_scopes"])
    return _user_to_response(new_user)


# ---------------------------------------------------------------------------
# Users — fetch single
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}", response_model=UserResponse, dependencies=[_ADMIN])
async def get_user(
    user_id: uuid_module.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    return _user_to_response(await _user_or_404(db, user_id))


# ---------------------------------------------------------------------------
# Users — update role / hubs / display_name (TC-I-API-11)
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def update_user(
    user_id: uuid_module.UUID,
    body: UserUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Edit a user's role, hubs, or display name (FR-USER-2).

    Role demotion from admin is blocked when the target is the last admin
    (TC-I-API-11).
    """
    target = await _user_or_404(db, user_id)
    before_role = target.role
    before_name = target.display_name

    if body.role is not None and body.role != RoleEnum.admin and target.role == RoleEnum.admin:
        remaining = await _count_other_active_admins(db, user_id)
        _last_admin_guard(remaining)

    changes: list[str] = []

    if body.display_name is not None and body.display_name != target.display_name:
        target.display_name = body.display_name
        changes.append(f"display_name:{before_name!r}→{body.display_name!r}")

    if body.role is not None and body.role != target.role:
        target.role = body.role
        changes.append(f"role:{before_role}→{body.role}")
        await write_audit(
            db,
            action=AuditAction.role_change,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"user:{user_id} {before_role}→{body.role}",
            client_ip=client_ip(request),
        )

    if body.allowed_hubs is not None:
        # Load and delete via ORM so the relationship is refreshed.
        scopes = (
            (await db.execute(select(UserHubScope).where(UserHubScope.user_id == user_id)))
            .scalars()
            .all()
        )
        for scope in scopes:
            await db.delete(scope)
        await db.flush()

        for hub in body.allowed_hubs:
            db.add(UserHubScope(user_id=user_id, hub_name=hub))

        changes.append(f"allowed_hubs→{body.allowed_hubs!r}")
        await write_audit(
            db,
            action=AuditAction.hub_scope_change,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"user:{user_id} hubs:{body.allowed_hubs!r}",
            client_ip=client_ip(request),
        )

    if changes:
        await write_audit(
            db,
            action=AuditAction.user_updated,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"user:{user_id} changes:{'; '.join(changes)}",
            client_ip=client_ip(request),
        )

    await db.flush()
    # `populate_existing=True` forces the identity-map instance to be updated
    # with fresh DB data including the re-issued selectinload for hub_scopes.
    stmt = (
        select(User)
        .options(selectinload(User.hub_scopes))
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    refreshed = (await db.execute(stmt)).scalar_one_or_none()
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return _user_to_response(refreshed)


# ---------------------------------------------------------------------------
# Users — deactivate (TC-I-API-10, FR-USER-2, NFR-PRIV-5 wired in PR 2)
# ---------------------------------------------------------------------------


@router.post(
    "/users/{user_id}/deactivate",
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def deactivate_user(
    user_id: uuid_module.UUID,
    request: Request,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Soft-delete a user (FR-USER-2).

    Flow (M6 spec, NFR-PRIV-5):
    1. Last-admin guard check.
    2. Set is_active=False.
    3. Revoke all active sessions.
    4. Write deactivation audit row — capture timestamp BEFORE write so
       the audit row's ``created_at`` falls after ``deactivation_ts``.
    5. Commit app transaction (automatic via get_db).
    6–7. BackgroundTask: redact PII in historical audit rows for this actor,
         using the ``ta_report_erasure`` DB role, filtered to rows created
         BEFORE ``deactivation_ts`` (so step-4's audit row is not erased).
    """
    target = await _user_or_404(db, user_id)

    if not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already deactivated.",
        )

    if target.role == RoleEnum.admin:
        remaining = await _count_other_active_admins(db, user_id)
        _last_admin_guard(remaining)

    target.is_active = False
    await db.flush()

    revoked = await revoke_all_sessions_for(db, user_id)

    # Capture timestamp BEFORE the audit write.  The audit row's DB-side
    # created_at will be >= deactivation_ts, so the erasure filter
    # `created_at < deactivation_ts` won't touch it (M6 spec).
    deactivation_ts = datetime.now(UTC)
    await write_audit(
        db,
        action=AuditAction.user_deactivated,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"user:{user_id} email:{target.email} sessions_revoked:{revoked}",
        client_ip=client_ip(request),
    )

    # Schedule erasure to run after the app transaction commits (step 6–7).
    # Pass the factory so tests can inject the test engine via monkeypatch.
    background_tasks.add_task(
        _erasure_background,
        user_id,
        deactivation_ts,
        get_erasure_session_factory(),
    )

    return {"status": "deactivated", "sessions_revoked": str(revoked)}


# ---------------------------------------------------------------------------
# Users — revoke sessions (M4, kept here for completeness)
# ---------------------------------------------------------------------------


@router.post(
    "/users/{user_id}/revoke-sessions",
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def revoke_user_sessions(
    user_id: uuid_module.UUID,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    """Revoke every active session of ``user_id`` (ADR 0012, TC-I-AUTH-10)."""
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


# ---------------------------------------------------------------------------
# Config — read
# ---------------------------------------------------------------------------


@router.get("/config", response_model=ConfigResponse, dependencies=[_ADMIN])
async def get_config(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigResponse:
    """Return the current admin-editable config (FR-CONFIG-1..2)."""
    kv = await _load_config_kv(db)
    settings = get_settings()

    mappings = (await db.execute(select(ColumnMapping))).scalars().all()
    col_map: dict[str, str] = {m.logical_name: m.source_column for m in mappings}

    return ConfigResponse(
        spreadsheet_id=kv.get(_KEY_SPREADSHEET_ID, settings.spreadsheet_id),
        spreadsheet_tab_name=kv.get(_KEY_SPREADSHEET_TAB, settings.spreadsheet_tab_name),
        audit_retention_months=int(
            kv.get(_KEY_AUDIT_RETENTION, str(RETENTION_AUDIT_MONTHS_DEFAULT))
        ),
        backup_retention_days=int(
            kv.get(_KEY_BACKUP_RETENTION, str(RETENTION_BACKUP_DAYS_DEFAULT))
        ),
        column_mappings=col_map,
    )


# ---------------------------------------------------------------------------
# Config — update spreadsheet + column mappings (TC-I-API-5, FR-CONFIG-4/5)
# ---------------------------------------------------------------------------


@router.post(
    "/config",
    response_model=ConfigResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def update_config(
    body: ConfigUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigResponse:
    """Update spreadsheet ID/tab and/or column mappings (FR-CONFIG-1..5).

    Validates the spreadsheet is reachable before saving (FR-CONFIG-4).
    Invalid config returns 422 and leaves the previous config unchanged
    (FR-CONFIG-5, TC-I-API-5).
    """
    kv = await _load_config_kv(db)
    settings = get_settings()
    current_id = kv.get(_KEY_SPREADSHEET_ID, settings.spreadsheet_id)
    current_tab = kv.get(_KEY_SPREADSHEET_TAB, settings.spreadsheet_tab_name)

    new_id = body.spreadsheet_id if body.spreadsheet_id is not None else current_id
    new_tab = body.spreadsheet_tab_name if body.spreadsheet_tab_name is not None else current_tab

    # Validate column mapping structure before any I/O.
    if body.column_mappings is not None:
        try:
            validate_column_mapping(body.column_mappings)
        except ColumnMappingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    # Validate spreadsheet reachability when ID or tab changed.
    if body.spreadsheet_id is not None or body.spreadsheet_tab_name is not None:
        error = await _validate_spreadsheet(new_id, new_tab)
        if error is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Spreadsheet validation failed: {error}",
            )

    changes: list[str] = []

    if body.spreadsheet_id is not None and body.spreadsheet_id != current_id:
        await _upsert_config_kv(db, _KEY_SPREADSHEET_ID, body.spreadsheet_id, user.id)
        changes.append(f"spreadsheet_id:{current_id!r}→{body.spreadsheet_id!r}")

    if body.spreadsheet_tab_name is not None and body.spreadsheet_tab_name != current_tab:
        await _upsert_config_kv(db, _KEY_SPREADSHEET_TAB, body.spreadsheet_tab_name, user.id)
        changes.append(f"tab:{current_tab!r}→{body.spreadsheet_tab_name!r}")

    if body.column_mappings is not None:
        # Replace all column_mappings rows.
        existing = (await db.execute(select(ColumnMapping))).scalars().all()
        for row in existing:
            await db.delete(row)
        await db.flush()
        for logical, source in body.column_mappings.items():
            db.add(ColumnMapping(logical_name=logical, source_column=source, updated_by_id=user.id))
        changes.append(f"column_mappings updated ({len(body.column_mappings)} entries)")
        await write_audit(
            db,
            action=AuditAction.column_mapping_edit,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"mappings:{list(body.column_mappings.keys())!r}",
            client_ip=client_ip(request),
        )

    if changes:
        await write_audit(
            db,
            action=AuditAction.config_edit,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target="; ".join(changes),
            client_ip=client_ip(request),
        )

    await db.flush()
    return await get_config(db)


# ---------------------------------------------------------------------------
# Config — retention windows (TC-I-API-13, NFR-PRIV-2, NFR-PRIV-4)
# ---------------------------------------------------------------------------


@router.patch(
    "/config/retention",
    response_model=ConfigResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def update_retention(
    body: RetentionUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigResponse:
    """Update audit and/or backup retention windows (NFR-PRIV-2, NFR-PRIV-4).

    Pydantic enforces the ge/le bounds on the request model, so any value
    outside the configured range is rejected as 422 before reaching this body
    (TC-I-API-13).
    """
    kv = await _load_config_kv(db)
    changes: list[str] = []

    if body.audit_retention_months is not None:
        old = kv.get(_KEY_AUDIT_RETENTION, str(RETENTION_AUDIT_MONTHS_DEFAULT))
        await _upsert_config_kv(db, _KEY_AUDIT_RETENTION, str(body.audit_retention_months), user.id)
        changes.append(f"audit_retention_months:{old}→{body.audit_retention_months}")

    if body.backup_retention_days is not None:
        old = kv.get(_KEY_BACKUP_RETENTION, str(RETENTION_BACKUP_DAYS_DEFAULT))
        await _upsert_config_kv(db, _KEY_BACKUP_RETENTION, str(body.backup_retention_days), user.id)
        changes.append(f"backup_retention_days:{old}→{body.backup_retention_days}")

    if changes:
        await write_audit(
            db,
            action=AuditAction.config_edit,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target="; ".join(changes),
            client_ip=client_ip(request),
        )

    await db.flush()
    return await get_config(db)


# ---------------------------------------------------------------------------
# Hub pairs — list (TC-I-API-12)
# ---------------------------------------------------------------------------


@router.get("/hub-pairs", response_model=list[HubPairResponse], dependencies=[_ADMIN])
async def list_hub_pairs(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[HubPairResponse]:
    pairs = (await db.execute(select(HubPair).order_by(HubPair.city_name))).scalars().all()
    return [HubPairResponse.model_validate(p) for p in pairs]


# ---------------------------------------------------------------------------
# Hub pairs — create
# ---------------------------------------------------------------------------


@router.post(
    "/hub-pairs",
    status_code=status.HTTP_201_CREATED,
    response_model=HubPairResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def create_hub_pair(
    body: HubPairCreateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HubPairResponse:
    existing = (
        await db.execute(select(HubPair).where(HubPair.city_name == body.city_name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A hub pair for city {body.city_name!r} already exists.",
        )

    pair = HubPair(city_name=body.city_name, hub_name=body.hub_name, created_by_id=user.id)
    db.add(pair)
    await db.flush()

    await write_audit(
        db,
        action=AuditAction.hub_pair_edit,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"create city:{body.city_name!r} hub:{body.hub_name!r}",
        client_ip=client_ip(request),
    )
    return HubPairResponse.model_validate(pair)


# ---------------------------------------------------------------------------
# Hub pairs — update
# ---------------------------------------------------------------------------


@router.patch(
    "/hub-pairs/{pair_id}",
    response_model=HubPairResponse,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def update_hub_pair(
    pair_id: uuid_module.UUID,
    body: HubPairUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HubPairResponse:
    pair = (await db.execute(select(HubPair).where(HubPair.id == pair_id))).scalar_one_or_none()
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub pair not found.")

    changes: list[str] = []
    if body.city_name is not None and body.city_name != pair.city_name:
        changes.append(f"city:{pair.city_name!r}→{body.city_name!r}")
        pair.city_name = body.city_name
    if body.hub_name is not None and body.hub_name != pair.hub_name:
        changes.append(f"hub:{pair.hub_name!r}→{body.hub_name!r}")
        pair.hub_name = body.hub_name

    if changes:
        await write_audit(
            db,
            action=AuditAction.hub_pair_edit,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"update pair:{pair_id} {'; '.join(changes)}",
            client_ip=client_ip(request),
        )

    await db.flush()
    return HubPairResponse.model_validate(pair)


# ---------------------------------------------------------------------------
# Hub pairs — delete
# ---------------------------------------------------------------------------


@router.delete(
    "/hub-pairs/{pair_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def delete_hub_pair(
    pair_id: uuid_module.UUID,
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    pair = (await db.execute(select(HubPair).where(HubPair.id == pair_id))).scalar_one_or_none()
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hub pair not found.")

    city = pair.city_name
    hub = pair.hub_name
    await db.delete(pair)

    await write_audit(
        db,
        action=AuditAction.hub_pair_edit,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target=f"delete pair:{pair_id} city:{city!r} hub:{hub!r}",
        client_ip=client_ip(request),
    )


# ---------------------------------------------------------------------------
# Retention sweep trigger (NFR-PRIV-4, TC-I-AUD-6)
# ---------------------------------------------------------------------------


@router.post(
    "/sweep/trigger",
    dependencies=[Depends(require_csrf), _ADMIN],
)
async def trigger_sweep(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    sweep_db: Annotated[AsyncSession, Depends(get_sweep_db)],
) -> dict[str, int]:
    """Manually trigger the audit-log retention sweep (NFR-PRIV-4).

    Runs the sweep synchronously (blocks until complete) and returns the
    number of deleted rows.  An audit row for the trigger event is written
    in the app transaction; the sweep itself runs in the sweep DB role.
    """
    from app.audit.sweep import _get_audit_retention_months, sweep_audit_log  # noqa: PLC0415

    retention_months = await _get_audit_retention_months(db)

    await write_audit(
        db,
        action=AuditAction.sweep_triggered,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        target="audit_log",
        client_ip=client_ip(request),
    )

    rows_deleted = await sweep_audit_log(sweep_db, retention_months=retention_months)
    return {"rows_deleted": rows_deleted}
