"""FastAPI application entry point.

The real routes, auth, and report pipeline are not implemented yet. This
module wires up the minimum skeleton: health endpoints, CORS, request IDs,
and structured logging. See HANDOFF.md at the repo root.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging import configure_logging, get_logger

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

    log.info("app_started", extra={"app_env": settings.app_env})
    return app


app = create_app()
