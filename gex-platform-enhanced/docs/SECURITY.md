# GEX Security Posture

Honest statement of what is enforced, what is deferred, and why. A buyer's
security questionnaire should be answerable from this page.

## Enforced today

- **JWT auth** (HS256 dev / RS256 via key paths), 30-min access tokens,
  refresh tokens, bcrypt-family (pbkdf2_sha256) password hashing.
- **Production guardrails (fail-fast at startup)** — `app/core/config.py`:
  - `ENVIRONMENT=production|staging` + default `SECRET_KEY` → refuses to start.
  - `ENVIRONMENT=production|staging` + `GEX_DEMO_MODE=True` → refuses to start
    (demo headers bypass JWT verification and are dev-only).
- **Demo account controls**: `GEX_SEED_DEMO_USERS=0` disables seeding;
  `GEX_DEMO_PASSWORD` overrides the shared dev password.
- **ABAC**: server-side visibility for projects, gates, risk flags
  (classification × stakeholding × clearance), 404-not-403 to avoid
  existence leaks. Policy is code-reviewed Python (policy-as-code) — a
  deliberate choice: auditable in git, changed via PR, not via console.
- **Append-only audit**: evidence transitions, project-context changes, and
  risk-flag lifecycle each write to insert-only event tables with actor and
  timestamp. Waivers require a justification note.
- **Evidence documents**: content-addressed (sha256), size-capped (25 MB),
  filename-sanitised, upload requires a valid bearer token; document arrival
  never auto-verifies (SUBMITTED at most — verification is a human transition).
- **Rules versioning**: every bankability snapshot is stamped with
  `rules_version`; the changelog lives next to the rules.

## Known deferrals (accepted risks, with reasoning)

1. **Tokens in `localStorage`** (XSS-exfiltratable). Migration to httpOnly
   SameSite cookies + CSRF token touches every authenticated fetch and the
   session bootstrap; scheduled as one change, not piecemeal. Mitigations
   until then: 30-min TTL, no third-party scripts in the bundle.
2. **No SSO/SCIM**. Enterprise identity (OIDC against the buyer's IdP) is a
   prerequisite for any multi-company production deployment; the JWKS
   endpoint already exists as the integration seam.
3. **SQLite, single node**. WAL-mode SQLite is adequate for the current
   single-tenant demo scale and trivially backed up; Postgres migration path
   exists (`DATABASE_URL` already configured, Alembic present).
4. **No rate limiting / WAF**. Behind a reverse proxy in any deployment;
   not enforced in-app yet.
5. **No SOC2/ISO27001**. Organisational, not technical; requires the
   operational maturity tracked in OPERATIONS.md first.

## Reporting

Suspected vulnerability: open a private issue or contact the maintainer
directly. Do not file public issues for security findings.
