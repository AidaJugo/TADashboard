# Testing Strategy and Acceptance Criteria

Status: DRAFT v0.3
Owner: Aida Jugo Krstulovic
Last updated: 2026-04-17

This doc is the source of truth for how we test the app and what "done" looks like for each feature in [prd.md](prd.md). Every PR updates it alongside code.

## 1. Test pyramid

- Unit (fast, majority): pure functions. Report logic, status classification, period aggregation, column-mapping validation, authorization helpers.
- Integration (medium): Sheets client against fixtures, DB models and migrations, auth flow against a mocked Google OIDC, authorization middleware, audit writer.
- E2E (slow, minimum critical flows): Playwright against a running stack with a seeded DB and a mocked Google auth server.

Coverage targets:

- Unit: 85% on `backend/app/report/` and `backend/app/auth/`.
- Integration: every API route has at least one happy path and one deny path.
- E2E: all security-critical flows listed in section 5 (currently 12 scenarios covering login, scope, scope-preserving year switch, YoY overlay, PDF export, and the last-admin guard).

## 2. Tools

- Python backend: `pytest`, `pytest-cov`, FastAPI `TestClient`, `respx` for HTTP mocks, `pytest-alembic` for migration checks.
- TypeScript frontend: `vitest`, `@testing-library/react`.
- E2E: Playwright with a docker-compose test stack.
- Fixtures: `legacy/Hiring_Report_TEST_DATA.xlsx` as the known-good dataset. Synthetic datasets in `backend/tests/fixtures/` for edge cases (empty month, schema drift, above-midpoint explosion, null salaries).

## 3. Unit test cases

### 3.1 Report aggregation

- TC-U-REP-1: Given a period with one Below, one At mid-point, one Above, one No-salary hire, KPI counts and percentages match.
- TC-U-REP-2: Empty period returns `has_data=false` and all numeric KPIs zero.
- TC-U-REP-3: Per-hub tables group correctly by Type (WF, NonWF) and Status.
- TC-U-REP-4: Quarterly, half-year, annual roll-ups equal the sum of contributing months.
- TC-U-REP-5: Above-midpoint detail joins the correct comment, recruiter name, and hire note from the database.
- TC-U-REP-6: Hub-scoped aggregation excludes non-allowed hubs from KPIs, summary, per-hub cards, and above-midpoint section.
- TC-U-REP-7: Currency rounding matches the prototype output.
- TC-U-REP-8: Unknown status value is counted in a fallback bucket and surfaced as a warning, not silently dropped.
- TC-U-REP-9: Rows with missing Month are excluded from all monthly aggregations with a warning.
- TC-U-REP-10: Year selector: aggregation scoped to the selected year excludes rows from other years.
- TC-U-REP-11: Year-over-year comparison: for a given period and year, the overlay returns the same period in the previous year, with the same hub scoping applied to both years.
- TC-U-REP-12: Year-over-year comparison: missing previous-year data is flagged (not silently zeroed).
- TC-U-REP-13: Hire note longer than 500 characters is rejected at the aggregation/validation boundary.

### 3.2 Column mapping validation

- TC-U-MAP-1: Missing required column is rejected with an error naming the column.
- TC-U-MAP-2: Duplicate mapping (same source column mapped twice) is rejected.
- TC-U-MAP-3: Extra columns in the Sheet are ignored, not failed.
- TC-U-MAP-4: Valid mapping with all required fields succeeds.
- TC-U-MAP-5: Required fields include `Year`, `Recruiter`, and `Note` per FR-CONFIG-2. Missing any of these is rejected.

### 3.3 Authorization helpers

- TC-U-AUTHZ-1: `require_role("admin")` on a viewer returns 403.
- TC-U-AUTHZ-2: Hub scoping filter with empty `allowed_hubs` returns the full dataset.
- TC-U-AUTHZ-3: Hub scoping filter with `["Sarajevo"]` filters at every aggregation stage, not only the final table.
- TC-U-AUTHZ-4: Hub scoping filter does not mutate the original dataset.

### 3.4 Design system conformance

