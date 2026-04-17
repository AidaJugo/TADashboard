"""Integration tests for the Sheets client (TC-I-SH-1 through TC-I-SH-6).

These tests mock the Google Sheets API so no real credentials are needed.
They do not require a Postgres connection.

docs/testing.md §4.1:
  TC-I-SH-1: Happy path: fixture Sheet loads and parses into the canonical model.
  TC-I-SH-2: Missing required column returns a schema error (stale=True, last_good
             preserved — B2 hardening).
  TC-I-SH-3: Sheet unreachable: last-known-good snapshot is returned with stale=True.
  TC-I-SH-4: Cache hit within TTL does not call Google.
  TC-I-SH-5: Cache miss after TTL refreshes the data and updates the snapshot.
  TC-I-SH-6: Manual refresh bypasses cache, updates snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.sheets.cache import SheetCache
from app.sheets.client import SheetsClient, _parse_rows
from app.sheets.models import HireRow, SheetFetchResult
from tests.fixtures.sheets_fixtures import (
    FIXED_FETCHED_AT,
    FIXTURE_ALL_VALUES,
    FIXTURE_EMPTY,
    FIXTURE_HEADERS,
    FIXTURE_MISSING_YEAR,
    FIXTURE_ROWS,
    VALID_MAPPING,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings() -> MagicMock:
    s = MagicMock()
    s.google_service_account_json_path = "/fake/key.json"
    s.spreadsheet_id = "fake-id"
    s.spreadsheet_tab_name = "Report Template"
    s.app_env = "test"
    s.log_level = "WARNING"
    return s


def _make_client(ttl: int = 60) -> SheetsClient:
    return SheetsClient(
        column_mapping=VALID_MAPPING,
        ttl_seconds=ttl,
        settings=_make_mock_settings(),  # type: ignore[arg-type]
    )


def _mock_worksheet(all_values: list[list[str]]) -> MagicMock:
    ws = MagicMock()
    ws.get_all_values.return_value = all_values
    return ws


def _mock_spreadsheet(worksheet: MagicMock) -> MagicMock:
    ss = MagicMock()
    ss.worksheet.return_value = worksheet
    return ss


def _mock_gspread_client(spreadsheet: MagicMock) -> MagicMock:
    gc = MagicMock()
    gc.open_by_key.return_value = spreadsheet
    return gc


# ---------------------------------------------------------------------------
# TC-I-SH-1: happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_tc_i_sh_1_happy_path_parses_fixture(mock_build: MagicMock) -> None:
    """TC-I-SH-1: Fixture Sheet loads and parses into HireRow objects."""
    ws = _mock_worksheet(FIXTURE_ALL_VALUES)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    client = _make_client()
    result = await client.get_rows(db=None)

    assert result.stale is False
    assert result.schema_error is None
    assert len(result.rows) == len(FIXTURE_ROWS)
    first = result.rows[0]
    assert isinstance(first, HireRow)
    assert first.position == "Software Engineer"
    assert first.city == "Sarajevo"
    assert first.status == "At mid-point"
    assert first.recruiter == "Jane Smith"


@pytest.mark.integration
def test_tc_i_sh_1_parse_rows_ignores_extra_columns() -> None:
    """TC-I-SH-1 / TC-U-MAP-3: _parse_rows silently ignores ExtraColumn."""
    rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)

    assert len(rows) == 3
    assert all(isinstance(r, HireRow) for r in rows)


# ---------------------------------------------------------------------------
# TC-I-SH-2: missing required column
# ---------------------------------------------------------------------------


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_tc_i_sh_2_missing_required_column_returns_schema_error(
    mock_build: MagicMock,
) -> None:
    """TC-I-SH-2: Sheet missing a required column returns a schema error."""
    ws = _mock_worksheet(FIXTURE_MISSING_YEAR)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    client = _make_client()
    result = await client.get_rows(db=None)

    assert result.schema_error is not None
    assert "Year" in result.schema_error
    assert result.rows == []


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_tc_i_sh_2_schema_error_sets_stale_true(mock_build: MagicMock) -> None:
    """B2/N5: A schema-error result must have stale=True so it is never promoted
    to last_good in the cache and never persisted as the snapshot."""
    ws = _mock_worksheet(FIXTURE_MISSING_YEAR)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    client = _make_client()
    result = await client.get_rows(db=None)

    assert result.stale is True
    assert result.schema_error is not None


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_tc_i_sh_2_schema_error_does_not_overwrite_last_good(
    mock_build: MagicMock,
) -> None:
    """B2 (hardened TC-I-SH-2): a previous good result must survive a subsequent
    schema-error fetch.  last_good must remain the original good result."""
    good_rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)
    pre_existing_good = SheetFetchResult(rows=good_rows, stale=False, fetched_at=FIXED_FETCHED_AT)

    client = _make_client(ttl=0)  # ttl=0 so every call re-fetches
    client._cache._last_good = pre_existing_good  # noqa: SLF001

    ws = _mock_worksheet(FIXTURE_MISSING_YEAR)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    schema_error_result = await client.get_rows(db=None)

    assert schema_error_result.schema_error is not None
    assert schema_error_result.stale is True
    # last_good must be the original good result, not the schema-error result
    assert client._cache.last_good is pre_existing_good  # noqa: SLF001
    assert client._cache.last_good.rows == good_rows  # noqa: SLF001


# ---------------------------------------------------------------------------
# TC-I-SH-3: Sheet unreachable → stale fallback
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_tc_i_sh_3_unreachable_sheet_returns_stale_snapshot() -> None:
    """TC-I-SH-3: When Google is unreachable, last-known-good snapshot is returned."""
    good_rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)
    last_good = SheetFetchResult(rows=good_rows, stale=False, fetched_at=FIXED_FETCHED_AT)

    cache = SheetCache(ttl_seconds=0)
    cache._last_good = last_good  # noqa: SLF001

    async def _fail() -> SheetFetchResult:
        raise ConnectionError("Google Sheets unreachable")

    result = await cache.get(_fail)

    assert result.stale is True
    assert len(result.rows) == len(good_rows)
    assert result.fetched_at == FIXED_FETCHED_AT


@pytest.mark.integration
async def test_tc_i_sh_3_no_snapshot_reraises_exception() -> None:
    """TC-I-SH-3: If there is no last_good and fetch fails, the error propagates."""
    cache = SheetCache(ttl_seconds=0)

    async def _fail() -> SheetFetchResult:
        raise ConnectionError("Google Sheets unreachable")

    with pytest.raises(ConnectionError):
        await cache.get(_fail)


# ---------------------------------------------------------------------------
# TC-I-SH-4: cache hit within TTL
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_tc_i_sh_4_cache_hit_does_not_call_fetcher() -> None:
    """TC-I-SH-4: A warm cache returns without calling the fetcher."""
    good_rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)
    cached = SheetFetchResult(rows=good_rows, stale=False, fetched_at=FIXED_FETCHED_AT)

    cache = SheetCache(ttl_seconds=3600)
    cache._cached = cached  # noqa: SLF001
    cache._cached_at = 1e18  # far future so TTL never expires

    call_count = 0

    async def _fetcher() -> SheetFetchResult:
        nonlocal call_count
        call_count += 1
        return cached

    result = await cache.get(_fetcher)

    assert call_count == 0
    assert result is cached


# ---------------------------------------------------------------------------
# TC-I-SH-5: cache miss after TTL refreshes + updates last_good
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_tc_i_sh_5_cache_miss_calls_fetcher_and_updates_last_good() -> None:
    """TC-I-SH-5: An expired cache calls the fetcher and updates last_good."""
    good_rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)
    fresh = SheetFetchResult(rows=good_rows, stale=False, fetched_at=datetime.now(UTC))

    cache = SheetCache(ttl_seconds=0)
    call_count = 0

    async def _fetcher() -> SheetFetchResult:
        nonlocal call_count
        call_count += 1
        return fresh

    result = await cache.get(_fetcher)

    assert call_count == 1
    assert result.stale is False
    assert cache.last_good is fresh


# ---------------------------------------------------------------------------
# TC-I-SH-6: manual refresh bypasses cache
# ---------------------------------------------------------------------------


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_tc_i_sh_6_manual_refresh_bypasses_cache(mock_build: MagicMock) -> None:
    """TC-I-SH-6: invalidate() forces a live fetch even within the TTL window."""
    ws = _mock_worksheet(FIXTURE_ALL_VALUES)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    client = _make_client(ttl=3600)
    first = await client.get_rows(db=None)

    client.invalidate()
    second = await client.get_rows(db=None)

    assert first.stale is False
    assert second.stale is False
    assert mock_build.call_count == 2


# ---------------------------------------------------------------------------
# Cache TTL edge case
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_cache_with_zero_ttl_always_fetches() -> None:
    """Cache with TTL=0 is immediately stale; fetcher is called each time."""
    rows = _parse_rows(FIXTURE_ROWS, FIXTURE_HEADERS, VALID_MAPPING)
    result = SheetFetchResult(rows=rows, stale=False, fetched_at=datetime.now(UTC))
    cache = SheetCache(ttl_seconds=0)
    calls = 0

    async def _fetcher() -> SheetFetchResult:
        nonlocal calls
        calls += 1
        return result

    await cache.get(_fetcher)
    await cache.get(_fetcher)

    assert calls == 2


# ---------------------------------------------------------------------------
# Empty Sheet
# ---------------------------------------------------------------------------


@pytest.mark.integration
@patch("app.sheets.client._build_gspread_client")
async def test_empty_sheet_returns_zero_rows(mock_build: MagicMock) -> None:
    """An empty Sheet returns a SheetFetchResult with zero rows and no error."""
    ws = _mock_worksheet(FIXTURE_EMPTY)
    mock_build.return_value = _mock_gspread_client(_mock_spreadsheet(ws))

    client = _make_client()
    result = await client.get_rows(db=None)

    assert result.rows == []
    assert result.stale is False
    assert result.schema_error is None
