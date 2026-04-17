# ADR 0003: Sheet access via a Google Cloud service account, not delegated OAuth

- Status: Accepted
- Date: 2026-04-17
- Deciders: Aida Jugo Krstulovic, Enis Kudo

## Context

The backend needs to read the Google Sheet that holds hiring rows. Two options:

1. A Google Cloud service account with read-only access to the one Sheet.
2. Delegated OAuth: reuse the signed-in user's Google token to fetch the Sheet.

## Decision

Use a dedicated Google Cloud service account with `https://www.googleapis.com/auth/spreadsheets.readonly` limited to the single Sheet shared explicitly with the service account email.

## Consequences

- Hub scoping is enforced server-side, not by Google's per-user sharing. This is what we want: the Sheet is shared with the TA team; the app applies per-hub filters before returning data to viewers. Delegated OAuth would force us to share the Sheet with every viewer directly, which defeats the scoping model.
- Only one set of Google credentials to rotate. Service account JSON key goes through the secret manager (see [ADR 0008](0008-secrets-env-vars.md)).
- If the service account key leaks, the blast radius is one read-only Sheet. We still treat it as a secret and scan for leaks in CI.
- No per-user Google OAuth flow for Sheet access. We do still use Google OAuth for authentication (see [ADR 0004](0004-google-workspace-sso.md)), but with no Drive scope.

## Alternatives rejected

- Delegated OAuth: incompatible with per-hub scoping (the app must see all hubs to filter them), adds a second OAuth consent step for each user, and leaks the "who can read which rows" decision into Google's sharing model where we have less control.
- Anonymous / link-based Sheet access: off the table for confidential data.
