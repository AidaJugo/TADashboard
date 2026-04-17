# PRD: TA Hiring Report Platform

Status: DRAFT v0.1
Owner: Aida Jugo Krstulovic
Contributors: Enis Kudo (TA)
Last updated: 2026-04-17

## 1. Purpose

Symphony's TA (Talent Acquisition) team tracks hiring performance against salary benchmarks. Today, all of this data lives in a Google Sheet, and reports are generated manually by copying, filtering, and formatting data before sharing it with stakeholders. This is slow, error-prone, and hard to scope to the right audience.

Enis Kudo (TA) identified the problem, had the idea for a live benchmarking report, and built a working prototype (`generate_report.py`) that reads the Sheet and emits a static HTML dashboard. He validated the prototype with the TA team and downstream users (leadership, finance partners, hiring managers). Feedback was positive: the dashboard answers the right questions and everyone wants it available continuously, not as an ad-hoc export.

The next step is to scale the validated prototype into a secure, production-grade internal tool so it can be:

- Accessed continuously by the TA team and stakeholders, behind company SSO.
- Scoped per user and per hub, so each stakeholder sees only what they should.
- Maintained without code changes (comments, column mapping, users, hubs editable in a UI).
- Audited, monitored, and deployed inside Symphony's standard operational envelope.

The current prototype is the design spec for the report itself. This project replaces the manual report generation workflow with a continuously-available web app, without changing what TA edits day to day (the Google Sheet remains the source of truth).

## 2. Users and personas

- TA Admin (1 to 2 people): owns the Sheet, user access, column mapping, comments, benchmark notes. Day one: Aida Jugo Krstulovic and Enis Kudo.
- TA Editor (0 to 3 people): edits comments and benchmark notes. Cannot manage users or config.
- Viewer (up to ~7 people): leadership, finance partners, hiring managers. Reads the report. May be scoped to specific hubs.
- Service account (non-human): reads the Google Sheet.

Total human users: ~10.

## 3. Goals

- Replace the manual report generation workflow with a continuously-available web app behind company SSO.
- Preserve the validated prototype's report format and insights. No redesign in v1.
- Keep TA editing the Google Sheet where they already work. No new editing tool to learn.
- Give role- and hub-appropriate views to non-TA stakeholders so the same live report serves multiple audiences.
- Make business rules (comments, column mapping, hub pairs, users) editable in a UI, not in code.
- Keep proprietary hiring data safe. No public exposure, audit trail for every sensitive action, least privilege.

## 4. Non-goals (v1)

- Not a general TA or HR suite. Hiring benchmarking only.
- No write-back to Google Sheets.
- No DB-backed editor for hiring rows (Sheet remains source of truth).
- No multi-company or multi-tenant.
- No live integrations with Slack, Jira, HRIS in v1. Architecture keeps a clean extension point so these can be added later when Symphony has a central internal tool (see A-7).
- No external (non-company) access.

## 5. Glossary

- Company: Symphony.
- Primary Google Workspace domain: `symphony.is`.
- Google Workspace org: `devlogic.eu` (org ID `559486237593`, customer ID `C030gs0en`).
- TA team: Talent Acquisition team at Symphony. Owner of this tool.
- Hub (contracting hub): Sarajevo, Banja Luka, Belgrade, Novi Sad, Nis, Skopje, Medellin, Remote, plus Netherlands, USA, UK. Hub list is editable by admins at runtime.
- WF / NonWF (hire type): WF = billable hire, staffed on client work. NonWF = internal Symphony staff (not billable to a client). The prototype's `WFM / NonWFM` labels are renamed to `WF / NonWF` throughout the app. Raw column values in the Sheet keep whatever label TA uses; the mapping is configurable.
- Midpoint: target salary for (Position, Seniority, Hub).
- Status: Below / At mid-point / Above / No salary.
- Period: Monthly, Quarterly (Q1-Q4), Half-year (H1, H2), Annual.
- Year: calendar year. v1 supports 2026 live plus historical 2025 for comparison. More years added as data lands.
- Recruiter: person who owned the hire. Displayed next to each hire.
- Hire note: free-text note per hire, up to 500 characters, editable by TA. Used for context like explaining an above-midpoint hire.

## 6. Background and constraints

