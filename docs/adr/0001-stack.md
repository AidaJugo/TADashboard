# ADR 0001: Backend FastAPI, frontend React + Vite + TypeScript

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic, Enis Kudo

## Context

The validated prototype ([generate_report.py](../../legacy/generate_report.py)) is a Python script that reads a Google Sheet, computes hiring stats, and emits a self-contained HTML report using Chart.js. We need to scale it into a secure, multi-user web app without losing that logic or the design Enis validated with stakeholders.

Constraints:

- Small scale (~10 users, a few thousand rows).
- One developer plus an AI agent iterating.
- Port the existing Python aggregation logic without rewriting it in another language.
- The HTML/CSS/Chart.js dashboard from the prototype (`generate_report.py` lines 260-412) must port cleanly to components.

## Decision

- Backend: Python 3.12 + FastAPI. Alembic for migrations. `uv` for dependency and virtualenv management. `pytest` for tests.
- Frontend: React 18 + Vite + TypeScript. Chart.js for the existing charts. Playwright for E2E.
- Database: PostgreSQL 16 for app metadata (users, roles, hub scopes, config, comments, audit log, last-known-good snapshot). Hiring rows stay in Sheets (see [ADR 0002](0002-sheet-as-source-of-truth.md)).

## Consequences

- Python lets us reuse the prototype's aggregation math verbatim, minimising porting risk.
- FastAPI gives us typed request/response models and OpenAPI for free, which the frontend can consume.
- Vite + TS keeps dev feedback tight and lets us lift the prototype's JS inline logic into typed components.
- `uv` is fast and reproducible (lockfile), but is newer than Poetry. If we hit friction, we can fall back to Poetry without changing the runtime.
- Two languages to lint, type-check, and secure in CI. Accepted cost.

## Alternatives considered

- Node-only (Next.js full stack): would require rewriting the Python aggregation logic. Rejected.
- Django: more batteries than we need, slower OpenAPI story. Rejected.
- Flask + jQuery: matches the prototype's style but gives no type safety and leaves the frontend unstructured. Rejected.
