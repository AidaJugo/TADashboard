"""Canonical audit action names (FR-AUDIT-1, FR-AUDIT-3).

Every audit row's ``action`` column must be one of these constants.  Treating
them as a closed vocabulary gives us:

- grepability of which handlers write which events,
- a single point to update when a new event type is introduced,
- a simple fixture in tests (``AuditAction.<name>``) rather than stringly-typed
  assertions.

Do not inline raw strings in audit calls.  If a new event type is needed, add
it here first.
"""

from __future__ import annotations

from typing import Final


class AuditAction:
    """Namespace for audit action name constants.

    Using a plain class (rather than an ``Enum``) keeps the value a bare ``str``
    so it can be inserted into ``audit_log.action`` (``VARCHAR(100)``) without
    any ``.value`` unwrapping at call sites.
    """

    # Authentication (ADR 0004, FR-AUTH-1..5)
    login_success: Final[str] = "login_success"
    login_denied_domain: Final[str] = "login_denied_domain"
    login_denied_email_unverified: Final[str] = "login_denied_email_unverified"
    login_denied_allowlist: Final[str] = "login_denied_allowlist"
    login_denied_inactive: Final[str] = "login_denied_inactive"
    logout: Final[str] = "logout"

    # Authorization (FR-AUTHZ-2, FR-AUTHZ-4)
    role_change: Final[str] = "role_change"
    hub_scope_change: Final[str] = "hub_scope_change"
    hub_scope_violation: Final[str] = "hub_scope_violation"
    #: Non-admin caller hit an admin-only route, or a handler that enforces
    #: ``require_role`` at the dependency layer.  Written by
    #: ``app.authz.roles.require_role`` before the 403 surfaces (FR-AUTHZ-2,
    #: TC-S-3).  ``target`` is ``f"{METHOD} {path}"``.
    access_denied: Final[str] = "access_denied"
    #: Admin invoked ``POST /api/admin/users/{id}/revoke-sessions`` to close
    #: every active session of a user (ADR 0012, TC-I-AUTH-10).  ``target``
    #: is ``f"user:{uid}"``.
    admin_revoke_sessions: Final[str] = "admin_revoke_sessions"

    # User lifecycle (FR-USER-*; admin UI lands in M5)
    user_created: Final[str] = "user_created"
    user_updated: Final[str] = "user_updated"
    user_deactivated: Final[str] = "user_deactivated"
    user_reactivated: Final[str] = "user_reactivated"
    user_erased: Final[str] = "user_erased"

    # Report pipeline (FR-REPORT-7, FR-AUDIT-1)
    #: Written when a user successfully views the report.  This is a read-only
    #: audit event so it is NOT bound to the same-transaction rule that applies
    #: to mutations; the audit row is written in its own DB commit after the
    #: report data is returned.  Confirmed acceptable in the M5 planning
    #: session (see PR description for context).
    report_view: Final[str] = "report_view"
    #: Meaning: a refresh was *attempted*.  The row is written before any
    #: Google Sheets call so it survives a refresh that fails halfway
    #: through.  M5 may add ``sheet_refresh_success`` /
    #: ``sheet_refresh_failed`` once the actual fetch lands and we have a
    #: real outcome to record.
    sheet_refresh: Final[str] = "sheet_refresh"

    # Config edits (FR-CONFIG-*)
    config_edit: Final[str] = "config_edit"
    column_mapping_edit: Final[str] = "column_mapping_edit"
    hub_pair_edit: Final[str] = "hub_pair_edit"

    # Comments / notes (FR-COMMENT-*, FR-NOTE-*)
    comment_created: Final[str] = "comment_created"
    comment_updated: Final[str] = "comment_updated"
    comment_deleted: Final[str] = "comment_deleted"
    note_created: Final[str] = "note_created"
    note_updated: Final[str] = "note_updated"
    note_deleted: Final[str] = "note_deleted"

    # Report export (FR-REPORT-10, ADR 0009)
    #: Written after every successful PDF export.  Read-only event; audit row
    #: is written in its own transaction (same pattern as report_view).
    #: ``target`` captures ``year=<y> period=<p> hubs=<server-resolved-set>``.
    report_export_pdf: Final[str] = "report_export_pdf"

    # Maintenance jobs (NFR-PRIV-4, NFR-PRIV-2, ADR 0010)
    #: Written when an admin triggers the retention sweep via the API trigger
    #: endpoint.  The sweep function itself logs to stdout; this row records
    #: the human actor who initiated it.
    sweep_triggered: Final[str] = "sweep_triggered"

    # Bootstrap / deployment (FR-AUTH-3, TC-I-AUTH-11)
    #: Written by ``python -m app.admin.bootstrap`` each time it seeds an admin.
    #: actor_email = "system", actor_display_name = "bootstrap".
    #: target = "user:<uuid> email:<email> created|updated"
    admin_seeded: Final[str] = "admin_seeded"


#: Full set of known audit actions — used by the writer to validate a string
#: against the closed vocabulary before insert.
ALL_AUDIT_ACTIONS: frozenset[str] = frozenset(
    v for k, v in vars(AuditAction).items() if not k.startswith("_") and isinstance(v, str)
)
