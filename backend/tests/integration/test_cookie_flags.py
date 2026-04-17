"""TC-S-7 — the session cookie carries HttpOnly, Secure, SameSite=Lax.

The cookie is set in two places: the OAuth callback (PR 4) and any other
flow that could produce a login.  :func:`app.auth.cookies.set_session_cookie`
is the only code path that writes the cookie; this test pins its
behaviour against a real ``Response`` so the flags cannot silently
regress.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import Response

from app.auth.cookies import SESSION_COOKIE_NAME, set_session_cookie


@pytest.fixture(autouse=True)
def _force_production_cookie_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """TC-S-7 asserts *production* semantics; clear the dev override."""
    monkeypatch.delenv("SESSION_COOKIE_INSECURE", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()


def test_tc_s_7_session_cookie_has_httponly_secure_samesite_lax() -> None:
    response = Response()
    set_session_cookie(response, uuid.uuid4())

    raw = response.headers["set-cookie"]
    assert raw.startswith(f"{SESSION_COOKIE_NAME}="), raw
    lowered = raw.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "max-age=" in lowered


def test_dev_override_disables_secure_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_COOKIE_INSECURE", "1")
    response = Response()
    set_session_cookie(response, uuid.uuid4())
    lowered = response.headers["set-cookie"].lower()
    assert "secure" not in lowered
    # HttpOnly + SameSite must still be on.
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
