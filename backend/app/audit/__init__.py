"""Append-only audit log.

TODO: implement
- audit_log table write helpers, one per event type
  (login, report_view, config_edit, comment_edit, role_change, user_add, user_remove).
- Writes happen in the same transaction as the mutation they describe.
- No update or delete paths. The table is append-only.
"""
