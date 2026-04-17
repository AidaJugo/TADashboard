"""Unit tests for column mapping validation.

Covers TC-U-MAP-1 through TC-U-MAP-5 from docs/testing.md.
All tests are pure-Python (no network, no DB).
"""

from __future__ import annotations

import pytest

from app.sheets.column_mapping import ColumnMappingError, validate_column_mapping
from app.sheets.models import REQUIRED_LOGICAL_COLUMNS
from tests.fixtures.sheets_fixtures import VALID_MAPPING

# ---------------------------------------------------------------------------
# TC-U-MAP-4: valid mapping succeeds
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fr_config_2_valid_mapping_succeeds() -> None:
    """TC-U-MAP-4: A mapping with all required columns is accepted."""
    config = validate_column_mapping(VALID_MAPPING)

    assert set(config.mapping.keys()) >= REQUIRED_LOGICAL_COLUMNS


# ---------------------------------------------------------------------------
# TC-U-MAP-1: missing required column is rejected
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fr_config_2_missing_required_column_rejected() -> None:
    """TC-U-MAP-1: A mapping missing a required column is rejected, naming the column."""
    incomplete = {k: v for k, v in VALID_MAPPING.items() if k != "Salary"}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(incomplete)

    assert "Salary" in str(exc_info.value)
    assert "Salary" in exc_info.value.missing


@pytest.mark.unit
def test_fr_config_2_multiple_missing_columns_all_named() -> None:
    """TC-U-MAP-1: All missing columns are named in the error, not just the first."""
    incomplete = {k: v for k, v in VALID_MAPPING.items() if k not in {"Salary", "Midpoint"}}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(incomplete)

    error_msg = str(exc_info.value)
    assert "Salary" in error_msg
    assert "Midpoint" in error_msg
    assert set(exc_info.value.missing) >= {"Salary", "Midpoint"}


# ---------------------------------------------------------------------------
# TC-U-MAP-5: Year, Recruiter, Note are required
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fr_config_2_missing_year_is_rejected() -> None:
    """TC-U-MAP-5: Year is a required logical column per FR-CONFIG-2."""
    without_year = {k: v for k, v in VALID_MAPPING.items() if k != "Year"}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(without_year)

    assert "Year" in exc_info.value.missing


@pytest.mark.unit
def test_fr_config_2_missing_recruiter_is_rejected() -> None:
    """TC-U-MAP-5: Recruiter is a required logical column per FR-CONFIG-2."""
    without = {k: v for k, v in VALID_MAPPING.items() if k != "Recruiter"}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(without)

    assert "Recruiter" in exc_info.value.missing


@pytest.mark.unit
def test_fr_config_2_missing_note_is_rejected() -> None:
    """TC-U-MAP-5: Note is a required logical column per FR-CONFIG-2."""
    without = {k: v for k, v in VALID_MAPPING.items() if k != "Note"}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(without)

    assert "Note" in exc_info.value.missing


# ---------------------------------------------------------------------------
# TC-U-MAP-2: duplicate source column is rejected
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fr_config_2_duplicate_source_column_rejected() -> None:
    """TC-U-MAP-2: Two logical columns pointing at the same source header is rejected."""
    dup_mapping = {**VALID_MAPPING, "Gap_EUR": VALID_MAPPING["Salary"]}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(dup_mapping)

    assert exc_info.value.duplicates


@pytest.mark.unit
def test_fr_config_2_duplicate_error_names_the_source_column() -> None:
    """TC-U-MAP-2: The error message names the duplicated source column."""
    dup_mapping = {**VALID_MAPPING, "Gap_EUR": VALID_MAPPING["Salary"]}

    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping(dup_mapping)

    assert VALID_MAPPING["Salary"] in str(exc_info.value)


# ---------------------------------------------------------------------------
# TC-U-MAP-3: extra columns in the Sheet are ignored
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fr_config_2_extra_sheet_columns_ignored() -> None:
    """TC-U-MAP-3: A mapping with extra (unknown) keys beyond required set is accepted."""
    extended = {**VALID_MAPPING, "ExtraLogical": "SomeBonusColumn"}

    config = validate_column_mapping(extended)

    assert set(config.mapping.keys()) >= REQUIRED_LOGICAL_COLUMNS
    assert "ExtraLogical" in config.mapping


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_mapping_raises_with_all_required_columns() -> None:
    """All required columns are listed when the mapping is entirely empty."""
    with pytest.raises(ColumnMappingError) as exc_info:
        validate_column_mapping({})

    assert set(exc_info.value.missing) == REQUIRED_LOGICAL_COLUMNS


@pytest.mark.unit
def test_column_mapping_error_is_value_error_subclass() -> None:
    """ColumnMappingError must be a ValueError for consistent API error handling."""
    assert issubclass(ColumnMappingError, ValueError)
