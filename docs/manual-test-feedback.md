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

### Example — Report shows "No hires yet for this period" with valid Sheet data

- **Where**: http://localhost:5173/, after Google login as an admin
- **Expected**: report renders rows from the Google Sheet for the current year
- **Actual**: empty state message; backend log shows `sheet_schema_error` with `missing: Note, Recruiter, Year`
- **Severity**: high
- **Logs / screenshots**: backend log line redacted to remove `actor_email`
- **Status**: open
