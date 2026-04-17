# AGENTS.md

Guidance for any AI agent (Cursor, Claude Code, Codex, etc.) or human contributor working in this repository.

Read this file before your first edit. It is short on purpose.

## The one-paragraph context

This is a Symphony internal tool. It replaces a manual TA (Talent Acquisition) hiring report with a live, SSO-protected, per-hub scoped web app. Hiring data lives in a Google Sheet (source of truth); app metadata lives in Postgres. All day-one users are on `@symphony.is`. The data is classified **Strictly Confidential** (see [docs/adr/0009-data-classification.md](docs/adr/0009-data-classification.md)). Break that, and we have a problem.

Everything else is in [docs/prd.md](docs/prd.md). Read it before a non-trivial change.

## Before you start

1. Read [docs/prd.md](docs/prd.md) and the relevant ADR under [docs/adr/](docs/adr/).
2. Load the Cursor skill [.cursor/skills/symphony-design/SKILL.md](.cursor/skills/symphony-design/SKILL.md) for anything that touches UI or user-facing copy.
3. Check `.cursor/rules/` for per-area rules. Cursor loads them automatically; if you are another agent, read them manually for the area you are editing.
4. Run `make install` once, then `make test` before and after your change.

## How to contribute

- One change, one concern. Small PRs beat big PRs here.
- Branch off `main`: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- Conventional commits: `feat(auth): enforce hd=symphony.is on callback`.
- Every PR updates docs and tests that it affects. See [CONTRIBUTING.md](CONTRIBUTING.md) and the PR template.
- Every PR passes the full CI pipeline. No skipping hooks.

## Do's

- Respect the PRD and ADRs. If you disagree, write a new ADR in the same PR and link it.
- Add tests for the behaviour you change. Unit for logic, integration for boundaries, Playwright E2E for security-critical flows (see [docs/testing.md](docs/testing.md)).
- Use typed models everywhere: Pydantic on the backend, TypeScript on the frontend. Treat `Any` and `any` as bugs.
- Read secrets from environment variables, never hardcode. See [ADR 0008](docs/adr/0008-secrets-env-vars.md).
- Write structured JSON logs via the shared logger. Redact PII per [ADR 0007](docs/adr/0007-observability-stdout.md).
- Use the design tokens from [frontend/src/theme/tokens.ts](frontend/src/theme/tokens.ts) and the voice rules from [.cursor/skills/symphony-design/SKILL.md](.cursor/skills/symphony-design/SKILL.md) for every UI or copy change.

## Don'ts

- **Do not commit secrets.** `gitleaks` will block you, but do not get into the habit. No `.env`, no service account JSON, no OAuth client secret anywhere in the repo.
- Do not bypass auth or hub scoping for convenience. If a change makes `GET /report` return data a viewer should not see, the change is wrong.
- Do not introduce a new runtime language, framework, or heavy dependency without an ADR.
- Do not fetch from third-party CDNs at runtime (no Google Fonts, no CDN chart libs). Vendor it in.
- Do not delete or rewrite the audit log. It is append-only by design.
- Do not edit `legacy/`. It is the reference prototype, preserved for context.
- Do not write files that look like user data into the repo (fixtures are fine but must be clearly synthetic; use made-up names).

## Model guidance

- Default to a capable general model (Claude Sonnet or equivalent) for most work.
- For auth, authz, session handling, migrations, or anything that touches the audit log or secret handling, prefer the strongest available model and treat the change as security-critical.
- When the PR description says "security-sensitive", two humans review before merge (see [CODEOWNERS](CODEOWNERS)).

## Do-not-touch zones

Changes to anything under these paths require an ADR update or PRD update in the same PR:

- `backend/app/auth/`
- `backend/app/authz/`
- `backend/app/audit/`
- `backend/alembic/versions/` (migrations are forward-only; never rewrite history)
- `docs/adr/`
- `docs/prd.md`
- `.github/workflows/ci.yml`
- `.cursor/skills/symphony-design/`

## Useful commands

```bash
make install        # install backend (uv) and frontend (npm) deps
make lint           # ruff, black, eslint, prettier, mypy
make test           # unit + integration
make e2e            # Playwright end-to-end
make dev            # docker-compose up (db + backend + frontend)
make ci             # run everything CI runs, locally
make migration m="add users table"  # new Alembic migration
```

## When in doubt

Ask Aida. Small misread > large rewrite.