- Source of truth for hiring rows: Google Sheet on Google Drive. This remains true in v1.
- Auxiliary data (comments, config, users, audit): Postgres.
- Data volume: thousands of rows over 10 years. Small.
- Concurrent users: ~10.
- Data classification: Strictly Confidential. No other specific classification rules apply at Symphony.
- Deployment environment: likely the same VPN-gated environment as the company's core internal tool. Exact platform decided at M6. See OQ-3.

## 7. Functional requirements

### 7.1 Authentication

- FR-AUTH-1: Users sign in via Google Workspace SSO.
- FR-AUTH-2: Only accounts with `hd=symphony.is` can sign in. `devlogic.eu` accounts are not permitted.
- FR-AUTH-3: A signed-in user without an entry in the `users` allowlist sees "Access denied" and cannot reach protected routes.
- FR-AUTH-4: Sessions expire after 4 hours of inactivity. Absolute maximum session length 24 hours, after which the user must re-authenticate. Chosen because the data is classified Strictly Confidential; 4h idle is a conservative industry default for sensitive internal tools.
- FR-AUTH-5: Logout invalidates the session server-side.

### 7.2 Authorization

- FR-AUTHZ-1: Three roles: `admin`, `editor`, `viewer`.
- FR-AUTHZ-2: Admin-only routes reject non-admin users with HTTP 403 and an audit entry.
- FR-AUTHZ-3: Each user may have 0 or more allowed hubs. 0 means all hubs.
- FR-AUTHZ-4: Hub-scoped users see only their hubs in KPIs, tables, charts, and totals. Other hubs must not leak anywhere in the UI or API response.
- FR-AUTHZ-5: Hub scoping cannot be bypassed by URL or API query manipulation.

### 7.3 Report viewing

- FR-REPORT-1: On page load, fetch latest data from the configured Sheet, cache in-process for 60 seconds, render within 3 seconds on a typical connection.
- FR-REPORT-2: If the Sheet is unreachable, show the last-known-good snapshot with a "Data may be stale" banner and the snapshot timestamp.
- FR-REPORT-3: Period navigation: Monthly, Quarterly, Half-year, Annual, matching the prototype's layout in `generate_report.py`.
- FR-REPORT-4: KPIs, WF/NonWF summary table, per-hub breakdowns, above-midpoint exceptions table, donut and bar charts.
- FR-REPORT-5: Above-midpoint rows show the stored comment, recruiter name, and any benchmark note for the period.
- FR-REPORT-6: Empty periods show a clear empty state, not an error.
- FR-REPORT-7: A "Refresh" button bypasses the cache and fetches fresh data. Refresh action is audited.
- FR-REPORT-8: Year selector. Users can switch between available years (2025, 2026, ...). Default is the current year. Historical 2025 data is imported from the existing dataset during M4.
- FR-REPORT-9: Year-over-year comparison view. For a selected period, the user can toggle a "vs previous year" overlay that shows the same period in the previous year side by side. Applies the viewer's hub scoping to both years.
- FR-REPORT-10: Export the currently visible view (respecting hub scope and year) as PDF. Available to anyone with view access. The PDF contains only what the user can see on screen, never more.

### 7.4 Configuration (admin)

- FR-CONFIG-1: Admins can change the spreadsheet ID and tab name without a deploy.
- FR-CONFIG-2: Admins can remap columns (Position, Seniority, City, Salary, Midpoint, Gap_EUR, Gap_PCT, Status, Month, Year, Type, Recruiter, Note).
- FR-CONFIG-3: Admins can manage hub pairs.
- FR-CONFIG-4: Before saving, config is validated: the spreadsheet is reachable, the tab exists, required columns map to real columns, value types parse.
- FR-CONFIG-5: Invalid config is rejected with a specific error (naming the column or problem). Previous config remains active.

### 7.5 Comments and benchmark notes (admin + editor)

- FR-COMMENT-1: Editors and admins can create, read, update, delete comments keyed by (Position, Seniority, Hub, Salary).
- FR-COMMENT-2: Same for benchmark notes per period (Jan..Dec, Q1..Q4, H1, H2, Annual).
- FR-COMMENT-3: Same for city-level notes.
- FR-COMMENT-4: All changes are audited with before/after summary.

### 7.6 User management (admin only)

- FR-USER-1: Admins can add a user by email, assign role, assign allowed hubs.
- FR-USER-2: Admins can edit or remove users. Removing a user invalidates their session on next request.
- FR-USER-3: The last admin cannot be removed or demoted.
- FR-USER-4: First admins are seeded from an environment variable at bootstrap. Day-one admins: `aida.jugo@symphony.is` and `enis.kudo@symphony.is`.

