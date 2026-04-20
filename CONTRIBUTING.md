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

**First-run on a fresh deployment** — seed the day-one admin before anyone can log in:

```bash
# With the venv active and the database reachable:
python -m app.admin.bootstrap \
    --email aida.jugo@symphony.is \
    --name "Aida Jugo Krstulović"

# Re-running is safe (idempotent).
# For CI / CD pipelines, set DAY_ONE_ADMIN_EMAILS instead of using --email:
# DAY_ONE_ADMIN_EMAILS="aida.jugo@symphony.is:Aida Jugo" python -m app.admin.bootstrap
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

## Iteration loop

This is the workflow we hold ourselves and any AI agent to. It exists because we have already drifted once: during M6 troubleshooting, fixes landed on `main` directly, the column-mapping spec was silently relaxed, and a few config workarounds got mixed into product code. The loop below is what stops that.

### One change, one branch, one PR

- Branch off `main`. Name it `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, or `docs/<slug>`.
- Never commit to `main`. Even a one-line UI fix gets a branch and a PR (see #2 as the worked example).
- One concern per PR. If you find a second thing while in flight, open a follow-up issue or a second branch. Do not bundle.

### Before you write code

1. State the goal in one sentence. If you cannot, the scope is wrong.
2. Find the PRD section and ADR(s) the change touches. Link them in the PR body.
3. If the change conflicts with the PRD or an ADR, stop and write the ADR (or PRD note) **first**, in the same PR. Do not silently bend the spec to fit the code.
4. List the test cases the change must pass or add. Reference IDs from `docs/testing.md`.

### While coding

- Keep config fixes (env vars, Docker, infra) separate from product code. Mixing them slows review and hides regressions.
- If a deployment problem forces a code change, that code change still needs a test. No "temporary" relaxations.
- If you touch a do-not-touch zone (see [AGENTS.md](AGENTS.md)), the PR body must call it out and link the ADR/PRD update.

### Before you push

```bash
make ci          # everything CI runs, locally
```

Push only when green. CI is not a remote linter; it is the last gate before review.

### Pull request

1. Open against `main` using the [PR template](.github/pull_request_template.md). Fill every section.
2. CI must be green. No `--no-verify`.
3. Self-review the diff in GitHub before requesting a human or agent reviewer. Half of all review comments come from things you can spot yourself.
4. Tag a reviewer per [CODEOWNERS](CODEOWNERS). Security-sensitive areas need two.
5. Squash-merge. Delete the branch.

### After merge

- Pull `main` locally with `--ff-only`.
- If the PR closed a HANDOFF.md item or unblocks the next milestone, update HANDOFF.md in the next PR (not this one).
- If the PR exposed a spec gap, open a follow-up branch the same day. Do not let it linger.

### Working with an AI agent

Treat the agent as a junior engineer with strong typing skills and zero memory.

- Give a written prompt with: goal, scope, files in/out of scope, acceptance criteria (test IDs), and the PRD/ADR references.
- Require a plan before code on anything bigger than a one-file change.
- Reject any PR where the agent silently changes scope, weakens validation, or skips tests. The fix is a new PR, not an amend.
- The agent should pick model strength based on risk: stronger model for auth, authz, audit, migrations, and anything in the do-not-touch zones; default model for UI, copy, and isolated logic.
- If the agent gets stuck in a loop or starts deviating from the spec, end the session, write down what you learned in HANDOFF.md, and start a new session with a tighter prompt.

### Worked example

PR #2 (`fix/header-contrast-wcag-aa`) is the smallest possible end-to-end pass: branch, single-concern commit, PR with template, four CI checks green, squash-merge, delete branch, fast-forward `main`. Anything larger uses the same shape.

## Reporting a security issue

Do not open a public issue. Message Aida directly.
