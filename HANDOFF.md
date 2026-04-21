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

### M5: report endpoint + UI port — **COMPLETE**

All backend logic, API endpoint, frontend components, numerical parity test, and
Playwright E2E scaffolding are implemented and tested.

**What landed:**

- `fix/tc-i-sh-6-cache-flake`: Fixed `SheetCache.invalidate()` — CI now green.
- `feat/m5-report-logic`: `backend/app/report/logic.py` + `models.py` — typed pure functions,
  `ReportAux` dataclass, `build_period_data` + `compute_period`. All TC-U-REP-1..13 pass.
- `feat/m5-report-api`: `GET /api/report` + `POST /api/report/refresh` — hub scoping before
  aggregation, YoY overlay, stale flag propagation, `report_view` audit row. All integration
  tests pass (TC-I-API-1, TC-I-API-6, TC-I-API-8, TC-I-API-9, TC-I-AUD-7).
- `feat/m5-frontend-shell`: React page + all components (`KpiCardRow`, `SummaryTable`,
  `HubCards`, `AboveMidpointTable`, `PeriodNav`, `YearSelector`, `YoYToggle`, `StaleBanner`).
  Design tokens only (TC-U-BRAND-1..5 pass). YoYToggle shows "previous year missing" marker
  (TC-U-REP-12). StaleBanner shown when `stale=true` (TC-E-7).
- `feat/m5-parity-e2e` (this PR):
  - `backend/tests/unit/test_report_parity.py` — 10-test parity suite against
    `legacy/Hiring_Report_TEST_DATA.xlsx` (all 31 rows, Q1 + Annual). TC-U-REP-7 passes.
  - `backend/app/e2e/routes.py` — `POST /api/e2e/seed-session` test-only fixture endpoint
    (guarded by `APP_ENV=test`; returns 404 in production).
  - `docker-compose.test.yml` — isolated E2E stack (separate DB port 5433,
    `APP_ENV=test`, `SESSION_COOKIE_INSECURE=1`).
  - `frontend/e2e/global-setup.ts` — Playwright global setup; seeds viewer,
    hub-scoped viewer, and admin sessions before any spec runs.
  - `frontend/e2e/report.spec.ts` — TC-E-1, TC-E-4, TC-E-5, TC-E-7, TC-E-9, TC-E-10
    (Sheet calls mocked at network layer via `page.route()`).
  - `frontend/e2e/smoke.spec.ts` — updated heading assertion.

**PRD change**: `month` query param renamed to `period` per M5 planning session. `HANDOFF.md`
M5 spec wording was stale — fixed here.

**M5 definition of done: fully met.** All in-scope tests pass (TC-U-REP-1..13, TC-U-BRAND-1..5,
TC-I-API-1/6/8/9, TC-I-AUD-7, TC-U-REP-7 parity, TC-E-1/4/5/7/9/10).
`docs/testing.md` section 7 updated. `HANDOFF.md` updated.

### M6: admin UI + historical data + PDF export — **COMPLETE (with M7 carry-overs)**

All backend logic, admin API endpoints, admin UI, PDF export, erasure, and
retention sweep are implemented and tested.

**What landed:**

- `backend/app/admin/routes.py` — user management (list, create, update role/hubs,
  deactivate), config management (spreadsheet ID/tab, retention windows), hub pair
  CRUD, sweep trigger. Every mutation audited. Last-admin guard (TC-I-API-10/11).
- `backend/app/comments/routes.py` — comment CRUD for hire-key comments (FR-COMMENT-1..4).
- `backend/app/audit/erasure.py` — `redact_actor` PII redaction (NFR-PRIV-5, ADR 0010).
- `backend/app/audit/sweep.py` — `sweep_audit_log` / `run_sweep` (NFR-PRIV-4, ADR 0006).
  Uses `relativedelta` for correct calendar-month arithmetic.
- `backend/app/report/pdf.py` — WeasyPrint HTML-to-PDF with:
  - Deny-all URL fetcher (SSRF protection, P1-6).
  - Symphony brand tokens: Poppins font, navy/sand/blueGrey palette.
  - Hub scope applied by endpoint before render; no client strings echoed.
