# ADR 0011: E2E test TC-E-4 runs in M5, not M4

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic
- Related: [testing.md](../testing.md) section 5, [prd.md](../prd.md) FR-AUTHZ-*, FR-REPORT-*

## Context

TC-E-4 is a Playwright scenario: a viewer scoped to Sarajevo and Skopje signs in
and the rendered report page contains no Belgrade data anywhere in the DOM.

The test requires three components to run end-to-end:

1. Login + server-side session (M4).
2. Hub-scoping filter applied to every aggregation stage (M4).
3. The `/api/report` endpoint and the React report page that renders KPIs,
   per-hub cards, the summary, and the above-midpoint section (M5).

In the initial test plan, TC-E-4 was listed under M4 acceptance. M4 does not
build components 3, so the test cannot run end-to-end in M4.

## Decision

TC-E-4 is an M5 acceptance gate, not an M4 acceptance gate.

- `docs/testing.md` section 5 keeps TC-E-4 in place but marks it "runs in M5
  (see ADR 0011)".
- In M4, hub-scoping correctness is validated by:
  - `TC-U-AUTHZ-3` — unit test that the scoping filter applies at every
    aggregation stage, not only the final table.
  - `TC-I-API-6` — integration test that a hub-scoped viewer requesting an
    out-of-scope hub receives 403 and an audit entry is written.
- The mapping in `docs/testing.md` section 7 under FR-AUTHZ is unchanged: TC-E-4
  remains listed, now understood to be an M5 gate.

## Consequences

- M4 ships with hub-scoping coverage at the function layer (TC-U-AUTHZ-3) and
  the HTTP-API layer (TC-I-API-6). The backend cannot serve unscoped data.
- The DOM-level "Belgrade is absent from the rendered page" invariant is only
  testable once the real report UI exists. That becomes an M5 acceptance gate.
- No new test cases are created. TC-E-4 itself is unchanged; only its milestone
  slot moves.
- The M5 PR must run TC-E-4 in CI before it merges.

## Alternatives rejected

- **Build a throwaway `/api/report` stub plus a placeholder report page in M4
  solely so TC-E-4 runs end-to-end now.** Placeholder HTML does not exercise the
  real report rendering path, so a passing TC-E-4 against it would not prove the
  M5 UI is scope-safe. Throwaway code delays M4 for no coverage gain.
- **Build a scoped `/api/report` stub without UI in M4 and adapt TC-E-4 to
  assert on JSON response shape.** That duplicates `TC-I-API-6`, which already
  asserts 403 on out-of-scope hubs. Adds no new coverage beyond what the
  integration tests already provide.
