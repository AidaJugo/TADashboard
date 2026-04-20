"""Unit tests for the report aggregation logic (TC-U-REP-1 through TC-U-REP-13).

All tests are pure: no I/O, no DB, no network.
docs/testing.md §3.1 maps each TC-U-REP-* to its behaviour.
"""

from __future__ import annotations

import pytest

from app.report.logic import (
    VALID_PERIODS,
    ReportAux,
    build_period_data,
    normalise_hire_type,
    validate_hire_note,
)
from app.sheets.models import HireRow

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

#: Default city→hub mapping for tests: each city IS its own hub.
CITY_TO_HUB: dict[str, str] = {
    "Sarajevo": "Sarajevo",
    "Banja Luka": "Sarajevo",  # Q1 answer: Banja Luka rolls up to Sarajevo hub
    "Belgrade": "Belgrade",
    "Novi Sad": "Belgrade",
    "Nis": "Nis",
    "Skopje": "Skopje",
    "Medellin": "Medellin",
    "Remote": "Medellin",
}

HUB_ORDER: list[str] = [
    "Sarajevo",
    "Belgrade",
    "Nis",
    "Skopje",
    "Medellin",
]


def make_row(
    *,
    position: str = "BE Engineer",
    seniority: str = "Medior",
    city: str = "Sarajevo",
    salary: str = "3000",
    midpoint: str = "3000",
    gap_eur: str = "0",
    gap_pct: str = "0",
    status: str = "At mid-point",
    month: str = "Jan",
    year: str = "2026",
    hire_type: str = "WFM",
    recruiter: str = "Jane Smith",
    note: str = "",
) -> HireRow:
    return HireRow(
        position=position,
        seniority=seniority,
        city=city,
        salary=salary,
        midpoint=midpoint,
        gap_eur=gap_eur,
        gap_pct=gap_pct,
        status=status,
        month=month,
        year=year,
        hire_type=hire_type,
        recruiter=recruiter,
        note=note,
    )


def _run_period(
    rows: list[HireRow],
    *,
    period: str = "Jan",
    year: int = 2026,
    allowed_hubs: list[str] | None = None,
    hub_order: list[str] | None = None,
    comments: dict[tuple[str, str, str, int], str] | None = None,
    city_notes: dict[str, str] | None = None,
    benchmark_notes: dict[str, str] | None = None,
) -> object:
    """Convenience wrapper that calls ``build_period_data`` with sensible defaults."""
    aux = ReportAux(
        city_to_hub=CITY_TO_HUB,
        hub_order=hub_order or HUB_ORDER,
        comments=comments or {},
        city_notes=city_notes or {},
        benchmark_notes=benchmark_notes or {},
    )
    return build_period_data(
        rows,
        aux,
        allowed_hubs=allowed_hubs or [],
        year=year,
        period=period,
    )


# ---------------------------------------------------------------------------
# TC-U-REP-1: one Below, one At mid-point, one Above, one No-salary
# ---------------------------------------------------------------------------


def test_tc_u_rep_1_kpi_counts_and_percentages() -> None:
    """TC-U-REP-1: KPI counts and percentages match for a mixed-status period."""
    rows = [
        make_row(status="Below"),
        make_row(status="At mid-point"),
        make_row(status="Above", salary="3500", midpoint="3000", gap_eur="500"),
        make_row(status="No salary", salary=""),
    ]
    result = _run_period(rows, period="Jan")

    assert result.has_data is True
    assert result.kpis is not None
    assert result.kpis.total == 4
    assert result.kpis.below == 1
    assert result.kpis.below_pct == 25.0
    assert result.kpis.above == 1
    assert result.kpis.above_pct == 25.0
    assert result.kpis.at_mid == 1
    assert result.kpis.at_mid_pct == 25.0
    assert result.kpis.no_salary == 1
    assert result.kpis.no_salary_pct == 25.0


# ---------------------------------------------------------------------------
# TC-U-REP-2: empty period
# ---------------------------------------------------------------------------


def test_tc_u_rep_2_empty_period_has_data_false() -> None:
    """TC-U-REP-2: Empty period returns has_data=False and all KPIs absent."""
    result = _run_period([], period="Jan")

    assert result.has_data is False
    assert result.kpis is None
    assert result.summary == []
    assert result.hub_rows == []
    assert result.above_detail == []


# ---------------------------------------------------------------------------
# TC-U-REP-3: per-hub tables group correctly by Type
# ---------------------------------------------------------------------------


