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
-- Wrapped in DO blocks so this file is safe to run during Docker DB init,
-- before Alembic migrations have created the tables. The backend entrypoint
-- re-runs this file after `alembic upgrade head` to apply the full grants.

DO $$ BEGIN
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
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'tables not yet created; skipping app role table grants (will be applied after alembic upgrade head)';
END $$;

DO $$ BEGIN
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ta_report_app;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
  GRANT SELECT, INSERT ON TABLE audit_log TO ta_report_app;
  REVOKE UPDATE, DELETE ON TABLE audit_log FROM ta_report_app;
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'audit_log not yet created; skipping audit_log grants';
END $$;

-- ---------------------------------------------------------------------------
-- ta_report_erasure: column-restricted UPDATE on audit_log PII fields only
-- ---------------------------------------------------------------------------

DO $$ BEGIN
  GRANT SELECT ON TABLE audit_log TO ta_report_erasure;
  GRANT UPDATE (actor_email, actor_display_name) ON TABLE audit_log TO ta_report_erasure;
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'audit_log not yet created; skipping erasure role grants';
END $$;

-- ---------------------------------------------------------------------------
-- ta_report_sweep: DELETE only on audit_log (retention sweep, ADR 0006)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
  GRANT SELECT, DELETE ON TABLE audit_log TO ta_report_sweep;
EXCEPTION WHEN undefined_table THEN
  RAISE NOTICE 'audit_log not yet created; skipping sweep role grants';
END $$;
