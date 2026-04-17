"""Integration tests.

Real tests live here once the auth, DB, and Sheets layers are wired.
Tracking tests (see docs/testing.md) that must appear:

- test_unauthorized_domain_rejected
- test_allowlist_enforced
- test_viewer_cannot_read_out_of_scope_hub
- test_audit_log_append_only
- test_sheet_fallback_to_last_known_good
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.skip(reason="Integration suite not wired yet; see HANDOFF.md")
def test_placeholder() -> None:
    assert True
