"""Google Sheets client for the TA Hiring Report Platform.

Responsibilities
----------------
1. Authenticate with the Google Sheets API using a service account key (ADR 0003).
2. Validate the fetched headers against the admin-configured column mapping.
3. Parse rows into HireRow objects.
4. Cache results in-process for the configured TTL (FR-REPORT-1).
5. Persist the last-successful fetch to the ``sheet_snapshot`` Postgres table
   and serve it on failure with ``stale=True`` (FR-REPORT-2).
6. Support manual cache invalidation triggered by the "Refresh" button (FR-REPORT-7).

The client is instantiated once at startup and held in app state.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import Settings, get_settings
from app.db.models import SheetSnapshot
from app.logging import get_logger
from app.sheets.cache import SheetCache
from app.sheets.column_mapping import validate_column_mapping
from app.sheets.models import HireRow, SheetFetchResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


log = get_logger(__name__)

_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _column_hash(headers: list[str]) -> str:
    """SHA-256 of sorted headers — detects schema drift between fetches."""
    return hashlib.sha256(",".join(sorted(headers)).encode()).hexdigest()


def _build_gspread_client(service_account_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
        service_account_path, scopes=_SHEETS_SCOPES
    )
    return gspread.authorize(creds)


class SheetsClient:
    """Wraps gspread + TTL cache + snapshot persistence.

    Parameters
    ----------
    column_mapping:
        dict mapping logical names → source column headers. The default
        mapping uses the prototype's column order (legacy/generate_report.py).
    ttl_seconds:
        How long to serve cached data before re-fetching.
    """

    #: Default column mapping matching the prototype's Sheet layout.
    DEFAULT_MAPPING: dict[str, str] = {
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

    def __init__(
        self,
        column_mapping: dict[str, str] | None = None,
        ttl_seconds: int = 60,
        settings: Settings | None = None,
    ) -> None:
        self._mapping = validate_column_mapping(column_mapping or self.DEFAULT_MAPPING).mapping
        self._cache = SheetCache(ttl_seconds=ttl_seconds)
        self._settings_override: Settings | None = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """Force the next fetch to bypass the cache (FR-REPORT-7)."""
        self._cache.invalidate()

    def update_mapping(self, new_mapping: dict[str, str]) -> None:
        """Replace the column mapping and invalidate the cache (FR-CONFIG-2).

        Raises ColumnMappingError if the new mapping is invalid; the old
        mapping remains active (FR-CONFIG-5).
        """
        validated = validate_column_mapping(new_mapping)
        self._mapping = validated.mapping
        self._cache.invalidate()
        log.info("column_mapping_updated", extra={"new_mapping": list(new_mapping.keys())})

    async def get_rows(self, db: AsyncSession | None = None) -> SheetFetchResult:
        """Return hiring rows, using the cache or snapshot as appropriate.

        ``db`` is optional; when provided, the last-known-good snapshot is
        persisted to Postgres on a successful live fetch and loaded as the
        initial fallback if the cache is cold (TC-I-SH-3, TC-I-SH-5).
        """
        if db is not None:
            await self._prime_cache_from_snapshot(db)

        result = await self._cache.get(self._fetch_live)

        # B2: only persist a clean, non-schema-error result as the snapshot.
        if db is not None and not result.stale and result.schema_error is None:
            await self._persist_snapshot(db, result)

        return result

    # ------------------------------------------------------------------
    # Internal: live fetch
    # ------------------------------------------------------------------

    async def _fetch_live(self) -> SheetFetchResult:
        settings = self._settings_override or get_settings()
        if not settings.google_service_account_json_path:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_PATH is not set")
        if not settings.spreadsheet_id:
            raise RuntimeError("SPREADSHEET_ID is not set")

        gspread_client = _build_gspread_client(settings.google_service_account_json_path)
        spreadsheet = gspread_client.open_by_key(settings.spreadsheet_id)
        worksheet = spreadsheet.worksheet(settings.spreadsheet_tab_name)
        raw: list[list[str]] = worksheet.get_all_values()

        if not raw:
            log.warning("sheet_empty", extra={"tab": settings.spreadsheet_tab_name})
            return SheetFetchResult(rows=[], fetched_at=datetime.now(UTC))

        headers: list[str] = [str(h).strip() for h in raw[0]]
        col_hash = _column_hash(headers)

        # Validate that all required logical columns are present in the Sheet.
        source_columns = set(self._mapping.values())
        missing_in_sheet = source_columns - set(headers)
        if missing_in_sheet:
            error_msg = (
                f"Required columns missing from Sheet: {', '.join(sorted(missing_in_sheet))}"
            )
            log.error(
                "sheet_schema_error",
                extra={"missing": sorted(missing_in_sheet), "tab": settings.spreadsheet_tab_name},
            )
            # B2/N5: stale=True ensures the cache does not promote this result to
            # last_good and the caller does not persist it as the snapshot.
            return SheetFetchResult(
                rows=[],
                stale=True,
                fetched_at=datetime.now(UTC),
                column_hash=col_hash,
                schema_error=error_msg,
            )

        rows = _parse_rows(raw[1:], headers, self._mapping)
        log.info(
            "sheet_fetched",
            extra={"row_count": len(rows), "tab": settings.spreadsheet_tab_name},
        )
        return SheetFetchResult(rows=rows, fetched_at=datetime.now(UTC), column_hash=col_hash)

    # ------------------------------------------------------------------
    # Internal: snapshot persistence
    # ------------------------------------------------------------------

    async def _prime_cache_from_snapshot(self, db: AsyncSession) -> None:
        """Load the Postgres snapshot into the cache as the initial last_good.

        Only runs when the cache has no last_good value (cold start or test).
        """
        if self._cache.last_good is not None:
            return

        result = await db.execute(select(SheetSnapshot).where(SheetSnapshot.id == 1))
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return

        try:
            rows_data: list[dict[str, str]] = snapshot.raw_rows  # JSONB, already parsed
            rows = [HireRow(**r) for r in rows_data]
        except Exception as exc:
            log.warning("snapshot_parse_error", extra={"error": str(exc)})
            return

        self._cache._last_good = SheetFetchResult(  # noqa: SLF001
            rows=rows,
            stale=True,
            fetched_at=snapshot.fetched_at,
            column_hash=snapshot.column_hash,
        )

    async def _persist_snapshot(self, db: AsyncSession, result: SheetFetchResult) -> None:
        """Upsert the last-successful fetch into the sheet_snapshot table (TC-I-SH-5).

        raw_rows is stored as JSONB (N4); no JSON serialisation needed here.
        """
        raw_rows = [r.model_dump() for r in result.rows]
        stmt = insert(SheetSnapshot).values(
            id=1,
            raw_rows=raw_rows,
            fetched_at=result.fetched_at,
            column_hash=result.column_hash,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "raw_rows": stmt.excluded.raw_rows,
                "fetched_at": stmt.excluded.fetched_at,
                "column_hash": stmt.excluded.column_hash,
            },
        )
        await db.execute(stmt)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_rows(
    data_rows: list[list[str]],
    headers: list[str],
    mapping: dict[str, str],
) -> list[HireRow]:
    """Convert raw Sheet rows to HireRow objects using the active column mapping."""
    source_to_logical = {v: k for k, v in mapping.items()}
    header_index: dict[str, int] = {h: i for i, h in enumerate(headers)}

    result: list[HireRow] = []
    for raw_row in data_rows:
        row_dict: dict[str, str] = {}
        for source_col, logical in source_to_logical.items():
            idx = header_index.get(source_col)
            value = raw_row[idx].strip() if idx is not None and idx < len(raw_row) else ""
            row_dict[logical.lower()] = value

        result.append(
            HireRow(
                position=row_dict.get("position", ""),
                seniority=row_dict.get("seniority", ""),
                city=row_dict.get("city", ""),
                salary=row_dict.get("salary", ""),
                midpoint=row_dict.get("midpoint", ""),
                gap_eur=row_dict.get("gap_eur", ""),
                gap_pct=row_dict.get("gap_pct", ""),
                status=row_dict.get("status", ""),
                month=row_dict.get("month", ""),
                year=row_dict.get("year", ""),
                hire_type=row_dict.get("type", ""),
                recruiter=row_dict.get("recruiter", ""),
                note=row_dict.get("note", ""),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Module-level singleton (used by FastAPI app state)
# ---------------------------------------------------------------------------

_client: SheetsClient | None = None


def get_sheets_client() -> SheetsClient:
    """Return the module-level SheetsClient singleton.

    Call ``reset_sheets_client()`` in tests to inject a test-configured client.
    """
    global _client  # noqa: PLW0603
    if _client is None:
        _client = SheetsClient()
    return _client


def reset_sheets_client(client: SheetsClient | None = None) -> None:
    """Replace the module-level singleton (for tests)."""
    global _client  # noqa: PLW0603
    _client = client
