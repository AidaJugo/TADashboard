"""Database loaders for the report pipeline (M5).

These async functions read the auxiliary tables (hub_pairs, comments,
benchmark_notes, city_notes) into the in-memory structures consumed by the
pure aggregation layer.  They are the only place where the report pipeline
touches SQLAlchemy — keeping I/O at the boundary so the logic layer stays
testable without a DB connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.authz.hub_scope import filter_hub_names
from app.db.models import BenchmarkNote, CityNote, Comment, HubPair
from app.report.logic import ReportAux

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _load_static_aux(
    db: AsyncSession,
    *,
    allowed_hubs: list[str],
) -> tuple[dict[str, str], list[str], dict[tuple[str, str, str, int], str], dict[str, str]]:
    """Load the year-agnostic parts of ReportAux.

    Returns ``(city_to_hub, hub_order, comments, city_notes)``.
    These four structures are identical regardless of which year or period is
    being requested, so they can be computed once and reused for YoY overlays.
    """
    hub_pair_rows = (await db.execute(select(HubPair))).scalars().all()
    city_to_hub: dict[str, str] = {hp.city_name: hp.hub_name for hp in hub_pair_rows}
    all_hub_names: list[str] = list(dict.fromkeys(hp.hub_name for hp in hub_pair_rows))
    hub_order = filter_hub_names(all_hub_names, allowed_hubs)

    comment_rows = (await db.execute(select(Comment))).scalars().all()
    comments: dict[tuple[str, str, str, int], str] = {
        (c.position, c.seniority, c.hub, c.salary_eur): c.text for c in comment_rows
    }

    city_note_rows = (await db.execute(select(CityNote))).scalars().all()
    city_notes: dict[str, str] = {cn.city_name: cn.text for cn in city_note_rows}

    return city_to_hub, hub_order, comments, city_notes


async def load_benchmark_note(
    db: AsyncSession,
    *,
    year: int,
    period: str,
) -> dict[str, str]:
    """Load the benchmark note for a specific year + period.

    Returns a single-entry dict ``{period: note_text}`` (empty string when no
    note exists).  Kept as a separate function so the caller can fetch just the
    note for YoY overlays without re-querying hub_pairs, comments, or city_notes.
    """
    stmt = select(BenchmarkNote).where(
        BenchmarkNote.period == period,
        BenchmarkNote.year == year,
    )
    bn = (await db.execute(stmt)).scalar_one_or_none()
    return {period: bn.text if bn else ""}


async def load_report_aux(
    db: AsyncSession,
    *,
    allowed_hubs: list[str],
    year: int,
    period: str,
) -> ReportAux:
    """Load all auxiliary data needed for a single report request.

    Hub order is derived from the hub_pairs table, scoped to the caller's
    allowed_hubs list.  Comments are loaded for all hubs (scoping happens
    via the hub key itself — a comment keyed to Belgrade never appears in
    a Sarajevo-only view because the above-midpoint detail loop only iterates
    over the caller's hub_order).

    Parameters
    ----------
    db:
        Async SQLAlchemy session.
    allowed_hubs:
        Caller's hub scope.  Empty = all hubs.
    year, period:
        Used to load the correct benchmark note.

    See Also
    --------
    load_benchmark_note : fetch only the benchmark note for YoY reuse.
    """
    city_to_hub, hub_order, comments, city_notes = await _load_static_aux(
        db, allowed_hubs=allowed_hubs
    )
    benchmark_notes = await load_benchmark_note(db, year=year, period=period)

    return ReportAux(
        city_to_hub=city_to_hub,
        hub_order=hub_order,
        comments=comments,
        city_notes=city_notes,
        benchmark_notes=benchmark_notes,
    )
