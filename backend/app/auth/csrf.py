"""CSRF protection for state-changing routes (NFR-SEC-2, TC-S-1).

Pattern: **double-submit cookie + header**.

Why this shape
--------------
- *SameSite=Lax* on ``ta_sid`` blocks the cross-site POST vector in modern
  browsers, but does **not** stop a same-site ``<form>`` post (e.g. a
  malicious page hosted on a sibling subdomain or an XSS in another
  Symphony tool).  PRD NFR-SEC-2 and testing.md §6 TC-S-1 require an
  explicit token check; this module is that check.
- Stateless: the CSRF token does not need a server-side row.  The
  invariant is "the request carries the token in *both* the cookie and
  the header — JS in the page can read the cookie and echo it; an
  attacker on a different origin cannot read the cookie at all."
- Issued at login time (set in the OAuth callback alongside ``ta_sid``)
  and on logout we drop both cookies.

Cookie contract
---------------
- Name        — ``ta_csrf``
- Value       — 32 random bytes, URL-safe base64 (``secrets.token_urlsafe``)
- ``HttpOnly`` — **False**.  JS *must* read this to echo it as a header.
- ``Secure``  — True (HTTPS only; same dev override as ``ta_sid``).
- ``SameSite`` — Lax  (matches ``ta_sid``).
- ``Path``     — ``/``
- ``Max-Age``  — same as ``ta_sid``.

Header contract
---------------
- Name  — ``X-CSRF-Token``
- Value — must equal the cookie byte-for-byte (``secrets.compare_digest``).

The dependency is a no-op for safe methods (GET, HEAD, OPTIONS).
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Final

from fastapi import HTTPException, Request, status

from app.auth.cookies import _secure_cookie
from app.config import get_settings

if TYPE_CHECKING:
    from fastapi import Response

#: Cookie name for the CSRF token.  Do not rename without an ADR — the SPA
#: reads this cookie name directly.
CSRF_COOKIE_NAME: Final[str] = "ta_csrf"

#: Header name carrying the echoed token on state-changing requests.
CSRF_HEADER_NAME: Final[str] = "X-CSRF-Token"

#: HTTP methods that are exempt from CSRF.  RFC 9110 §9.2.1 (safe
#: methods); these must not have side effects so a missing token is fine.
_SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS"})


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response) -> str:
    """Issue a fresh CSRF token onto ``response``.  Returns the value.

    Called from the OAuth callback right after ``set_session_cookie``.
    Rotated on every login so a leaked token from a prior session cannot
    survive a re-authentication.
    """
    settings = get_settings()
    token = _generate_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.session_absolute_timeout_minutes * 60,
        # Deliberately HttpOnly=False: JavaScript in the SPA must read
        # this cookie and echo it as the X-CSRF-Token header.
        httponly=False,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )
    return token


def clear_csrf_cookie(response: Response) -> None:
    """Drop the CSRF cookie (logout, paired with ``clear_session_cookie``).

    Mirror the set-time attributes (Safari delete-attr-mismatch hygiene,
    same reason as ``clear_session_cookie``).
    """
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=_secure_cookie(),
        samesite="lax",
        httponly=True,
    )


async def require_csrf(request: Request) -> None:
    """FastAPI dependency that enforces the double-submit token.

    For safe methods (GET/HEAD/OPTIONS) this is a no-op so we can attach
    it broadly without changing read semantics.  For everything else we
    require both the cookie and the header to be present and equal.

    The 403 detail string is stable across the three failure modes so a
    defender's log search ("csrf token") finds them all without leaking
    which leg of the comparison failed.
    """
    if request.method.upper() in _SAFE_METHODS:
        return

    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    header = request.headers.get(CSRF_HEADER_NAME)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf token missing or invalid",
        )
