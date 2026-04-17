"""Google Workspace OAuth (see ADR 0004).

TODO: implement
- GET /auth/login redirects to Google with hd=symphony.is
- GET /auth/callback verifies hd and email_verified server-side,
  checks allowlist, creates server-side session cookie.
- POST /auth/logout invalidates session.
"""
