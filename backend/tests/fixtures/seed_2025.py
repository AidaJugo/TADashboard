"""Synthetic 2025 Sheet fixture data for year-over-year (YoY) tests.

These fixtures enable TC-E-9, TC-E-10, TC-U-REP-10, TC-U-REP-11, and
TC-I-API-8 / TC-I-API-9 without touching the live Google Sheet.

All names, salaries, and identifiers are entirely made up.
Never use real employee data in fixtures (AGENTS.md).

Usage in tests
--------------
Inject alongside the standard FIXTURE_ROWS_2026 (from sheets_fixtures.py)
to simulate a two-year Sheet.  Tests can then call the report API with
``year=2025`` or ``compare_previous=true`` to exercise the YoY path.

Example::

    from tests.fixtures.sheets_fixtures import FIXTURE_HEADERS
    from tests.fixtures.seed_2025 import FIXTURE_ROWS_2025, ALL_2025_ROWS

    # Build a fake Sheet with both years present.
    all_rows = [FIXTURE_HEADERS, *FIXTURE_ROWS_2025, *FIXTURE_ROWS_2026]
"""

from __future__ import annotations

from app.sheets.models import HireRow

# ---------------------------------------------------------------------------
# Synthetic 2025 HireRow objects
#
# Deliberately different from the 2026 rows so year-switch assertions have
# unambiguous fingerprints (e.g. 2025 total=7, 2026 total=3 in the default
# fixture set).
# ---------------------------------------------------------------------------

FIXTURE_ROWS_2025: list[HireRow] = [
    HireRow(
        position="Software Engineer",
        seniority="Junior",
        city="Sarajevo",
        salary="2700",
        midpoint="2700",
        gap_eur="0",
        gap_pct="0",
        status="At mid-point",
        month="3",
        year="2025",
        hire_type="WF",
        recruiter="Robin Taylor",
        note="",
    ),
    HireRow(
        position="Software Engineer",
        seniority="Mid",
        city="Sarajevo",
        salary="3100",
        midpoint="3000",
        gap_eur="100",
        gap_pct="0.033",
        status="Above",
        month="4",
        year="2025",
        hire_type="WF",
        recruiter="Robin Taylor",
        note="Band applied.",
    ),
    HireRow(
        position="Data Analyst",
        seniority="Mid",
        city="Sarajevo",
        salary="2800",
        midpoint="2900",
        gap_eur="-100",
        gap_pct="-0.034",
        status="Below",
        month="5",
        year="2025",
        hire_type="NonWF",
        recruiter="Morgan Lee",
        note="",
    ),
    HireRow(
        position="Product Designer",
        seniority="Senior",
        city="Belgrade",
        salary="4200",
        midpoint="4200",
        gap_eur="0",
        gap_pct="0",
        status="At mid-point",
        month="3",
        year="2025",
        hire_type="WF",
        recruiter="Alex Jones",
        note="",
    ),
    HireRow(
        position="Product Manager",
        seniority="Mid",
        city="Belgrade",
        salary="4800",
        midpoint="4600",
        gap_eur="200",
        gap_pct="0.043",
        status="Above",
        month="6",
        year="2025",
        hire_type="WF",
        recruiter="Alex Jones",
        note="Approved by VP.",
    ),
    HireRow(
        position="QA Engineer",
        seniority="Junior",
        city="Skopje",
        salary="2100",
        midpoint="2100",
        gap_eur="0",
        gap_pct="0",
        status="At mid-point",
        month="4",
        year="2025",
        hire_type="WF",
        recruiter="Sam Lee",
        note="",
    ),
    HireRow(
        position="DevOps Engineer",
        seniority="Senior",
        city="Medellin",
        salary="5200",
        midpoint="5200",
        gap_eur="0",
        gap_pct="0",
        status="At mid-point",
        month="7",
        year="2025",
        hire_type="WF",
        recruiter="Jordan Rivera",
        note="",
    ),
]

# ---------------------------------------------------------------------------
# Pre-built SheetFetchResult for tests that need a ready-made fetch object.
# ---------------------------------------------------------------------------


def make_2025_fetch_result():
    """Return a SheetFetchResult containing only 2025 rows."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from app.sheets.models import SheetFetchResult  # noqa: PLC0415

    return SheetFetchResult(
        rows=FIXTURE_ROWS_2025,
        stale=False,
        fetched_at=datetime(2025, 12, 31, 12, 0, 0, tzinfo=UTC),
    )
