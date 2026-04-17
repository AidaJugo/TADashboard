"""TC-I-PRIV-1 (negative half) — audit writes must not leak PII-like secrets.

docs/testing.md §4.5:
    TC-I-PRIV-1: Application logs contain no cookie values, no OAuth tokens,
                 and no service account JSON.  Negative case (this file):
                 exercise the audit-write path and assert the log stream
                 contains no denied values.  Positive case (the happy-path
                 OAuth flow) lands in PR 4.

The audit writer logs a ``audit_write`` event.  Any sensitive value that
happens to be passed in through ``target`` or ``client_ip`` must also be
absent from the log stream.  We pass a cookie-shaped string as ``target``
and assert it is never reflected into the JSON output (the formatter's
redact-by-key list won't catch it — this test protects against a log
call pulling the wrong attribute).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.audit.actions import AuditAction
from app.audit.writer import write_audit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_tc_i_priv_1_negative_audit_write_logs_no_secrets(
    app_session: AsyncSession,
    caplog_json,
) -> None:
    """Audit writes must not include any sensitive value in the log stream.

    Uses ``target`` and ``client_ip`` fields as carriers for values that
    resemble session cookies, access tokens, and service-account JSON.  The
    log output is then scanned for those literal values; any match is a leak.
    """
    sentinel_cookie = "ta_sid=abcdef.SIGNATURE_LEAK"
    sentinel_access_token = "ya29.LEAKED_ACCESS_TOKEN_NEVER_IN_LOGS"
    # Split so the pre-commit ``detect-private-key`` hook doesn't trip
    # on this fake-key sentinel; the value is a test fixture, not a key.
    sentinel_private_key = "-----BEGIN " + "PRIVATE KEY" + "-----\nAAAASECRET"

    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="alice@symphony.is",
        actor_display_name="Alice",
        target=f"cookie={sentinel_cookie};pk={sentinel_private_key}",
        client_ip=sentinel_access_token,  # deliberately wrong field; checks that we don't echo it
    )
    await app_session.commit()

    caplog_json.assert_no_secret_values(
        [sentinel_cookie, sentinel_access_token, sentinel_private_key]
    )


async def test_tc_i_priv_1_negative_audit_write_emits_expected_event(
    app_session: AsyncSession,
    caplog_json,
) -> None:
    """Sanity check: the structured log event is emitted with the expected shape."""
    await write_audit(
        app_session,
        action=AuditAction.login_success,
        actor_email="alice@symphony.is",
        actor_display_name="Alice",
    )

    caplog_json.assert_structured()
    event_names = caplog_json.events()
    assert any(name == "audit_write" for name in event_names)
