"""Pydantic models for the report API response (FR-REPORT-4, FR-REPORT-9).

These types are the contract between the backend aggregation layer and the
frontend.  Every field is annotated; no ``Any`` allowed.

Naming follows the PRD glossary:
  - WF / NonWF  (not WFM / NonWFM — those are raw Sheet values)
  - period      accepts Jan..Dec | Q1..Q4 | H1 | H2 | Annual
  - hub         canonical hub name after HubPair resolution
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves at runtime

from pydantic import BaseModel, ConfigDict, Field


class StatusCounts(BaseModel):
    """Hire counts broken down by benchmark status."""

    model_config = ConfigDict(frozen=True)

    below: int = 0
    at_mid: int = 0
    above: int = 0
    no_salary: int = 0
    total: int = 0


class TypeSummaryRow(BaseModel):
    """One row of the WF / NonWF / Total summary table."""

    model_config = ConfigDict(frozen=True)

    hire_type: str  # "WF", "NonWF", or "Total"
    below: int = 0
    at_mid: int = 0
    above: int = 0
    no_salary: int = 0
    total: int = 0


class HubRow(BaseModel):
    """Per-hub breakdown with WF / NonWF / Total rows."""

    model_config = ConfigDict(frozen=True)

    hub: str
    has_data: bool
    total: int = 0
    rows: list[TypeSummaryRow] = Field(default_factory=list)
    city_note: str = ""


class AboveMidpointEntry(BaseModel):
    """One above-midpoint hire row shown in the exceptions table (FR-REPORT-5)."""

    model_config = ConfigDict(frozen=True)

    position: str
    seniority: str
    hub: str
    salary: float | None
    midpoint: float | None
    gap_eur: float | None
    gap_pct: float | None
    """Salary gap as a **decimal fraction** (e.g. 0.176 = 17.6%).

    The Google Sheet stores Gap(%) as a fraction; the frontend multiplies by
    100 before rendering.  Do not change the storage unit — doing so would
    break TC-U-REP-7 (numerical parity against the XLSX test data) and cause
    the UI to display values 100× too large.
    """
    recruiter: str = ""
    comment: str = ""
    hire_note: str = ""


class KpiBlock(BaseModel):
    """Top-level KPI card values for a period."""

    model_config = ConfigDict(frozen=True)

    total: int
    wf: int
    non_wf: int
    below: int
    below_pct: float
    above: int
    above_pct: float
    at_mid: int
    at_mid_pct: float
    no_salary: int
    no_salary_pct: float


class PeriodData(BaseModel):
    """Aggregated data for a single period (month, quarter, half-year, or annual).

    ``has_data=False`` means no hires exist for this period in the selected
    year; the frontend renders an empty state (FR-REPORT-6).
    """

    model_config = ConfigDict(frozen=True)

    has_data: bool
    kpis: KpiBlock | None = None
    summary: list[TypeSummaryRow] = Field(default_factory=list)
    hub_rows: list[HubRow] = Field(default_factory=list)
    above_detail: list[AboveMidpointEntry] = Field(default_factory=list)
    hub_totals: dict[str, int] = Field(default_factory=dict)
    benchmark_note: str = ""
    unknown_statuses: list[str] = Field(
        default_factory=list,
        description="Status values not in the known set; surfaced as a warning (TC-U-REP-8).",
    )
    rows_missing_month: int = Field(
        default=0,
        description="Count of rows excluded because Month was blank (TC-U-REP-9).",
    )


class ReportResponse(BaseModel):
    """Full API response for GET /api/report."""

    model_config = ConfigDict(frozen=True)

    year: int
    period: str
    stale: bool = False
    fetched_at: datetime
    data: PeriodData

    # Year-over-year fields (FR-REPORT-9).  Populated only when
    # compare_previous=true is requested.
    previous_year: int | None = None
    previous_year_data: PeriodData | None = None
    previous_year_missing: bool = False
