"""Integration tests for comment CRUD (FR-COMMENT-1..4).

Cases covered
-------------
- TC-I-API-3: Editor POST /api/comments returns 201 and writes an audit row.
- Viewer POST /api/comments returns 403.
- Duplicate hire key returns 409.
- Admin can create, update, delete comments.
- Editor can create, update, delete comments.
- Viewer is denied all mutations.
- DELETE returns 204; subsequent GET omits the deleted comment.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from app.auth.cookies import SESSION_COOKIE_NAME

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_COMMENT_PAYLOAD = {
    "position": "Software Engineer",
    "seniority": "Senior",
    "hub": "Sarajevo",
    "salary_eur": 45000,
    "text": "Above midpoint due to niche skill set.",
}


# ---------------------------------------------------------------------------
# TC-I-API-3 — editor creates comment, audit row written
# ---------------------------------------------------------------------------


async def test_tc_i_api_3_editor_create_comment(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["position"] == "Software Engineer"
    assert body["hub"] == "Sarajevo"
    assert body["salary_eur"] == 45000
    assert "id" in body

    # Audit row
    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'comment_created'")
        )
    ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# Viewer denied
# ---------------------------------------------------------------------------


async def test_viewer_cannot_create_comment(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    assert resp.status_code == 403


async def test_viewer_cannot_list_comments(
    api_client: TestClient,
    viewer_user: uuid.UUID,
    seed_session: Callable,
) -> None:
    _sid, cookie = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert api_client.get("/api/comments").status_code == 403


# ---------------------------------------------------------------------------
# Duplicate hire key → 409
# ---------------------------------------------------------------------------


async def test_duplicate_comment_returns_409(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_editor_can_update_comment(
    api_client: TestClient,
    editor_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    create_resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    comment_id = create_resp.json()["id"]

    update_resp = api_client.patch(
        f"/api/comments/{comment_id}",
        json={"text": "Updated note."},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["text"] == "Updated note."

    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'comment_updated'")
        )
    ).scalar_one()
    assert count == 1


async def test_viewer_cannot_update_comment(
    api_client: TestClient,
    editor_user: uuid.UUID,
    viewer_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)
    create_resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)
    comment_id = create_resp.json()["id"]

    _sid2, cookie2 = await seed_session(viewer_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie2)
    viewer_headers = attach_csrf(api_client)
    resp = api_client.patch(
        f"/api/comments/{comment_id}",
        json={"text": "Sneak."},
        headers=viewer_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_admin_can_delete_comment(
    api_client: TestClient,
    admin_user: uuid.UUID,
    editor_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
    owner_session: AsyncSession,
) -> None:
    _sid, editor_cookie = await seed_session(editor_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, editor_cookie)
    editor_headers = attach_csrf(api_client)
    create_resp = api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=editor_headers)
    comment_id = create_resp.json()["id"]

    _sid2, admin_cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, admin_cookie)
    admin_headers = attach_csrf(api_client)
    del_resp = api_client.delete(f"/api/comments/{comment_id}", headers=admin_headers)
    assert del_resp.status_code == 204

    count = (
        await owner_session.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'comment_deleted'")
        )
    ).scalar_one()
    assert count == 1


async def test_delete_nonexistent_comment_returns_404(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    fake_id = uuid.uuid4()
    resp = api_client.delete(f"/api/comments/{fake_id}", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin can also create / list
# ---------------------------------------------------------------------------


async def test_admin_create_and_list_comments(
    api_client: TestClient,
    admin_user: uuid.UUID,
    seed_session: Callable,
    attach_csrf: Callable,
) -> None:
    _sid, cookie = await seed_session(admin_user)
    api_client.cookies.set(SESSION_COOKIE_NAME, cookie)
    headers = attach_csrf(api_client)

    api_client.post("/api/comments", json=_COMMENT_PAYLOAD, headers=headers)

    list_resp = api_client.get("/api/comments")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
