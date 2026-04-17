"""Google Workspace OIDC login (FR-AUTH-1..5, ADR 0004).

The public surface is deliberately small:

- :class:`OIDCClient` — protocol the callback handler depends on; tests
  supply a fake implementation through FastAPI's ``dependency_overrides``.
- :class:`GoogleOIDCClient` — production implementation.  Hits Google's
  token endpoint (``https://oauth2.googleapis.com/token``) via ``httpx``
  and verifies the returned id_token via :mod:`google.oauth2.id_token`.
- :func:`build_authorization_url` — the URL we redirect unauthenticated
  browsers to at the start of the flow.
- :func:`resolve_login` — pure function that runs the accept/reject
  decision tree once the id_token has been verified.  Input: verified
  claims + DB.  Output: ``LoginResolution`` variant carrying the outcome.
  The HTTP handler translates the resolution into a response.

Acceptance rules (in order, ADR 0004 §4):

1. ``email_verified`` must be truthy.          → ``login_denied_email_unverified``
2. ``hd`` must equal ``Settings.allowed_hd``.  → ``login_denied_domain``
3. Email must exist in ``users`` and be active.→ ``login_denied_allowlist``
   (``login_denied_inactive`` when the row exists but ``is_active=False``)
4. Otherwise accept.                           → ``login_success``

Every rejection writes an audit row via the caller; ``resolve_login``
returns the intended audit action so the handler does not need to
re-derive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypedDict
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import select

from app.audit.actions import AuditAction
from app.config import get_settings
from app.db.models import User
from app.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class IdTokenClaims(TypedDict, total=False):
    """Subset of the Google id_token claims we read.

    ``total=False`` because ``hd`` is only present on Workspace accounts
    and ``email_verified`` might be missing if Google changes the API; we
    treat missing just like False (see :func:`resolve_login`).
    """

    sub: str
    email: str
    email_verified: bool
    hd: str
    name: str


class OAuthError(Exception):
    """Raised when the OAuth exchange or id_token verification fails."""


class OIDCClient(Protocol):
    """Async contract between the route handler and whatever talks to Google.

    The production implementation is :class:`GoogleOIDCClient`; tests
    provide a fake that returns scripted claims (see the test's
    ``install_fake_oidc`` fixture).
    """

    async def exchange_code(self, *, code: str, redirect_uri: str) -> str:
        """Swap ``code`` for a raw id_token JWT string."""
        ...

    async def verify_id_token(self, id_token: str) -> IdTokenClaims:
        """Validate signature / audience / issuer and return the claims."""
        ...


# ---------------------------------------------------------------------------
# Authorization URL builder (pure)
# ---------------------------------------------------------------------------


_GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 — URL, not a secret


def build_authorization_url(*, state: str, redirect_uri: str) -> str:
    """Return the Google authorization URL the browser should be redirected to.

    We pass ``hd=<allowed_hd>`` as a hint so Google already filters to
    Symphony accounts on the selector — but we still verify ``hd``
    server-side on the callback (FR-AUTH-1, ADR 0004).
    """
    settings = get_settings()
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "hd": settings.allowed_hd,
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"{_GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Production OIDC client
# ---------------------------------------------------------------------------


class GoogleOIDCClient:
    """Talks to Google's token endpoint via httpx and verifies id_tokens.

    ``verify_id_token`` delegates to ``google.oauth2.id_token`` which
    handles JWKS fetching, signature verification, audience + issuer
    checks, and clock skew tolerance.  We never log the raw tokens
    (NFR-PRIV / TC-I-PRIV-1).
    """

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def exchange_code(self, *, code: str, redirect_uri: str) -> str:
        settings = get_settings()
        data = {
            "code": code,
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        try:
            resp = await self._client.post(_GOOGLE_TOKEN_ENDPOINT, data=data)
        except httpx.HTTPError as exc:  # pragma: no cover — network failure path
            raise OAuthError("token endpoint unreachable") from exc
        if resp.status_code != httpx.codes.OK:
            # Do not log the response body — may contain a refresh_token.
            log.warning(
                "oauth_token_exchange_failed",
                extra={"status_code": resp.status_code},
            )
            raise OAuthError(f"token exchange failed: HTTP {resp.status_code}")
        payload: dict[str, Any] = resp.json()
        token = payload.get("id_token")
        if not isinstance(token, str) or not token:
            raise OAuthError("token response missing id_token")
        return token

    async def verify_id_token(self, id_token: str) -> IdTokenClaims:
        settings = get_settings()
        try:
            raw: dict[str, Any] = google_id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                id_token,
                google_requests.Request(),
                settings.google_oauth_client_id,
            )
        except ValueError as exc:
            raise OAuthError("id_token failed verification") from exc
        return _narrow_claims(raw)


def _narrow_claims(raw: dict[str, Any]) -> IdTokenClaims:
    """Copy only the keys we care about so the TypedDict stays honest."""
    out: IdTokenClaims = {}
    for key in ("sub", "email", "email_verified", "hd", "name"):
        if key in raw:
            out[key] = raw[key]
    return out


# ---------------------------------------------------------------------------
# Pure resolution (accept / reject decision)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoginResolution:
    """Outcome of applying the login policy to a verified set of claims.

    ``accepted=True`` means the caller should create a session for
    :attr:`user`.  ``accepted=False`` means the caller should return the
    :attr:`message` to the browser and write an audit row with
    :attr:`audit_action` + the claims we learned about the attempt.
    """

    accepted: bool
    audit_action: str
    message: str
    user: User | None = None
    email: str | None = None
    display_name: str | None = None


async def resolve_login(
    db: AsyncSession,
    claims: IdTokenClaims,
) -> LoginResolution:
    """Apply the accept/reject rules to a verified id_token.

    Order matters — we surface the most specific failure first so the
    audit trail reflects *why* a login was denied.
    """
    settings = get_settings()

    email = claims.get("email")
    display_name = claims.get("name") or email or "unknown"

    if not claims.get("email_verified"):
        return LoginResolution(
            accepted=False,
            audit_action=AuditAction.login_denied_email_unverified,
            message="Your Google account's email is not verified. Contact IT.",
            email=email,
            display_name=display_name,
        )

    hd = claims.get("hd")
    if hd != settings.allowed_hd:
        return LoginResolution(
            accepted=False,
            audit_action=AuditAction.login_denied_domain,
            message=(
                f"Only {settings.allowed_hd} accounts can sign in. "
                "Please use your Symphony account."
            ),
            email=email,
            display_name=display_name,
        )

    if not email:
        return LoginResolution(
            accepted=False,
            audit_action=AuditAction.login_denied_allowlist,
            message="Access denied.",
            email=None,
            display_name=display_name,
        )

    stmt = select(User).where(User.email == email)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        return LoginResolution(
            accepted=False,
            audit_action=AuditAction.login_denied_allowlist,
            message="Access denied. Contact an administrator for access.",
            email=email,
            display_name=display_name,
        )
    if not user.is_active:
        return LoginResolution(
            accepted=False,
            audit_action=AuditAction.login_denied_inactive,
            message="Your account has been deactivated. Contact IT.",
            email=email,
            display_name=display_name,
            user=user,
        )

    return LoginResolution(
        accepted=True,
        audit_action=AuditAction.login_success,
        message="ok",
        user=user,
        email=email,
        display_name=user.display_name,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency (overridable in tests)
# ---------------------------------------------------------------------------


def get_oidc_client() -> OIDCClient:
    """Return the production OIDC client.

    Tests call ``app.dependency_overrides[get_oidc_client] = lambda: fake``
    to inject a scripted fake without hitting the real Google endpoint.
    Returning a fresh client per call is fine because ``GoogleOIDCClient``
    lazy-instantiates the underlying ``httpx.AsyncClient``; for production
    load we would switch to a module-level singleton.
    """
    return GoogleOIDCClient()
