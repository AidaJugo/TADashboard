"""Synthetic Sheet fixture data for tests.

All names, salaries, and identifiers are entirely made up.
Never use real employee data in fixtures (AGENTS.md).
"""

from __future__ import annotations

from datetime import UTC, datetime

#: Minimal valid column mapping matching the prototype's default Sheet layout.
VALID_MAPPING: dict[str, str] = {
    "Position": "Position",
    "Seniority": "Seniority",
    "City": "City",
    "Salary": "Salary",
    "Midpoint": "Midpoint",
    "Gap_EUR": "Gap_EUR",
    "Gap_PCT": "Gap_PCT",
    "Status": "Status",
    "Month": "Month",
    "Year": "Year",
    "Type": "Type",
    "Recruiter": "Recruiter",
    "Note": "Note",
}

#: Sheet with all required headers present plus a bonus extra column.
FIXTURE_HEADERS: list[str] = [
    "Position",
    "Seniority",
    "City",
    "Salary",
    "Midpoint",
    "Gap_EUR",
    "Gap_PCT",
    "Status",
    "Month",
    "Year",
    "Type",
    "Recruiter",
    "Note",
    "ExtraColumn",  # must be silently ignored (TC-U-MAP-3)
]

#: Three synthetic rows covering different statuses.
FIXTURE_ROWS: list[list[str]] = [
    # Position, Seniority, City, Salary, Midpoint, Gap_EUR, Gap_PCT, Status,
    # Month, Year, Type, Recruiter, Note, ExtraColumn
    [
        "Software Engineer",
        "Mid",
        "Sarajevo",
        "3000",
        "3000",
        "0",
        "0%",
        "At mid-point",
        "Jan",
        "2026",
        "WF",
        "Jane Smith",
        "",
        "ignored",
    ],
    [
        "Product Designer",
        "Senior",
        "Belgrade",
        "4500",
        "4000",
        "500",
        "12.5%",
        "Above",
        "Jan",
        "2026",
        "NonWF",
        "Alex Jones",
        "Strong candidate",
        "ignored",
    ],
    [
        "Data Analyst",
        "Junior",
        "Skopje",
        "2200",
        "2500",
        "-300",
        "-12%",
        "Below",
        "Feb",
        "2026",
        "WF",
        "Sam Lee",
        "",
        "ignored",
    ],
]

#: Sheet that contains ALL required headers — used for TC-I-SH-1 (happy path).
FIXTURE_ALL_VALUES: list[list[str]] = [FIXTURE_HEADERS, *FIXTURE_ROWS]

#: Sheet missing the "Year" column — used for TC-I-SH-2 / TC-U-MAP-5.
MISSING_YEAR_HEADERS: list[str] = [h for h in FIXTURE_HEADERS if h != "Year"]
FIXTURE_MISSING_YEAR: list[list[str]] = [
    MISSING_YEAR_HEADERS,
    *[row[:9] + row[10:] for row in FIXTURE_ROWS],
]

#: Completely empty Sheet (no rows at all).
FIXTURE_EMPTY: list[list[str]] = []

#: Sentinel fetch timestamp for stable assertions.
FIXED_FETCHED_AT: datetime = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
