# ADR 0012: Day-one offboarding: allowlist + admin revoke, automatic Google probe deferred

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic
- Related: [prd.md](../prd.md) NFR-COMP-2, [ADR 0004](0004-google-workspace-sso.md),
  [ADR 0008](0008-secrets-env-vars.md), [testing.md](../testing.md) section 4.2

## Context

NFR-COMP-2 requires that when Symphony HR deactivates a user's Google Workspace
account, access to the app is removed automatically. The NFR names Google
Workspace as the offboarding system of record; it does not dictate the mechanism.

Two mechanisms achieve automatic detection:

1. **Refresh-token probe.** On login, Google issues a refresh token. We store
   it per session and periodically exchange it for a new access token against
   Google's token endpoint. If Google returns `invalid_grant`, the user is
   deactivated and we revoke the session. This requires storing a
   Google-issued per-user secret at rest (encrypted). It would be the first
   per-user secret in the system (see ADR 0008).
2. **Userinfo probe.** We store the access token Google returned at login and
   call the userinfo endpoint periodically. If Google returns 401, we revoke.
   The access token is short-lived (≈1 hour), so this only detects offboarding
   within that window. After it expires, there is nothing to probe with and no
   way to refresh without a refresh token (mechanism 1).

Both mechanisms require a new column on `sessions` and a forward-only Alembic
migration.

Day-one scale is 10 users, of whom two (Aida Jugo Krstulovic, Enis Kudo) are
admins and will be notified of any offboarding by Symphony's HR/ops channel.

## Decision

For M4 / day-one, offboarding is enforced by two application-layer backstops
rather than an automatic Google probe:

1. **Allowlist.** When HR notifies an admin of an offboarding, the admin
   removes the user from the `users` allowlisted set. The user's next SSO
   callback is rejected (`TC-I-AUTH-3`: allowlist miss returns "Access denied"
   and writes an audit entry). Removal also prevents any new session issuance.
2. **Admin-triggered session revoke.** Admins set `sessions.revoked_at` for
   all active sessions of the offboarded user via an admin endpoint
   (`POST /api/admin/users/{id}/revoke-sessions`). The auth middleware must
   treat any session with `revoked_at IS NOT NULL` as invalid on the next
   authenticated request and return 401. This endpoint and the middleware
   check are both in M4 scope.

An automatic Google probe is **deferred to a Post-M4 follow-up PR** tracked in
`HANDOFF.md`. The choice between the refresh-token probe and the userinfo probe
(and the encryption-at-rest design that a refresh-token probe requires) is
itself a decision that warrants its own ADR when the follow-up is picked up.

## Consequences

- NFR-COMP-2 is met in M4 through an **operator-assisted path**: offboarding
  takes effect within the time it takes an admin to (a) remove the user from
  the allowlist and (b) revoke their active sessions. Without (b), a stolen
  cookie or an active tab could outlive removal for up to 4 hours idle / 24
  hours absolute. With (b) applied, the next request on that session returns
  401 and is audited.
- No per-user secret is stored at rest in M4. The refresh-token-vs-userinfo
  design choice is deferred.
- M4 scope gains: the admin session-revoke endpoint and the middleware check
  for `revoked_at`. These are small additions on top of work already in scope.
- `docs/testing.md` changes:
  - `TC-I-AUTH-9` (automatic Google probe invalidates session) is re-slotted
    as **Post-M4** and linked to this ADR. The test itself is unchanged.
  - A new case, `TC-I-AUTH-10`, is added for M4: admin-triggered revoke via
    `sessions.revoked_at` causes the next authenticated request on that
    session to return 401 and writes an audit entry.
  - The NFR-COMP-2 mapping in section 7 is updated to list the M4 path
    (`TC-I-AUTH-3` + `TC-I-AUTH-10`) and the Post-M4 path (`TC-I-AUTH-9`).
- `HANDOFF.md` Post-M4 backlog gains an entry for the Google probe with a
  two-line summary of the refresh-token vs. userinfo trade-off.

## Alternatives rejected

- **Full refresh-token probe in M4.** Adds encrypted-at-rest secret storage,
  a key-management choice (not yet decided per ADR 0008), and a new column on
  `sessions`. Muddies the M4 review, which already covers login, session,
  authz, and audit. Warrants its own focused ADR and PR.
- **Userinfo probe in M4.** Detects offboarding only within the ≈1-hour
  access-token lifetime, after which there is nothing to probe with. Shipping
  this code and then removing it when the full refresh-token probe lands is
  wasted churn.
- **No operator-assisted path in M4, relying only on the allowlist.** The
  allowlist blocks future logins but does not invalidate an active session for
  up to the absolute-timeout window (24 hours). Unacceptable for a Strictly
  Confidential application (ADR 0009) because a user removed today could still
  act for a day. The admin session-revoke endpoint closes this window.
