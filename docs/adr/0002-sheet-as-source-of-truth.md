# ADR 0002: Google Sheet is the source of truth for hiring rows

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic, Enis Kudo

## Context

Hiring data currently lives in a Google Sheet (`SPREADSHEET_ID = "1QQ4EW7_XhVdQmrLQKAWVF9MESxvv8EYiGUotzqnxzcE"`). The TA team already edits there daily. They do not want a new editing tool in v1. The validated prototype reads this Sheet directly.

Options considered:

1. Keep Sheet as source of truth, app reads it live.
2. Import rows into Postgres, app reads from Postgres, TA edits via a new UI.
3. Import rows into Postgres, sync both ways with the Sheet.
4. Store hiring rows in JSON files in the repo.

## Decision

Phase 1 (this project): the Google Sheet remains the source of truth for hiring rows. The app reads it on demand, validates the schema, caches briefly in process, and stores the last-successful response as a snapshot in Postgres so the report stays viewable if Sheets is unreachable.

Auxiliary data (users, roles, hub scopes, comments, benchmark notes, column mappings, city pairs, audit log) lives in Postgres from day one.

Phase 2 (future, only if needed): evaluate a DB-backed editor for hiring rows once the tool is in real use.

## Consequences

- TA's existing workflow is unchanged. No migration, no re-training.
- We inherit Google Sheets' limits: rate caps, occasional outages, schema drift if someone renames a column.
- We mitigate drift with server-side schema validation and an admin-editable column mapping (see PRD FR-CONFIG-2).
- We mitigate outages with a last-known-good snapshot (PRD FR-REPORT-6) and "refresh now" button.
- Write-back is out of scope for v1. If TA wants to edit comments in the app, those live in Postgres, not the Sheet.

## Alternatives rejected

- JSON files: no validation, no multi-user edits, no audit trail, not editable by non-engineers.
- Postgres-primary with a new UI: scope creep. Would force TA to change workflow and would double the surface area to build.
- Two-way sync: high complexity, conflict resolution is hard, not justified at this scale.
