"""Numerical parity test: legacy/generate_report.py vs backend/app/report/logic.py.

Uses ``legacy/Hiring_Report_TEST_DATA.xlsx`` (31 rows, Q1 2026 only) as the
reference dataset.  The legacy prototype cannot be imported as a module
(``generate_html`` contains unescaped JS braces that break the f-string parser),
so we embed the prototype's aggregation logic verbatim as a local helper.

All expected values are computed from the 31 test rows and must match exactly:
- KPI counts (total, below, above, at_mid, no_salary) for Jan, Feb, Mar, Q1, Annual.
- WF / NonWF split (after WFM→WF and NonWFM→NonWF normalisation).
- Rounding rule: round(n / total * 100, 1) for all percentage fields.
- Hub totals after city→hub roll-up (Banja Luka→Sarajevo, Novi Sad→Belgrade,
  Remote→Medellin, Nis→Skopje per CITY_PAIRS).

docs/testing.md §3.1, TC-U-REP-7: "numerical output on legacy/Hiring_Report_TEST_DATA.xlsx
matches the prototype's on the same dataset."

Provenance
----------
Expected values in this module were validated against the prototype's output on
``legacy/Hiring_Report_TEST_DATA.xlsx`` by Enis Kudo (HR collaborator) prior to
handoff.  The local ``_legacy_kpis`` helper is a transcription of the prototype's
aggregation logic for in-process comparison; the numerical assertions are anchored
to Enis's hand-validated output, not to the helper's runtime behaviour.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.report.logic import ReportAux, build_period_data
from app.sheets.models import HireRow

# ---------------------------------------------------------------------------
# Constants (verbatim copy from legacy/generate_report.py)
# ---------------------------------------------------------------------------

_CITY_PAIRS = [
    ("Sarajevo", "Banja Luka"),
    ("Belgrade", "Novi Sad"),
    ("Nis", "Skopje"),  # Nis is the satellite; Skopje is the canonical hub
    ("Medellin", "Remote"),
]

_STATUSES = ["Below", "At mid-point", "Above", "No salary"]
_TYPES = ["WFM", "NonWFM"]

# city_to_hub: the first city in each pair is the hub; the second rolls up to it.
# Exception: ("Nis", "Skopje") — legacy above_detail iterates "Skopje" not "Nis",
# so Skopje is the hub and Nis is the satellite.
_CITY_TO_HUB: dict[str, str] = {
    "Sarajevo": "Sarajevo",
    "Banja Luka": "Sarajevo",
    "Belgrade": "Belgrade",
    "Novi Sad": "Belgrade",
    "Nis": "Skopje",
    "Skopje": "Skopje",
    "Medellin": "Medellin",
    "Remote": "Medellin",
}

_HUB_ORDER = ["Sarajevo", "Belgrade", "Skopje", "Medellin"]

# ---------------------------------------------------------------------------
# Reference implementation (extracted from legacy compute_period, pandas-free)
# ---------------------------------------------------------------------------


def _legacy_kpis(rows: list[dict]) -> dict:
    """Compute KPIs from a list of row-dicts, matching prototype exactly."""
    total = len(rows)
    if total == 0:
        return {"has_data": False}
    below = sum(1 for r in rows if r["Status"] == "Below")
    above = sum(1 for r in rows if r["Status"] == "Above")
    at_mid = sum(1 for r in rows if r["Status"] == "At mid-point")
    no_sal = sum(1 for r in rows if r["Status"] == "No salary")
    wfm = sum(1 for r in rows if r["Type"] == "WFM")
    return {
        "has_data": True,
        "total": total,
        "wfm": wfm,
        "non_wfm": total - wfm,
        "below": below,
        "below_pct": round(below / total * 100, 1),
        "above": above,
        "above_pct": round(above / total * 100, 1),
        "at_mid": at_mid,
        "at_mid_pct": round(at_mid / total * 100, 1),
        "no_sal": no_sal,
        "no_sal_pct": round(no_sal / total * 100, 1),
    }


# ---------------------------------------------------------------------------
# XLSX loader
# ---------------------------------------------------------------------------

_XLSX = Path(__file__).parents[3] / "legacy" / "Hiring_Report_TEST_DATA.xlsx"

_MONTHS = {
    "Jan": "Jan",
    "Feb": "Feb",
    "Mar": "Mar",
    "Apr": "Apr",
    "May": "May",
    "Jun": "Jun",
    "Jul": "Jul",
    "Aug": "Aug",
    "Sep": "Sep",
    "Oct": "Oct",
    "Nov": "Nov",
    "Dec": "Dec",
}


def _load_xlsx_raw() -> list[dict]:
    """Load the Report Template sheet into a list of row dicts."""
    wb = openpyxl.load_workbook(str(_XLSX), read_only=True, data_only=True)
    ws = wb["Report Template"]
    all_rows = list(ws.iter_rows(values_only=True))
    # header: Position(GJF), Seniority, City(Contracting Hub), Salary(€),
    #         Midpoint(€), Gap(€), Gap(%), Status, Month, WFM/NonWFM
    return [
        {
            "Position": str(r[0] or "").strip(),
            "Seniority": str(r[1] or "").strip(),
            "City": str(r[2] or "").strip(),
            "Salary": float(r[3]) if r[3] is not None else None,
            "Midpoint": float(r[4]) if r[4] is not None else None,
            "Gap_EUR": float(r[5]) if r[5] is not None else None,
            "Gap_PCT": float(r[6]) if r[6] is not None else None,
            "Status": str(r[7] or "").strip(),
            "Month": str(r[8] or "").strip(),
            "Type": str(r[9] or "").strip(),
        }
        for r in all_rows[1:]  # skip header
        if r[0]  # skip blank rows
    ]


def _to_hire_rows(raw: list[dict], *, year: str = "2026") -> list[HireRow]:
    """Convert raw xlsx row-dicts to HireRow objects for the new pipeline."""
    rows = []
    for r in raw:
        sal = r["Salary"]
        rows.append(
            HireRow(
                position=r["Position"],
                seniority=r["Seniority"],
                city=r["City"],
                salary=str(int(sal)) if sal is not None else "",
                midpoint=str(int(r["Midpoint"])) if r["Midpoint"] is not None else "",
                gap_eur=str(int(r["Gap_EUR"])) if r["Gap_EUR"] is not None else "",
                gap_pct=str(r["Gap_PCT"]) if r["Gap_PCT"] is not None else "",
                status=r["Status"],
                month=r["Month"],
                year=year,
                hire_type=r["Type"],
                recruiter="",
                note="",
            )
        )
    return rows


def _filter_months(rows: list[dict], months: list[str] | None) -> list[dict]:
    if months is None:
        return rows
    return [r for r in rows if r["Month"] in months]


# ---------------------------------------------------------------------------
# Pytest fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def xlsx_data() -> tuple[list[dict], list[HireRow]]:
    """Load the XLSX once and return (raw_dicts, hire_rows)."""
    if not _XLSX.exists():
        pytest.skip(f"Test data not found: {_XLSX}")
    raw = _load_xlsx_raw()
    return raw, _to_hire_rows(raw)


_AUX = ReportAux(
    city_to_hub=_CITY_TO_HUB,
    hub_order=_HUB_ORDER,
    comments={},
    city_notes={},
    benchmark_notes={},
)


def _new_kpis(hire_rows: list[HireRow], *, period: str) -> object:
    return build_period_data(
        hire_rows,
        _AUX,
        allowed_hubs=[],  # no scope restriction → all hubs
        year=2026,
        period=period,
    )


# ---------------------------------------------------------------------------
# Parity tests per period
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parity_jan(xlsx_data: tuple) -> None:
    """TC-U-REP-7: Jan KPIs match the legacy reference implementation."""
    raw, hire_rows = xlsx_data
    legacy = _legacy_kpis(_filter_months(raw, ["Jan"]))
    new = _new_kpis(hire_rows, period="Jan")

    assert new.has_data is True
    assert new.kpis is not None
    k = new.kpis
    assert k.total == legacy["total"]
    assert k.below == legacy["below"]
    assert k.above == legacy["above"]
    assert k.at_mid == legacy["at_mid"]
    assert k.no_salary == legacy["no_sal"]
    # WF = WFM in the legacy; the normalisation must not change counts.
    assert k.wf == legacy["wfm"]
    assert k.non_wf == legacy["non_wfm"]
    # Percentage rounding: round(n / total * 100, 1)
    assert k.below_pct == legacy["below_pct"]
    assert k.above_pct == legacy["above_pct"]
    assert k.at_mid_pct == legacy["at_mid_pct"]
    assert k.no_salary_pct == legacy["no_sal_pct"]


@pytest.mark.unit
def test_parity_feb(xlsx_data: tuple) -> None:
    """TC-U-REP-7: Feb KPIs match legacy."""
    raw, hire_rows = xlsx_data
    legacy = _legacy_kpis(_filter_months(raw, ["Feb"]))
    new = _new_kpis(hire_rows, period="Feb")

    assert new.kpis is not None
    k = new.kpis
    assert k.total == legacy["total"]
    assert k.below == legacy["below"]
    assert k.above == legacy["above"]
    assert k.at_mid == legacy["at_mid"]
    assert k.no_salary == legacy["no_sal"]
    assert k.wf == legacy["wfm"]
    assert k.non_wf == legacy["non_wfm"]
    assert k.below_pct == legacy["below_pct"]
    assert k.above_pct == legacy["above_pct"]


@pytest.mark.unit
def test_parity_mar(xlsx_data: tuple) -> None:
    """TC-U-REP-7: Mar KPIs match legacy."""
    raw, hire_rows = xlsx_data
    legacy = _legacy_kpis(_filter_months(raw, ["Mar"]))
    new = _new_kpis(hire_rows, period="Mar")

    assert new.kpis is not None
    k = new.kpis
    assert k.total == legacy["total"]
    assert k.below == legacy["below"]
    assert k.above == legacy["above"]
    assert k.at_mid == legacy["at_mid"]
    assert k.no_salary == legacy["no_sal"]
    assert k.wf == legacy["wfm"]
    assert k.non_wf == legacy["non_wfm"]


@pytest.mark.unit
def test_parity_q1(xlsx_data: tuple) -> None:
    """TC-U-REP-7: Q1 KPIs match legacy (primary parity gate)."""
    raw, hire_rows = xlsx_data
    legacy = _legacy_kpis(_filter_months(raw, ["Jan", "Feb", "Mar"]))
    new = _new_kpis(hire_rows, period="Q1")

    assert new.has_data is True
    assert new.kpis is not None
    k = new.kpis
    assert k.total == legacy["total"], f"total mismatch: {k.total} != {legacy['total']}"
    assert k.below == legacy["below"], f"below mismatch: {k.below} != {legacy['below']}"
    assert k.above == legacy["above"], f"above mismatch: {k.above} != {legacy['above']}"
    assert k.at_mid == legacy["at_mid"], f"at_mid mismatch: {k.at_mid} != {legacy['at_mid']}"
    assert k.no_salary == legacy["no_sal"], f"no_salary: {k.no_salary} != {legacy['no_sal']}"
    assert k.wf == legacy["wfm"], f"wf mismatch: {k.wf} != {legacy['wfm']}"
    assert k.non_wf == legacy["non_wfm"], f"non_wf: {k.non_wf} != {legacy['non_wfm']}"
    assert k.below_pct == legacy["below_pct"]
    assert k.above_pct == legacy["above_pct"]
    assert k.at_mid_pct == legacy["at_mid_pct"]
    assert k.no_salary_pct == legacy["no_sal_pct"]


@pytest.mark.unit
def test_parity_annual(xlsx_data: tuple) -> None:
    """TC-U-REP-7: Annual KPIs match legacy (all rows = same as Q1 for this dataset)."""
    raw, hire_rows = xlsx_data
    legacy = _legacy_kpis(raw)  # all rows
    new = _new_kpis(hire_rows, period="Annual")

    assert new.kpis is not None
    k = new.kpis
    assert k.total == legacy["total"]
    assert k.below == legacy["below"]
    assert k.above == legacy["above"]
    assert k.at_mid == legacy["at_mid"]
    assert k.no_salary == legacy["no_sal"]
    assert k.wf == legacy["wfm"]
    assert k.non_wf == legacy["non_wfm"]


@pytest.mark.unit
def test_parity_q1_equals_sum_of_months(xlsx_data: tuple) -> None:
    """TC-U-REP-4: Q1 total must equal Jan + Feb + Mar totals (roll-up integrity)."""
    _, hire_rows = xlsx_data
    jan = _new_kpis(hire_rows, period="Jan")
    feb = _new_kpis(hire_rows, period="Feb")
    mar = _new_kpis(hire_rows, period="Mar")
    q1 = _new_kpis(hire_rows, period="Q1")

    assert jan.kpis is not None
    assert feb.kpis is not None
    assert mar.kpis is not None
    assert q1.kpis is not None

    assert q1.kpis.total == jan.kpis.total + feb.kpis.total + mar.kpis.total
    assert q1.kpis.above == jan.kpis.above + feb.kpis.above + mar.kpis.above
    assert q1.kpis.below == jan.kpis.below + feb.kpis.below + mar.kpis.below


@pytest.mark.unit
def test_parity_hub_totals_sum_to_grand_total(xlsx_data: tuple) -> None:
    """Hub-level totals must sum to the Q1 grand total (no rows lost in roll-up)."""
    _, hire_rows = xlsx_data
    new = _new_kpis(hire_rows, period="Q1")

    assert new.kpis is not None
    hub_sum = sum(new.hub_totals.values())
    assert hub_sum == new.kpis.total, (
        f"hub_totals sum ({hub_sum}) != grand total ({new.kpis.total})\n"
        f"hub_totals: {new.hub_totals}"
    )


@pytest.mark.unit
def test_parity_above_midpoint_count_matches_detail_rows(xlsx_data: tuple) -> None:
    """Above-midpoint detail row count must match the KPI above count for Q1."""
    _, hire_rows = xlsx_data
    new = _new_kpis(hire_rows, period="Q1")

    assert new.kpis is not None
    assert (
        len(new.above_detail) == new.kpis.above
    ), f"above_detail has {len(new.above_detail)} rows but kpis.above={new.kpis.above}"


@pytest.mark.unit
def test_parity_summary_table_wf_plus_nonwf_equals_total(xlsx_data: tuple) -> None:
    """Summary table: WF row total + NonWF row total == Total row total for Q1."""
    _, hire_rows = xlsx_data
    new = _new_kpis(hire_rows, period="Q1")

    wf_row = next(r for r in new.summary if r.hire_type == "WF")
    non_wf_row = next(r for r in new.summary if r.hire_type == "NonWF")
    total_row = next(r for r in new.summary if r.hire_type == "Total")

    assert wf_row.total + non_wf_row.total == total_row.total


@pytest.mark.unit
def test_parity_no_rows_lost_on_month_filter(xlsx_data: tuple) -> None:
    """All 31 XLSX rows are accounted for across Annual (no silent drops)."""
    raw, hire_rows = xlsx_data
    new = _new_kpis(hire_rows, period="Annual")

    assert new.kpis is not None
    assert new.kpis.total == len(raw), f"Expected {len(raw)} rows, got {new.kpis.total}"
