"""Retention sweep — hard-deletes audit rows older than the configured window.

This module exposes:
- :func:`sweep_audit_log` — deletes rows older than ``audit_retention_months``.
- :func:`run_sweep` — loads config from DB and calls the above; entry point
  for the CLI (``python -m app.audit.sweep``) and the admin trigger endpoint
  (``POST /api/admin/sweep/trigger``).

Database role
-------------
Deletions run as the ``ta_report_sweep`` role, which holds ``DELETE`` on
``audit_log`` only (ADR 0010, TC-I-AUD-6).  Callers must supply a session
bound to that role via :func:`app.db.session.get_sweep_session_factory`.

Scheduling
----------
No in-process scheduler.  Wire a cron job or systemd timer to run:
  ``python -m app.audit.sweep``
An admin-accessible trigger endpoint is provided for manual invocation
without shell access (see ``admin/routes.py``).  M7 deployment runbook adds
the OS-level cron entry.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, select

from app.config import RETENTION_AUDIT_MONTHS_DEFAULT
from app.db.models import AuditLog, ConfigKV
from app.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_KEY_AUDIT_RETENTION = "audit_retention_months"


async def _get_audit_retention_months(app_db: AsyncSession) -> int:
    """Read the configured audit retention window from config_kv.

    Uses a *read-only* query on the app session.  The sweep session (which
    holds only DELETE on audit_log) cannot query config_kv, so we accept an
    app session here purely for the read.
    """
    row = (
        await app_db.execute(select(ConfigKV).where(ConfigKV.key == _KEY_AUDIT_RETENTION))
    ).scalar_one_or_none()
    if row is None:
        return RETENTION_AUDIT_MONTHS_DEFAULT
    try:
        return int(row.value)
    except ValueError:
        return RETENTION_AUDIT_MONTHS_DEFAULT


async def sweep_audit_log(
    sweep_db: AsyncSession,
    *,
    retention_months: int,
) -> int:
    """Hard-delete audit rows older than ``retention_months``.

    Must be called against a session bound to the ``ta_report_sweep`` role.
    Returns the number of deleted rows.  The caller commits the transaction.

    Parameters
    ----------
    sweep_db:
        AsyncSession bound to ``ta_report_sweep``.  Any other role with
        insufficient privileges will raise ``InsufficientPrivilege``.
    retention_months:
        Number of months to keep.  Rows with ``created_at`` older than
        ``now() - retention_months`` are deleted.
    """
    cutoff = datetime.now(UTC) - relativedelta(months=retention_months)
    stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
    result = await sweep_db.execute(stmt)
    rowcount = int(getattr(result, "rowcount", 0) or 0)
    log.info(
        "sweep_audit_log_complete",
        extra={
            "retention_months": retention_months,
            "rows_deleted": rowcount,
            "cutoff": cutoff.isoformat(),
        },
    )
    return rowcount


async def run_sweep(*, actor_id: str | None = None) -> dict[str, int]:
    """Load config and run the audit log sweep.

    This is the top-level entry point used by:
    - The CLI: ``python -m app.audit.sweep``
    - The admin trigger endpoint: ``POST /api/admin/sweep/trigger``

    Returns a dict with ``{"rows_deleted": N}`` for the caller to report.
    """
    from app.db.session import (  # noqa: PLC0415
        get_session_factory,
        get_sweep_session_factory,
    )

    # Load retention config via the app role (read-only).
    app_factory = get_session_factory()
    async with app_factory() as app_db:
        retention_months = await _get_audit_retention_months(app_db)

    # Run deletion via the sweep role.
    sweep_factory = get_sweep_session_factory()
    async with sweep_factory() as sweep_db:
        rows_deleted = await sweep_audit_log(sweep_db, retention_months=retention_months)
        await sweep_db.commit()

    log.info(
        "sweep_complete",
        extra={"rows_deleted": rows_deleted, "actor_id": actor_id},
    )
    return {"rows_deleted": rows_deleted}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    from app.logging import configure_logging

    configure_logging()
    result = asyncio.run(run_sweep())
    print(f"Sweep complete: {result['rows_deleted']} rows deleted.")  # noqa: T201
    sys.exit(0)
