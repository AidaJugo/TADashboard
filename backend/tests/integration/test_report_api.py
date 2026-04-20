"""Integration tests for GET /api/report and POST /api/report/refresh.

docs/testing.md §4.3:
  TC-I-API-1: Viewer GET /api/report?period=Q1&year=2026 returns 200 and only
              the hubs they are scoped to.
  TC-I-API-6: Hub-scoped viewer GET /api/report?hub=Belgrade where Belgrade is
              not in their scope returns 403 and audit entry.
              (This test case lives in test_hub_scope_guard.py as it was there
              in M4; we keep it there to avoid disrupting the audit-log grant
              test that lives alongside it.)
  TC-I-API-8: Year-over-year: compare_previous=true returns both years,
              each filtered by the caller's hub scope.
  TC-I-API-9: Year-over-year across a year with no data returns
              previous_year_missing=true rather than zeros.

docs/testing.md §4.4:
  TC-I-AUD-7: Refresh action writes an audit row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import AuditLog, HubPair
from app.sheets.models import HireRow, SheetFetchResult

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_hire_row(
    *,
    city: str = "Sarajevo",
    year: str = "2026",
    month: str = "Jan",
    status: str = "At mid-point",
    hire_type: str = "WFM",
) -> HireRow:
    return HireRow(
        position="BE Engineer",
        seniority="Medior",
        city=city,
        salary="3000",
        midpoint="3000",
        gap_eur="0",
        gap_pct="0",
        status=status,
        month=month,
        year=year,
        hire_type=hire_type,
        recruiter="Jane Smith",
        note="",
    )


def _mock_fetch_result(rows: list[HireRow], *, stale: bool = False) -> SheetFetchResult:
    from datetime import UTC, datetime

    return SheetFetchResult(
        rows=rows,
        stale=stale,
        fetched_at=datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC),
    )


async def _seed_hub_pairs(session: AsyncSession) -> None:
    """Seed a minimal set of hub_pairs rows so load_report_aux can build hub_order."""
    pairs = [
        ("Sarajevo", "Sarajevo"),
        ("Banja Luka", "Sarajevo"),
        ("Belgrade", "Belgrade"),
        ("Novi Sad", "Belgrade"),
        ("Nis", "Nis"),
        ("Skopje", "Skopje"),
        ("Medellin", "Medellin"),
        ("Remote", "Medellin"),
    ]
    for city, hub in pairs:
        session.add(HubPair(city_name=city, hub_name=hub))
    await session.commit()


# ---------------------------------------------------------------------------
# TC-I-API-1: viewer GET returns 200 and only their scoped hubs
# ---------------------------------------------------------------------------


async def test_tc_i_api_1_viewer_gets_scoped_report(
    api_client: TestClient,
    hub_scoped_viewer: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """TC-I-API-1: Scoped viewer (Sarajevo + Skopje) only sees those hubs."""
    await _seed_hub_pairs(owner_session)

    rows = [
        _make_hire_row(city="Sarajevo", year="2026", month="Jan"),
        _make_hire_row(city="Belgrade", year="2026", month="Jan"),
        _make_hire_row(city="Skopje", year="2026", month="Jan"),
    ]
    fetch_result = _mock_fetch_result(rows)

    _session_id, cookie = await seed_session(hub_scoped_viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = MagicMock(return_value=fetch_result)

        async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
            return fetch_result

        mock_client.get_rows = _get_rows
        mock_get_client.return_value = mock_client

        response = api_client.get(
            "/api/report",
            params={"period": "Jan", "year": 2026},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2026
    assert body["period"] == "Jan"
    assert body["stale"] is False

    # Hub rows must only contain Sarajevo and Skopje.
    hub_names = [h["hub"] for h in body["data"]["hub_rows"]]
    assert "Belgrade" not in hub_names
    assert "Sarajevo" in hub_names
    assert "Skopje" in hub_names

    # KPIs must only reflect Sarajevo + Skopje (2 hires), not Belgrade.
    assert body["data"]["kpis"]["total"] == 2


# ---------------------------------------------------------------------------
# TC-I-API-8: year-over-year compare_previous=true returns both years
# ---------------------------------------------------------------------------


async def test_tc_i_api_8_yoy_returns_both_years_hub_scoped(
    api_client: TestClient,
    hub_scoped_viewer: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """TC-I-API-8: compare_previous=true returns 2025 + 2026 both scoped."""
    await _seed_hub_pairs(owner_session)

    rows = [
        # 2026 Sarajevo + Belgrade
        _make_hire_row(city="Sarajevo", year="2026", month="Jan"),
        _make_hire_row(city="Belgrade", year="2026", month="Jan"),
        # 2025 Sarajevo + Belgrade
        _make_hire_row(city="Sarajevo", year="2025", month="Jan"),
        _make_hire_row(city="Belgrade", year="2025", month="Jan"),
    ]
    fetch_result = _mock_fetch_result(rows)

    _session_id, cookie = await seed_session(hub_scoped_viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
        return fetch_result

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = _get_rows
        mock_get_client.return_value = mock_client

        response = api_client.get(
            "/api/report",
            params={"period": "Jan", "year": 2026, "compare_previous": True},
        )

    assert response.status_code == 200
    body = response.json()

    assert body["previous_year"] == 2025
    assert body["previous_year_missing"] is False
    assert body["previous_year_data"] is not None

    # Both years must be scoped: only Sarajevo (Belgrade excluded).
    current_hubs = {h["hub"] for h in body["data"]["hub_rows"]}
    previous_hubs = {h["hub"] for h in body["previous_year_data"]["hub_rows"]}

    assert "Belgrade" not in current_hubs
    assert "Belgrade" not in previous_hubs
    assert "Sarajevo" in current_hubs
    assert "Sarajevo" in previous_hubs


# ---------------------------------------------------------------------------
# TC-I-API-9: year-over-year with no previous-year data → missing flag
# ---------------------------------------------------------------------------


async def test_tc_i_api_9_yoy_missing_previous_year(
    api_client: TestClient,
    hub_scoped_viewer: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """TC-I-API-9: No 2025 Jan data → previous_year_missing=true."""
    await _seed_hub_pairs(owner_session)

    # Only 2026 data; no 2025 rows at all.
    rows = [
        _make_hire_row(city="Sarajevo", year="2026", month="Jan"),
    ]
    fetch_result = _mock_fetch_result(rows)

    _session_id, cookie = await seed_session(hub_scoped_viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
        return fetch_result

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = _get_rows
        mock_get_client.return_value = mock_client

        response = api_client.get(
            "/api/report",
            params={"period": "Jan", "year": 2026, "compare_previous": True},
        )

    assert response.status_code == 200
    body = response.json()

    assert body["previous_year_missing"] is True
    # previous_year_data is still returned but has_data=False (TC-U-REP-12).
    assert body["previous_year_data"]["has_data"] is False


# ---------------------------------------------------------------------------
# TC-I-AUD-7: refresh writes an audit row
# ---------------------------------------------------------------------------


async def test_tc_i_aud_7_refresh_writes_audit_row(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
    attach_csrf: Callable[..., dict[str, str]],
) -> None:
    """TC-I-AUD-7: POST /api/report/refresh audits the action (FR-REPORT-7)."""
    rows = [_make_hire_row()]
    fetch_result = _mock_fetch_result(rows)

    _session_id, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    csrf_headers = attach_csrf(api_client)

    async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
        return fetch_result

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = _get_rows
        mock_client.invalidate = MagicMock()
        mock_get_client.return_value = mock_client

        response = api_client.post("/api/report/refresh", headers=csrf_headers)

    assert response.status_code == 202

    audit_rows = (
        (
            await owner_session.execute(
                select(AuditLog).where(
                    AuditLog.actor_id == admin_user,
                    AuditLog.action == AuditAction.sheet_refresh,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1, f"Expected 1 sheet_refresh audit row, got {len(audit_rows)}"


# ---------------------------------------------------------------------------
# Stale flag propagates from Sheet result
# ---------------------------------------------------------------------------


async def test_stale_flag_propagates_to_response(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
    owner_session: AsyncSession,
) -> None:
    """FR-REPORT-2: stale=True from the Sheet is forwarded to the API response."""
    await _seed_hub_pairs(owner_session)

    fetch_result = _mock_fetch_result([], stale=True)
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
        return fetch_result

    with patch("app.report.routes.get_sheets_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_rows = _get_rows
        mock_get_client.return_value = mock_client

        response = api_client.get("/api/report", params={"period": "Jan", "year": 2026})

    assert response.status_code == 200
    assert response.json()["stale"] is True


# ---------------------------------------------------------------------------
# Invalid period returns 422
# ---------------------------------------------------------------------------


async def test_invalid_period_returns_422(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable[..., object],
) -> None:
    _session_id, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    response = api_client.get("/api/report", params={"period": "InvalidXyz"})
    assert response.status_code == 422
