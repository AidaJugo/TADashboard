# ADR 0008: Secret management: environment variables for v1, scanned by gitleaks

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

Symphony does not yet expose a shared secret manager for this project. We need somewhere to put the Google service account JSON, the OAuth client secret, the session signing key, and the database URL. We have to ship without blocking on a decision we cannot drive.

## Decision

- v1: secrets live in environment variables. Developers use `.env` (git-ignored) locally; production uses whatever the chosen deployment target injects (Cloud Run secrets, systemd `EnvironmentFile`, VPN-gated host's config management).
- `.env.example` is committed with empty values and clear comments explaining each secret and how to obtain it.
- `gitleaks` runs on every commit (pre-commit) and every PR (CI). A detected secret blocks the merge.
- The session signing key is rotated at least every 90 days.
- The Google service account JSON key is rotated at least every 180 days and immediately if exposed.

When a centralised secret manager is available (GCP Secret Manager, AWS Secrets Manager, HashiCorp Vault), we migrate. A new ADR will document the migration.

## Consequences

- Simple, portable, works on every deployment candidate considered in [ADR 0005](0005-deployment-deferred.md).
- Secret rotation is manual. Documented in the runbook (see `handover` milestone).
- Dev mistakes (checking in `.env`, pasting a key in a log) are the main risk. Mitigated by gitleaks and the logging redaction rules in [ADR 0007](0007-observability-stdout.md).

## Alternatives rejected

- Ship with a specific secret manager: premature, ties us to a host before [ADR 0005](0005-deployment-deferred.md) resolves.
- Secrets in the repo: obviously off the table.
- `.env` committed with real values encrypted via `sops` or similar: adds tooling and ceremony disproportionate to a 10-user internal tool at this stage. Revisit if the team grows.
