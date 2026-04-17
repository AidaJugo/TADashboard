"""Unit tests for the ``require_role`` FastAPI dependency (TC-U-AUTHZ-1).

docs/testing.md §3.3:
    TC-U-AUTHZ-1: ``require_role(admin)`` denies a viewer and allows an admin.

Additional invariants tested here:
    - Dependency-factory rejects an empty ``allowed`` list at construction time
      (fail-loud safeguard: an empty list would deny every caller).
    - Multiple roles are OR-ed (admin OR editor accepts both).
    - String names and enum values are both accepted at the factory call site.
    - An unauthenticated request (``get_current_user`` raises 401) surfaces as
      401, not 403.

Note: as of M4 review follow-up PR A, ``require_role`` writes an
``access_denied`` audit row on 403.  The unit tests here use an
in-memory fake ``AsyncSession`` via ``get_db`` override so they don't
need a real database.  TC-S-3 in ``test_admin_guard.py`` exercises the
real DB path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user
from app.authz.roles import Role, require_role
from app.db.models import User
from app.db.session import get_db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test-only fixtures
# ---------------------------------------------------------------------------


def _make_user(role: Role) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role.value}@symphony.is",
        display_name=f"{role.value.title()} User",
        role=role,
        is_active=True,
    )


class _FakeAsyncSession:
    """Just enough of :class:`AsyncSession` for ``write_audit`` + commit.

    ``write_audit`` calls ``.add(row)`` then ``await .flush()``; the role
    guard then calls ``await .commit()``.  We record nothing — the unit
    tests only care that the 403 is raised after audit + commit succeed.
    The full audit-row contract is exercised by TC-S-3 in
    ``test_admin_guard.py``.
    """

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


async def _override_get_db() -> AsyncGenerator[_FakeAsyncSession, None]:
    yield _FakeAsyncSession()


def _app_with_role_guard(*allowed: Role | str) -> FastAPI:
    app = FastAPI()
    dep = require_role(*allowed)

    @app.get("/guarded")
    async def guarded(user: User = Depends(dep)) -> dict[str, str]:  # noqa: B008
        return {"role": user.role.value}

    app.dependency_overrides[get_db] = _override_get_db
    return app


# ---------------------------------------------------------------------------
# TC-U-AUTHZ-1
# ---------------------------------------------------------------------------


def test_tc_u_authz_1_admin_allowed() -> None:
    """Admin-only route accepts an admin."""
    app = _app_with_role_guard(Role.admin)
    admin = _make_user(Role.admin)

    async def _current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = _current_user
    client = TestClient(app)
    response = client.get("/guarded")
    assert response.status_code == 200
    assert response.json() == {"role": "admin"}


def test_tc_u_authz_1_viewer_denied() -> None:
    """Admin-only route rejects a viewer with 403."""
    app = _app_with_role_guard(Role.admin)
    viewer = _make_user(Role.viewer)

    async def _current_user() -> User:
        return viewer

    app.dependency_overrides[get_current_user] = _current_user
    client = TestClient(app)
    response = client.get("/guarded")
    assert response.status_code == 403
    assert response.json()["detail"] == "insufficient role"


def test_editor_allowed_when_admin_or_editor() -> None:
    app = _app_with_role_guard(Role.admin, Role.editor)
    editor = _make_user(Role.editor)

    async def _current_user() -> User:
        return editor

    app.dependency_overrides[get_current_user] = _current_user
    client = TestClient(app)
    assert client.get("/guarded").status_code == 200


def test_viewer_denied_when_admin_or_editor() -> None:
    app = _app_with_role_guard(Role.admin, Role.editor)
    viewer = _make_user(Role.viewer)

    async def _current_user() -> User:
        return viewer

    app.dependency_overrides[get_current_user] = _current_user
    client = TestClient(app)
    assert client.get("/guarded").status_code == 403


def test_string_role_names_are_accepted() -> None:
    """For ergonomics: ``require_role("admin")`` works the same as ``require_role(Role.admin)``."""
    app = _app_with_role_guard("admin")
    admin = _make_user(Role.admin)

    async def _current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = _current_user
    client = TestClient(app)
    assert client.get("/guarded").status_code == 200


def test_empty_allowed_list_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="no allowed roles"):
        require_role()


def test_unauthenticated_user_gets_401_not_403() -> None:
    """When ``get_current_user`` itself raises 401, the guard must surface 401."""
    app = _app_with_role_guard(Role.admin)
    # Do not override get_current_user — it defaults to raising 401.
    client = TestClient(app)
    response = client.get("/guarded")
    assert response.status_code == 401