- TC-U-BRAND-1: No component file under `frontend/src/` contains a hardcoded hex colour literal (e.g. `#6c69ff`). Enforced via a lint rule or a ripgrep test.
- TC-U-BRAND-2: All text colour assignments in components resolve to `tokens.colors.black` or `tokens.colors.white`. Enforced via a lint rule.
- TC-U-BRAND-3: Poppins is declared via local `@font-face` only. No `fonts.googleapis.com` or `cdn.jsdelivr.net` references anywhere in `frontend/`.
- TC-U-BRAND-4: The design-system token export in `frontend/src/theme/tokens.ts` matches the palette and typography scale documented in FR-BRAND section of PRD (snapshot test on the exported object).
- TC-U-BRAND-5: Colour contrast of token combinations used in the UI meets WCAG AA (AAA where feasible). Automated check on the token matrix.

## 4. Integration test cases

### 4.1 Sheets client

- TC-I-SH-1: Happy path: fixture Sheet loads and parses into the canonical model.
- TC-I-SH-2: Missing required column returns a schema error and writes an audit entry.
- TC-I-SH-3: Sheet unreachable: last-known-good snapshot is returned and `stale=true` flag is set.
- TC-I-SH-4: Cache hit within TTL does not call Google.
- TC-I-SH-5: Cache miss after TTL refreshes the data and updates the snapshot.
- TC-I-SH-6: Manual refresh bypasses cache, updates snapshot, writes audit entry.

### 4.2 Auth flow

- TC-I-AUTH-1: Unauthenticated request to a protected route redirects to login.
- TC-I-AUTH-2: Google callback with a non-`symphony.is` `hd` claim (including `devlogic.eu`) is rejected with a clear message and audit entry.
- TC-I-AUTH-3: Google callback with `hd=symphony.is` but no allowlist entry is rejected with "Access denied" and audit entry.
- TC-I-AUTH-4: Allowlisted user receives a session cookie and reaches the protected route.
- TC-I-AUTH-5: Idle timeout: session with no activity for `SESSION_IDLE_TIMEOUT_MINUTES` + 1 minute is rejected on the next request (FR-AUTH-4, default 240 minutes).
- TC-I-AUTH-6: Absolute timeout: session older than `SESSION_ABSOLUTE_TIMEOUT_MINUTES` is rejected even if active (FR-AUTH-4, default 1440 minutes).
- TC-I-AUTH-7: Logout clears the session server-side. Reuse of the old cookie returns 401.
- TC-I-AUTH-8: Google callback with missing or false `email_verified` is rejected.
- TC-I-AUTH-9: Google Workspace offboarding: when the OAuth refresh/userinfo call fails because the Google account is deactivated, the session is invalidated on the next authenticated request (NFR-COMP-2). **Post-M4, see [ADR 0012](adr/0012-day-one-offboarding.md).** In M4, NFR-COMP-2 is met via TC-I-AUTH-3 (allowlist removal blocks re-login) plus TC-I-AUTH-10 (admin-triggered session revoke).
- TC-I-AUTH-10: Admin-triggered session revoke: setting `sessions.revoked_at` (via `POST /api/admin/users/{id}/revoke-sessions`) causes the next authenticated request on that session to return 401 and writes an audit entry ([ADR 0012](adr/0012-day-one-offboarding.md)).

### 4.3 API authorization

- TC-I-API-1: Viewer GET `/api/report?period=Q1&year=2026` returns 200 and only the hubs they are scoped to.
- TC-I-API-2: Viewer GET `/api/admin/users` returns 403.
- TC-I-API-3: Editor POST `/api/comments` returns 201 and writes an audit row.
- TC-I-API-4: Editor POST `/api/admin/config` returns 403.
- TC-I-API-5: Admin POST `/api/admin/config` with invalid spreadsheet returns 422 and does not update config.
- TC-I-API-6: Hub-scoped viewer GET `/api/report?hub=Belgrade` where Belgrade is not in their scope returns 403 and audit entry.
- TC-I-API-7: Viewer GET `/api/report/export-pdf` returns a PDF containing only the hubs they are scoped to. Hub names outside the scope never appear in the PDF bytes (checked via extracted text).
- TC-I-API-8: Year-over-year: GET `/api/report?period=Q1&year=2026&compare_previous=true` returns both 2025 and 2026 data, each filtered by the caller's hub scope.
- TC-I-API-9: Year-over-year across a year with no data: response includes an explicit `previous_year_missing=true` marker rather than zeros.
- TC-I-API-10: Admin POST `/api/admin/users` with payload that would remove the last admin returns 409 and no change is made (FR-USER-3).
- TC-I-API-11: Admin PATCH `/api/admin/users/{id}` that would demote the last admin to editor/viewer returns 409 and no change (FR-USER-3).
- TC-I-API-12: Admin CRUD on `/api/admin/hub-pairs` succeeds; viewer and editor are denied (FR-CONFIG-3).
- TC-I-API-13: Admin PATCH `/api/admin/config/retention` accepts audit retention between 6 and 60 months and backup retention between 7 and 90 days; values outside the range return 422 (NFR-PRIV-2, NFR-PRIV-4).

