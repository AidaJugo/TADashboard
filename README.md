# Symphony TA Hiring Report Platform

Internal Symphony tool. Replaces the manual TA hiring report with a live, SSO-protected, per-hub scoped web app.

Source of truth for hiring rows: a Google Sheet the TA team already edits. App metadata (users, roles, hub scopes, comments, audit log) lives in Postgres.

Data classification: **Strictly Confidential**. Treat accordingly.

## Status

Scaffolding. See [HANDOFF.md](HANDOFF.md) for the current state and the next agent's starting point.

## Start here

1. [AGENTS.md](AGENTS.md): the short rulebook for any contributor (human or agent).
2. [docs/prd.md](docs/prd.md): product requirements.
3. [docs/adr/](docs/adr/): architectural decisions.
4. [docs/testing.md](docs/testing.md): test strategy.
5. [CONTRIBUTING.md](CONTRIBUTING.md): setup and PR rules.

## Local development

Requirements: Python 3.12, Node 20, Docker, `uv`, `pre-commit`.

```bash
make install
pre-commit install
cp .env.example .env  # fill in Google OAuth, service account path, DB URL
make dev              # docker-compose up: db + backend + frontend
make test             # unit + integration
make e2e              # Playwright
make ci               # the full CI suite, locally
```

## Layout

```
.
├── AGENTS.md                # rules for agents and humans
├── CONTRIBUTING.md          # human setup and PR rules
├── CODEOWNERS
├── docs/
│   ├── prd.md
│   ├── testing.md
│   ├── adr/
│   └── brand-guidlines/
├── .cursor/
│   ├── rules/               # per-area Cursor rules
│   └── skills/
│       └── symphony-design/ # brand voice + visual tokens
├── .github/
│   ├── workflows/ci.yml
│   └── pull_request_template.md
├── backend/                 # FastAPI + Alembic + uv + pytest
├── frontend/                # Vite + React + TS + Playwright
├── legacy/                  # reference prototype; do not edit
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitleaks.toml
├── .pre-commit-config.yaml
└── .gitignore
```

## Contact

Aida Jugo Krstulovic (owner). Enis Kudo (TA, day-one admin).
