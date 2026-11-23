# GEX security posture

What is enforced, what is not, and what must change before GEX runs on a public
server. A buyer's security questionnaire should be answerable from this page.

**Checked against the code and the development database on 22 Nov 2026** (migration
head 129). If this page and the code disagree, the code wins: fix this page. The
detail and the history behind each point are in `.claude/CLAUDE.md` and
`docs/CLAUDE_HANDOFF.md`.

---

## 1. Enforced today

### Accounts and sign-in

- **Accounts are vetted, not self-served.**
  - `POST /api/v1/account/register` creates a `PENDING` account and nothing else.
  - Only `ACTIVE` accounts may sign in (`core/account_lifecycle.py`).
  - Activation needs:
    - GEX staff;
    - telephone verification;
    - a signed usage agreement;
    - separation of duties (the activator is not the claimant).
- **Password policy** (`core/password_policy.py`):
  - minimum length 12, and 16 for GEX platform administrators;
  - common and context-derived passwords are refused.
- **Changing a password** revokes every refresh token and writes `account.password_changed` to the ledger.
- **Tokens.** GEX issues its own JWTs:
  - HS256 with `SECRET_KEY`, or RS256 with `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` (`scripts/generate_jwt_keys.sh`);
  - access tokens last 30 minutes, refresh tokens 7 days;
  - a refresh re-reads the account under the sign-in rule, so a suspended account cannot renew its session.
- **Production start-up guards** (`app/core/config.py`). With `ENVIRONMENT` set to `production`, `prod` or `staging`, the backend refuses to start:
  - on the development `SECRET_KEY`, unless RS256 keys are set;
  - with `GEX_DEMO_MODE=True`;
  - with `GEX_SEED_DEMO_USERS` enabled.
- **The backend refuses to start if any data slice reads SQLite.** PostgreSQL is the only runtime store (`db_backend.assert_postgres_runtime`).

### Tenant isolation: two layers

- **ABAC middleware** (`core/abac_middleware.py`) decides each request from the token's user, company, roles and project assignments.
- **PostgreSQL row-level security** applies underneath, whatever the application does.
  - The runtime connects as **`gex_app`**: no SUPERUSER, no BYPASSRLS, no DDL.
  - Migrations use a separate role, `gex_user`.
  - Measured 22 Nov: **171 of 178** tables carry FORCED RLS.
  - A connection with no tenant bound sees nothing (deny sentinel).
- **`PLATFORM_ADMIN` context** is used only at the bootstrap call sites listed in `.claude/CLAUDE.md`, and every use is logged.
- **Single-purpose roles:**
  - `gex_engine` (PF engine run log) and `gex_anchor` (ledger anchor) can each touch only their own tables;
  - their passwords are random.
- **Granting project access** is GEX administration only (migration 062). A tenant cannot grant itself access.

### Evidence and gates

- **A reviewer status is a verification.**
  - Who may verify which gate is fixed in `abac.REVIEWER_GATES`: certifier, independent engineer, lenders' adviser, insurer, and the three capital-provider advisers.
  - Never the submitter, its company or the project owner's company.
  - The actor is the token's user, never the request body.
  - VERIFIED must name the sha256 of a document on file.
- **Reviewers are appointed by GEX staff** on the instruction of a named party (`core/reviewer_appointments.py`). Self-appointment and owner instruction are refused.
- **Evidence documents** are stored by content hash. A document arriving never verifies anything on its own.
- **Gate figures come from the PF engine only** (`app/core/engine_view.py`). Every snapshot carries `rules_version` (now 4.9.0).

### Records that cannot be rewritten

- **Append-only tables** for evidence events, the contract record, custody inputs, conversion factors, allocations, idempotency records and the ledger outbox.
  - `gex_app` holds no UPDATE, DELETE or TRUNCATE on them.
  - The migrations that set this assert it afterwards.
- **Closed custody periods and frozen contract terms** cannot change; database triggers enforce this.
- **Four eyes inside each party** for trade confirmation and delivery confirmation (`core/wae.py`). Market roles are decided in one place (`core/market_policy.py`).
- **GEX staff are read-only on client projects** (ABAC rule R0P): they may read gate evaluations and evidence, nothing else.

### Supply chain

- **The frontend has no Supabase client or key.** `scripts/audit-supabase.mjs` fails the build if one comes back.

---

## 2. Not in place: fix before the public server

These are real gaps, not accepted risks. Items 1–6 make a public deployment unsafe as the configuration stands today.

1. **Demo header sign-in is on by default.**
   - `GEX_DEMO_MODE` defaults to `True`. While it is, a request with no `Authorization` header but an `x-demo-user` header is served as that user (`abac_middleware.py`).
   - `files/gex-demo-compose.yml` sets `ENVIRONMENT: development`, so the production guard never runs.
   - On the server: set `ENVIRONMENT=production` and `GEX_DEMO_MODE=False`.
2. **Secrets in public files.**
   - `gex-demo-compose.yml` writes `SECRET_KEY`, `GEX_JWT_SECRET` and the PostgreSQL superuser password as literals.
   - The `gex_app` and `gex_user` development passwords are also in `app/core/config.py`, `.claude/launch.json`, both `docker-compose*.yml` and the handoff.
   - All of these are on the public `co-work` GitHub repository. Anyone holding the signing key can forge a valid token.
   - On the server: new random values for every secret and every database role, supplied only from the environment.
3. **`docker-compose.prod.yml` publishes PostgreSQL (5432) and Redis (6379)** on every interface, with the public password and no Redis authentication. Do not deploy it as written. The pinned `files/gex-demo-compose.yml` exposes only the frontend (8080).
4. **Tokens are kept in `localStorage`** (`gex_auth_session`, `lib/authToken.ts`).
   - Any script injected into the page can read them.
   - The fix is httpOnly SameSite cookies plus a CSRF token. That touches every authenticated call, so it is one change, not a piecemeal one.
5. **No rate limiting or account lockout** on sign-in, registration or any other route. Put the server behind a reverse proxy that limits requests, and add lockout in the application.
6. **No security headers.**
   - Neither FastAPI nor `docker/nginx.conf` sets HSTS, Content-Security-Policy, X-Frame-Options or X-Content-Type-Options.
   - CORS defaults to `localhost` origins with credentials allowed; set `CORS_ORIGINS` to the real domain only.
   - TLS must end at the proxy.
7. **The production guard does not cover enough.** It checks the signing key, demo mode and demo seeding only. It does not check:
   - database passwords;
   - `DEBUG`, which defaults to `True`;
   - `CORS_ORIGINS`.

   The default `DATABASE_URL` in `config.py` points at port **5432**, which on the development Mac is a different, non-GEX PostgreSQL. Always set it explicitly.
8. **No second factor.** The "Enable Two-Factor Authentication" button on `/account` does nothing.
9. **No single sign-on (OIDC/SAML) or SCIM.** The JWKS endpoint (`/api/v1/auth/jwks`) is the integration point for it.
10. **Old exposures that are still live:**
    - The Supabase anon key has no recorded rotation; it is still in git history and in earlier public Docker images.
    - Real client staff email addresses are in the public repository's history.
11. **Auth tables carry no RLS by design** (`auth_users`, `auth_user_project_roles`). Role rows are protected by the application alone.
12. **No SOC 2 or ISO 27001.** These are organisational, and follow from the operations in `OPERATIONS.md`.

---

## 3. Reporting a vulnerability

Contact the maintainer directly. Do not open a public GitHub issue: the `co-work`
repository is public.