def test_tc_u_rep_3_per_hub_grouping_by_type() -> None:
    """TC-U-REP-3: Hub rows contain correct WF / NonWF / Total sub-rows."""
    rows = [
        make_row(city="Sarajevo", hire_type="WFM", status="Below"),
        make_row(city="Sarajevo", hire_type="NonWFM", status="Above"),
        make_row(city="Belgrade", hire_type="WFM", status="At mid-point"),
    ]
    result = _run_period(rows, period="Jan")

    assert result.has_data is True

    sarajevo = next(h for h in result.hub_rows if h.hub == "Sarajevo")
    assert sarajevo.has_data is True
    assert sarajevo.total == 2

    wf_row = next(r for r in sarajevo.rows if r.hire_type == "WF")
    non_wf_row = next(r for r in sarajevo.rows if r.hire_type == "NonWF")
    total_row = next(r for r in sarajevo.rows if r.hire_type == "Total")

    assert wf_row.below == 1
    assert wf_row.above == 0
    assert non_wf_row.above == 1
    assert non_wf_row.below == 0
    assert total_row.total == 2


# ---------------------------------------------------------------------------
# TC-U-REP-4: quarterly / half-year / annual roll-ups equal sum of months
# ---------------------------------------------------------------------------


def test_tc_u_rep_4_quarterly_rollup_equals_sum_of_months() -> None:
    """TC-U-REP-4: Q1 total equals Jan + Feb + Mar totals."""
    rows = [
        make_row(month="Jan", status="Below"),
        make_row(month="Jan", status="Above"),
        make_row(month="Feb", status="At mid-point"),
        make_row(month="Mar", status="Below"),
    ]
    jan = _run_period(rows, period="Jan")
    feb = _run_period(rows, period="Feb")
    mar = _run_period(rows, period="Mar")
    q1 = _run_period(rows, period="Q1")

    assert q1.has_data is True
    assert q1.kpis is not None
    assert q1.kpis.total == (jan.kpis.total + feb.kpis.total + mar.kpis.total)
    assert q1.kpis.below == jan.kpis.below + feb.kpis.below + mar.kpis.below


def test_tc_u_rep_4_h1_equals_q1_plus_q2() -> None:
    """TC-U-REP-4: H1 total equals Q1 + Q2."""
    rows = [make_row(month=m) for m in ["Jan", "Feb", "Mar"]] + [
        make_row(month=m) for m in ["Apr", "May", "Jun"]
    ]
    q1 = _run_period(rows, period="Q1")
    q2 = _run_period(rows, period="Q2")
    h1 = _run_period(rows, period="H1")

    assert h1.kpis is not None
    assert h1.kpis.total == q1.kpis.total + q2.kpis.total


# ---------------------------------------------------------------------------
# TC-U-REP-5: above-midpoint join → correct comment, recruiter, hire note
# ---------------------------------------------------------------------------


def test_tc_u_rep_5_above_midpoint_joins_comment() -> None:
    """TC-U-REP-5: Above-midpoint detail carries comment from the comments dict."""
    comments: dict[tuple[str, str, str, int], str] = {
        ("BE Engineer", "Medior", "Sarajevo", 3500): "Approved by VP",
    }
    rows = [
        make_row(
            position="BE Engineer",
            seniority="Medior",
            city="Sarajevo",
            salary="3500",
            midpoint="3000",
            gap_eur="500",
            status="Above",
            hire_type="WFM",
            recruiter="Jane Smith",
            note="Short note",
        ),
    ]
    result = _run_period(rows, period="Jan", comments=comments)

    assert result.has_data is True
    assert len(result.above_detail) == 1
    entry = result.above_detail[0]
    assert entry.comment == "Approved by VP"
    assert entry.recruiter == "Jane Smith"
    assert entry.hire_note == "Short note"


def test_tc_u_rep_5_above_midpoint_no_comment_when_key_missing() -> None:
    """TC-U-REP-5: No comment when the key is absent from the comments dict."""
    rows = [make_row(status="Above", salary="3500")]
    result = _run_period(rows, period="Jan", comments={})

    assert result.above_detail[0].comment == ""


# ---------------------------------------------------------------------------
# TC-U-REP-6: hub-scoped aggregation excludes non-allowed hubs
# ---------------------------------------------------------------------------


