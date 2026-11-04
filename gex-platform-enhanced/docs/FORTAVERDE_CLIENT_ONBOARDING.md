# FortaVerde — client onboarding (Möhring Energie, Pecém)

**Status:** decided by JML on 2026-11-02. Checked against the tree on 2026-11-02: account vetting, lifecycle and password policy are unchanged since 2026-09; nothing in `app/` inserts into `tenants`. Handoff for Claude Code, working in `gex-platform-enhanced`.
**Data:** `backend/scripts/fortaverde_client_accounts.json` (tenant and users) and
`backend/scripts/fortaverde_knowledge_v2.json` (what GEX knows about the project).
Read `.claude/CLAUDE.md` first: the database, credential and vetting rules there apply to every step below.

---

## 1. Goal

Möhring Energie becomes a real client tenant with two registered users:

| Contact | Name | Title | Email | business_function |
|---|---|---|---|---|
| P1 | Sascha Möhring | Managing Director and CTO | contact-p1@client.invalid | EXECUTIVE |
| P2 | Jan Block | CEO | contact-p2@client.invalid | EXECUTIVE |

Tenant: `company_id = mohring_energie`, `company_name = Möhring Energie`, `PRODUCER`, `DE`.
`company_id` must equal `company_slug("Möhring Energie")`, which returns `mohring_energie`. Project ownership depends on that match.

Claude Code does steps 3 and 4 and stops. Steps 5–6 are human vetting by GEX staff, and step 7 follows activation.

## 2. Rules that do not bend

1. **No `demo1234`, and no password chosen by GEX for a client.** The password policy rejects it: shorter than 12 characters, and it is the platform's shared demo default (`DEMO_PASSWORD`). A password known to GEX also means the audit trail cannot tell the client's actions from GEX's. Do **not** edit `app/core/password_policy.py`, catch its error, or write a hash directly to get around it.
   **Exception, JML 2026-11-03:** the two Möhring users are registered with one temporary password chosen by JML, which they change. Run `onboard_fortaverde_client.py --register --temporary-password --execute`: the password is typed at a getpass prompt, never written to a file, a command line or a log, and each account carries an `account.temporary_password_set` event. Until the owners change it, the audit trail cannot tell their actions from those of anyone at GEX who knows it, so the change matters. Each owner changes it at **Change your password** (`/account/password`, the key button in the top bar); a banner asks on every screen until they do.
2. **Register through the real path.** Use `POST /api/v1/account/register` or the same code path, so the `account.registered` audit event is written. Accounts are created **PENDING**, and nothing in steps 3–4 makes them ACTIVE.
3. **Never write vetting evidence.** `phone_verified_*`, `agreement_*`, `activated_*` and the `claim` step are recorded only through the vetting endpoints, by the GEX employee who did the work, after it happened. Do not backfill, simulate or seed them.
4. **Separation of duties holds.** Whoever records the telephone verification must not be the one who activates (`assert_separation_of_duties`). If JML makes the calls, a different admin activates: `t-marwenc` or `t-mohamedk` (both `MANUAL_ADMIN_GRANT`, per `.claude/CLAUDE.md`).
5. **Credentials.** Use `ALEMBIC_DATABASE_URL` (gex_user) only for the tenant row in step 3. The runtime stays on `DATABASE_URL` (gex_app). Never point the runtime at a superuser to clear a permission error.

## 3. Create the tenant row (Claude Code)

Nothing in `app/` inserts into `tenants`: activation sets `auth_users.company_id` but creates no tenant. Without this row, `POST /projects` fails on the `projects.owner_tenant_id` foreign key.

- Write an idempotent script, `backend/scripts/onboard_fortaverde_client.py`, that reads `fortaverde_client_accounts.json`.
- Add `--tenant`: `INSERT … ON CONFLICT (company_id) DO NOTHING`, then print whether the row was created or already present.
- Default to a dry run and write only with `--execute`, the same convention as `load_comprehension_test_project.py`.
- Refuse if `company_slug(tenant.company_name) != tenant.company_id`.

## 4. Register the two users (Claude Code)

