#!/usr/bin/env bash
# init-db.sh — applied by the Postgres Docker entrypoint on first container
# creation (postgres-data volume does not yet exist).
#
# Runs grants.sql (idempotent role/grant bootstrap for ADR 0010) and sets
# dev-only passwords for the three DB roles.
#
# Re-running manually:
#   docker compose exec db psql -U postgres -d ta_report -f /docker-entrypoint-initdb.d/grants.sql
#   docker compose exec db psql -U postgres -d ta_report -f /docker-entrypoint-initdb.d/init-db.sh
#
# WARNING: passwords here are dev-only.  Production uses secrets injected at
# deploy time (ADR 0008) — these passwords must NOT appear in prod environments.

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -f /docker-entrypoint-initdb.d/01_grants.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
    ALTER ROLE ta_report_app       PASSWORD 'ta_report_app_dev'       LOGIN;
    ALTER ROLE ta_report_erasure   PASSWORD 'ta_report_erasure_dev'   LOGIN;
    ALTER ROLE ta_report_sweep     PASSWORD 'ta_report_sweep_dev'     LOGIN;
    -- Allow each role to connect to the database.
    GRANT CONNECT ON DATABASE ta_report TO ta_report_app, ta_report_erasure, ta_report_sweep;
EOSQL
