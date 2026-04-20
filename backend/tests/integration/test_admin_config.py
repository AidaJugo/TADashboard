"""Integration tests for admin config and hub-pair endpoints.

Cases covered
-------------
- TC-I-API-5: Admin POST /api/admin/config with invalid spreadsheet returns 422;
              previous config is unchanged.
- TC-I-API-12: Admin CRUD on /api/admin/hub-pairs succeeds; viewer and editor denied.
- TC-I-API-13: PATCH /api/admin/config/retention accepts values within bounds;
               values outside bounds return 422.
- TC-I-AUD-2: Config edit writes an audit row with before/after summary.
- Happy paths: get config, update tab name, create/update/delete hub pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from app.auth.cookies import SESSION_COOKIE_NAME
from app.config import (
    RETENTION_AUDIT_MONTHS_MAX,
    RETENTION_AUDIT_MONTHS_MIN,
    RETENTION_BACKUP_DAYS_MAX,
    RETENTION_BACKUP_DAYS_MIN,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Config — happy path
# ---------------------------------------------------------------------------


async def test_get_config_returns_defaults(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)

    resp = api_client.get("/api/admin/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "spreadsheet_id" in body
    assert "audit_retention_months" in body
    assert "backup_retention_days" in body
    assert "column_mappings" in body


async def test_update_config_tab_name_writes_audit(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    # Patch spreadsheet validation so we don't need real credentials.
    with patch("app.admin.routes._validate_spreadsheet", new=AsyncMock(return_value=None)):
        resp = api_client.post(
            "/api/admin/config",
            json={"spreadsheet_tab_name": "NewTab2026"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["spreadsheet_tab_name"] == "NewTab2026"

    # TC-I-AUD-2: audit row written
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'config_edit'")
        )
    ).scalar_one()
    assert count >= 1


# ---------------------------------------------------------------------------
# TC-I-API-5 — invalid spreadsheet → 422, config unchanged
# ---------------------------------------------------------------------------


async def test_tc_i_api_5_invalid_spreadsheet_returns_422_config_unchanged(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    """Invalid spreadsheet ID returns 422 and does not modify stored config."""
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    # Record config before the attempted update.
    before_resp = api_client.get("/api/admin/config")
    before_tab = before_resp.json()["spreadsheet_tab_name"]

    error_msg = "Spreadsheet 'bad-id' not found or not shared."
    with patch(
        "app.admin.routes._validate_spreadsheet",
        new=AsyncMock(return_value=error_msg),
    ):
        resp = api_client.post(
            "/api/admin/config",
            json={"spreadsheet_id": "bad-id", "spreadsheet_tab_name": "ShouldNotSave"},
            headers=headers,
        )

    assert resp.status_code == 422
    assert "validation failed" in resp.json()["detail"].lower()

    # Config must be unchanged.
    after_resp = api_client.get("/api/admin/config")
    assert after_resp.json()["spreadsheet_tab_name"] == before_tab


# ---------------------------------------------------------------------------
# Config forbidden for non-admin
# ---------------------------------------------------------------------------


async def test_config_update_forbidden_for_editor(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post("/api/admin/config", json={}, headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC-I-API-13 — retention bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"audit_retention_months": RETENTION_AUDIT_MONTHS_MIN}, 200),
        ({"audit_retention_months": RETENTION_AUDIT_MONTHS_MAX}, 200),
        ({"backup_retention_days": RETENTION_BACKUP_DAYS_MIN}, 200),
        ({"backup_retention_days": RETENTION_BACKUP_DAYS_MAX}, 200),
        ({"audit_retention_months": RETENTION_AUDIT_MONTHS_MIN - 1}, 422),
        ({"audit_retention_months": RETENTION_AUDIT_MONTHS_MAX + 1}, 422),
        ({"backup_retention_days": RETENTION_BACKUP_DAYS_MIN - 1}, 422),
        ({"backup_retention_days": RETENTION_BACKUP_DAYS_MAX + 1}, 422),
    ],
)
async def test_tc_i_api_13_retention_bounds(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    payload: dict,
    expected: int,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.patch("/api/admin/config/retention", json=payload, headers=headers)
    assert resp.status_code == expected


async def test_retention_update_writes_audit_row(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    api_client.patch(
        "/api/admin/config/retention",
        json={"audit_retention_months": 24},
        headers=headers,
    )

    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'config_edit'")
        )
    ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# TC-I-API-12 — hub-pairs CRUD access control
# ---------------------------------------------------------------------------


async def test_tc_i_api_12_viewer_denied_hub_pairs(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert api_client.get("/api/admin/hub-pairs").status_code == 403


async def test_tc_i_api_12_editor_denied_hub_pairs(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert api_client.get("/api/admin/hub-pairs").status_code == 403


async def test_tc_i_api_12_admin_hub_pair_crud(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    # Create
    resp = api_client.post(
        "/api/admin/hub-pairs",
        json={"city_name": "Bihać", "hub_name": "Sarajevo"},
        headers=headers,
    )
    assert resp.status_code == 201
    pair_id = resp.json()["id"]

    # List
    resp = api_client.get("/api/admin/hub-pairs")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert pair_id in ids

    # Update
    resp = api_client.patch(
        f"/api/admin/hub-pairs/{pair_id}",
        json={"hub_name": "Banja Luka"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["hub_name"] == "Banja Luka"

    # Delete
    resp = api_client.delete(f"/api/admin/hub-pairs/{pair_id}", headers=headers)
    assert resp.status_code == 204

    # Confirm deleted
    resp = api_client.get("/api/admin/hub-pairs")
    ids = {p["id"] for p in resp.json()}
    assert pair_id not in ids

    # Audit rows for the operations
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'hub_pair_edit'")
        )
    ).scalar_one()
    assert count >= 3  # create + update + delete


async def test_hub_pair_duplicate_city_returns_409(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    api_client.post(
        "/api/admin/hub-pairs",
        json={"city_name": "Mostar", "hub_name": "Sarajevo"},
        headers=headers,
    )
    resp = api_client.post(
        "/api/admin/hub-pairs",
        json={"city_name": "Mostar", "hub_name": "Belgrade"},
        headers=headers,
    )
    assert resp.status_code == 409