- `backend/app/config.py` — `database_url_erasure` / `database_url_sweep` fields.
- `backend/app/main.py` — lifespan startup assertion: blocks prod start if role
  URLs are missing or equal the app URL (ADR 0010, P0-1/P0-5).
- `backend/app/db/session.py` — role engine logging; fallback only in dev/test.
- `backend/Dockerfile` — WeasyPrint system libs (libpango, libcairo, etc.).
- `backend/init-db.sh` + `docker-compose.yml` — three-role DB provisioning (ADR 0010).
- `frontend/src/` — admin shell + users page + config page, comment CRUD UI,
  `ExportPdfButton`, React Router wiring, React Query hooks.
- `docs/adr/0013-benchmark-city-notes-deferred-m7.md` — explicit deferral of
  benchmark/city notes CRUD to M7.

**Carry-overs to M7 (first priority):**

1. Benchmark notes CRUD (`POST/PATCH/DELETE /api/admin/benchmark-notes`) — ADR 0013.
2. City notes CRUD (`POST/PATCH/DELETE /api/admin/city-notes`) — ADR 0013.
3. TC-I-DB-1..3 DB role grant enforcement tests — require three separate Postgres
   role connections in the test fixture. Pin these tests with `@pytest.mark.skipif`
   until the CI DB provisions grants.sql on first run.
