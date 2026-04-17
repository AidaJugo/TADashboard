"""Report aggregation pipeline.

TODO: port from legacy/generate_report.py:
- compute_period() and build_period_data() to typed, unit-tested functions.
- Apply the hub-scoping filter from app.authz before aggregation (not after).
- Read rows from app.sheets.client.load_rows() or the last-known-good snapshot
  on failure (see PRD FR-REPORT-6 and ADR 0002).
"""