### 4.4 Audit

- TC-I-AUD-1: Login success writes an audit row with actor, IP, timestamp.
- TC-I-AUD-2: Config edit writes an audit row with before/after summary.
- TC-I-AUD-3: Audit log is append-only. No update or delete endpoint exists. The DB role used by the app has no `UPDATE` or `DELETE` grant on `audit_log`.
- TC-I-AUD-4: Audit filter by actor, action, date range returns the expected rows.
- TC-I-AUD-5: Right to erasure: removing a user replaces `actor_email` and `actor_display_name` with `"deleted user"` placeholders in existing audit rows, while `actor_id`, `action`, `target`, and `timestamp` are preserved (NFR-PRIV-5).
- TC-I-AUD-6: Retention sweep: audit rows older than the configured window (default 18 months) are hard-deleted by the scheduled cleanup job (NFR-PRIV-4).
- TC-I-AUD-7: Refresh action (FR-REPORT-7) writes an audit row with actor and timestamp.
- TC-I-AUD-8: PDF export writes an audit row capturing the actor, year, period, and hub scope used (FR-REPORT-10).

### 4.5 Privacy and logging

- TC-I-PRIV-1: Application logs do not contain the session cookie, OAuth tokens, or service account JSON on any path (positive + negative cases, asserted via log capture).
- TC-I-PRIV-2: Application logs are valid JSON, one object per line, with required fields `timestamp`, `level`, `request_id`, `event` (NFR-PRIV-6).
- TC-I-PRIV-3: Backup cleanup job deletes backups older than the configured window (default 30 days) (NFR-PRIV-2).

## 5. E2E scenarios (Playwright)

- TC-E-1: Admin signs in, lands on report, sees all hubs.
- TC-E-2: Sign-in from `devlogic.eu` (or any non-`symphony.is` domain) is rejected with a clear message.
- TC-E-3: Sign-in from `symphony.is` but not in allowlist is rejected.
- TC-E-4: Viewer scoped to Sarajevo and Skopje signs in. Report shows only those hubs in KPIs, summary, per-hub cards, and above-midpoint section. Belgrade data is not present anywhere in the DOM. **Runs in M5 acceptance, not M4, see [ADR 0011](adr/0011-e2e-scope-m4-vs-m5.md).** In M4, hub-scoping correctness is covered by TC-U-AUTHZ-3 and TC-I-API-6.
- TC-E-5: Editor adds a comment on an above-midpoint hire. Comment appears in the report without a full reload.
- TC-E-6: Admin changes the spreadsheet tab name to an invalid value. Save fails with a validation error. Previous config remains active.
- TC-E-7: Google returns 500 (mocked outage). Report renders from last-known-good snapshot with a "stale" banner.
- TC-E-8: Audit log shows entries for all of the above actions with correct actors and timestamps.
- TC-E-9: Year selector: viewer switches between 2025 and 2026. KPIs and tables update for the selected year; hub scope is preserved across the switch (FR-REPORT-8).
- TC-E-10: Year-over-year overlay: viewer enables the "vs previous year" toggle. Both years render side by side, both filtered to the viewer's hub scope. Hubs outside scope are absent in both years (FR-REPORT-9).
- TC-E-11: Hub-scoped viewer exports PDF. The downloaded PDF's extracted text contains only their hubs; no other hub names appear anywhere in the bytes (FR-REPORT-10, NFR-PRIV-3).
- TC-E-12: Admin attempts to demote the last remaining admin. UI blocks the save; server returns 409; role is unchanged (FR-USER-3).

## 6. Security test cases

