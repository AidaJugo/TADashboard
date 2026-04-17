# Pull request

## What

<!-- One or two sentences. What behaviour changes? -->

## Why

<!-- Link the PRD section, ADR, or issue this PR advances. -->

- PRD: <!-- docs/prd.md#fr-auth-1 -->
- ADR: <!-- docs/adr/0004-google-workspace-sso.md -->

## How

<!-- Short architectural note. Point at the files a reviewer should read first. -->

## Risk

- [ ] Touches auth, authz, audit, migrations, or secrets. If checked, request a second reviewer.
- [ ] Changes a response payload, DB schema, or public API contract.
- [ ] Introduces a new runtime dependency.

## Checklist

- [ ] PRD and ADRs updated (or explicitly no change).
- [ ] Unit tests added or updated.
- [ ] Integration tests added or updated.
- [ ] E2E tests added or updated (only for security-critical flows per `docs/testing.md`).
- [ ] No secrets in the diff. `gitleaks` green locally and in CI.
- [ ] No hardcoded colours, fonts, or user-facing strings outside the design tokens and copy files.
- [ ] `make ci` passes locally.
- [ ] Audit log entry added for any new sensitive action.

## Screenshots or copy changes

<!-- If this touches UI or user-facing text, paste before/after and confirm the Symphony design skill checklist (.cursor/skills/symphony-design/SKILL.md) passes. -->
