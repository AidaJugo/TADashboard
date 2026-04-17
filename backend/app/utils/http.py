"""Small HTTP helpers shared by handlers and dependencies.

Currently holds :func:`client_ip`, which was previously duplicated in
``app.auth.routes``, ``app.report.routes`` and ``app.admin.routes``.  The
duplication was flagged in the M4 review (nice-to-have #1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


def client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    ``X-Forwarded-For`` wins when a proxy (ALB, Cloudflare, reverse proxy)
    sits in front of the app; we take the first entry since later entries
    are the proxy chain.  Falls back to the direct peer address exposed by
    Starlette / ``httpx``.  Returns ``None`` rather than an empty string so
    the audit writer can distinguish "unknown" from "empty".
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip() or None
    peer = request.client
    return peer.host if peer else None
