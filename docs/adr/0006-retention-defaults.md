# ADR 0006: Retention defaults: 18 months audit log, 30 days backups

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

The app holds Strictly Confidential hiring data and writes an audit log of every sensitive action. Symphony does not yet have a published internal retention policy that covers this tool. GDPR applies because identifiable employee data is processed.

## Decision

Default retention, configurable in the admin UI without a redeploy:

- Audit log: 18 months, then hard-delete.
- Database backups: 30 days, encrypted at rest, then hard-delete.
- Last-known-good Sheet snapshot: keep only the latest.
- Session records: deleted on expiry.

Right to erasure: an admin can remove a user and their audit log entries within 30 days of a written request, except where legal obligation requires retention.

## Consequences

- Defensible defaults that align with GDPR principles (purpose limitation, storage limitation).
- Values live in the `config_kv` table so Symphony's DPO can tighten them without code changes.
- Any reduction below 90 days for the audit log requires a new ADR.

## Alternatives rejected

- Infinite retention: unjustified under GDPR and unnecessary for this tool's purpose.
- Matching Symphony's yet-to-be-published policy: not written yet; we cannot block on it.
