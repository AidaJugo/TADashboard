# Handoff to the implementation agent

Status: scaffolding and guardrails complete. Implementation starts here.

This file tells the next agent (and the next human) exactly what is in place, what to build next, and in what order.

## What is in place

Docs and decisions:

- [docs/prd.md](docs/prd.md): product requirements, reviewed with Enis.
- [docs/testing.md](docs/testing.md): test strategy and acceptance criteria.
- [docs/adr/](docs/adr/): nine accepted ADRs covering stack, Sheets as source of truth, service account access, SSO, deployment deferral, retention, observability, secrets, and data classification.
- [docs/brand-guidlines/](docs/brand-guidlines/): Symphony brand book (2021).

Guardrails for agents and humans:

- [AGENTS.md](AGENTS.md): short rulebook.
- [CONTRIBUTING.md](CONTRIBUTING.md): setup + PR rules.
- [CODEOWNERS](CODEOWNERS): review requirements, two approvers on security-sensitive areas.
- [.github/pull_request_template.md](.github/pull_request_template.md): filled every PR.
- [.cursor/rules/](.cursor/rules/): project baseline, backend, frontend, auth, migrations, testing.
- [.cursor/skills/symphony-design/](.cursor/skills/symphony-design/): brand voice + visual tokens.

Repo scaffold:

- [backend/](backend/): FastAPI skeleton with `/healthz`, `/readyz`, CORS, request IDs, JSON logging, config via pydantic-settings, Alembic bootstrap, pytest (unit + integration dirs).
- [frontend/](frontend/): Vite + React + TS app with design tokens, a placeholder landing page, Vitest unit test, Playwright smoke test, nginx-served Dockerfile.
- [legacy/](legacy/): the original prototype (`generate_report.py`, `SETUP_GUIDE.md`, `Hiring_Report_TEST_DATA.xlsx`), frozen.
- [docker-compose.yml](docker-compose.yml): db + backend + frontend.
- [Makefile](Makefile): `install`, `dev`, `lint`, `typecheck`, `test`, `e2e`, `ci`, `migration`.
- [.env.example](.env.example): all required env vars documented.
- [.github/workflows/ci.yml](.github/workflows/ci.yml): backend, frontend, e2e, security (gitleaks, semgrep).
- [.pre-commit-config.yaml](.pre-commit-config.yaml) and [.gitleaks.toml](.gitleaks.toml): hooks for every commit.

## First things the next agent should do

1. Initialise git and push. The scaffold is not yet a git repo. Pick the remote with Aida first.
2. Run `make install` and `make ci`. Fix any environment-specific issues. The scaffold is intended to pass lint + unit tests out of the box (minus real integration, which is marked skip).
3. Decide the GitHub org/repo and update [CODEOWNERS](CODEOWNERS) handles (currently placeholder slugs).

## Implementation order (milestones)

Pick tasks from the plan's todo list in this order. Ship each milestone in its own small PR, or a small sequence of PRs.

### M3: data model + Sheets client (closed loop, no UI yet)

1. `backend/app/db/` models for `users`, `roles`, `user_hub_scopes`, `config_kv`, `column_mappings`, `comments`, `benchmark_notes`, `city_pairs`, `audit_log`, `sheet_snapshot`. Alembic migration generated in one shot, forward-only (see [.cursor/rules/migrations.mdc](.cursor/rules/migrations.mdc)).
2. `backend/app/sheets/` client with service account auth, admin-configurable column mapping, in-process TTL cache, "refresh now" invalidation, fallback to `sheet_snapshot` on failure.
3. Tests: unit for column mapping, integration that spins Postgres via the CI service and validates the fallback path with a mocked Sheets client.

### M4: auth + authz

1. `backend/app/auth/`: OAuth2 login flow with `hd=symphony.is` enforced server-side, allowlist check, server-side session, CSRF on state-changing routes.
2. `backend/app/authz/`: role enum + dependencies + single-source hub scoping filter.
3. `backend/app/audit/`: one helper per event type, writes in the same transaction as the mutation.
4. Tests: unit for role checks, integration for "unauthorized domain rejected", "un-allowlisted user rejected", "viewer cannot see other hub", E2E Playwright for the login redirect shape (mocked OAuth server).