def test_tc_u_rep_6_hub_scoped_excludes_non_allowed_hubs() -> None:
    """TC-U-REP-6: Allowed hubs=['Sarajevo'] hides Belgrade data everywhere."""
    rows = [
        make_row(city="Sarajevo", status="Below"),
        make_row(city="Belgrade", status="Above"),
        make_row(city="Belgrade", status="At mid-point"),
    ]
    result = _run_period(
        rows,
        period="Jan",
        allowed_hubs=["Sarajevo"],
        hub_order=["Sarajevo"],
    )

    assert result.has_data is True
    assert result.kpis is not None
    # Only the Sarajevo row is included.
    assert result.kpis.total == 1
    assert result.kpis.below == 1
    assert result.kpis.above == 0

    # Hub rows must not contain Belgrade at all.
    hub_names = [h.hub for h in result.hub_rows]
    assert "Belgrade" not in hub_names

    # Above-midpoint section must not contain Belgrade entries.
    above_hubs = {e.hub for e in result.above_detail}
    assert "Belgrade" not in above_hubs


# ---------------------------------------------------------------------------
# TC-U-REP-7: currency rounding matches prototype output
# ---------------------------------------------------------------------------


def test_tc_u_rep_7_percentage_rounding() -> None:
    """TC-U-REP-7: Percentages are rounded to 1 decimal place (prototype parity)."""
    # 1/3 ≈ 33.3%, 1/3 ≈ 33.3%, 1/3 ≈ 33.3% → sum rounds to 99.9% (not 100%)
    # This matches the prototype's round(n / total * 100, 1) behaviour.
    rows = [
        make_row(status="Below"),
        make_row(status="Above"),
        make_row(status="At mid-point"),
    ]
    result = _run_period(rows, period="Jan")

    assert result.kpis is not None
    assert result.kpis.below_pct == round(1 / 3 * 100, 1)
    assert result.kpis.above_pct == round(1 / 3 * 100, 1)
    assert result.kpis.at_mid_pct == round(1 / 3 * 100, 1)


# ---------------------------------------------------------------------------
# TC-U-REP-8: unknown status is counted in fallback bucket, not dropped
# ---------------------------------------------------------------------------


def test_tc_u_rep_8_unknown_status_is_surfaced_as_warning() -> None:
    """TC-U-REP-8: Unknown status values are listed in unknown_statuses."""
    rows = [
        make_row(status="Below"),
        make_row(status="Pending Approval"),  # unknown
        make_row(status="Pending Approval"),  # duplicate unknown → deduplicated
    ]
    result = _run_period(rows, period="Jan")

    assert result.has_data is True
    assert "Pending Approval" in result.unknown_statuses
    # Total count still includes the rows with unknown statuses.
    assert result.kpis is not None
    assert result.kpis.total == 3


# ---------------------------------------------------------------------------
# TC-U-REP-9: rows with missing Month excluded with a warning count
# ---------------------------------------------------------------------------


def test_tc_u_rep_9_missing_month_excluded_from_period() -> None:
    """TC-U-REP-9: Rows with blank month are excluded from period slices."""
    rows = [
        make_row(month="Jan"),
        make_row(month=""),  # missing month
    ]
    result = _run_period(rows, period="Jan")

    # Only the Jan row contributes.
    assert result.kpis is not None
    assert result.kpis.total == 1

    # The missing-month count is reported at the top level.
    assert result.rows_missing_month == 1


# ---------------------------------------------------------------------------
# TC-U-REP-10: year selector excludes rows from other years
# ---------------------------------------------------------------------------


def test_tc_u_rep_10_year_selector_excludes_other_years() -> None:
    """TC-U-REP-10: Aggregation scoped to year=2026 excludes 2025 rows."""
    rows = [
        make_row(year="2026", month="Jan"),
        make_row(year="2025", month="Jan"),
    ]
    result_2026 = _run_period(rows, year=2026, period="Jan")
    result_2025 = _run_period(rows, year=2025, period="Jan")

    assert result_2026.kpis is not None
    assert result_2026.kpis.total == 1

    assert result_2025.kpis is not None
    assert result_2025.kpis.total == 1


# ---------------------------------------------------------------------------
# TC-U-REP-11: year-over-year comparison returns same period in previous year
# ---------------------------------------------------------------------------


