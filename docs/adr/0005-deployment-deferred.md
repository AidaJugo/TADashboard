# ADR 0005: Deployment target deferred until M6

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic

## Context

Symphony has an existing VPN-gated internal tool. The exact deployment environment, DNS setup, secret manager, and operational runbook are not yet fully surfaced to this project. Picking a target now risks rework; picking too late blocks the go-live milestone.

## Decision

Build deployment-agnostic. Produce container images, 12-factor config via environment variables, standard health endpoints, structured JSON logs to stdout, and no dependency on a specific cloud SDK beyond Google Sheets.

Before we deploy (M6), Aida writes `docs/deployment-options.md` comparing:

1. Google Cloud Run behind Cloud IAP or Cloudflare Access.
2. Symphony's existing VPN-gated infrastructure (wherever the core internal tool runs).
3. A self-hosted VM with explicit VPN + TLS termination.

Decision gate: one option is selected before any production deploy. The choice ships as ADR 0010.

## Consequences

- We do not over-fit to any one provider in v1.
- We must not introduce Cloud Run-only features (for example, managed secrets, cold-start assumptions) without flagging them.
- The CI pipeline builds and scans images but does not push to a production registry yet.

## Alternatives rejected

- Decide now without context: risks picking something that conflicts with Symphony's network or compliance posture.
- Defer forever: blocks real use, which is the point of the project.
