"""FastAPI application entry point.

The real routes, auth, and report pipeline are not implemented yet. This
module wires up the minimum skeleton: health endpoints, CORS, request IDs,
and structured logging. See HANDOFF.md at the repo root.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.comments.routes import router as comments_router
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.report.routes import router as report_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Validate critical config at startup; block deployment if misconfigured."""
    settings = get_settings()

    if settings.app_env == "prod":
        # In production the two restricted DB role URLs MUST be explicitly
        # configured.  Falling back to the app role silently breaks the privacy
        # contract of ADR 0010 (NFR-PRIV-4, NFR-PRIV-5).
        missing = [
            name
            for name, val in [
                ("DATABASE_URL_ERASURE", settings.database_url_erasure),
                ("DATABASE_URL_SWEEP", settings.database_url_sweep),
            ]
            if not val.strip()
        ]
        if missing:
            raise RuntimeError(
                f"Production startup blocked: {', '.join(missing)} must be set "
                "(ADR 0010 — three-role DB grant model). "
                "See .env.example and docs/adr/0010-audit-log-grants.md."
            )
        # Belt-and-suspenders: the role URLs must not be the same as the app URL.
        for name, val in [
            ("DATABASE_URL_ERASURE", settings.database_url_erasure),
            ("DATABASE_URL_SWEEP", settings.database_url_sweep),
        ]:
            if val.strip() == settings.database_url.strip():
                raise RuntimeError(
                    f"Production startup blocked: {name} must point to the "
                    "restricted role, not the app role (ADR 0010)."
                )

    log.info(
        "engine_role_resolved",
        extra={
            "app_env": settings.app_env,
            "erasure_url_set": bool(settings.database_url_erasure.strip()),
            "sweep_url_set": bool(settings.database_url_sweep.strip()),
        },
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Symphony TA Hiring Report",
        version="0.0.1",
        docs_url="/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    def readyz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(comments_router)
    app.include_router(report_router)

    # The e2e router is a session-seed backdoor for Playwright tests.
    # It MUST NOT be registered in production.  The import itself is gated so
    # the symbols never load outside APP_ENV=test.  Strict equality — not
    # ``in``, not ``startswith``, no case-folding.
    if settings.app_env == "test":
        from app.e2e.routes import router as e2e_router  # noqa: PLC0415

        app.include_router(e2e_router)

    log.info("app_started", extra={"app_env": settings.app_env})
    return app


app = create_app()