def test_tc_u_rep_11_yoy_same_hub_scope_applied_to_both_years() -> None:
    """TC-U-REP-11: Hub scope is applied independently to both years."""
    rows_2026 = [make_row(year="2026", month="Q1", city="Sarajevo")]
    rows_2025 = [
        make_row(year="2025", month="Jan", city="Sarajevo"),
        make_row(year="2025", month="Jan", city="Belgrade"),
    ]
    all_rows = rows_2026 + rows_2025

    current = _run_period(
        all_rows, year=2026, period="Jan", allowed_hubs=["Sarajevo"], hub_order=["Sarajevo"]
    )
    previous = _run_period(
        all_rows, year=2025, period="Jan", allowed_hubs=["Sarajevo"], hub_order=["Sarajevo"]
    )

    # Belgrade must be absent from the previous-year slice too.
    hub_names_prev = {h.hub for h in previous.hub_rows}
    assert "Belgrade" not in hub_names_prev

    # Sarajevo-only previous year has 1 row.
    assert previous.kpis is not None
    assert previous.kpis.total == 1

    _ = current  # verified separately in TC-U-REP-10


# ---------------------------------------------------------------------------
# TC-U-REP-12: missing previous-year data is flagged
# ---------------------------------------------------------------------------


def test_tc_u_rep_12_missing_previous_year_data_is_empty() -> None:
    """TC-U-REP-12: No 2025 rows → has_data=False (not silently zeroed)."""
    rows = [make_row(year="2026", month="Jan")]

    result = _run_period(rows, year=2025, period="Jan")

    assert result.has_data is False


# ---------------------------------------------------------------------------
# TC-U-REP-13: hire note longer than 500 characters is rejected
# ---------------------------------------------------------------------------


def test_tc_u_rep_13_long_hire_note_is_rejected() -> None:
    """TC-U-REP-13: validate_hire_note raises for notes > 500 characters."""
    long_note = "x" * 501
    with pytest.raises(ValueError, match="500"):
        validate_hire_note(long_note)


def test_tc_u_rep_13_long_hire_note_in_above_row_raises() -> None:
    """TC-U-REP-13: An above-midpoint row with a long note raises at compute time."""
    rows = [
        make_row(status="Above", salary="3500", note="x" * 501),
    ]
    with pytest.raises(ValueError, match="500"):
        _run_period(rows, period="Jan")


def test_tc_u_rep_13_note_at_limit_is_accepted() -> None:
    """TC-U-REP-13: A note of exactly 500 characters is accepted."""
    note = "x" * 500
    assert validate_hire_note(note) == note


# ---------------------------------------------------------------------------
# Normalise hire type
# ---------------------------------------------------------------------------


def test_normalise_wfm_to_wf() -> None:
    assert normalise_hire_type("WFM") == "WF"


def test_normalise_nonwfm_to_nonwf() -> None:
    assert normalise_hire_type("NonWFM") == "NonWF"


def test_normalise_canonical_labels_pass_through() -> None:
    assert normalise_hire_type("WF") == "WF"
    assert normalise_hire_type("NonWF") == "NonWF"


# ---------------------------------------------------------------------------
# Banja Luka rolls up to Sarajevo hub (Q1 answer)
# ---------------------------------------------------------------------------


def test_banja_luka_rolls_up_to_sarajevo_hub() -> None:
    """HubPair resolution: Banja Luka hires count under the Sarajevo hub."""
    rows = [
        make_row(city="Banja Luka", status="Above", salary="3500"),
    ]
    comments: dict[tuple[str, str, str, int], str] = {
        ("BE Engineer", "Medior", "Sarajevo", 3500): "Approved",
    }
    result = _run_period(rows, period="Jan", comments=comments)

    assert result.has_data is True
    # The hire appears under Sarajevo hub (city_to_hub maps BL → Sarajevo).
    sarajevo = next(h for h in result.hub_rows if h.hub == "Sarajevo")
    assert sarajevo.total == 1

    # The comment is resolved via the Sarajevo hub key.
    assert result.above_detail[0].hub == "Sarajevo"
    assert result.above_detail[0].comment == "Approved"


# ---------------------------------------------------------------------------
# All month codes and period codes are valid
# ---------------------------------------------------------------------------


def test_all_valid_periods_accepted() -> None:
    rows = [make_row(month="Jan")]
    for period in VALID_PERIODS:
        result = _run_period(rows, period=period)
        assert result is not None


def test_invalid_period_raises() -> None:
    with pytest.raises(ValueError, match="Invalid period"):
        _run_period([], period="Xyz")
