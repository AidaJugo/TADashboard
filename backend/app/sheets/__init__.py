"""Sheets layer public API.

Re-exports the key types and functions so callers use ``from app.sheets import ...``.
"""

from app.sheets.cache import SheetCache
from app.sheets.client import SheetsClient, get_sheets_client, reset_sheets_client
from app.sheets.column_mapping import ColumnMappingError, validate_column_mapping
from app.sheets.models import (
    REQUIRED_LOGICAL_COLUMNS,
    ColumnMappingConfig,
    HireRow,
    SheetFetchResult,
)

__all__ = [
    "ColumnMappingConfig",
    "ColumnMappingError",
    "HireRow",
    "REQUIRED_LOGICAL_COLUMNS",
    "SheetCache",
    "SheetFetchResult",
    "SheetsClient",
    "get_sheets_client",
    "reset_sheets_client",
    "validate_column_mapping",
]
