"""Regression tests: /api/e2e/seed-session env guard.

Verifies that the session-seed backdoor endpoint is invisible and
unreachable in non-test environments.

TC coverage:
  - Endpoint returns 404 for APP_ENV=prod, dev, and empty string.
  - Router is absent from a fresh app built under APP_ENV=prod.
  - Router is present in a fresh app built under APP_ENV=test.

No database is required: when APP_ENV != "test" the router is never
registered, so FastAPI's own 404 fires before any handler runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

pytestmark = pytest.mark.integration

_E2E_PATH = "/api/e2e/seed-session"


def _fresh_client(monkeypatch: pytest.MonkeyPatch, app_env: str) -> TestClient:
    """Build a fresh FastAPI app with APP_ENV overridden and return a TestClient.

    ``get_settings`` is lru_cached; we clear the cache before and after so
    sibling tests are not affected by the monkeypatched value.
    """
    monkeypatch.setenv("APP_ENV", app_env)
    get_settings.cache_clear()
    try:
        from app.main import create_app

        return TestClient(create_app(), raise_server_exceptions=True)
    finally:
        # Clear again so the cache is definitely cold when the next test runs.
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Endpoint must return 404 when APP_ENV is not "test"
# ---------------------------------------------------------------------------


def test_e2e_seed_session_returns_404_when_app_env_is_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV=prod → route not registered → 404."""
    client = _fresh_client(monkeypatch, "prod")
    response = client.post(_E2E_PATH, json={})
    assert response.status_code == 404


def test_e2e_seed_session_returns_404_when_app_env_is_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV=dev → route not registered → 404."""
    client = _fresh_client(monkeypatch, "dev")
    response = client.post(_E2E_PATH, json={})
    assert response.status_code == 404


def test_e2e_seed_session_returns_404_when_app_env_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV="" (empty string) → route not registered → 404."""
    client = _fresh_client(monkeypatch, "")
    response = client.post(_E2E_PATH, json={})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Router registration must be conditional on APP_ENV == "test"
# ---------------------------------------------------------------------------


def test_e2e_router_not_registered_when_app_env_is_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /api/e2e/seed-session path must not appear in the route table under prod."""
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    try:
        from app.main import create_app

        fresh_app = create_app()
    finally:
        get_settings.cache_clear()

    paths = [route.path for route in fresh_app.routes]  # type: ignore[attr-defined]
    assert _E2E_PATH not in paths, (
        f"{_E2E_PATH!r} is registered in prod — backdoor is exposed.\n" f"Full route list: {paths}"
    )


def test_e2e_router_registered_when_app_env_is_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /api/e2e/seed-session path must be present in the route table under test."""
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    try:
        from app.main import create_app

        fresh_app = create_app()
    finally:
        get_settings.cache_clear()

    paths = [route.path for route in fresh_app.routes]  # type: ignore[attr-defined]
    assert _E2E_PATH in paths, (
        f"{_E2E_PATH!r} is missing from the route table under APP_ENV=test.\n"
        f"Full route list: {paths}"
    )