### 7.7 Design and branding

Source documents:
- Voice and tone guide: [Google Doc](https://docs.google.com/document/d/1Jql49Vy7SeBaxdLwoR71fLe-4TIIBDbp6MMZlh4ymkA/edit)
- Brand book 2021 (visual identity): [`docs/brand-guidlines/Symphony-brandguidelines_2021.pdf`](brand-guidlines/Symphony-brandguidelines_2021.pdf)

Design tokens (the contract):

- Primary purple `#6c69ff`
- Red `#fe7475`
- Yellow `#ffbe3d`
- Light grey `#f4f5fb`
- Black `#000000`
- White `#ffffff`
- Secondary (accent, never text): deep navy `#222453`, light blue `#91afea`, blue-grey `#9fabc0`, peach `#f9dfc4`
- Typography: Poppins. H1 Bold 72, H2 Bold 48, H3 SemiBold 36, H4 Medium 30, body Regular 16 (23/10 line-height and tracking per brand book), tag Bold 20, CTA Bold 30
- Text colour: black or white only. Never a secondary colour.

Requirements:

- FR-BRAND-1: The app follows Symphony's brand voice (precise, direct, human, confident; no hype) and visual identity (brand book 2021).
- FR-BRAND-2: Typography is Poppins, with the weight and size scale above. Loaded via a self-hosted font, not a third-party CDN.
- FR-BRAND-3: The prototype's layout (KPI cards, summary table, per-hub cards, above-midpoint section, period navigation) is preserved. Visuals are re-themed to Symphony's palette, not redesigned.
- FR-BRAND-4: Design tokens live in a single source file (`frontend/src/theme/tokens.ts`) and are consumed by all components. No hardcoded hex values in components.
- FR-BRAND-5: Accessibility. Text is only ever black or white on any background. Contrast ratios meet WCAG AA. Secondary palette is used only for accents, shapes, and non-text UI elements.
- FR-BRAND-6: Logo, favicon, and document title reflect Symphony. Logo safety area (1/2 x-height), no crop/distort/rotate/gradient/shadow/colour changes (misuse rules from brand book 2021).
- FR-BRAND-7: Shape accents (minimal geometric shapes, solid or stroke, never mixed) can be used as chart decorations or section dividers, in line with the brand book.
- FR-BRAND-8: All UI copy is checked against the voice guide's "Before you publish" 5-question rubric. Codified in `.cursor/skills/symphony-design/SKILL.md` so agents enforce it on every UI change.

### 7.8 Audit

- FR-AUDIT-1: Append-only audit log for: login success, login denied (with reason), report view, manual refresh, config edit, comment CRUD, user CRUD, role change, hub scope change.
- FR-AUDIT-2: Each entry records actor email, action, target, timestamp (UTC), client IP.
- FR-AUDIT-3: Admins can view the audit log with filters by actor, action, and date range.

## 8. Non-functional requirements

### 8.1 Security

- NFR-SEC-1: HTTPS-only with HSTS. HttpOnly, Secure, SameSite=Lax session cookies.
- NFR-SEC-2: CSRF protection on state-changing requests.
- NFR-SEC-3: Google service account has read-only access to exactly one spreadsheet. No Drive-wide access.
- NFR-SEC-4: Secrets managed as environment variables in v1 (see NFR-PRIV-7). Never committed to git. Never written to logs. Upgrade path to a secret manager is a single PR when Symphony adopts one.
- NFR-SEC-5: Rate limiting on login and write endpoints.
- NFR-SEC-6: Dependency, container, and SAST scanning in CI. Block on high-severity findings.
- NFR-SEC-7: No PII in application logs. Structured logging with redaction.
- NFR-SEC-8: Security headers: `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`.

### 8.2 Privacy and data handling

- NFR-PRIV-1: No third-party analytics or telemetry.
- NFR-PRIV-2: Database backups encrypted at rest. Retention default 30 days, configurable 7 to 90 days via admin config.
- NFR-PRIV-3: PDF export is limited to the user's currently visible, hub-scoped view (see FR-REPORT-10). No full-dataset export endpoint in v1.
- NFR-PRIV-4: Audit log retention default 18 months, configurable 6 to 60 months via admin config. GDPR-aligned.
- NFR-PRIV-5: Right to erasure. When a user is removed, their email and display name are replaced with "deleted user" placeholders in the audit log while the stable user ID and actions remain. Personal data (email, display name) is not retained beyond active user records + the 18 month audit window.
- NFR-PRIV-6: Observability. Structured JSON logs to stdout by default. The deployment platform's native log sink is used (Cloud Run Logging, Kubernetes logs, etc.). No third-party observability vendor in v1.
- NFR-PRIV-7: Secret management. v1 uses environment variables injected by the deployment platform, with `.env` files git-ignored locally and `gitleaks` in CI. When Symphony adopts a standard secret manager, the app switches in a single PR.

### 8.3 Performance

- NFR-PERF-1: Report page loads in under 3 seconds on a typical connection for a typical period.
- NFR-PERF-2: Scales to 10 concurrent users without degradation.

### 8.4 Availability

- NFR-AVAIL-1: Business hours availability target 99%. Single-region acceptable at this scale.
- NFR-AVAIL-2: Graceful degradation if Google Sheets is unreachable (see FR-REPORT-2).

### 8.5 Compliance

- NFR-COMP-1: Data is treated as Strictly Confidential. Decision captured in an ADR.
- NFR-COMP-2: Offboarding is handled automatically by Google Workspace: when a user's Symphony account is deactivated on their last day, SSO login fails and the existing session is invalidated on the next authenticated request. No separate offboarding hook is required.

## 9. Assumptions

- A-1: Symphony uses Google Workspace. Primary domain `symphony.is`, Workspace org `devlogic.eu`. Single-domain login is the default assumption.
- A-2: A dedicated Google Cloud project will be created for this tool (e.g. `symphony-ta-report`). Existing projects (`studious-sign-480709-i6`, `gen-lang-client-0109407117`) are unrelated and will not be reused.
- A-2a: Sheet access uses a service account (decision captured in ADR-0005). One service account inside the dedicated project, with the hiring Sheet explicitly shared as Viewer. No domain-wide delegation. No per-user delegated OAuth for Sheet reads. Users sign in with OAuth for identity only.
- A-2b: Service account key stored in a secret manager. Rotated on a scheduled cadence (default 90 days) tracked in the runbook.
- A-2c: Direct Drive access to the hiring Sheet is limited to TA admins and editors. All other users see only the scoped view through the app.
- A-3: ~10 users over the life of the tool.
- A-4: A few thousand hiring rows over 10 years.
- A-5: The Sheet structure is stable enough that TA will adjust gracefully when warned about schema drift.
- A-6: Deployment can sit behind the same VPN as the company's core internal tool.
- A-7: A clean extension point (outbound webhooks or a small integration module) is added so Slack/Jira/HRIS/central-company-tool integrations can be plugged in later without re-architecting.
- A-8: Historical 2025 hiring data will be imported during M4 so year-over-year comparison has meaningful content on launch.

## 10. Open questions

- OQ-3: Where does the core internal tool run (Kubernetes, VMs, which cloud)? Decision gate is M6 (deploy). Work through M2 to M5 is deployment-agnostic; Docker and docker-compose are sufficient.
- OQ-11a: Logo SVG source. Brand book 2021 specifies logo usage, but we need the actual SVG file for primary, secondary, and one-colour variants. Action: Aida locates the files and drops them into `frontend/src/assets/brand/`. Placeholders used until then.

## 11. Success metrics

- SM-1: All TA stakeholders who currently receive the static HTML switch to the app within 1 month of launch.
- SM-2: Zero security findings of severity "high" or above in the first post-launch review.
- SM-3: Time from Sheet update to visible in app is under 1 minute (with cache and manual refresh).
- SM-4: Zero incidents of unauthorized access in the first 6 months.

## 12. Milestones

- M1: PRD and test strategy approved.
- M2: Guardrails, CI, scaffolding merged.
- M3: Auth, authorization, hub scoping working end-to-end with E2E tests.
- M4: Report UI ported. Reading live from Sheet with last-known-good fallback.
- M5: Admin config, comment management, and audit in production.
- M6: Deployment decision, deployed, handover docs.

## 13. Review checklist (for you)

Before we move on, please confirm or correct:

- Users and personas reflect the real team.
- Roles and the per-hub scoping model fit how TA wants to share the data.
- Non-goals list is correct (nothing missed that should be in v1, nothing in v1 that should be deferred).
- Security section is aligned with company policy.
- Open questions section is where you want to loop in your friend for answers.
