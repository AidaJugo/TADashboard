# ADR 0004: Authentication via Google Workspace SSO, `symphony.is` only

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic, Enis Kudo

## Context

All day-one users are Symphony employees with `@symphony.is` Google Workspace accounts. Symphony's Google Cloud org is `devlogic.eu` for historical reasons, but user identity is on `symphony.is`. The tool holds Strictly Confidential hiring data.

## Decision

- Single sign-on via Google OAuth 2.0 / OIDC.
- Enforce `hd=symphony.is` in the authorization request and re-verify `hd` and `email_verified` server-side on the ID token.
- Reject `@devlogic.eu` and any other domain at the login endpoint. Log the rejection.
- Maintain an allowlist in the `users` table. A verified `symphony.is` login only grants a session if the email exists in the allowlist.
- Session cookies are HttpOnly, Secure, SameSite=Lax, server-signed, with a 4-hour idle timeout and a 24-hour absolute timeout (see PRD NFR-SEC).

## Consequences

- Leverages Symphony's existing identity provider, MFA, and offboarding. When a person leaves, disabling their Google account kills their access without any code change.
- Allowlist means a random `symphony.is` account cannot self-enrol. A TA Admin must add them. Matches the "small, named group" scope.
- Cross-domain accounts (devlogic.eu) are explicitly not supported. If Symphony later consolidates, we re-visit.

## Alternatives rejected

- Username/password: adds password management, weaker security, duplicates identity.
- Auth0 / Okta: overkill for 10 users on a single domain.
- Magic links via email: weaker than SSO, bypasses MFA.