### M5: report endpoint + UI port

1. `backend/app/report/`: port `compute_period` and `build_period_data` from `legacy/generate_report.py` lines 157-254 as typed, unit-tested functions. Apply hub scope from `app.authz` before aggregation.
2. `GET /api/report?year=&month=&hub=` returning the JSON shape the frontend needs.
3. Port `legacy/generate_report.py` lines 260-412 into React components: `KpiCardRow`, `SummaryTable`, `HubCards`, `AboveMidpointTable`, `PeriodNav`. Wire via React Query.
4. Honour the design tokens and the voice rules in [.cursor/skills/symphony-design/SKILL.md](.cursor/skills/symphony-design/SKILL.md).

### M6: admin UI + historical data + PDF export

1. Admin screens (PRD FR-ADMIN): users, column mapping, comments, benchmark notes, city pairs, retention windows. Every mutation audited.
2. 2025 historical data import (PRD FR-REPORT-8, FR-REPORT-9): one-off loader + year selector + comparison view.
3. PDF export for the scoped view (PRD FR-REPORT-10). Server-side render to keep scoping honest.

### M7: security hardening + deployment decision

1. HTTPS-only, HSTS, CSP, rate limiting, session rotation, dependency scans required to merge.
2. Write `docs/deployment-options.md` comparing Cloud Run vs VPN-gated infra vs self-hosted VM. Pick one as ADR 0010.
3. Ship production: Dockerfiles, secrets, DB, domain, SSO, smoke tests, runbook.

## Test expectations

See [docs/testing.md](docs/testing.md). For every feature PR:

- Unit tests for every new pure function.
- Integration test for every new endpoint (happy path + at least one unauthorized case).
- E2E only for the security-critical flows listed in the test doc.
- Tests reference the PRD requirement they cover (`test_fr_report_5_last_known_good_snapshot`).

## Things to leave alone

- `legacy/` (reference only).
- Migrations already merged to `main`.
- `docs/adr/` (changes require a new or updated ADR, not a silent edit).
- `.cursor/skills/symphony-design/` (needs design review before editing).

## What is still open

- GitHub org/repo + branch protection rules (configure once the repo exists).
- Symphony logo SVG files in `frontend/src/assets/brand/` (PRD OQ-11a, need Aida to provide).
- Poppins `.woff2` files in `frontend/src/assets/fonts/`.
- Deployment target (ADR 0005 decision point at M7).
- Incident response contact list (needed before go-live).

## Escalation

- Unclear requirements: Aida Jugo Krstulovic.
- TA domain questions: Enis Kudo.
- Anything that touches auth, audit, or secrets: pair with Aida before merging.

## Post-M4 backlog

These items were identified during the M3 review and deferred. None are blockers for
M4 (auth + authz + audit). Pick them up in a follow-up PR once M4 is merged.

1. **Refactor `SheetCache` to expose `seed_last_good(result)`** — replace the direct
   private-attribute write `self._cache._last_good = ...` in
   `backend/app/sheets/client.py` (`_prime_cache_from_snapshot`) with a clean public
   method on `SheetCache`. Pure refactor, no behaviour change. Bundle with any other
   sheets-cache work.

2. **`asyncio.to_thread` around the gspread call in `_fetch_live`** — gspread is
   synchronous; wrapping it in `asyncio.to_thread` prevents it from blocking the
   event loop under concurrent requests. Fine for 10 users today, but worth doing
   before load increases. File: `backend/app/sheets/client.py`, `_fetch_live` method.

3. **`audit_log.target` as structured JSONB** — the current `target` column is free
   text. When M5 enumerates all audit event types (config edit, comment CRUD, user
   CRUD), convert `target` to JSONB with a typed diff structure. This needs a small
   design pass on the event schema. Do in M5.
