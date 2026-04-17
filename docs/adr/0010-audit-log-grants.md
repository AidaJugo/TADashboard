# ADR 0010: Audit log DB grants: app role INSERT + SELECT only

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

The audit log is designed to be append-only (FR-AUDIT-1, ADR 0009). The ORM model
deliberately has no `updated_at` column and the application never issues `UPDATE` or
`DELETE` statements against `audit_log`. TC-I-AUD-3 asserts this at test time. But a
model convention and a test alone do not enforce the invariant: any future code path
that uses the app DB connection could issue an `UPDATE` without a failing test catching
it immediately.

Additionally, GDPR right-to-erasure (NFR-PRIV-5) requires that personal data fields
(`actor_email`, `actor_display_name`) can be replaced with "deleted user" placeholders.
That operation is a targeted `UPDATE` issued by a one-off erasure job, not by the
normal app serving path.

## Decision

Three database roles are defined:

| Role | Grants on `audit_log` | Notes |
|------|----------------------|-------|
| `ta_report_app` | `INSERT`, `SELECT` | Normal app serving path. Cannot modify or delete audit rows. |
| `ta_report_erasure` | `UPDATE (actor_email, actor_display_name)` | Right-to-erasure job only. Column-restricted. |
| `ta_report_sweep` | `DELETE` | Retention sweep job (ADR 0006). Restricted to rows older than the retention window at the app layer. |

No role is granted `UPDATE` on any column other than the two PII fields, and no role
is granted unbounded `DELETE`. The grants for `ta_report_app` on all other tables are
`SELECT`, `INSERT`, `UPDATE`, and `DELETE` (normal CRUD), except `audit_log`.

The grants are defined in `backend/grants.sql` and applied idempotently at deploy time
(before `alembic upgrade head`). See the runbook.

## Consequences

- Any future code path that issues `UPDATE audit_log SET ...` from the app role will
  receive an `InsufficientPrivilege` error from Postgres. TC-I-AUD-3 asserts this.
- The erasure job runs as `ta_report_erasure` and can only UPDATE the two PII columns.
  It cannot DELETE rows or modify action/target/timestamps.
- The retention sweep runs as `ta_report_sweep` and can only DELETE rows.
- During local development with `DATABASE_URL` pointing at a single superuser, the
  grant enforcement is not active. The integration test that asserts TC-I-AUD-3 must
  connect explicitly as `ta_report_app` (a non-superuser role) to be meaningful; it
  is marked `integration` and skipped in unit mode.
- Role creation and grants are idempotent (`CREATE ROLE IF NOT EXISTS`,
  `GRANT ... ON TABLE`). Re-running `grants.sql` is safe.

## Alternatives rejected

- **Trust the ORM convention + tests alone**: works until a developer adds a convenience
  helper that issues `UPDATE audit_log` to fix a data problem without writing a test.
  DB-level enforcement catches this class of mistake.
- **Single app role with all grants**: convenient but makes the append-only invariant
  unenforced at the DB layer, which is the point of having an audit log.
- **Row-level security**: adds complexity disproportionate to the scale (10 users).
  Table-level grant restrictions are sufficient.
