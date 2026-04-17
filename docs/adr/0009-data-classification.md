# ADR 0009: Data classification: Strictly Confidential

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

The app holds per-hire salary, midpoint, gap, recruiter, city, and status information for identified or re-identifiable Symphony employees. This is sensitive personal and commercial data.

## Decision

Classify all hiring data held or processed by this tool as **Strictly Confidential** under Symphony's handling posture. Apply the following controls across design and operation:

1. Access only via SSO with an explicit allowlist ([ADR 0004](0004-google-workspace-sso.md)).
2. Role + per-hub scoping enforced server-side.
3. Append-only audit log of login, report view, config edits, and comment edits (see PRD FR-AUDIT).
4. Encrypted in transit (TLS 1.2+) and at rest (DB + backups).
5. No copies in screenshots, CI logs, error reports, or chat tools.
6. Incident response: a suspected data leak must be reported to Aida within 24 hours. Service account key rotated immediately.
7. No third-party analytics (no Google Analytics, no Sentry Pro without a DPA) in v1.

## Consequences

- Any feature that exports, shares, or forwards data must go through a security review in the PR.
- CI enforces the secret scan (gitleaks) and dependency scanning (pip-audit, npm audit).
- `docs/testing.md` includes security-specific cases (unauthorized domain rejected, hub scoping cannot be bypassed, audit log is append-only).

## Alternatives rejected

- Internal / Confidential (one step down): does not match the nature of the data (individual salaries). Off the table.
- Handling case-by-case: invites drift. Off the table.
