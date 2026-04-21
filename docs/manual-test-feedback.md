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
- **Status**: fixed — current Sheet schema includes all required columns; `sheet_fetched row_count: 322` confirmed 2026-04-21
