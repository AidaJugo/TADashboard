#!/usr/bin/env bash
set -euo pipefail

UV=/usr/local/bin/uv

# Convert SQLAlchemy URL to a plain psql-compatible URL.
PSQL_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+psycopg://|postgresql://|')

echo "Running Alembic migrations..."
$UV run alembic upgrade head

echo "Applying DB grants..."
psql "$PSQL_URL" -f /app/grants.sql

echo "Starting server..."
exec $UV run uvicorn app.main:app --host 0.0.0.0 --port 8000
