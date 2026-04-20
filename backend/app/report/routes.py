"""Report API — M5 implementation (FR-REPORT-1..9).

Endpoints
---------
GET  /api/report
    Returns aggregated period data for the authenticated caller.
    Query params:
      year             int  (default: current calendar year)
      period           str  (Jan..Dec | Q1..Q4 | H1 | H2 | Annual; default: Annual)
      hub              str  (optional; must be in caller's scope, else 403)
      compare_previous bool (default: false; triggers YoY overlay, FR-REPORT-9)

POST /api/report/refresh
    Bypasses the Sheet cache and fetches fresh data.
    Audited (FR-REPORT-7, TC-I-AUD-7).
    Admin and editor only.

Security notes
--------------
- Hub scoping: ``load_allowed_hubs`` resolves the session user's scope.
  The ``hub`` query param triggers a deny-check (TC-I-API-6) but does NOT
  substitute for scope enforcement — aggregation always uses ``allowed_hubs``.
- ``report_view`` audit rows are written in their own transaction after the
  response body is computed.  This is a read-only event; the same-transaction
  rule applies to mutations only (see AuditAction.report_view docstring).
- No PII in log messages: city/hub names are non-personal; hire details are
  never logged.
"""

from __future__ import annotations

import datetime
from dataclasses import replace as dataclass_replace
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

# Runtime imports required for FastAPI dependency introspection.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.csrf import require_csrf
from app.authz.hub_scope import is_hub_allowed, load_allowed_hubs
from app.authz.roles import CurrentUser, Role, require_role  # noqa: TC001
from app.db.session import get_db
from app.logging import get_logger
from app.report.db import load_benchmark_note, load_report_aux
from app.report.logic import VALID_PERIODS, build_period_data
from app.report.models import PeriodData, ReportResponse
from app.sheets.client import get_sheets_client
from app.utils.http import client_ip

router = APIRouter(prefix="/api/report", tags=["report"])

log = get_logger(__name__)

_DEFAULT_PERIOD = "Annual"


def _current_year() -> int:
    return datetime.datetime.now(datetime.UTC).year


# ---------------------------------------------------------------------------
# GET /api/report
# ---------------------------------------------------------------------------


@router.get("", response_model=ReportResponse)
async def get_report(  # noqa: PLR0913
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    year: int = Query(default=0, description="Report year (default: current year)"),
    period: str = Query(default=_DEFAULT_PERIOD, description="Period code"),
    hub: str | None = Query(
        default=None,
        max_length=100,
        description="Filter to a single hub (must be in scope; max 100 chars)",
    ),
    compare_previous: bool = Query(
        default=False,
        description="Include previous-year overlay (FR-REPORT-9)",
    ),
) -> ReportResponse:
    """Return aggregated report data for the authenticated caller.

    Hub scope is applied before aggregation, not after (FR-AUTHZ-4).
    """
    effective_year = year if year > 0 else _current_year()

    # --- Period validation --------------------------------------------------
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid period {period!r}. Valid values: {sorted(VALID_PERIODS)}",
        )

    # --- Hub scope check (TC-I-API-6) ---------------------------------------
    allowed_hubs = await load_allowed_hubs(db, user.id)

    if hub is not None and not is_hub_allowed(hub, allowed_hubs):
        await write_audit(
            db,
            action=AuditAction.hub_scope_violation,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"hub={hub}",
            client_ip=client_ip(request),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="hub not in scope",
        )

    # If a specific hub was requested and is in scope, narrow allowed_hubs to
    # just that hub so the aggregation only shows it (Q2 answer).
    effective_allowed_hubs = [hub] if hub is not None else allowed_hubs

    # --- Load auxiliary data from DB ----------------------------------------
    aux = await load_report_aux(
        db,
        allowed_hubs=effective_allowed_hubs,
        year=effective_year,
        period=period,
    )

    # --- Fetch Sheet rows (uses cache, FR-REPORT-1) -------------------------
    sheets_client = get_sheets_client()
    fetch_result = await sheets_client.get_rows(db=db)

    # --- Build current-year data --------------------------------------------
    current_data: PeriodData = build_period_data(
        fetch_result.rows,
        aux,
        allowed_hubs=effective_allowed_hubs,
        year=effective_year,
        period=period,
    )

    # --- Year-over-year overlay (FR-REPORT-9, TC-I-API-8, TC-I-API-9) ------
    previous_year: int | None = None
    previous_data: PeriodData | None = None
    previous_year_missing = False

    if compare_previous:
        previous_year = effective_year - 1
        # hub_pairs, comments, and city_notes are year-agnostic — reuse aux
        # from the current-year call and fetch only the benchmark note for the
        # previous year.  Halves DB round-trips on every YoY view.
        prev_benchmark = await load_benchmark_note(
            db,
            year=previous_year,
            period=period,
        )
        prev_aux = dataclass_replace(aux, benchmark_notes=prev_benchmark)
        previous_data = build_period_data(
            fetch_result.rows,
            prev_aux,
            allowed_hubs=effective_allowed_hubs,
            year=previous_year,
            period=period,
        )
        # TC-I-API-9: flag when the previous-year period slice has no data.
        previous_year_missing = not previous_data.has_data

    # --- Audit report view (FR-AUDIT-1) -------------------------------------
    # Written after the response is assembled so a failed aggregation does not
    # produce a ghost audit row.  Own transaction (read-only event).
    try:
        await write_audit(
            db,
            action=AuditAction.report_view,
            actor_id=user.id,
            actor_email=user.email,
            actor_display_name=user.display_name,
            target=f"year={effective_year} period={period}",
            client_ip=client_ip(request),
        )
        await db.commit()
    except Exception:
        log.warning("report_view_audit_failed", extra={"user_id": str(user.id)})

    return ReportResponse(
        year=effective_year,
        period=period,
        stale=fetch_result.stale,
        fetched_at=fetch_result.fetched_at,
        data=current_data,
        previous_year=previous_year,
        previous_year_data=previous_data,
        previous_year_missing=previous_year_missing,
    )


# ---------------------------------------------------------------------------
# POST /api/report/refresh
# ---------------------------------------------------------------------------


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
    """Bypass the Sheet cache and fetch fresh data (FR-REPORT-7, TC-I-AUD-7).

    Audit row is written before the fetch so it survives a fetch that fails
    partway through (consistent with the sheet_refresh action semantics
    documented in AuditAction).
    """
    await write_audit(
        db,
        action=AuditAction.sheet_refresh,
        actor_id=user.id,
        actor_email=user.email,
        actor_display_name=user.display_name,
        client_ip=client_ip(request),
    )
    await db.commit()

    sheets_client = get_sheets_client()
    sheets_client.invalidate()
    await sheets_client.get_rows(db=db)

    return {"status": "accepted"}
