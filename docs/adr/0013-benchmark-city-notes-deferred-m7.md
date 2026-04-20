# ADR 0013 — Benchmark notes and city notes CRUD deferred to M7

**Status:** Accepted
**Date:** 2026-04-20
**Authors:** Aida Jugo Krstulovic

## Context

PRD FR-COMMENT-2 (benchmark notes) and FR-COMMENT-3 (city notes) are listed
under "FR-ADMIN" scope. The data models — `BenchmarkNote` and `CityNote` — were
added to the schema in the M3 migration and are read by the report aggregation
pipeline (`app/report/logic.py`). The M6 review identified that no CRUD API
routes or admin UI screens exist for these two tables.

Two options were considered for resolution:

1. Add thin CRUD routers for `benchmark_notes` and `city_notes` in M6.
2. Defer them to M7, document the gap, and ship a placeholder response.

## Decision

Defer to M7. The models are in place and the read path works. The gap affects
operator convenience only — staff can seed benchmark/city notes directly via SQL
until the admin UI is available. Shipping untested CRUD endpoints in a late M6
fix creates more risk than leaving the read-only path as-is.

An ADR is the appropriate vehicle for recording the deferral (per AGENTS.md
"Schema changes raise as a question before migration; new ADRs only for auth,
data source, deployment, or secrets — or to record explicit scope deferrals").

## Consequences

- `GET /api/report` and `GET /api/report/export-pdf` already surface
  `benchmark_note` from the report aggregation. No report regression.
- No M6 routes exist for `POST/PATCH/DELETE /api/admin/benchmark-notes`
  or `POST/PATCH/DELETE /api/admin/city-notes`.
- HANDOFF.md M7 section will include these endpoints as first-priority work.
- `docs/testing.md` section 7 will record FR-COMMENT-2 and FR-COMMENT-3 as
  pending coverage until M7 ships the admin UI.

## Alternatives considered

**Add thin routers in M6** — rejected. The M6 scope is already broad (admin user
management, config screens, PDF export, erasure, retention sweep). Adding two
more CRUD surfaces without adequate test coverage creates regression risk and
delays the M6 sign-off further.