- TC-S-1: CSRF token missing on a POST request returns 403.
- TC-S-2: Rate limit triggers after N failed login attempts from the same IP.
- TC-S-3: `/admin/*` accessed by a viewer session returns 403 and writes an audit entry.
- TC-S-4: Hub-scoped consumer tries to query a disallowed hub via query param. Response is 403. Data is never leaked.
- TC-S-5: Secret scanner in CI fails the build if credentials are committed.
- TC-S-6: Security headers present on all responses: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`.
- TC-S-7: Cookie flags: session cookie has `HttpOnly`, `Secure`, `SameSite=Lax`.
- TC-S-8: Dependency audit fails the build on high-severity findings.

## 7. Mapping to PRD requirements

Each requirement in [prd.md](prd.md) maps to at least one test case:

- FR-AUTH-1..5: TC-I-AUTH-1..10, TC-E-2, TC-E-3.
- FR-AUTHZ-1..5: TC-U-AUTHZ-1..4, TC-I-API-2, TC-I-API-4, TC-I-API-6, TC-E-4, TC-S-3, TC-S-4.
- FR-REPORT-1..7: TC-U-REP-1..9, TC-I-SH-1, TC-I-SH-3, TC-I-SH-6, TC-E-1, TC-E-7, TC-I-AUD-7.
- FR-REPORT-8 (year selector): TC-U-REP-10, TC-I-API-1, TC-E-9.
- FR-REPORT-9 (year-over-year): TC-U-REP-11, TC-U-REP-12, TC-I-API-8, TC-I-API-9, TC-E-10.
- FR-REPORT-10 (PDF export): TC-I-API-7, TC-I-AUD-8, TC-E-11.
- FR-CONFIG-1..5: TC-U-MAP-1..5, TC-I-API-5, TC-I-API-12, TC-I-API-13, TC-E-6.
- FR-COMMENT-1..4: TC-U-REP-5, TC-U-REP-13, TC-I-API-3, TC-E-5.
- FR-USER-1..4: TC-I-API-2, TC-I-API-10, TC-I-API-11, TC-E-12.
- FR-BRAND-1..8: TC-U-BRAND-1..5, plus the mandatory design-skill publish checklist on every UI-touching PR (enforced via review, not automated test).
- FR-AUDIT-1..3: TC-I-AUD-1..4, TC-I-AUD-7, TC-I-AUD-8, TC-E-8.
- NFR-SEC-*: TC-S-1..8.
- NFR-PRIV-2 (backup retention): TC-I-API-13, TC-I-PRIV-3.
- NFR-PRIV-3 (PDF scope): TC-I-API-7, TC-E-11.
- NFR-PRIV-4 (audit retention): TC-I-API-13, TC-I-AUD-6.
- NFR-PRIV-5 (right to erasure): TC-I-AUD-5.
- NFR-PRIV-6 (structured logs, PII redaction): TC-I-PRIV-1, TC-I-PRIV-2.
- NFR-PRIV-7 (secret management): TC-S-5 (gitleaks).
- NFR-COMP-2 (offboarding via Google Workspace): M4 path — TC-I-AUTH-3 (allowlist) + TC-I-AUTH-10 (admin revoke); Post-M4 path — TC-I-AUTH-9 (automatic Google probe). See [ADR 0012](adr/0012-day-one-offboarding.md).

Any PRD requirement without a mapped test is a gap and must be closed before that requirement is considered "done".

## 8. How to run

- `make test` runs unit + integration (backend + frontend).
- `make e2e` runs Playwright against `docker-compose.test.yml`.
- `make ci` runs everything plus lint, type-check, and security scans.
- CI runs all three on every PR and blocks merge on failure.

## 9. Update policy

- Any change to `backend/app/report/`, `backend/app/auth/`, `backend/app/api/`, or `frontend/src/api/` must include or update a test in this doc's scope.
- New acceptance criteria must land in this doc in the same PR as the feature.
- When a test is skipped or removed, the PR must link the ADR or ticket justifying it.
- This doc and [prd.md](prd.md) are reviewed at the end of every milestone (M1..M6) and updated if reality has diverged.

## 10. Review checklist (for you)

- Coverage targets are acceptable (85% on report + auth).
- E2E list covers the flows you care about. Add or drop scenarios as needed.
- Security test cases match what the company would audit against.
- Mapping in section 7 shows you that every PRD requirement is testable. Flag any gaps.
