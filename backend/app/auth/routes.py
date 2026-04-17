"""Auth-facing HTTP routes.

- ``GET  /api/auth/login``    — redirect to Google with a CSRF-bound state.
- ``GET  /api/auth/callback`` — handle the OIDC callback, run the accept/
                                reject policy, write an audit row for every
                                outcome (FR-AUTH-1..5, FR-AUDIT-1).
- ``GET  /api/auth/me``       — identity probe, 401 when not signed in.
- ``POST /api/auth/logout``   — revoke the current session server-side and
                                clear the cookie (FR-AUTH-5).

The callback depends on :func:`app.auth.oauth.get_oidc_client` so tests
can override the network-facing half with a scripted fake.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

# Runtime imports required for FastAPI dependency introspection — see
# ``app/auth/deps.py`` for the full explanation.
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.audit.actions import AuditAction
from app.audit.writer import write_audit
from app.auth.cookies import (
    SESSION_COOKIE_NAME,
    InvalidCookieError,
    _secure_cookie,
    clear_session_cookie,
    set_session_cookie,
    verify_cookie,
)
from app.auth.csrf import clear_csrf_cookie, require_csrf, set_csrf_cookie
from app.auth.oauth import (
    OAuthError,
    OIDCClient,
    build_authorization_url,
    get_oidc_client,
    resolve_login,
)
from app.auth.sessions import create_session, revoke_all_sessions_for, revoke_session
from app.authz.roles import CurrentUser  # noqa: TC001 — used in handler signatures
from app.config import get_settings
from app.db.session import get_db
from app.logging import get_logger
from app.utils.http import client_ip

log = get_logger(__name__)

#: CSRF cookie for the OAuth ``state`` parameter.  Short-lived (5 min);
#: cleared on callback success or failure.
_OAUTH_STATE_COOKIE = "ta_oauth_state"
_OAUTH_STATE_MAX_AGE_SECONDS = 300

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# /login — start the OAuth dance
# ---------------------------------------------------------------------------


@router.get("/login")
async def login_start(request: Request) -> RedirectResponse:
    """Redirect the browser to Google with a fresh CSRF state.

    The state is stored in a short-lived, signature-agnostic cookie
    (HttpOnly + Secure + SameSite=Lax).  We verify equality on callback;
    an attacker that cannot read the cookie cannot replay it.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    redirect_url = build_authorization_url(
        state=state, redirect_uri=settings.google_oauth_redirect_uri
    )
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _set_state_cookie(response, state)
    return response


# ---------------------------------------------------------------------------
# /callback — Google redirects the browser back here with ?code=&state=
# ---------------------------------------------------------------------------


@router.get("/callback")
async def oauth_callback(  # noqa: PLR0913 — FastAPI deps + query args
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    oidc: Annotated[OIDCClient, Depends(get_oidc_client)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Handle the Google OAuth callback.

    High level::

        if error:                         → 400 (user cancelled / Google reported)
        verify(state)                     → 400 on CSRF mismatch
        token = exchange(code)            → 400 on token-exchange failure
        claims = verify_id_token(token)   → 400 on bad token
        resolution = resolve_login(claims)
        if not resolution.accepted:
            write audit row; 403 with resolution.message
        else:
            create session + audit + cookie; 302 to app_base_url

    Every accept/reject writes exactly one audit row, in the same DB
    transaction as the state change (``get_db`` commits on success).
    """
    settings = get_settings()

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"google oauth error: {error}",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing code or state",
        )

    expected = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not expected or not secrets.compare_digest(state, expected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid state",
        )

    try:
        id_token = await oidc.exchange_code(
            code=code, redirect_uri=settings.google_oauth_redirect_uri
        )
        claims = await oidc.verify_id_token(id_token)
    except OAuthError as exc:
        log.warning("oauth_callback_failed", extra={"reason": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolution = await resolve_login(db, claims)

    if not resolution.accepted:
        await write_audit(
            db,
            action=resolution.audit_action,
            actor_id=resolution.user.id if resolution.user else None,
            actor_email=resolution.email or "unknown",
            actor_display_name=resolution.display_name or "unknown",
            target=None,
            client_ip=client_ip(request),
        )
        # Return (don't raise).  ``get_db`` commits on normal return, so
        # the audit row lands in the same transaction as any other work
        # the handler did.  No manual ``db.commit()`` — that was the
        # double-commit noted in the M4 review.  The hub-scope-violation
        # path in ``get_report`` has to ``raise HTTPException`` because
        # it can't set cookies; here we need to clear ``ta_oauth_state``
        # on the response, so return is the right shape.
        response = Response(
            content=resolution.message,
            status_code=status.HTTP_403_FORBIDDEN,
            media_type="text/plain",
        )
        _clear_state_cookie(response)
        return response

    assert resolution.user is not None  # noqa: S101 — enforced by accepted=True
    # Session rotation: close every prior live session of this user before
    # minting a fresh one.  Prevents a leaked or stolen cookie from
    # out-living a re-authentication.
    await revoke_all_sessions_for(db, resolution.user.id)
    session_row = await create_session(
        db,
        user=resolution.user,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await write_audit(
        db,
        action=AuditAction.login_success,
        actor_id=resolution.user.id,
        actor_email=resolution.user.email,
        actor_display_name=resolution.user.display_name,
        target=None,
        client_ip=client_ip(request),
    )

    response = RedirectResponse(url=settings.app_base_url, status_code=status.HTTP_302_FOUND)
    set_session_cookie(response, session_row.id)
    # Mint a fresh CSRF token paired with the session cookie.  The SPA
    # reads ``ta_csrf`` from JS and echoes it as ``X-CSRF-Token`` on
    # every state-changing request (NFR-SEC-2, see app.auth.csrf).
    set_csrf_cookie(response)
    _clear_state_cookie(response)
    return response


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.get("/me")
async def me(user: CurrentUser) -> dict[str, object]:
    """Return the signed-in user's identity.

    401 is raised by :func:`get_current_user` when the session is invalid;
    nothing here needs to check that again.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.value,
    }


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> Response:
    """Revoke the current session and clear the cookie (FR-AUTH-5, TC-I-AUTH-7).

    Reading the user via ``CurrentUser`` guarantees we only act on a live
    session (401 otherwise).  The cookie still carries the session id we
    need to revoke — so we re-read it here rather than threading session
    state through the dependency.
    """
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if raw:
        try:
            session_id = verify_cookie(raw)
        except InvalidCookieError:
            session_id = None
        if session_id is not None:
            await revoke_session(db, session_id)
            await write_audit(
                db,
                action=AuditAction.logout,
                actor_id=user.id,
                actor_email=user.email,
                actor_display_name=user.display_name,
                client_ip=client_ip(request),
            )

    clear_session_cookie(response)
    clear_csrf_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def _set_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=_OAUTH_STATE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )


def _clear_state_cookie(response: Response) -> None:
    response.delete_cookie(key=_OAUTH_STATE_COOKIE, path="/")


__all__ = ["router"]
