"""Column mapping validation for the Sheets layer.

Validates that the admin-supplied column mapping covers all required logical
columns (FR-CONFIG-2) and translates raw Sheet headers to the canonical names
the rest of the app uses.

All functions here are pure (no I/O, no DB) so they are fast to unit-test.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.sheets.models import (
    REQUIRED_LOGICAL_COLUMNS,
    ColumnMappingConfig,
    HireRow,
)


class ColumnMappingError(ValueError):
    """Raised when the admin-supplied column mapping is invalid.

    ``missing`` — logical column names that have no mapping entry.
    ``duplicates`` — source column headers mapped to more than one logical name.
    ``message`` — human-readable description of the problem (FR-CONFIG-5).
    """

    def __init__(
        self,
        message: str,
        missing: list[str] | None = None,
        duplicates: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.missing = missing or []
        self.duplicates = duplicates or []


def validate_column_mapping(raw_mapping: dict[str, str]) -> ColumnMappingConfig:
    """Validate and return a ColumnMappingConfig.

    Raises ColumnMappingError if:
    - Any required logical column is absent (TC-U-MAP-1, TC-U-MAP-5).
    - Any source column is mapped twice (TC-U-MAP-2).

    Extra logical keys beyond the required set are silently accepted (TC-U-MAP-3).
    A mapping containing all required fields succeeds (TC-U-MAP-4).
    """
    missing = sorted(REQUIRED_LOGICAL_COLUMNS - raw_mapping.keys())
    if missing:
        raise ColumnMappingError(
            f"Column mapping is missing required columns: {', '.join(missing)}",
            missing=missing,
        )

    source_to_logical: dict[str, list[str]] = {}
    for logical, source in raw_mapping.items():
        source_to_logical.setdefault(source, []).append(logical)

    dup_sources = sorted(src for src, logicals in source_to_logical.items() if len(logicals) > 1)
    if dup_sources:
        raise ColumnMappingError(
            f"Source column(s) mapped more than once: {', '.join(dup_sources)}",
            duplicates=dup_sources,
        )

    try:
        return ColumnMappingConfig(mapping=raw_mapping)
    except ValidationError as exc:
        raise ColumnMappingError(str(exc)) from exc


def apply_mapping(headers: list[str], raw_mapping: dict[str, str]) -> dict[str, str]:
    """Return a dict of logical_name → column_index_or_header for use by the parser.

    Validates the mapping first. Raises ColumnMappingError on invalid mapping.
    Unknown Sheet headers (not in the mapping values) are silently ignored (TC-U-MAP-3).
    """
    config = validate_column_mapping(raw_mapping)
    source_to_logical = {v: k for k, v in config.mapping.items()}
    return {source_to_logical[h]: h for h in headers if h in source_to_logical}


def map_row(
    raw_row: dict[str, str],
    mapping: dict[str, str],
) -> HireRow:
    """Convert a raw {header: value} row dict to a HireRow using the given mapping.

    ``mapping`` should be the dict returned by ``validate_column_mapping(...).mapping``.
    Missing cells default to empty string.
    """
    source_to_logical = {v: k for k, v in mapping.items()}
    logical_row: dict[str, str] = {}
    for source_col, value in raw_row.items():
        logical = source_to_logical.get(source_col)
        if logical:
            logical_row[logical.lower().replace("_", "_")] = value

    return HireRow(
        position=logical_row.get("position", ""),
        seniority=logical_row.get("seniority", ""),
        city=logical_row.get("city", ""),
        salary=logical_row.get("salary", ""),
        midpoint=logical_row.get("midpoint", ""),
        gap_eur=logical_row.get("gap_eur", ""),
        gap_pct=logical_row.get("gap_pct", ""),
        status=logical_row.get("status", ""),
        month=logical_row.get("month", ""),
        year=logical_row.get("year", ""),
        hire_type=logical_row.get("type", ""),
        recruiter=logical_row.get("recruiter", ""),
        note=logical_row.get("note", ""),
    )
