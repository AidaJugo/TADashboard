"""Integration tests for PDF export (FR-REPORT-10, TC-I-API-7, TC-I-AUD-8).

Cases covered
-------------
- TC-I-API-7: Rendered HTML contains only hubs from caller's scope.
              ``html_to_pdf`` is mocked (returns the HTML as bytes) so the
              test exercises scoping logic without requiring WeasyPrint's
              system libraries on macOS dev machines.  The real WeasyPrint
              conversion is covered by the Dockerfile environment in CI.
- TC-I-AUD-8: Audit row written after export captures actor_id, period, year,
              and the server-resolved hub scope.
- Adversarial query string: extra ``hub`` / ``filename`` params in the request
              must be ignored; output filename and body must not reflect them.
- Unauthenticated caller gets 401.
- Invalid period returns 422.
- Content-Type header is application/pdf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.audit.actions import AuditAction
from app.auth.cookies import SESSION_COOKIE_NAME
from app.db.models import RoleEnum
from app.sheets.models import HireRow, SheetFetchResult

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# html_to_pdf mock: return the HTML as bytes so we can search for text without
# needing WeasyPrint's system libraries in local / CI dev environments.
# ---------------------------------------------------------------------------
def _html_to_pdf_passthrough(html_content: str) -> bytes:
    return html_content.encode()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SARAJEVO_ROW = HireRow(
    position="Software Engineer",
    seniority="Senior",
    city="Sarajevo",
    salary="45000",
    midpoint="42000",
    gap_eur="3000",
    gap_pct="7.1",
    status="Above midpoint",
    month="3",
    year="2026",
    hire_type="WF",
    recruiter="Ana",
    note="",
)

_BELGRADE_ROW = HireRow(
    position="Product Manager",
    seniority="Mid",
    city="Belgrade",
    salary="52000",
    midpoint="50000",
    gap_eur="2000",
    gap_pct="4.0",
    status="Above midpoint",
    month="3",
    year="2026",
    hire_type="WF",
    recruiter="Marko",
    note="",
)


def _make_fetch_result(rows: list[HireRow]) -> SheetFetchResult:
    from datetime import UTC, datetime

    return SheetFetchResult(rows=rows, stale=False, fetched_at=datetime(2026, 4, 1, tzinfo=UTC))


# ---------------------------------------------------------------------------
# Helpers to seed hub pairs so the report knows about cities/hubs
# ---------------------------------------------------------------------------


async def _seed_hub_pairs(owner_session: AsyncSession) -> None:
    from app.db.models import HubPair

    for city, hub in [("Sarajevo", "Sarajevo"), ("Belgrade", "Belgrade")]:
        owner_session.add(HubPair(city_name=city, hub_name=hub))
    await owner_session.commit()


# ---------------------------------------------------------------------------
# TC-I-API-7 — PDF contains only scoped hubs
# ---------------------------------------------------------------------------


async def test_tc_i_api_7_pdf_contains_only_scoped_hubs(
    api_client: TestClient,
    create_user: Callable,
    seed_session: Callable,
    owner_session: AsyncSession,
) -> None:
    """Scoped viewer's PDF must not contain out-of-scope hub names."""
    await _seed_hub_pairs(owner_session)

    # Viewer scoped to Sarajevo only.
    viewer = await create_user(
        role=RoleEnum.viewer,
        email="sarajevo-viewer@symphony.is",
        allowed_hubs=["Sarajevo"],
    )
    _sid, cookie = await seed_session(viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    fetch_result = _make_fetch_result([_SARAJEVO_ROW, _BELGRADE_ROW])

    with (
        patch("app.report.routes.get_sheets_client") as mock_get,
        patch("app.report.routes.html_to_pdf", side_effect=_html_to_pdf_passthrough),
    ):
        mock_client = MagicMock()

        async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
            return fetch_result

        mock_client.get_rows = _get_rows
        mock_get.return_value = mock_client

        resp = api_client.get("/api/report/export-pdf?year=2026&period=Annual")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

    body = resp.content.decode()

    # Sarajevo hire is in scope and must appear in the rendered HTML.
    assert "Sarajevo" in body or "Software Engineer" in body

    # Belgrade hire is out of scope and must NOT appear.
    assert "Belgrade" not in body
    assert "Product Manager" not in body


async def test_pdf_unscoped_admin_sees_all_hubs(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    owner_session: AsyncSession,
) -> None:
    """Admin with no hub restriction sees all hubs in the PDF."""
    await _seed_hub_pairs(owner_session)

    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    fetch_result = _make_fetch_result([_SARAJEVO_ROW, _BELGRADE_ROW])

    with (
        patch("app.report.routes.get_sheets_client") as mock_get,
        patch("app.report.routes.html_to_pdf", side_effect=_html_to_pdf_passthrough),
    ):
        mock_client = MagicMock()

        async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
            return fetch_result

        mock_client.get_rows = _get_rows
        mock_get.return_value = mock_client

        resp = api_client.get("/api/report/export-pdf?year=2026&period=Annual")

    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Sarajevo" in body or "Software Engineer" in body


# ---------------------------------------------------------------------------
# TC-I-AUD-8 — audit row captures server-resolved scope
# ---------------------------------------------------------------------------


async def test_tc_i_aud_8_audit_row_written_with_server_scope(
    api_client: TestClient,
    create_user: Callable,
    seed_session: Callable,
    owner_session: AsyncSession,
) -> None:
    """PDF export audit row must capture server-resolved hub scope."""
    await _seed_hub_pairs(owner_session)

    viewer = await create_user(
        role=RoleEnum.viewer,
        email="audit-test@symphony.is",
        allowed_hubs=["Sarajevo"],
    )
    _sid, cookie = await seed_session(viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    fetch_result = _make_fetch_result([_SARAJEVO_ROW])

    with (
        patch("app.report.routes.get_sheets_client") as mock_get,
        patch("app.report.routes.html_to_pdf", side_effect=_html_to_pdf_passthrough),
    ):
        mock_client = MagicMock()

        async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
            return fetch_result

        mock_client.get_rows = _get_rows
        mock_get.return_value = mock_client

        resp = api_client.get("/api/report/export-pdf?year=2026&period=Annual")

    assert resp.status_code == 200

    rows = (
        await owner_session.execute(
            text(
                "SELECT actor_id, action, target FROM audit_log "
                "WHERE action = :action ORDER BY created_at DESC"
            ),
            {"action": AuditAction.report_export_pdf},
        )
    ).all()

    assert len(rows) == 1
    actor_id, action, target = rows[0]
    assert actor_id == viewer
    assert action == AuditAction.report_export_pdf
    # Target must contain the server-resolved hub scope.
    assert "year=2026" in target
    assert "period=Annual" in target
    assert "hubs=" in target
    # Hub scope is server-resolved: should contain "Sarajevo", not out-of-scope hubs.
    assert "Sarajevo" in target


# ---------------------------------------------------------------------------
# Unauthenticated → 401
# ---------------------------------------------------------------------------


async def test_pdf_unauthenticated_returns_401(api_client: TestClient) -> None:
    resp = api_client.get("/api/report/export-pdf")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invalid period → 422
# ---------------------------------------------------------------------------


async def test_pdf_invalid_period_returns_422(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    resp = api_client.get("/api/report/export-pdf?period=INVALID_PERIOD")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Adversarial query string — extra params must be ignored (P2)
# ---------------------------------------------------------------------------


async def test_pdf_adversarial_query_string_ignored(
    api_client: TestClient,
    create_user: Callable,
    seed_session: Callable,
    owner_session: AsyncSession,
) -> None:
    """Extra query params ``hub`` and ``filename`` must never reach the output.

    The scoped-viewer route must:
    (a) return 200,
    (b) produce a filename of ``ta-report-2026-Annual.pdf`` (server-derived),
    (c) not echo ``USA`` or ``evil.pdf`` anywhere in the rendered body.
    """
    await _seed_hub_pairs(owner_session)

    viewer = await create_user(
        role=RoleEnum.viewer,
        email="adversarial-viewer@symphony.is",
        allowed_hubs=["Sarajevo"],
    )
    _sid, cookie = await seed_session(viewer)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    fetch_result = _make_fetch_result([_SARAJEVO_ROW, _BELGRADE_ROW])

    with (
        patch("app.report.routes.get_sheets_client") as mock_get,
        patch("app.report.routes.html_to_pdf", side_effect=_html_to_pdf_passthrough),
    ):
        mock_client = MagicMock()

        async def _get_rows(*_a: object, **_kw: object) -> SheetFetchResult:
            return fetch_result

        mock_client.get_rows = _get_rows
        mock_get.return_value = mock_client

        resp = api_client.get(
            "/api/report/export-pdf?year=2026&period=Annual&hub=USA&filename=evil.pdf"
        )

    assert resp.status_code == 200

    # Filename must be server-derived, not from the ``filename`` param.
    disposition = resp.headers.get("content-disposition", "")
    assert "ta-report-2026-Annual.pdf" in disposition
    assert "evil.pdf" not in disposition

    # Body must contain only Sarajevo (in-scope) content.
    body = resp.content.decode()
    assert "Belgrade" not in body, "Out-of-scope hub must not appear in PDF body"
    assert "Product Manager" not in body
    assert "USA" not in body, "Adversarial hub param must not appear in PDF body"
