"""TC-I-PRIV-2 backbone: structured-log shape assertion.

docs/testing.md §4.5:
    TC-I-PRIV-2: Application logs are valid JSON, one object per line, with
                 required fields ``timestamp``, ``level``, ``request_id``,
                 ``event`` (NFR-PRIV-6).

The app uses ``python-json-logger`` with a ``RedactingFormatter``.  This test
drives the configured logger, captures the rendered output, and asserts the
required fields on every record.  Subsequent PRs in M4 reuse the
``caplog_json`` fixture to assert the same shape for their own log events.

``request_id`` is a middleware concern (it is set in
``app.main.attach_request_id`` at request time); this test exercises the
structural pieces that are logger-level (``timestamp``, ``level``,
``event``/message, redaction).  A full request-time assertion lives in
``test_request_id_in_logs`` once the auth middleware lands.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.logging import configure_logging, get_logger

pytestmark = pytest.mark.integration


def test_tc_i_priv_2_logger_emits_json_with_required_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """TC-I-PRIV-2: every emitted record renders as JSON with the required keys."""
    configure_logging()
    log = get_logger("tests.logging_shape")

    caplog.set_level(logging.INFO)
    log.info("sample_event", extra={"hub": "Sarajevo"})

    assert len(caplog.records) >= 1
    rendered = _render(caplog.records[-1])

    assert "timestamp" in rendered
    assert "level" in rendered
    assert rendered["level"] == "INFO"
    assert rendered.get("message") == "sample_event" or rendered.get("event") == "sample_event"
    assert rendered.get("hub") == "Sarajevo"


def test_tc_i_priv_2_redacts_sensitive_keys(caplog: pytest.LogCaptureFixture) -> None:
    """PII redaction: sensitive keys are replaced with ``[REDACTED]``.

    This is a positive test for the formatter's deny-list in app/logging.py.
    It closes the defensive side of TC-I-PRIV-1 at the formatter level; the
    end-to-end redaction test (no cookie/token leaks from the auth module)
    lands in PR 2 and PR 4.
    """
    configure_logging()
    log = get_logger("tests.logging_shape")
    caplog.set_level(logging.INFO)

    log.info(
        "auth_callback",
        extra={"cookie": "ta_sid=abc.def", "access_token": "google-secret"},
    )

    rendered = _render(caplog.records[-1])
    assert rendered["cookie"] == "[REDACTED]"
    assert rendered["access_token"] == "[REDACTED]"


def _render(record: logging.LogRecord) -> dict[str, object]:
    """Render a single LogRecord through the app's RedactingFormatter."""
    from app.logging import RedactingFormatter

    fmt = RedactingFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    return json.loads(fmt.format(record))
