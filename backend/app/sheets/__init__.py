"""Google Sheets client (see ADR 0003).

TODO: implement
- Service-account-authenticated client using gspread.
- load_rows(): fetches rows using the admin-configured column mapping
  (see PRD FR-CONFIG-2).
- Schema validation: unknown required columns raise a typed error,
  the app falls back to the last-known-good snapshot stored in Postgres.
- Short in-process TTL cache, invalidated on explicit "refresh now".
"""
