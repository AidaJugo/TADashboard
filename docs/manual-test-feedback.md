# Manual-test feedback log

Running list of findings from manual testing. Append new entries at the top. The `/triage-feedback` command reads every entry whose status is `open`.

## How to add an entry

Copy the template, fill it in, set status to `open`. Do not pre-classify the bucket; the triage command does that.

```
### YYYY-MM-DD — Short title

- **Where**: URL or screen (e.g. http://localhost:5173/admin/users, ReportPage > YearSelector)
- **Expected**: what the PRD/ADR/spec says should happen
- **Actual**: what you saw
- **Severity**: blocker | high | medium | low
- **Logs / screenshots**: optional, paste relevant lines or attach paths. Redact secrets and PII.
- **Status**: open | triaged | in-pr (#N) | fixed (#N) | deferred
```

## Findings

<!-- Newest first. Append above this comment, not below. -->

### 2026-04-21 — PDF export fails with 500 (WeasyPrint/Pillow venv mismatch)

- **Where**: `http://localhost:5173/` — "Export PDF" button on the report page
- **Expected**: FR-REPORT-10 — clicking Export PDF downloads a scoped PDF of the current view.
- **Actual**: Browser shows "Site wasn't available" and saves "export-pdf.txt". Backend returns 500 on every request to `GET /api/report/export-pdf`.
- **Severity**: high
- **Root cause**: `ImportError: cannot import name '_imaging' from 'PIL'` inside the backend container. Pillow's C extension is compiled for macOS (from `make install` on the host) but the container is Linux. The `./backend:/app` bind mount in `docker-compose.yml` shares the `.venv` between host and container, so the Linux container ends up with a macOS-native Pillow wheel that it cannot load. WeasyPrint (which depends on Pillow) fails to import on every PDF request.
- **Logs**: `ImportError: cannot import name '_imaging' from 'PIL' (/app/.venv/lib/python3.12/site-packages/PIL/__init__.py)` — `GET /api/report/export-pdf → 500 Internal Server Error`
- **Status**: triaged → **config** → `fix/pdf-export-venv-isolation`

### 2026-04-21 — Above-midpoint table: Salary, Midpoint, Gap (%) show as dashes

- **Where**: `http://localhost:5173/` — "Above mid-point — exceptions and justifications" section
- **Expected**: Salary (€), Midpoint (€), and Gap (%) columns display numeric values for all above-midpoint hires.
- **Actual**: Salary and Midpoint always show `—`. Gap (€) shows only for values < €1,000. Gap (%) always shows `—`.
- **Severity**: high
- **Root cause (two bugs, same fix PR):**
  - F-004a: `_to_float` in `backend/app/report/logic.py` calls `float("3,600.00")` which raises `ValueError` on comma-formatted numbers. Returns `None` → frontend renders `—`. Values ≥ 1,000 all have commas; values < 1,000 happen to parse correctly.
  - F-004b: `populate_salary_report.py` writes `gap_pct` as `"20.0%"` (percentage string). Pipeline expects a decimal fraction (`"0.200"`); the frontend multiplies by 100 to display. `%` sign also blocks `_to_float`.
- **Logs / screenshots**: Screenshot 2026-04-21_at_12.23.10. No backend errors — `_to_float` silently returns `None` on parse failure.
- **Status**: triaged → `fix/above-midpoint-numeric-parsing` (F-004a + F-004b)

### 2026-04-21 — Hub pairs not configured; hub cards and above-midpoint section empty

- **Where**: `http://localhost:5173/` — hub cards section and above-midpoint section both empty; admin config page Hub Pairs table has no rows
- **Expected**: Hub cards and above-midpoint exceptions table render per-hub data (FR-REPORT-4, FR-REPORT-5).
- **Actual**: `hub_pairs` DB table is empty → `hub_order = []` → hub cards section renders nothing, above-midpoint section renders nothing. KPIs and summary table still work. Backend logs confirm: `SELECT hub_pairs... {}`.
- **Severity**: high (core report sections invisible)
- **Logs / screenshots**: `SELECT hub_pairs.id... FROM hub_pairs [cached since ...] {}` — empty result on every report request.
- **Status**: triaged → **config** (no code fix needed). Resolution: add hub pairs in the admin config page. See triage note for the full list of city→hub mappings required for the synthetic dataset.

### 2026-04-21 — Year selector excludes 2024; new Sheet data not visible

- **Where**: `http://localhost:5173/` — year selector dropdown (top-right header)
- **Expected**: Year selector shows every year that has data in the Sheet. PRD FR-REPORT-8 and §5 state "more years added as data lands". New synthetic data for 2024, 2025, and H1 2026 was added to the Sheet and should be accessible.
- **Actual**: Dropdown only offers `[2025, 2026]`. 2024 is permanently excluded by a hardcoded floor filter (`>= 2025`). Backend logs confirm data is fetched correctly (`sheet_fetched row_count: 322`, no `sheet_schema_error`). 2024 data is present in the Sheet but unreachable. 2025 is visible only as a YoY comparison panel; users can select it directly from the dropdown. H1 2026 data IS visible once the correct period tab is selected.
- **Severity**: high
- **Logs / screenshots**: `sheet_fetched row_count: 322, tab: "Report Template"` — no schema error. Root cause is frontend-only: `AVAILABLE_YEARS = [CURRENT_YEAR - 1, CURRENT_YEAR].filter((y) => y >= 2025)` in `frontend/src/pages/ReportPage.tsx` line 44.
- **Status**: triaged → `fix/year-selector-available-years` (F-001)

### Example — Report shows "No hires yet for this period" with valid Sheet data

- **Where**: http://localhost:5173/, after Google login as an admin
- **Expected**: report renders rows from the Google Sheet for the current year
- **Actual**: empty state message; backend log shows `sheet_schema_error` with `missing: Note, Recruiter, Year`
- **Severity**: high
- **Logs / screenshots**: backend log line redacted to remove `actor_email`
- **Status**: open
