# ADR 0007: Observability: structured JSON logs to stdout for v1

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

Symphony does not have a company-mandated observability stack for this project. Picking Datadog / Grafana Cloud / Honeycomb before we know where the app is deployed risks wasted integration work.

## Decision

- Emit structured JSON logs to stdout. One line per event. Required fields: `timestamp`, `level`, `request_id`, `actor` (if authenticated), `event`, `route`, `status`, `duration_ms`.
- Redact PII: no email bodies, no Sheet row payloads, no session tokens. Only include actor email on security-relevant events (login, role change, config edit).
- Expose `/healthz` (liveness) and `/readyz` (checks DB and, if applicable, Sheets).
- No metrics endpoint in v1. Logs are the single signal.

When we pick a deployment target (see [ADR 0005](0005-deployment-deferred.md)), logs land in whatever the host offers natively (Cloud Logging, rsyslog, Loki, etc.). Metrics and traces can be added in a later ADR without changing the app's logging shape.

## Consequences

- Zero vendor lock-in for v1.
- If we need dashboards or alerts before M6, we can ingest the JSON stream into any tool.
- Troubleshooting relies on grep-friendly logs. Acceptable for the scale and team size.

## Alternatives rejected

- Pick Datadog now: cost and integration work not justified by current scale.
- No logging: audit and debug impossible. Off the table for a confidential tool.
