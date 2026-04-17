# Contributing

Thanks for working on this. This is an internal Symphony tool that handles Strictly Confidential hiring data. The rules below are not optional.

Read [AGENTS.md](AGENTS.md) first. It has the short version and is the single source of truth for both agents and humans.

## Setup

Requirements:

- Python 3.12
- Node 20
- Docker and docker-compose
- `uv` (`pipx install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `pre-commit` (`pipx install pre-commit`)

One-time:

```bash
make install
pre-commit install
cp .env.example .env  # fill in values, never commit
```

Day to day:

```bash
make dev     # starts db + backend + frontend
make test    # unit + integration
make e2e     # Playwright end-to-end
make lint    # lint + typecheck
make ci      # everything CI runs, locally
```

## Branches and commits

- Branch off `main`. No work on `main`.
- Branch names: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- Conventional commits: `feat(scope): concise summary`. Examples:
  - `feat(auth): enforce hd=symphony.is on oauth callback`
  - `fix(report): apply hub scope before aggregation`
  - `chore(ci): add gitleaks to pre-commit`

## Pull requests

Every PR:

1. Targets `main`.
2. Passes CI. No `--no-verify`.
3. Uses the [PR template](.github/pull_request_template.md). Fill every section.
4. Updates `docs/prd.md` and the relevant ADR if the change touches scope, data, auth, or deployment.
5. Adds or updates tests for the behaviour changed.
6. Leaves the repo in a state where `make ci` is green locally.

Security-sensitive PRs (auth, authz, audit, migrations, secrets, CI) need two reviewers per [CODEOWNERS](CODEOWNERS).

## Reviewing

- Read the PRD section the PR references.
- Pull the branch and run `make ci`.
- Approve only if: tests pass, docs match reality, no secrets, no bypasses, no dead code.

## Reporting a security issue

Do not open a public issue. Message Aida directly.
