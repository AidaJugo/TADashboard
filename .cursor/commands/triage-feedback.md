---
description: Triage and fix feedback from a manual-testing pass, one PR at a time, following the iteration loop.
---

You are picking up the Symphony TA Hiring Report repo to triage and fix feedback from a manual-testing pass.

## Read first

1. `AGENTS.md` (root)
2. `.cursor/rules/iteration-loop.mdc` — non-negotiable workflow
3. `docs/prd.md` and the relevant ADRs in `docs/adr/`
4. `HANDOFF.md` (current state, open items, deferred work)
5. `docs/manual-test-feedback.md` if it exists (running log of findings)

## How to work

Follow the iteration loop exactly. One concern per branch, one branch per PR, branch off `main`, never commit to `main`. Match the shape of PR #2 (`fix/header-contrast-wcag-aa`) and PR #4 (`chore/iteration-loop-rule`).

Before any code:

1. Triage every finding into one of these buckets:
   - **bug**: code does not match the PRD or an ADR. Fix in product code with a regression test.
   - **spec drift**: code matches a previous behaviour that has since changed in the PRD/ADR, or the PRD/ADR is silent. Stop. Write an ADR (or PRD update) **first** in the same PR, then change the code.
   - **config**: env vars, Docker, infra, secrets. Goes in a separate PR from product code. Never bundled with a bug fix.
   - **UX**: visual, copy, accessibility. Apply the `symphony-design` Cursor skill. Tokens only, no hex literals, voice rules from the skill.
   - **out of scope / defer**: belongs to a later milestone or needs a product call. Do not silently fix. Add to `HANDOFF.md` "Open follow-ups" with a one-line rationale.

2. Produce a written triage table (finding → bucket → PR plan → test IDs from `docs/testing.md`). Show it to me and wait for sign-off before writing code.

3. After sign-off, ship one PR at a time, smallest first. For each PR:
   - Branch: `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`
   - Add or update a test that fails before your change and passes after
   - Run `make ci` locally; push only when green
   - Open a PR with the template filled, reference the finding ID and the PRD/ADR section
   - Self-review the diff in GitHub before tagging me
   - Do **not** merge without my explicit go-ahead, even if all checks pass

## Hard rules

- Do not relax validation, schema checks, or scope checks to "make it work". If the live data does not match the spec, the spec wins. Either the data is wrong or the spec is wrong; the agent does not get to silently relax the code.
- Do not edit anything in the do-not-touch zones (see `AGENTS.md`) without an ADR or PRD update in the same PR. Call it out in the PR body.
- Do not bundle config fixes with product code. Separate PRs.
- Do not commit secrets. If a finding includes a secret in a screenshot or log paste, redact it in your response and do not write it to disk.
- If you find yourself looping or unsure, stop and ask. Small misread > large rewrite.

## What I want back

1. The triage table, sorted by severity (security/auth/scope first, then correctness, then UX, then defer).
2. A proposed PR sequence (PR-by-PR plan, dependencies called out).
3. Wait for my "go" before any branch is created.

## Findings

If I have pasted findings below this section in chat, use those. Otherwise read `docs/manual-test-feedback.md` and triage every entry whose status is `open`.
