"""Signed session cookie encoding / decoding.

The browser only ever holds a signed session **id**, not any claims
(FR-AUTH-4, ADR 0004).  Signature uses
:class:`itsdangerous.URLSafeTimedSerializer` keyed on
``Settings.session_secret_key``.

Cookie attributes (all set at write time; read code does not need them):

- ``Name``      — ``ta_sid``
- ``HttpOnly``  — True  (no JS access)
- ``Secure``    — True  (HTTPS only; dev uses ``SESSION_COOKIE_INSECURE=1``)
- ``SameSite``  — Lax   (allows top-level GET navigation back from OAuth)
- ``Path``      — ``/``
- ``Max-Age``   — ``SESSION_ABSOLUTE_TIMEOUT_MINUTES * 60``

The signature carries a timestamp; we reject any cookie older than the
absolute timeout even if the DB session row were somehow still alive.  The
session row itself is the source of truth for timeouts (see
:mod:`app.auth.sessions`), this is belt-and-braces.
"""

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Final

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

if TYPE_CHECKING:
    from fastapi import Response

#: Cookie name for the signed session id.  Do not rename without an ADR.
SESSION_COOKIE_NAME: Final[str] = "ta_sid"

#: Serializer salt.  Pinning the salt means rotating the secret key alone is
#: enough to invalidate all existing cookies (FR-AUTH-4 secret rotation).
_SERIALIZER_SALT: Final[str] = "ta_report.session.v1"


class InvalidCookieError(ValueError):
    """Raised when the signed cookie value fails verification."""


def _secure_cookie() -> bool:
    """True unless explicitly disabled for local HTTP dev via SESSION_COOKIE_INSECURE=1."""
    return os.environ.get("SESSION_COOKIE_INSECURE", "0") != "1"


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(
        secret_key=settings.session_secret_key,
        salt=_SERIALIZER_SALT,
    )


def sign_session_id(session_id: uuid.UUID) -> str:
    """Return a signed cookie value carrying ``session_id``."""
    return _serializer().dumps(str(session_id))


def verify_cookie(cookie_value: str) -> uuid.UUID:
    """Return the session id embedded in ``cookie_value`` or raise.

    Verifies both the HMAC signature and the absolute-timeout age stamped
    into the cookie itself.  Callers still have to check the DB session row
    for idle timeout, revocation, and user ``is_active``.
    """
    max_age_seconds = get_settings().session_absolute_timeout_minutes * 60
    try:
        raw = _serializer().loads(cookie_value, max_age=max_age_seconds)
    except SignatureExpired as exc:
        raise InvalidCookieError("session cookie expired") from exc
    except BadSignature as exc:
        raise InvalidCookieError("session cookie signature invalid") from exc

    if not isinstance(raw, str):
        raise InvalidCookieError("session cookie payload has unexpected type")
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise InvalidCookieError("session cookie payload is not a UUID") from exc


def set_session_cookie(response: Response, session_id: uuid.UUID) -> None:
    """Write the signed session cookie onto ``response`` with the correct flags.

    Development override: setting ``SESSION_COOKIE_INSECURE=1`` disables the
    ``Secure`` flag so local non-HTTPS dev can run.  Production must never
    set this env var.
    """
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session_id(session_id),
        max_age=settings.session_absolute_timeout_minutes * 60,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from ``response`` (logout).

    Mirror the set-time attributes so Safari (which sometimes refuses to
    clear a cookie when delete-time attrs disagree with set-time attrs)
    drops it reliably.  Server-side revocation is the source of truth;
    this is just hygiene.
    """
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_secure_cookie(),
        samesite="lax",
        httponly=True,
    )
