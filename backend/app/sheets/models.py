"""Pydantic models for the Sheets layer.

These types flow from the raw Google Sheet rows through the column mapping
validator into the report aggregation layer.  No DB models are imported
here — this module must stay dependency-free of SQLAlchemy so the unit tests
can run without a Postgres connection.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves field types at runtime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

#: Fixed set of logical column names the app understands (FR-CONFIG-2).
REQUIRED_LOGICAL_COLUMNS: frozenset[str] = frozenset(
    {
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
    }
)


class ColumnMappingConfig(BaseModel):
    """Admin-supplied mapping from logical column names to Sheet column headers.

    Keys are the fixed logical names (REQUIRED_LOGICAL_COLUMNS).
    Values are the actual header strings in the Google Sheet.
    Extra keys beyond the required set are ignored (TC-U-MAP-3 inverse).
    """

    model_config = ConfigDict(frozen=True)

    mapping: dict[str, str] = Field(
        description="logical_name → source_column_header",
    )

    @field_validator("mapping")
    @classmethod
    def validate_mapping(cls, v: dict[str, str]) -> dict[str, str]:
        missing = REQUIRED_LOGICAL_COLUMNS - v.keys()
        if missing:
            sorted_missing = sorted(missing)
            raise ValueError(
                f"Column mapping is missing required logical columns: {', '.join(sorted_missing)}"
            )
        duplicates = [col for col, source in v.items() if list(v.values()).count(source) > 1]
        if duplicates:
            seen_sources = set()
            dup_sources = []
            for col in REQUIRED_LOGICAL_COLUMNS:
                src = v.get(col, "")
                if src in seen_sources:
                    dup_sources.append(src)
                seen_sources.add(src)
            if dup_sources:
                raise ValueError(
                    f"Duplicate source column(s) in mapping: {', '.join(sorted(set(dup_sources)))}"
                )
        return v


# ---------------------------------------------------------------------------
# Raw hiring row (after column mapping is applied)
# ---------------------------------------------------------------------------


class HireRow(BaseModel):
    """One row from the Sheet after header normalisation.

    Fields use the logical column names. All values are strings as read
    from the Sheet; numeric coercion happens in the aggregation layer.
    Missing optional fields default to None.
    """

    model_config = ConfigDict(frozen=True)

    position: str = ""
    seniority: str = ""
    city: str = ""
    salary: str = ""
    midpoint: str = ""
    gap_eur: str = ""
    gap_pct: str = ""
    status: str = ""
    month: str = ""
    year: str = ""
    hire_type: str = ""
    recruiter: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Sheet fetch result
# ---------------------------------------------------------------------------


class SheetFetchResult(BaseModel):
    """The outcome of a single Sheet fetch attempt.

    ``rows``  — the parsed rows (may be empty if the Sheet is empty).
    ``stale`` — True when this data came from the last-known-good snapshot
                rather than a live fetch.
    ``fetched_at`` — when the data was originally fetched from Google.
    ``column_hash`` — SHA-256 of sorted column headers at fetch time,
                      used to detect schema drift between calls.
    ``schema_error`` — set when a required column was missing from the Sheet.
    """

    model_config = ConfigDict(frozen=True)

    rows: list[HireRow]
    stale: bool = False
    fetched_at: datetime
    column_hash: str | None = None
    schema_error: str | None = None
