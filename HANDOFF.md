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

### M4: auth + authz + audit

Schema is ready: `sessions`, `users` (with native `user_role` Postgres ENUM), `user_hub_scopes`, and `audit_log` landed in the M3 follow-up migration `20260417_0002`. Do not add new columns to these without a new migration.

1. `backend/app/auth/`: OAuth2 login flow with `hd=symphony.is` enforced server-side, allowlist check, server-side session backed by the `sessions` table (4h idle via `last_seen_at`, 24h absolute via `expires_at`, revoke via `revoked_at`), CSRF on state-changing routes. The auth middleware must treat any session with `revoked_at IS NOT NULL` as invalid and return 401 with an audit entry on the next request.
2. `backend/app/authz/`: role dependencies + single-source hub scoping filter (no second implementation).
3. `backend/app/audit/`: one helper per event type, writes in the **same transaction** as the mutation.
4. **Admin session-revoke endpoint**: `POST /api/admin/users/{id}/revoke-sessions` sets `sessions.revoked_at` for all active sessions of that user. Required by [ADR 0012](docs/adr/0012-day-one-offboarding.md) so that operator-assisted offboarding can close an active session without waiting for the 24h absolute timeout. Covered by TC-I-AUTH-10.
5. **Apply [backend/grants.sql](backend/grants.sql) in your dev and test databases.** It sets up the three-role grants model from [docs/adr/0010-audit-log-grants.md](docs/adr/0010-audit-log-grants.md): app role gets `INSERT`+`SELECT` on `audit_log` only; erasure role gets `UPDATE` on PII columns for NFR-PRIV-5; sweep role gets `DELETE` for retention. TC-I-AUD-3 asserts this from the test fixture, so load `grants.sql` in your pytest DB setup. Production application of this SQL is an M7 deploy-runbook concern, not M4.
6. Tests: unit for role checks, integration for "unauthorized domain rejected", "un-allowlisted user rejected", "viewer cannot see other hub", session idle + absolute timeout, admin-triggered revoke invalidates the next request (TC-I-AUTH-10). E2E Playwright for login redirect shape (mocked OIDC server).

**Out of M4 scope by decision:**

- `TC-E-4` (Playwright DOM scope check) runs in M5 once the report UI exists. See [ADR 0011](docs/adr/0011-e2e-scope-m4-vs-m5.md). Hub scoping in M4 is covered by `TC-U-AUTHZ-3` and `TC-I-API-6`.
- `TC-I-AUTH-9` (automatic Google offboarding probe) is Post-M4. See [ADR 0012](docs/adr/0012-day-one-offboarding.md). M4 meets NFR-COMP-2 via allowlist removal (`TC-I-AUTH-3`) plus admin session revoke (`TC-I-AUTH-10`).

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
2. Write `docs/deployment-options.md` comparing Cloud Run vs VPN-gated infra vs self-hosted VM. Pick one as ADR 0013 (0010–0012 are taken: audit-log grants, E2E scope, day-one offboarding).
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

4. **Clear `esbuild` GHSA-67mh-4wv8-2f99 (5 moderate npm audit findings)** — all five
   findings chain from `esbuild <=0.24.2` via `vite`, `@vitest/mocker`, `vitest`, and
   `vite-node`. Dev-server-only vulnerability: no production runtime impact (nginx
   serves the built bundle). CI passes because the threshold is `high`. Fix by bumping
   `vite` to a patched `^5.x` or moving to Vite 7 in a dedicated dep PR. Do NOT run
   `npm audit fix --force` — it proposes Vite 8 which is a breaking jump. Captured
   from `npm audit` run on 2026-04-17 after `make install` on `main`.

5. **Automatic Google Workspace offboarding probe (`TC-I-AUTH-9`)** — deferred per
   [ADR 0012](docs/adr/0012-day-one-offboarding.md). Scope for this PR:

   - Decide between **refresh-token probe** (long-lived, requires encrypted per-user
     secret storage; first per-user secret at rest in the system — review against
     [ADR 0008](docs/adr/0008-secrets-env-vars.md)) and **userinfo probe** (short,
     ~1h window, no new secret). Capture the trade-off in a new ADR.
   - Forward-only Alembic migration adding either `sessions.google_refresh_token`
     (encrypted) + `sessions.last_google_verified_at`, or only the timestamp column.
   - Probe mechanism in `backend/app/auth/offboarding.py` (or equivalent), invoked
     from the auth middleware on a cadence (e.g. every 15 minutes per session).
     `invalid_grant` or 401 from Google → set `sessions.revoked_at`.
   - Re-enable `TC-I-AUTH-9` and add unit tests for the probe mechanism.
   - Update `docs/testing.md` section 7: NFR-COMP-2 gets the automatic path added
     alongside the existing M4 allowlist + admin-revoke path.

6. **Investigate ruff-vs-black config drift on PEP 695 generics** — `ruff format`
   and `black` disagree on how to wrap generic function signatures of the form
   `def filter_by_hub[T](...)` (see `backend/app/authz/hub_scope.py`). Ruff
   produces `def filter_by_hub[\n    T\n](args, ...)` with a trailing comma,
   black collapses to the conventional `def name[T](\n    args,\n)` style.
   This is a formatter-vs-formatter fight, not a `ruff check` lint rule, so
   there is nothing to add to `[tool.ruff.lint]` ignores. Resolution options
   for a follow-up: pin matching versions, drop one of the two formatters
   (likely black since ruff is canonical here), or wait for upstream to align
   on PEP 695. Today we work around it by running black before pushing
   anything that touches generic signatures. Captured 2026-04-17 while
   pushing the M4 nit-fix series.

7. **`test_tc_i_sh_6_manual_refresh_bypasses_cache` fails in CI, passes locally** —
   `backend/tests/integration/test_sheets_client.py::test_tc_i_sh_6_manual_refresh_bypasses_cache`
   asserts `mock_build.call_count == 2` after `client.invalidate()` followed by
   a second `get_rows()`; CI sees 1. Failing run:
   https://github.com/AidaJugo/TADashboard/actions/runs/24580615250. Main has
   been red since the M4 nit-fix series landed (commit `166c848`), but the
   failure is M3 sheets code, not M4. Likely causes, in order of probability:
   (a) `SheetCache.invalidate()` not actually dropping the cached entry on the
   CI Python/library combo; (b) per-test mock state leaking between the two
   `get_rows()` calls; (c) ordering-sensitive flake. Repro steps: run
   `uv run pytest tests/integration/test_sheets_client.py -k tc_i_sh_6
   --count=10 -p no:randomly` locally (from `backend/`) before assuming
   environment. Owner: whoever picks up M5 sheets work first. Captured
   2026-04-17 during the M4 review.