- Add `--register` to the same script. For each user, call the registration path with `email`, `user_name`, `company_name`, `company_type`, `business_function`, `jurisdiction` and `telephone`.
- **Telephone is mandatory** in `RegistrationRequest` (min 6 characters). Both values are `null` in the JSON. If either is missing, stop and report it; do not invent a number.
- **Password:** generate `secrets.token_urlsafe(32)`, pass it, and discard it. Never print, log or store it, the same pattern as `create_platform_admin.py`. The account then cannot be logged into until its owner sets a password (section 8).
- Registration of an existing address returns the same response without a `user_id`. Detect that and report "already registered"; do not retry.
- Print each `user_id` and `account_state` (expected: `PENDING`).

## 5. Vetting (GEX staff, not Claude Code)

For each user, in order, through `/api/v1/account/{user_id}/…`:

1. `claim` by a GEX admin. The account moves to IN_VETTING.
2. `telephone-verification`: who called, the number called, who they spoke with, identity and organisation confirmed.
3. `usage-agreement`: agreement reference, version, signed by, signed on. The software usage agreement must actually be signed; the draft MoU is not this agreement.

Record each value in `fortaverde_client_accounts.json → vetting` as it happens.

## 6. Activation (a second GEX admin)

`POST /api/v1/account/{user_id}/activate` with `company_id = "mohring_energie"`, by an admin who is **not** the one who made the call (for example `t-marwenc` or `t-mohamedk` if JML made it).

## 7. Project (after activation)

- The project is created by the client's own account (`POST /api/v1/projects` as P1 or P2), because the owner is always the caller's company. Use `fortaverde_knowledge_v2.json → project` for name, molecule (`NH3`), location, country (`BR`), power model (`HYBRID`), financing model (`PROJECT_FINANCE`) and phase.
- **Phase:** the record says `construction` on JML's FID statement, which contradicts the October email (contradiction X1). Use whatever phase the client states at creation; X1 stays open until the FID resolution is on file.
- After the project exists, run `scripts/convert_invented_evidence.py --assign-open` (dry run first) so open evidence requests get named assignees from the two ACTIVE accounts.
- Then retire the TEST fixture: `scripts/load_fortaverde_test_project.py --remove --execute`. The real tenant replaces it.
- Claims stay **UNVERIFIED**. Nothing from the knowledge record is written as evidence; the client submits documents, and the appointed reviewers verify them.

## 8. Open items

- **Passwords:** the platform has no invite or reset-by-email flow. Until one exists, an owner sets their password with `scripts/set_password.py <email>` at a terminal that reaches the instance, typed by the owner, not by GEX. Building an invite flow (single-use, expiring token, owner chooses password) is the proper fix; spec it separately.
- **Reachability:** the instance runs on `localhost`. The two users cannot reach it until it is deployed somewhere they can open.
- **Second admin:** confirm which of `t-marwenc` / `t-mohamedk` activates.
- **Stray admin `you_`:** `.claude/CLAUDE.md` lists a `MANUAL_ADMIN_GRANT` account `you_` created on 10-11. It very likely came from the placeholder `you@greenearthx.com` in setup instructions. An admin account sees every tenant. JML to confirm, then suspend it through the vetting endpoint. Do not delete it by SQL.
- **Telephone numbers:** needed for registration (step 4) and for the verification call (step 5).

## 9. Acceptance checks

- `tenants` has `mohring_energie`, and no other row changed.
- `auth_users` has exactly two new rows: emails as above, `company_name = Möhring Energie`, `account_state = PENDING`, `is_active = 0`, `kyc_status = UNVERIFIED`, all vetting columns empty.
- Logging in as either address returns 401 or 403, never 200, before step 6.
- `account.registered` events exist for both.
- `tests/` still passes with both `DATABASE_URL` and `ALEMBIC_DATABASE_URL` exported. Report the pass/skip counts, and read skip reasons with `-rs`.
- `git diff` touches only the new script, this doc and the accounts JSON. `password_policy.py` and `account_lifecycle.py` are unchanged.
