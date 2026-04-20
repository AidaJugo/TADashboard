"""Report aggregation logic — M5 port of legacy/generate_report.py lines 157-254.

Design rules (enforced by tests):
  - All functions are pure: no I/O, no SQLAlchemy, no side effects.
  - Hub scoping is applied via ``app.authz.hub_scope.filter_by_hub`` BEFORE
    aggregation, not after.  Aggregating first and then filtering is a data
    leak (FR-AUTHZ-4).
  - Numerical output on ``legacy/Hiring_Report_TEST_DATA.xlsx`` must match the
    prototype exactly (TC-U-REP-7, numerical parity requirement).
  - Unknown status values are counted in a fallback bucket and surfaced as
    warnings (TC-U-REP-8).  They are NOT silently dropped.
  - Rows with a blank ``month`` field are excluded from monthly aggregations
    and counted in ``rows_missing_month`` (TC-U-REP-9).
  - Hire notes longer than 500 characters are rejected at the validation
    boundary (TC-U-REP-13).

WF / NonWF rename:
  The Sheet stores "WFM" / "NonWFM" (or whatever the admin has configured).
  The app normalises to "WF" / "NonWF" inside the aggregation layer so that
  the API JSON and tests always use the PRD-canonical labels.

  The mapping is a module-level constant for M5.
  TODO(FR-CONFIG): make this admin-configurable (value-level column mapping)
  once M6 admin UI lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.authz.hub_scope import filter_by_hub

from .models import (
    AboveMidpointEntry,
    HubRow,
    KpiBlock,
    PeriodData,
    TypeSummaryRow,
)

if TYPE_CHECKING:
    from app.sheets.models import HireRow


# ---------------------------------------------------------------------------
# Auxiliary data container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportAux:
    """Auxiliary data loaded from Postgres for a single report request.

    Grouping these into one object keeps ``compute_period`` and
    ``build_period_data`` well below the PLR0913 argument limit and makes
    it straightforward to construct a test fixture in one place.
    """

    #: city_name → canonical hub_name (from hub_pairs table).
    city_to_hub: dict[str, str] = field(default_factory=dict)
    #: Ordered hub names to include in the response (post-scope filtering).
    hub_order: list[str] = field(default_factory=list)
    #: (position, seniority, hub, salary_eur_int) → comment text.
    comments: dict[tuple[str, str, str, int], str] = field(default_factory=dict)
    #: city_name → city note text.
    city_notes: dict[str, str] = field(default_factory=dict)
    #: period_code → benchmark note text.
    benchmark_notes: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical period ordering for all supported period codes.
ALL_MONTHS: list[str] = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

QUARTER_MONTHS: dict[str, list[str]] = {
    "Q1": ["Jan", "Feb", "Mar"],
    "Q2": ["Apr", "May", "Jun"],
    "Q3": ["Jul", "Aug", "Sep"],
    "Q4": ["Oct", "Nov", "Dec"],
}

HALF_YEAR_MONTHS: dict[str, list[str]] = {
    "H1": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "H2": ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

#: All valid period keys.
VALID_PERIODS: frozenset[str] = frozenset(
    ALL_MONTHS + list(QUARTER_MONTHS) + list(HALF_YEAR_MONTHS) + ["Annual"]
)

#: Known benchmark status values (must match Sheet content exactly).
KNOWN_STATUSES: list[str] = ["Below", "At mid-point", "Above", "No salary"]

#: Raw Sheet hire-type values → PRD-canonical app labels.
#: TODO(FR-CONFIG): make admin-configurable in M6 value-level column mapping.
HIRE_TYPE_NORMALISE: dict[str, str] = {
    "WFM": "WF",
    "NonWFM": "NonWF",
    # Pass-through in case the Sheet already uses the canonical labels.
    "WF": "WF",
    "NonWF": "NonWF",
}

CANONICAL_TYPES: list[str] = ["WF", "NonWF"]

#: Maximum hire-note length (PRD glossary, TC-U-REP-13).
MAX_NOTE_LENGTH: int = 500


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def validate_hire_note(note: str, context: str = "") -> str:
    """Reject notes longer than 500 characters (TC-U-REP-13).

    ``context`` is included in the error message for diagnostics.
    """
    if len(note) > MAX_NOTE_LENGTH:
        raise ValueError(
            f"Hire note exceeds {MAX_NOTE_LENGTH} characters" + (f" ({context})" if context else "")
        )
    return note


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def normalise_hire_type(raw: str) -> str:
    """Map raw Sheet hire-type value to the canonical app label.

    Falls back to the raw value if not in the mapping so unknown types surface
    rather than silently disappear.
    """
    return HIRE_TYPE_NORMALISE.get(raw.strip(), raw.strip())


def _to_float(value: str) -> float | None:
    """Parse a string to float; return None on empty or unparseable input."""
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------


def _status_counts(rows: list[HireRow], statuses: list[str]) -> dict[str, int]:
    """Count rows per status value (helper used by table builders)."""
    counts: dict[str, int] = dict.fromkeys(statuses, 0)
    counts["Total"] = len(rows)
    for row in rows:
        norm_status = row.status.strip()
        if norm_status in counts:
            counts[norm_status] += 1
    return counts


def _type_summary_row(label: str, rows: list[HireRow]) -> TypeSummaryRow:
    """Build one row of the WF / NonWF / Total summary table."""
    c = _status_counts(rows, KNOWN_STATUSES)
    return TypeSummaryRow(
        hire_type=label,
        below=c["Below"],
        at_mid=c["At mid-point"],
        above=c["Above"],
        no_salary=c["No salary"],
        total=c["Total"],
    )


def compute_period(
    rows: list[HireRow],
    aux: ReportAux,
    *,
    benchmark_note: str = "",
) -> PeriodData:
    """Aggregate one period's data from a hub-scoped list of HireRow objects.

    Parameters
    ----------
    rows:
        Hire rows already filtered to the caller's hub scope and year/period
        slice.  Hub scoping must happen BEFORE this call.
    aux:
        Auxiliary lookup data (hub order, city→hub map, comments, notes).
    benchmark_note:
        Free-text note for this period, from the ``benchmark_notes`` table.

    Returns
    -------
    PeriodData with ``has_data=False`` and all counts zero when ``rows`` is
    empty (FR-REPORT-6, TC-U-REP-2).
    """
    # Collect unrecognised status values for observability (TC-U-REP-8).
    # ``rows`` is already period-filtered by ``build_period_data`` before
    # ``compute_period`` is called, so this scan covers only the rows that
    # will actually be aggregated.  Do not move this scan upstream of the
    # period filter — doing so would attribute unknown statuses from other
    # periods to the current result, breaking TC-U-REP-8 isolation.
    unknown_statuses = sorted(
        {
            row.status.strip()
            for row in rows
            if row.status.strip() not in KNOWN_STATUSES and row.status.strip()
        }
    )

    if not rows:
        return PeriodData(
            has_data=False,
            benchmark_note=benchmark_note,
            unknown_statuses=unknown_statuses,
        )

    total = len(rows)

    # --- KPIs ---------------------------------------------------------------
    wf_n = sum(1 for r in rows if normalise_hire_type(r.hire_type) == "WF")
    below_n = sum(1 for r in rows if r.status.strip() == "Below")
    above_n = sum(1 for r in rows if r.status.strip() == "Above")
    at_n = sum(1 for r in rows if r.status.strip() == "At mid-point")
    no_n = sum(1 for r in rows if r.status.strip() == "No salary")

    kpis = KpiBlock(
        total=total,
        wf=wf_n,
        non_wf=total - wf_n,
        below=below_n,
        below_pct=round(below_n / total * 100, 1),
        above=above_n,
        above_pct=round(above_n / total * 100, 1),
        at_mid=at_n,
        at_mid_pct=round(at_n / total * 100, 1),
        no_salary=no_n,
        no_salary_pct=round(no_n / total * 100, 1),
    )

    # --- Summary table (WF / NonWF / Total) ---------------------------------
    wf_rows = [r for r in rows if normalise_hire_type(r.hire_type) == "WF"]
    non_wf_rows = [r for r in rows if normalise_hire_type(r.hire_type) == "NonWF"]
    summary = [
        _type_summary_row("WF", wf_rows),
        _type_summary_row("NonWF", non_wf_rows),
        _type_summary_row("Total", rows),
    ]

    # --- Per-hub breakdown --------------------------------------------------
    # Group by resolved hub name.
    hub_to_rows: dict[str, list[HireRow]] = {h: [] for h in aux.hub_order}
    for row in rows:
        hub_name = aux.city_to_hub.get(row.city.strip(), row.city.strip())
        if hub_name in hub_to_rows:
            hub_to_rows[hub_name].append(row)

    hub_rows: list[HubRow] = []
    for hub_name in aux.hub_order:
        h_rows = hub_to_rows[hub_name]
        if not h_rows:
            hub_rows.append(HubRow(hub=hub_name, has_data=False))
            continue
        h_wf = [r for r in h_rows if normalise_hire_type(r.hire_type) == "WF"]
        h_non_wf = [r for r in h_rows if normalise_hire_type(r.hire_type) == "NonWF"]
        hub_rows.append(
            HubRow(
                hub=hub_name,
                has_data=True,
                total=len(h_rows),
                rows=[
                    _type_summary_row("WF", h_wf),
                    _type_summary_row("NonWF", h_non_wf),
                    _type_summary_row("Total", h_rows),
                ],
                city_note=aux.city_notes.get(hub_name, ""),
            )
        )

    # --- Hub totals (for bar chart) -----------------------------------------
    hub_totals = {h: len(hub_to_rows[h]) for h in aux.hub_order}

    # --- Above-midpoint exceptions table (FR-REPORT-5) ----------------------
    above_detail: list[AboveMidpointEntry] = []
    for hub_name in aux.hub_order:
        hub_above = [r for r in hub_to_rows[hub_name] if r.status.strip() == "Above"]
        for row in hub_above:
            sal = _to_float(row.salary)
            sal_key = int(sal) if sal is not None else None
            comment_key: tuple[str, str, str, int] | None = (
                (row.position.strip(), row.seniority.strip(), hub_name, sal_key)
                if sal_key is not None
                else None
            )
            comment_text = aux.comments.get(comment_key, "") if comment_key else ""

            # Validate hire note length (TC-U-REP-13).
            raw_note = row.note.strip()
            validated_note = validate_hire_note(
                raw_note,
                context=f"{row.position}/{row.seniority}/{hub_name}",
            )

            above_detail.append(
                AboveMidpointEntry(
                    position=row.position.strip(),
                    seniority=row.seniority.strip(),
                    hub=hub_name,
                    salary=sal,
                    midpoint=_to_float(row.midpoint),
                    gap_eur=_to_float(row.gap_eur),
                    # gap_pct is stored as a decimal fraction in the Sheet (0.176 = 17.6%).
                    # The frontend multiplies by 100; do NOT pre-multiply here.
                    gap_pct=_to_float(row.gap_pct),
                    recruiter=row.recruiter.strip(),
                    comment=comment_text,
                    hire_note=validated_note,
                )
            )

    return PeriodData(
        has_data=True,
        kpis=kpis,
        summary=summary,
        hub_rows=hub_rows,
        above_detail=above_detail,
        hub_totals=hub_totals,
        benchmark_note=benchmark_note,
        unknown_statuses=unknown_statuses,
    )


# ---------------------------------------------------------------------------
# Period slicing
# ---------------------------------------------------------------------------


def _filter_period(rows: list[HireRow], period: str) -> list[HireRow]:
    """Return the subset of rows that belong to ``period``.

    Rows with a blank or None month are excluded (TC-U-REP-9).
    """
    if period in ALL_MONTHS:
        return [r for r in rows if r.month.strip() == period]
    if period in QUARTER_MONTHS:
        months = set(QUARTER_MONTHS[period])
        return [r for r in rows if r.month.strip() in months]
    if period in HALF_YEAR_MONTHS:
        months = set(HALF_YEAR_MONTHS[period])
        return [r for r in rows if r.month.strip() in months]
    if period == "Annual":
        return list(rows)
    raise ValueError(f"Unknown period: {period!r}")


def _count_missing_month(rows: list[HireRow], period: str) -> int:
    """Count rows excluded from a period slice because their month is blank.

    Only meaningful for period-filtered slices; Annual always includes all rows
    with a month (or no month), so we count blanks across all rows instead.
    """
    if period == "Annual":
        return sum(1 for r in rows if not r.month.strip())
    # For non-Annual periods, rows with blank month could belong to any period,
    # so we count them once globally (not per-period to avoid double-counting).
    return 0


def build_period_data(
    rows: list[HireRow],
    aux: ReportAux,
    *,
    allowed_hubs: list[str],
    year: int,
    period: str,
) -> PeriodData:
    """Entry point for the report pipeline.

    1. Filter to the requested year (TC-U-REP-10).
    2. Apply hub scope via ``filter_by_hub`` before aggregation (FR-AUTHZ-4).
    3. Slice to the requested period.
    4. Call ``compute_period``.

    Parameters
    ----------
    rows:
        All rows from the Sheet fetch result (all years, all hubs).
    aux:
        Auxiliary lookup data (hub order, city→hub map, comments, notes).
    allowed_hubs:
        The caller's hub scope (empty = all hubs).  Applied at step 2.
    year:
        The report year to aggregate (TC-U-REP-10).
    period:
        One of: Jan..Dec | Q1..Q4 | H1 | H2 | Annual.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period: {period!r}")

    # Step 1: filter to the requested year.
    year_rows = [r for r in rows if r.year.strip() == str(year)]

    # Rows with blank month are excluded from period-filtered slices.
    # Count them for transparency (TC-U-REP-9).
    missing_month_count = sum(1 for r in year_rows if not r.month.strip())

    # Step 2: apply hub scope before aggregation (MUST come before step 3).
    scoped_rows = filter_by_hub(
        year_rows,
        key=lambda r: aux.city_to_hub.get(r.city.strip(), r.city.strip()),
        allowed_hubs=allowed_hubs,
    )

    # Step 3: slice to the requested period.
    period_rows = _filter_period(scoped_rows, period)

    # Step 4: aggregate.
    result = compute_period(
        period_rows,
        aux,
        benchmark_note=aux.benchmark_notes.get(period, ""),
    )

    # Attach missing-month count to the result (TC-U-REP-9).
    # model_copy is used because PeriodData is frozen.
    return result.model_copy(update={"rows_missing_month": missing_month_count})
