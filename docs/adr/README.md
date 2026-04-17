# Architecture Decision Records

This directory captures significant decisions made for the Symphony TA Hiring Report Platform.

Format: one short Markdown file per decision, numbered sequentially. Status is `Proposed`, `Accepted`, `Superseded` (with link), or `Deprecated`.

Rule: any change that touches the auth model, data source, deployment target, or secret-handling posture requires a new ADR or an update to an existing one, with the PR linking to it.

## Index

| ID | Title | Status |
|----|-------|--------|
| [0001](0001-stack.md) | Backend FastAPI, frontend React + Vite + TypeScript | Accepted |
| [0002](0002-sheet-as-source-of-truth.md) | Google Sheet is the source of truth for hiring rows | Accepted |
| [0003](0003-service-account-sheet-access.md) | Sheet access via a Google Cloud service account, not delegated OAuth | Accepted |
| [0004](0004-google-workspace-sso.md) | Authentication via Google Workspace SSO, `symphony.is` only | Accepted |
| [0005](0005-deployment-deferred.md) | Deployment target deferred until M6 | Accepted |
| [0006](0006-retention-defaults.md) | Retention defaults: 18 months audit log, 30 days backups | Accepted |
| [0007](0007-observability-stdout.md) | Observability: structured JSON logs to stdout for v1 | Accepted |
| [0008](0008-secrets-env-vars.md) | Secret management: environment variables for v1, scanned by gitleaks | Accepted |
| [0009](0009-data-classification.md) | Data classification: Strictly Confidential | Accepted |