4. ~~Real WeasyPrint smoke test (non-mocked) — build the Docker image, call
   `html_to_pdf`, assert bytes start with `%PDF-`.~~ **Done — `backend/tests/unit/test_pdf_render.py` (fix/pdf-export-venv-isolation, PR #7).**
5. Poppins woff2 font commit — currently vendored into `backend/app/assets/fonts/`;
   confirm CI build copies them correctly (backend `COPY app ./app` covers it).

**M6 definition of done:** all in-scope tests pass (TC-U-REP-1..13, TC-U-BRAND-1..5,
TC-I-API-1/3/6/7/8/9/10/11/13, TC-I-AUD-7/8, TC-I-ADM-1..5, TC-I-SWP-1/2,
TC-E-6/11/12). `docs/testing.md` section 7 updated. ADR 0013 filed.

### Bootstrap: day-one admin seeding — **COMPLETE**

Solves the chicken-and-egg problem: a fresh deployment has no admin in the
allowlist, so no one can log in (FR-AUTH-3, TC-I-AUTH-11).

**What landed:**

- `backend/app/admin/bootstrap.py` — `seed_admin(db, email, display_name)` async
  function + `__main__` CLI. Idempotent upsert (promotes any existing user to admin,
  re-activates deactivated accounts). Writes an `admin_seeded` audit row every call.
- `AuditAction.admin_seeded` constant.
- `DAY_ONE_ADMIN_EMAILS` in `Settings` (comma-separated `email[:name]` pairs for
  automated deploy pipelines).
- `backend/tests/integration/test_bootstrap_admin.py` — TC-I-AUTH-11 (a–d):
  seed creates user + audit row, idempotency, re-activation, seeded admin completes
  the full OAuth callback flow with mocked OIDC.
- `tests/conftest.py` — `api_client` fixture now patches `DATABASE_URL_ERASURE` and
  `DATABASE_URL_SWEEP` to test-DB role URLs and calls `_state.reset()` so background
  tasks (erasure, sweep) connect to the isolated test database. Fixes 2 pre-existing
  failing tests (`test_deactivate_endpoint_erases_pii_in_background`,
  `test_sweep_trigger_admin_ok`).

**First-run setup (required on every fresh deployment):**

```bash
# Inside the backend container, or with the venv active and DB reachable:
python -m app.admin.bootstrap \
    --email aida.jugo@symphony.is \
    --name "Aida Jugo Krstulović"

# For automated CD pipelines, use the env var instead:
# DAY_ONE_ADMIN_EMAILS="aida.jugo@symphony.is:Aida Jugo,enis.kudo@symphony.is:Enis Kudo" \
# python -m app.admin.bootstrap
```

Run it once per deployment. Re-running is safe — idempotent. The audit log will
show an `admin_seeded` row for each run.

### First-run: Google Cloud + Sheet + Docker dev setup — **COMPLETE** (captured from live debugging, 2026-04-17)

This section documents every step and every gotcha we hit getting a fresh clone
to render a report on `http://localhost:5173`. Follow it in order on any new
machine or any new Google Cloud project. Each step lists the symptom you see
if you skip it.

#### 1. Google Cloud project

Use the project that owns the service account. The dev project today is
`talentacquisition-493909` (project number `761453883625`). Record the project
ID when creating a new one.

Required APIs (enable both, not just one):

- **Google Sheets API** — `https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=<PROJECT_NUMBER>`
- **Google Drive API** — `https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=<PROJECT_NUMBER>`

Symptom if missing: `gspread.exceptions.APIError: [403]: Google Sheets API has
not been used in project ... before or it is disabled`.

#### 2. Service account + JSON key

1. IAM & Admin → Service Accounts → create account (or reuse existing).
2. Keys → Add Key → JSON. Download the file.
3. Treat the file as a secret. Rotate every 180 days per [ADR 0008](docs/adr/0008-secrets-env-vars.md).

Place the JSON inside the repo at `secrets/service_account.json`. The
`./secrets` directory is mounted into the backend container at `/run/secrets`
by `docker-compose.yml`. The container reads the file via
`GOOGLE_SERVICE_ACCOUNT_JSON_PATH` (default `./secrets/service_account.json`,
which resolves to `/run/secrets/service_account.json` inside the container).

Symptom if missing: backend 500 with
`FileNotFoundError: [Errno 2] No such file or directory: '/run/secrets/service_account.json'`.

The `secrets/` directory is gitignored. Never commit the JSON.

#### 3. OAuth 2.0 client (for user SSO)

APIs & Services → Credentials → OAuth 2.0 Client ID (type: Web application).

**Authorised redirect URIs** must include, exactly:

- `http://localhost:8000/api/auth/callback` (dev)
- The production equivalent, when M7 ships.

Note: the path is `/api/auth/callback`, not `/auth/callback`. This is the
single most common misconfiguration.

Record the client ID and client secret into `.env`:

```
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/callback
APP_BASE_URL=http://localhost:5173
```

`APP_BASE_URL` must point at the SPA origin, not the backend. The backend
redirects the user here after a successful login; if it points at `:8000`
you get a blank page or a `{"detail":"Not Found"}` 404 after the OAuth
callback completes.

Symptom if `GOOGLE_OAUTH_REDIRECT_URI` disagrees with the console value:
`Error 400: redirect_uri_mismatch` from Google's consent screen.

#### 4. The Google Sheet itself

Two hard requirements, both easy to miss:

1. The file must be a **native Google Sheet**, not an Excel `.xlsx` uploaded
   to Drive. The Sheets API rejects `.xlsx` with
   `APIError: [400]: This operation is not supported for this document`.
   Fix: open the `.xlsx` in Drive, File → Save as Google Sheets, copy the
   **new** file's ID.

2. The sheet must be shared with the service account's email. Open the
   service-account JSON, find `"client_email": "...@...iam.gserviceaccount.com"`,
   and share the Sheet with that address (Viewer is enough for reads).

Then set in `.env`:

```
SPREADSHEET_ID=<the ID from the new native Sheet's URL>
SPREADSHEET_TAB_NAME=<usually "Report Template">
```

The tab name is case- and whitespace-sensitive.

Symptom if not shared: `APIError: [404]: Requested entity was not found`.

#### 5. Make Docker actually pick up `.env`

`docker compose restart` does **not** reload environment variables. It only
restarts the process inside the existing container. Environment values are
set at container creation and the FastAPI settings object is cached
(`@lru_cache` on `get_settings()`). Any change to `.env`, `docker-compose.yml`
environment blocks, or either `GOOGLE_*` / `SPREADSHEET_ID` / `APP_BASE_URL`
requires recreating the container:

```bash
docker compose up -d --force-recreate backend
# verify
docker compose exec backend printenv SPREADSHEET_ID
docker compose exec backend printenv GOOGLE_OAUTH_REDIRECT_URI
docker compose exec backend printenv APP_BASE_URL
```

If the printed value does not match `.env`, the container was not recreated.

For a cleaner wipe (also resets the Postgres volume, useful when grants.sql
or migrations changed):

```bash
docker compose down -v
make dev
```

#### 6. Seed day-one admins

First login fails with 403 until at least one allowlist entry exists in the
`users` table. Two paths:

Preferred (automated):

```bash
# .env already has:
# DAY_ONE_ADMIN_EMAILS=aida.jugo@symphony.is:Aida Jugo,enis.kudo@symphony.is:Enis Kudo
docker compose exec backend uv run python -m app.admin.bootstrap
```

Manual fallback (one user at a time):

```bash
docker compose exec backend uv run python -m app.admin.bootstrap \
  --email aida.jugo@symphony.is --name "Aida Jugo Krstulović"
```

Emergency fallback (SQL, only if bootstrap CLI itself is broken):

```bash
docker compose exec db psql -U postgres -d ta_report -c \
  "INSERT INTO users (id, email, display_name, role) VALUES \
   (gen_random_uuid(), 'aida.jugo@symphony.is', 'Aida Jugo Krstulović', 'admin'), \
   (gen_random_uuid(), 'enis.kudo@symphony.is', 'Enis Kudo', 'admin');"
```

Symptom if skipped: successful Google 2FA, callback returns 200, but the
report page shows a blank screen or a 403 because `resolve_login` denied the
user. Check `/api/auth/me` — it returns 401 when the user is not in the
allowlist.

#### 7. Summary checklist before loading the page

Confirm each of these on the host before opening `http://localhost:5173`:

- `secrets/service_account.json` exists and belongs to a service account in
  the same Google Cloud project that has Sheets API and Drive API enabled.
- The target Sheet is a native Google Sheet (converted from Excel if needed)
  and is shared with the service account email.
- `.env` has: `GOOGLE_OAUTH_REDIRECT_URI` ending in `/api/auth/callback`,
  `APP_BASE_URL=http://localhost:5173`, `SPREADSHEET_ID` and
  `SPREADSHEET_TAB_NAME` set, `DAY_ONE_ADMIN_EMAILS` populated.
- Google Cloud OAuth client has the exact same redirect URI registered.
- `docker compose up -d --force-recreate backend` was run after the last
  `.env` edit.
- `python -m app.admin.bootstrap` ran at least once (or equivalent SQL
  insert into `users`).

#### 8. Common errors, one-line fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `redirect_uri_mismatch` from Google | `GOOGLE_OAUTH_REDIRECT_URI` path or env not reloaded | Recheck `.env` path, `docker compose up -d --force-recreate backend` |
| `{"detail":"Not Found"}` after login | `APP_BASE_URL` pointing at backend instead of SPA | Set `APP_BASE_URL=http://localhost:5173`, recreate container |
| Blank screen after 2FA | User not in allowlist (`users` table empty) | Run `python -m app.admin.bootstrap` |
| `API error 500`, logs: `FileNotFoundError ... service_account.json` | JSON missing from `./secrets/` | Copy service-account JSON to `secrets/service_account.json`, restart |
| `APIError: [403]: Google Sheets API has not been used` | Sheets or Drive API disabled | Enable both in the Google Cloud project |
| `APIError: [400]: This operation is not supported for this document` | File is an uploaded `.xlsx`, not a Google Sheet | Drive → File → Save as Google Sheets, update `SPREADSHEET_ID` |
| `APIError: [404]: Requested entity was not found` | Service account not shared on the Sheet | Share with `client_email` from the service-account JSON |
| Frontend proxy logs `ECONNREFUSED` to `localhost:8000` | Vite proxy hardcoded to host | `VITE_API_PROXY_TARGET=http://backend:8000` in compose env |
| `ImportError: email-validator is not installed` | `pydantic[email]` extras not installed on bind-mounted venv | `cd backend && uv sync` on host, then restart backend |
| Frontend renders blank (no errors visible) | `QueryClientProvider` missing from `App.tsx` | Fixed on main; if it regresses, re-wrap root |

#### 9. Production carry-over

The whole list above becomes the M7 deploy runbook. The concrete deliverables:

- `docs/runbooks/first-run.md` extracted from this section, parameterised for
  staging and prod URLs.
- Automated health check that fails startup if any of the following is unset
  in prod: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
  `GOOGLE_OAUTH_REDIRECT_URI`, `APP_BASE_URL`, `SPREADSHEET_ID`,
  `DATABASE_URL_ERASURE`, `DATABASE_URL_SWEEP`, `SESSION_SECRET_KEY`.
- Startup log line that prints the resolved `APP_BASE_URL` and
  `GOOGLE_OAUTH_REDIRECT_URI` (no secrets) so misconfiguration is visible
  without an OAuth round-trip. (Already listed in Post-M6 backlog.)
- `grants.sql` applied during provisioning, before the first backend start.
- `python -m app.admin.bootstrap` invoked from the deploy pipeline once per
  environment, with `DAY_ONE_ADMIN_EMAILS` supplied via the secret store.

### M7: security hardening + deployment decision

1. Benchmark notes and city notes CRUD admin endpoints (carry-over from M6, ADR 0013).
2. HTTPS-only, HSTS, CSP, rate limiting, session rotation, dependency scans required to merge.
3. Write `docs/deployment-options.md` comparing Cloud Run vs VPN-gated infra vs self-hosted VM. Pick one as a new ADR.
4. Ship production: Dockerfiles, secrets, DB, domain, SSO, smoke tests, runbook.
5. Provision three-role DB grants (`grants.sql`) in staging + prod as part of the deploy runbook.
6. TC-I-AUTH-9 automatic Google Workspace offboarding probe (deferred per ADR 0012).

**Deploy-time constraint (from M5 E2E scaffolding):** `APP_ENV=test` must never
be set in production environments.  `POST /api/e2e/seed-session` is a
session-seed backdoor gated by `APP_ENV == "test"` (strict equality) and is
only registered in the FastAPI router under that env value.  Production Docker
images and deploy configs must set `APP_ENV=prod` explicitly.  The M7 deploy
runbook must codify this as a mandatory pre-flight check.

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

8. **Vite proxy target** — was hardcoded to `localhost:8000`; Docker dev needed `http://backend:8000`. Fixed via `VITE_API_PROXY_TARGET` env var (defaults to `http://localhost:8000` for host-mode dev). M7 deployment runbook should document this and confirm the production path serves the SPA from a static file server proxying to backend, not a Vite dev server.

9. **OAuth redirect URI and post-login APP_BASE_URL miswired in dev** — `GOOGLE_OAUTH_REDIRECT_URI` was missing the `/api` prefix (`/auth/callback` instead of `/api/auth/callback`), and `APP_BASE_URL` pointed at the backend (`localhost:8000`) instead of the SPA (`localhost:5173`). Both caused `{"detail":"Not Found"}` 404s after Google auth. Fixed in `.env`, `.env.example`, `config.py` defaults, and `docker-compose.yml`. Production runbook (M7) must document: `GOOGLE_OAUTH_REDIRECT_URI` always ends in `/api/auth/callback`; `APP_BASE_URL` always points at the SPA origin, never the backend.

10. **Dev venv isolation (PDF export 500)** — **Fixed in `fix/pdf-export-venv-isolation` (PR #7).**
    The `./backend:/app` bind-mount in `docker-compose.yml` caused the `.venv` to
    be shared between the macOS host and the Linux container. Running `make install`
    on macOS installed macOS-native Pillow wheels; the Linux container could not load
    the `_imaging` C extension, causing every `GET /api/report/export-pdf` request to
    return 500. Fix: added a `backend-venv` named volume scoped to `/app/.venv` so the
    container venv is always Linux-native. After `docker compose down -v && make dev`
    the issue is fully resolved. The `backend/tests/unit/test_pdf_render.py` smoke test
    (M6 carry-over #4) guards against regression.

7. **`test_tc_i_sh_6_manual_refresh_bypasses_cache`** — **Fixed in `fix/tc-i-sh-6-cache-flake`.**
   Root cause was (a): `SheetCache.invalidate()` only reset `_cached_at = 0.0`
   but not `_cached`. On CI containers where `time.monotonic()` is still under
   3600 s from process boot, `_is_fresh()` evaluated `(monotonic - 0.0) < 3600`
   as True and served the cached entry, so `_build_gspread_client` was only
   called once. Fix: `invalidate()` now also sets `_cached = None`, making
   `_is_fresh()` unconditionally False after invalidation. All 12 TC-I-SH-*
   tests pass. Main is green.
