"""FastAPI application entry point.

The real routes, auth, and report pipeline are not implemented yet. This
module wires up the minimum skeleton: health endpoints, CORS, request IDs,
and structured logging. See HANDOFF.md at the repo root.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.report.routes import router as report_router

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

configure_logging()
log = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Symphony TA Hiring Report",
        version="0.0.1",
        docs_url="/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
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
