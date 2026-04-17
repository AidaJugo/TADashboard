-- grants.sql — idempotent DB role + grant bootstrap for the TA Hiring Report Platform
--
-- Run ONCE before `alembic upgrade head` at deploy time, and after any schema migration
-- that creates new tables. Re-running is safe (all statements are idempotent).
--
-- See docs/adr/0010-audit-log-grants.md for the rationale.
--
-- Usage:
--   psql "$DATABASE_URL" -f backend/grants.sql
--
-- The DATABASE_URL used here must belong to the DB owner (superuser or the role
-- that owns the ta_report database). Do NOT run this as ta_report_app.

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------

-- Normal app serving path: SELECT + INSERT + UPDATE + DELETE on most tables,
-- but only INSERT + SELECT on audit_log (append-only, ADR 0010).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ta_report_app') THEN
    CREATE ROLE ta_report_app WITH LOGIN;
  END IF;
END $$;

-- Right-to-erasure job: can only UPDATE the two PII columns on audit_log (NFR-PRIV-5).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ta_report_erasure') THEN
    CREATE ROLE ta_report_erasure WITH LOGIN;
  END IF;
END $$;

-- Retention sweep job: can only DELETE from audit_log (ADR 0006).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ta_report_sweep') THEN
    CREATE ROLE ta_report_sweep WITH LOGIN;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Schema usage
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA public TO ta_report_app, ta_report_erasure, ta_report_sweep;

-- ---------------------------------------------------------------------------
-- ta_report_app: full CRUD on all tables EXCEPT audit_log
-- ---------------------------------------------------------------------------

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  users,
  user_hub_scopes,
  sessions,
  config_kv,
  column_mappings,
  comments,
  benchmark_notes,
  city_notes,
  hub_pairs,
  sheet_snapshot
TO ta_report_app;

-- Sequences (needed for INSERT with SERIAL / DEFAULT nextval)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ta_report_app;

-- audit_log: INSERT + SELECT only. No UPDATE, no DELETE.
GRANT SELECT, INSERT ON TABLE audit_log TO ta_report_app;

-- Explicitly revoke UPDATE and DELETE to make intent clear (in case a
-- prior broad GRANT was issued). REVOKE is a no-op if the privilege was
-- never granted.
REVOKE UPDATE, DELETE ON TABLE audit_log FROM ta_report_app;

-- ---------------------------------------------------------------------------
-- ta_report_erasure: column-restricted UPDATE on audit_log PII fields only
-- ---------------------------------------------------------------------------

GRANT SELECT ON TABLE audit_log TO ta_report_erasure;
GRANT UPDATE (actor_email, actor_display_name) ON TABLE audit_log TO ta_report_erasure;

-- ---------------------------------------------------------------------------
-- ta_report_sweep: DELETE only on audit_log (retention sweep, ADR 0006)
-- ---------------------------------------------------------------------------

GRANT SELECT, DELETE ON TABLE audit_log TO ta_report_sweep;
