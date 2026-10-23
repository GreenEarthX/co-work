# GEX Platform — Engineering Handoff

**Generated:** 2026-08-09 · **Last updated:** 2026-10-23 · **Derived from:** repository
inspection, not conversation history.
**Scope:** state of the tree at `files/gex-platform-enhanced` and its siblings.

Where this document states a number (table counts, test counts, occurrence counts), it was
measured against the working tree or the live database at the time of writing. Where it
states an intention, it is marked as such.

---

## 1. Architecture and service boundaries

Four processes, all currently running locally:

| Port | Service | Tree | Role |
|---|---|---|---|
| 8000 | GEX backend (FastAPI) | `gex-platform-enhanced/backend` | Product logic, authz, persistence, proxying |
| 8001 | PF engine (FastAPI) | `files/gex_pf_engine/backend` *(sibling repo)* | Project-finance / Gabillon cashflow engine |
| 8002 | TEA engine (FastAPI) | `gex-platform-enhanced/tea_engine` | Techno-economic analysis (OpenPyTEA-derived) |
| 3000 | Frontend (Vite/React/TS) | `gex-platform-enhanced/frontend` | UI |
| 55432 | PostgreSQL (via socat) | container `files-postgres-1` | Primary datastore |

**Port 55432 is not a typo.** A different, non-GEX PostgreSQL occupies `:5432` on this
machine. `55432` is a socat forwarder to the GEX container. `backend/.env` overrides the
`config.py` default (which still says `:5432`) for this reason. Any new environment must
make the same distinction or it will silently migrate the wrong database.

**`gex_pf_engine` and `deal_engine` are DIFFERENT services** — a name collision, not a
duplicate, and the more dangerous of the two problems because it invites deleting one as
redundant. `files/gex_pf_engine` (sibling) is the Gabillon PF engine on `:8001`:
`cfads.py`, `waterfall.py`, `debt/sculpting.py`, 42 source files.
`gex-platform-enhanced/deal_engine` (renamed 2026-09-09 from `gex_pf_engine`) computes
deals: `pre_cod.py`, `phases.py`, `ratios.py`, `cod_test.py`, `tea_adapter.py`, its own
`main.py` and `routes/deals.py`, 15 files. **Zero shared module names** — verified by
diffing the full file lists. `deal_engine` has no launch.json entry and no caller today.

**Starting the PF engine** is a documented sequence and has no launch.json entry:
```bash
cd files/gex_pf_engine/backend
source ../micro_service/bin/activate
uvicorn pf_engine.main:app --reload --port 8001
```

`uvicorn app.main:app` also still starts it: `gex_pf_engine/backend/app/` is a **guarded,
deprecated alias** kept because the old command lives in shell history (§7). Use
`pf_engine.main:app` in anything new — the Dockerfile and `.claude/CLAUDE.md` do.

`efuel_truth_stack/` is a self-contained event-sourced/CQRS/bitemporal reference core.
It is not wired into the running backend and is not part of the migration.

`backend/app/main.py` registers **66 routers**. There is no single registry object; the
list in `main.py` is the registry.

---

## 2. Authentication and authorization

Four distinct layers. They are not interchangeable and each fails differently.

### 2.1 Account lifecycle (the vetting gate) — authoritative

`backend/app/core/account_lifecycle.py` defines five states:

```
PENDING → IN_VETTING → ACTIVE ⇄ SUSPENDED
                    ↘ REJECTED (terminal)
```

`LOGIN_PERMITTED_STATES = frozenset({ACTIVE})`. Nothing else may authenticate. This is
enforced in `authenticate_user` (`app/core/auth.py`), which raises `AccountNotActive`.

`backend/app/api/v1/routes_account_vetting.py` exposes nine endpoints. **Only
`POST /register` is public**, and it can produce a `PENDING` account and nothing else.
The remaining eight (`/status`, `/vetting-queue`, `/{user_id}/claim`,
`/telephone-verification`, `/usage-agreement`, `/activate`, `/reject`, `/suspend`)
require GEX staff. Activation asserts three things independently: activator is GEX staff,
required evidence exists (telephone verification **and** signed usage agreement), and
separation of duties (the activator is not the claimant).

Accounts live in **`auth_users`** (there is no `users` table). It currently holds
**17 rows, all `ACTIVE`, all with `activated_by = 'SEED_GRANDFATHERED'`** and NULL
phone/agreement columns — i.e. every account in the system predates vetting and none has
yet been through it. **That marker is how you find them.** Do not backfill those NULLs.

### 2.2 Token authentication

HS256 JWT. `SECRET_KEY` defaults to `dev_secret_key_change_in_production` in
`config.py:20` — still the dev default in this environment.
`ACCESS_TOKEN_EXPIRE_MINUTES = 30`.

Service-to-service calls carry a service-role token. `get_user_payload_from_token`
has an explicit service branch assigning `company_id = "__platform_service__"`; before
that branch existed, service tokens crashed the ABAC middleware on a missing key.

### 2.3 ABAC middleware

`ABACMiddleware` is added in `main.py:558` with `phase=settings.ABAC_PHASE`, currently
**2**. This is middleware-level, not per-route dependency. A route added to `main.py`
is covered by default — which is the safe direction, but it also means route-level
authorization intent is not visible at the route.

`app/core/domain_authorization.py`, `entitlements.py`, `permission_engine.py`,
`route_security.py` sit above it for domain/project/action scoping.

### 2.4 PostgreSQL Row-Level Security (defence in depth)

**89 of 98 tables have RLS enabled, and it is FORCED** (`relforcerowsecurity`), so the
table owner does not bypass it. Policies key on
`current_setting('app.current_company_id', true)`.

Two roles, and since migration 045 they are used for different things:

- `gex_app` — **the runtime identity.** LOGIN, not superuser, no BYPASSRLS, USAGE but
  **not CREATE** on schema public. `DATABASE_URL` points here. RLS applies.
- `gex_user` — SUPERUSER, BYPASSRLS. **Migrations only**, via `ALEMBIC_DATABASE_URL`.

**RLS now binds at runtime.** Re-measured 2026-09-09 on a live `gex_app` connection after
the rebuild: `projects` returns **12** rows as `PLATFORM_ADMIN`, **1** as
`hamburgone_com`, **0** with no tenant context. Before migration 045 all three were equal,
because the runtime connected as a superuser and no policy was ever evaluated — "89 tables
under forced RLS" described the schema, not the running system.

Verified refused on that same connection: `CREATE TABLE`, `DROP TABLE`,
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, `SET ROLE gex_user`, and reading
`pg_authid`. Pinned by `tests/test_gex_app_runtime_role.py`, which asserts against
**whatever `DATABASE_URL` is actually configured** — so repointing it at a superuser, the
quickest way to make a permissions error disappear, fails loudly instead of silently
making every policy decorative.

Migration 032 introduced `SECURITY DEFINER` helper functions with pinned `search_path`
to break mutually-recursive policies from 020 (which had never been evaluated before
`gex_app` existed, so the recursion was latent). The same migration removed an
empty-string bypass in which an unset GUC granted visibility.

Four RLS shapes are in use, deliberately (see `tests/test_governance_slice.py`):
global-readable reference/rules, project-scoped via the 032 helpers, **admin-only for
user-scoped tables**, and direct company comparison. User-scoped tables are admin-only
because no `app.current_user_id` GUC exists — company-scoping them would let a colleague
read another user's permission overrides.

---

## 3. Databases actually used by each service

| Service | Store |
|---|---|
| GEX backend | Dual: PostgreSQL (schema complete) **and** SQLite `backend/gex_platform.db` (still serving) |
| PF engine `:8001` | SQLite only — 12 `sqlite3` sites, no PostgreSQL client |
| TEA engine `:8002` | **Stateless.** No database of any kind. Verified: no `sqlite3`, no `psycopg2`, no `DATABASE_URL` |
| Frontend | Supabase JS client, plus the backend API |

### The backend's dual-store state — read this before touching anything

The SQLite→PostgreSQL migration is **complete in schema and data; the per-slice switches
are not yet flipped.** PostgreSQL is at Alembic head **045**, holds **98 tables**, and
`migration_watermarks` records **53 copied tables** with their exact copied keys. The
runtime already connects to PostgreSQL as `gex_app` for the SQLAlchemy paths — it is the
eight *shim* switches that still read SQLite.

Eight independent backend switches exist in `config.py`:

```
AUTH_DB_BACKEND  EVIDENCE_DB_BACKEND  CAPITAL_DB_BACKEND    MARKET_DB_BACKEND
ENTITLEMENT_DB_BACKEND  EVENTSTORE_DB_BACKEND  FUELREF_DB_BACKEND  GOVERNANCE_DB_BACKEND
```

**All eight are `"sqlite"`.** `.env` sets `AUTH_DB_BACKEND=sqlite` explicitly; the rest
default. This is intentional — flipping before the target database is the real one would
migrate identity and evidence twice.

`app/core/db_backend.py` is the shim: `PostgresConnection` presents a `sqlite3`-shaped
API over psycopg2 (including `?`→`%s` rewriting), so call sites are backend-agnostic.

**Two database credentials, deliberately different roles — never collapse them:**

```
DATABASE_URL          gex_app    runtime. No SUPERUSER/BYPASSRLS/CREATE. RLS applies.
ALEMBIC_DATABASE_URL  gex_user   DDL and migrations only.
```

`alembic/env.py` prefers `ALEMBIC_DATABASE_URL`, so pointing `DATABASE_URL` at the
unprivileged role does not break migrations. DDL is not subject to RLS, so a migration
running with the runtime credential — or a runtime holding DDL rights — turns any
injection into a full read of every tenant. Both are asserted by tests.

**`ALEMBIC_DATABASE_URL` must be EXPORTED, not merely present in `.env`.** pydantic's
`env_file` populates `settings`, not `os.environ`, and Alembic reads `os.getenv`.

Alembic uses branches. `030_auth_slice` is an **independent root** with
`branch_labels='auth_slice'`; `020` was re-parented onto `030`. Upgrade with
`alembic upgrade auth_slice@head`, not bare `head`.

Raw `sqlite3.connect` occurrences in `backend/app/`: **68**, down from a guardrail
baseline of 97 in `tests/test_architecture_guardrails.py:300`. The baseline is a
ratchet — it may only decrease.

---

## 4. Communication paths

```
Browser
  ├─ /api/*  ──► vite proxy ──► backend :8000        (VITE_API_URL, default localhost:8000)
  └─ Supabase JS client ──► Supabase PostgREST       (9 lib files, see §5)

backend :8000
  ├─ ──► PF engine :8001      GEX_ENGINE_URL  (MODEL_ENGINE_URL / BANKABILITY_ENGINE_URL)
  ├─ ──► TEA engine :8002
  └─ ──► trading book         GEX_TRADING_BOOK_URL
```

Backend→engine calls forward the caller's bearer token. TEA verifies it with
`tea_engine/auth/gex_jwt.py` using shared-secret HS256 (`GEX_JWT_SECRET`, defaulting to
the platform dev secret and logging a warning when it does). The PF engine has an
equivalent bridge at `files/gex_pf_engine/backend/app/auth/gex_jwt.py`.

Frontend token reads are consolidated: `frontend/src/lib/authToken.ts` is the single
reader of the `gex_auth_session` key. `engineClient.ts` imports `getAuthToken` from it
(line 27/128). Only `main.tsx`, `UserRoleContext.tsx`, and `authToken.ts` itself touch
that storage key.

---

## 5. Security decisions that are now authoritative

These are settled. Do not re-open without Jim.

1. **Deal and product data belongs behind the GEX backend, not the frontend's Supabase
   `.from()`.** Vetted status, signed agreement, organisation role, project access and
   audit logging are product-policy decisions and live in the backend. Supabase/Postgres
   remains the persistence layer; RLS remains defence in depth — neither is the policy.
2. **Registration creates a `PENDING` account only.** Creating credentials or typing
   data into the UI confers no trust. A GEX employee must complete onboarding, including
   at least one telephone verification and exchange/signature of the software usage
   agreement, before activation. Thereafter, login plus security code suffices, subject
   to role and project permissions.
3. **Retirement is irreversible.** In `tokens_sqlite.py`, `RETIRED` has exactly one
   outgoing edge — `ANNULLED`, which is terminal and non-claimable. `SETTLED` cannot be
   voided; delivery is a fact. `tests/test_token_lifecycle.py` proves this by graph
   reachability (`_reachable(RETIRED) & CLAIMABLE_STATES` must be empty), not by
   enumerating edges — so a new state cannot smuggle a path back.
4. **The audit event is appended before the projection is written**, matching
   `create_token`. Reversing this reintroduces a self-deadlock, because `append_event`
   opens its own connection.
5. **Concurrent appends to `platform_events` serialise on a PostgreSQL advisory lock.**
   The unique constraint and single-root partial index (migration 040) are backstops
   that should never fire. Measured before the fix: 12 concurrent appends → 9 written,
   **3 rejected**, 1 fork. A rejected audit event is data loss, so the constraint alone
   was not a fix. After: 30/30, 0 rejected, 0 forks.
6. **RLS is enabled even where access is deliberately open** (reference data, approval
   rules), with an explicitly named permissive policy. "Deliberately public" must be
   distinguishable from "forgotten".
7. **A compliance rule you cannot read is a trap.** `approval_policies` and
   `sod_conflict_pairs` are readable by every tenant and writable only by admin.
8. **Tables with no `project_id` are admin-only.** No honest tenant policy exists for
   them; a policy that only appears to isolate is worse than none.
9. **Dead tables are quarantined, not dropped.** All 12 were renamed
   `<table>_quarantined_20260809` after confirming 0 rows. Backup:
   `backend/data/db_backups/gex_platform.pre-quarantine.20260809.db`.
10. **Supabase stays.** Leaving it would mean giving up the managed layers and running
    Postgres, auth, and the API by hand.

### TEA, LCA and regime integrity boundaries — do not cross

Folded in 2026-09-18 from `files/GEX_Handoff_Reference/HANDOFF.md` (2026-07-02), which
this document had never carried. Every artefact below was re-verified in the tree on
2026-09-18; the reference folder's `code/` copies are byte-identical to the live files.

- **`ascertained=False` everywhere, and it is not yours to flip.** Sizing, stoichiometry,
  emission factors and co-product prices are public-reference first-pass values, not
  verifier-signed. It flips to `True` only when a named ISO 14067 verifier signs the
  dataset. Live: 11 uses in `tea_engine/process_functions.py`, 5 in `tea_engine/lca.py`.
- **The GREET path is a GREET-*consistent approximation***, using real IRA 45V tier
  thresholds and a US-grid emission factor — not the licensed ANL model. Do not describe
  its output as a GREET result.
- **A TEA run never self-verifies.** An OpenPyTEA run is immutable *evidence*; it becomes
  a `model_base_case` *claim* only through IE/CFO approval, and the PF engine (:8001) may
  run release-gated compute only on a verified basis. Bridge: `routes_tea.py`.
- **An undefined molecule returns 422, never invented economics.** `has_process_function()`
  gates it. The registry defines e-methanol, e-SAF (Fischer-Tropsch), bio-SAF (HEFA),
  e-methane and ammonia; **green H₂ is still absent**.
- **OpenPyTEA correlation caveats.** Its boilers/heaters/furnaces category is unreliable at
  MW scale and the kettle-reboiler correlation is pathological; the registry curates around
  them. **`openpytea==3.0.0`** is pinned in `tea_engine/requirements.txt` (upgraded from
  2.1.0 on 2026-09-23). `>= 3.0` is required, not preferred: `run_monte_carlo` refuses an
  older engine at `MIN_OPENPYTEA_MC`. 3.0 added the `random_seed` parameter the service
  seeds with — 2.x sampled through numpy's global RNG, which no longer reproduces — and
  fixed the vectorised-MC bug that levelised every sample over the longest horizon, so
  `project_lifetime` is sampled again instead of held fixed. The upgrade also moved priced
  numbers (e-methanol CAPEX +2.0% on identical inputs), which is why `cost_basis_hash` now
  covers the engine and its version, and `model_base_case` stores `engine_version`.
  **Base cases verified under 2.1.0 are ~2% below what 3.0 computes and `_RECONCILE_TOL`
  is 1%, so they need re-verification before a release-gated PF compute will pass.**
- **The regime fork is real code, not a plan.** `tea_engine/regimes.py` forks certification
  gate, GHG method and subsidy across RFNBO · ADVANCED_BIOFUEL · BIOFUEL_CROP · RCF ·
  LOW_CARBON, and `evaluate_certification_gate()` rejects the wrong regime's evidence.
  `BIOFUEL_NODES` extends the truth-stack registry code-side; a v0.3 spec bump is owed.

**Companion documents.** `GEX_Handoff_Reference/HANDOFF.md` stays the live companion for
TEA/LCA/regime/pathway work — this file does not repeat it. `GEX_Handoff_ONEFILE.md` is a
convenience bundle (HANDOFF + running log + two design docs) and is regenerated when
HANDOFF changes, not edited. `GreenEarthX-Technical-Handoff.md` (2026-02-28) was retired to
`files/_retired/` on 2026-09-18: every defect it listed — no auth, no `/health`, missing
projects and bankability routes, missing QueryClient provider, placeholder pages, the
20-table `greenearth.db` — is fixed or superseded.

### Operational trap worth keeping

`cp` of the main `.db` file does **not** restore a WAL-mode SQLite database — the `-wal`
sidecar carries uncommitted state forward and silently reverts part of your restore.
Copy or remove `-wal`/`-shm` alongside it, or use `VACUUM INTO`.

---

## 6. Files materially changed

Grouped by intent. Full mtime-derived list is reproducible with
`find backend/app backend/tests backend/alembic/versions frontend/src docs tea_engine -mtime -14`.

**New modules**
- `backend/app/core/account_lifecycle.py` — vetting state machine and assertions
- `backend/app/core/projects_store.py` — canonical projects accessor
- `backend/app/core/db_backend.py` — dual-backend shim and the eight switches
- `backend/app/api/v1/routes_account_vetting.py` — nine vetting endpoints
- `frontend/src/lib/authToken.ts` — single reader of `gex_auth_session`
- `backend/.env` — `DATABASE_URL` on 55432, `AUTH_DB_BACKEND`

**Migrations 030–044** (plus 020/021 re-parented and JSONB defaults corrected):
auth · RLS role · policy recursion · projects collision · evidence · capital bridge ·
marketplace · entitlements · watermarks · event store · chain root · fuel reference ·
governance · chained ledgers · domain tail.

**Behaviour changes**
- `capital_bridge.py` — **1000× units defect fixed** (MWh→kWh conversion was missing
  before dividing by electrolyser SEC)
- `event_store.py` — advisory lock; `init_event_store()` guarded against running SQLite
  DDL at import under PostgreSQL
- `auth.py` — vetting gate, `auth_db_connection()`, lifecycle column grandfathering
- `tokens_sqlite.py` — `ANNULLED`, terminal-state sets, event-before-projection
- `project_truth.py`, `routes_projects.py` — repointed at `projects_store`
- `core/{wae,sod,css,drpl,permission_engine,fuel_catalog,vocabulary,entitlements}.py` —
  backend-aware `init_*` guards
- `tea_engine/{routes/tea.py,compute/openpytea_runner.py,cepci_extension.py}` — restored
  and hardened

**2026-09-14 — frontend**
- `frontend/src/features/pricing/MoleculePriceCurve.tsx` — accepts both pricing response
  shapes; figures a response does not carry render as "—", never a default; per-card error
  boundary (§7)
- `frontend/src/features/pricing/MoleculePriceCurve.test.tsx` (4) ·
  `MoleculePriceCurve.boundary.test.tsx` (1) — new

**2026-09-14 — duplicate tenor labels (sibling + frontend)** — no backup copies taken;
every change is listed here (§7)
- `gex_pf_engine/backend/pf_engine/core/gabillon.py` — new module-level `tenor_label()`;
  `term_structure()` uses it instead of `tenor_m // 12`
- `pf_engine/api/routes_pricing.py` — `/term-curve`'s tenor list hoisted to
  `TERM_CURVE_TENORS_MONTHS`, so the test exercises the list actually served
- `gex_pf_engine/backend/tests/test_tenor_label.py` — new, 18 tests
- `frontend/src/features/pricing/tenorLabel.ts` — new; the frontend copy of the rule, used
  by `MoleculePriceCurve.tsx` (fallback curve, label-missing case) and
  `GabillonAdminPage.tsx` (seed curve), which each built their own label before
- `MoleculePriceCurve.tsx` — `hasCurrentLabels()`: a stored published curve whose labels
  disagree with `tenorLabel()` is purged, the same path as a corrupted curve
- `tenorLabel.test.ts` (1) — new · `MoleculePriceCurve.test.tsx` 4 → 5
- `tenorLabel.engine-parity.test.ts` (1) — new; runs the engine's `tenor_label()` under the
  sibling's own interpreter and compares 0–600 months with `tenorLabel()`; skips if the
  sibling or its venv is absent

**2026-09-09 — sibling repo `files/gex_pf_engine`** (first time this engagement has
touched it; backups in `gex_pf_engine/backend/.backups/`). Paths are post-rename —
the package moved `app/` → `pf_engine/` the same day.
- `pf_engine/core/dscr_guard.py` — new; the single place a DSCR/covenant decision is made
- `pf_engine/core/engine.py` · `debt/sculpting.py` · `cfads.py` — routed through it
- `pf_engine/core/debt/sculpting.py` — rejects a CFADS horizon longer than the debt life
- `pf_engine/api/validation.py` — new. `FiniteModel` rejects Infinity/NaN on request
  models; `finite_safe_validation_handler` scrubs the 422 body. **Both halves are
  load-bearing:** with the handler removed the same request is a 500, because FastAPI's
  422 echoes the raw `inf` and serialising it raises. Verified by removing it.
- `pf_engine/api/routes_model.py` — the six request models inherit `FiniteModel`;
  `pf_engine/main.py` registers the handler
- `app/__init__.py` · `app/main.py` — guarded deprecated alias for `pf_engine` (§7)
- `tests/test_debt_sculptor_characterization.py` — defect test became three

**2026-09-09 — platform, alongside the sibling work**
- `backend/tests/test_sibling_app_alias.py` — new; pins the alias and its guard
- `backend/tests/test_architecture_guardrails.py` — `test_engines_verify_gex_identity_only`
  still named the pre-rename `gex_pf_engine/backend/app`; the sibling's "may be absent"
  exemption swallowed the missing path and **39 sibling files silently left the Supabase
  scan** while `scanned >= 2` stayed satisfied. Now fails on a rename (§7)

**2026-09-09 — rename**
- `gex_pf_engine/` → `deal_engine/` (12 files), plus guardrail, `deal.ts`,
  `engineClient.ts`, `contract-debt-coverage-spec.md`, `openpytea_pathwayspec_play.md`
- `backend/tests/test_dscr_llcr_characterization.py` — new, 12 cross-tree tests

**2026-09-08/09 — new files**
- `backend/scripts/restore_registry_projects.py` — rebuilds `projects` from the frontend
  seed after the schema loss; dry-run default, idempotent
- `backend/tests/test_chain_of_custody.py` — 7 tests: rename, 503/404, no-physics guard
- `frontend/src/features/auth/HeroField.tsx` — generative canvas hero (no raster, no licence)

**2026-09-08/09 — changed**
- `backend/app/api/v1/mass_balance.py` — Chain-of-Custody rename, RED III Art. 30 alignment
  and its four documented gaps, project validation
- `backend/app/main.py` — fail-loud registration, "Chain of Custody" tag
- `backend/app/core/domain_authorization.py` — path mapping follows the rename
- `backend/tests/test_architecture_guardrails.py` — `docker` in `skip_parts`
- `backend/tests/test_evidence_slice.py` — `UNATTRIBUTED_BASELINE` 39 → 41, with cause
- `frontend/src/features/auth/GuestLandingPage.tsx` — dark rebuild; breadth first
  (orchestration map), gates second as proof, ten molecules, research last
- `frontend/src/engine/registry/formulas.ts` — comment distinguishing engineering mass
  balance from the custody ledger

Frontend backups of the landing page are in `frontend/.backups/` (this is not a git repo).

**2026-09-10/11 — energy-economics constants**

Five defects that put a wrong number in front of a lender. Each was verified by hand
against the source before being changed, and each is guarded by a test that was
negative-verified: the defect reintroduced, the guardrail confirmed to fire, the defect
removed again.

- `backend/app/services/dscr_aggregator.py` — **`power_opex_share` was never settable.**
  `getattr(self, "power_opex_share", 0.73)` sat under a docstring saying a caller could
  override it. The identifier occurred **exactly twice in the tree** — that docstring and
  that `getattr` — so it always returned 0.73. Both heatmap axes act on the power term, so
  one constant set every cell of the grid and every break-even power price a credit
  committee reads. Now a real constructor argument with **no default**; when it is absent
  the surface, the sensitivity rows and the break-evens are omitted rather than
  fabricated, and a new `DSCRResult.sensitivity_basis` separates
  `none_no_cashflow_basis` from `none_power_opex_split_not_supplied`. That follows the
  `debt_service_source` idiom already in the file: an empty grid because a project has no
  debt service yet and an empty grid because nobody supplied the split are different facts.
- `backend/app/services/dscr_sensitivity.py` and `routes_finance_model.py` — **seven of
  eleven `DEFAULT_PARAMS` terms were frozen** under the comment "every caller may
  override"; the one real caller passed four. `base_efficiency_pct = 72.0` is the
  denominator of the efficiency axis, so a plant at 55% was stressed against 72%. Project
  values now reach the model, and both it and `power_opex_share` are query parameters that
  `frontend/src/api.ts` can send.
- `backend/app/core/plant_builder.py` and `routes_plant_builder.py` — **the equipment
  catalogue implied 200 kWh/kg.** `annual_power_mwh` and `capacity_tonnes_year` were two
  independent literals whose *ratio* is a specific energy consumption that nothing stated
  and nothing checked: PEM 200.00 against its own description's "55 kWh/kg", SOEC 132.76
  against "~37", alkaline 204.65 at **8,800 full-load hours in a year that contains
  8,760**, and water at 400–465 kg/kg against the 9 kg/kg `mass_balance.py:31` states.
  `capacity_factor`, `availability`, `load_factor` and `8760` appeared **zero times** in
  the engine, so full uptime was asserted and never priced. Items now declare `rated_mw`
  and `sec_kwh_per_kg` once and both annual figures are derived, so the drift is
  unrepresentable; `capacity_factor` moved **onto `PlantConfiguration` with no default**,
  because how long a plant runs follows from the power contract and not from the
  equipment — a derived converter costed without one returns 422. Power in LCOH went from
  €9,000/t to €2,475/t, and LCOH now responds to capacity factor at all: €11,393 / €7,843
  / €5,469 per tonne at cf 0.30 / 0.50 / 0.90.
- `../gex_pf_engine/backend/pf_engine/core/engine.py:343` — **1000× production defect.**
  `capacity_mtpd * 365` with the kg-per-tonne factor missing, while `price_eur_kg` and
  `opex_eur_kg` are per kilogram. A 100 MTPD project at €5/kg reported €182,500/yr
  instead of €182.5M/yr, i.e. universal covenant breach. The fixed line is now :343
  (`model_project_lifetime` starts at :319); the explanatory comment block added with the
  fix occupies :335–342, which is why an earlier draft of this entry cited :335.
  **`cfads.py:57-58` already carried the correct form, with an explicit comment about the
  ×1000** — the bug was found and fixed once and the second copy was never touched. Same
  defect class as the `capital_bridge.py` 1000× entry above.
  **Mind the path** (enumerated from the live app 2026-09-25): the engine route is
  `@router.post("/model/lifetime")` at `routes_model.py:236` under prefix `/api/v1/model`
  (`pf_engine/main.py:113`), so it serves `POST /api/v1/model/model/lifetime` — a doubled
  segment every sibling route in that file avoids (`/cfads/…`, `/waterfall/…`,
  `/integrate/…`). `POST /api/v1/model/lifetime` is **not** a registered route and 404s.
  The platform proxies it at `POST /api/v1/finance-model/lifetime`
  (`routes_finance_model.py:225`), and the hint string at `pre_cod_metrics.py:522` tells
  the user `POST /api/v1/finance-model/model/lifetime`, which is neither of them.
- `backend/app/core/decision_twin.py` — **an RFNBO pillar that could not fail.** The
  RED III temporal-matching check hardcoded `"passed": True` and downgraded its
  consequence to a medium warning, while its three sibling checks (GHG savings, renewable
  share, geographical correlation) each derive `passed` from input and set the project
  ineligible. Annual correlation therefore returned RFNBO-eligible. Now fails as critical
  per Delegated Regulation (EU) 2023/1184 Art. 6 — monthly qualifies until 31 Dec 2029,
  hourly from 1 Jan 2030, annual at no point — with the monthly case warning about the
  2030 cliff. Evaluating that cliff properly needs the project's COD year, which the
  signature does not carry; see §8 for the 45V sibling, which is worse.

**Tests added 2026-09-10/11:** `tests/test_plant_builder_energy.py` (10) and six added to
`tests/test_dscr_sensitivity.py` (17 total in that file). **One** is an AST guardrail —
`test_no_fabricated_power_share_default_returns` (:260), which walks the tree for
`getattr(…, "power_opex_share", <number>)` because its own explanation names the pattern it
forbids. Its neighbour `test_no_module_carries_its_own_sensitivity_model` (:298) is still
**regex/text**-matched and carries the two offending patterns inline, so it is a candidate
to convert — see §7 on guardrails that match their own prose.

**2026-09-25/26 — evidence rules 3.0.0, "the stronger bar"**

Product decision, 2026-09-25: adopt the stronger evidence bar. Implemented from
`GEX_Bankability_Ambition_Gap_and_Remediation_Standard.docx` and the gate document.
**Neither registry was adopted verbatim** — the platform registry's 69-key bar,
the obvious candidate, was weaker or wrong in five places: it dropped
`additionality_evidence` from G2 (an RFNBO pillar and deal-killer), accepted a
"strategy" and "concept note" for a gate named "Inputs Secured" (G3), contained
**no audit** in a gate named "Audit-Grade Model" (G8), dropped legal opinions from
Financial Close (G10), and required insurance **bound with lenders as loss payee at
STRUCTURALLY_BANKABLE** (G7) — two states before lenders approve credit, which on a
strictly sequential ladder is a deadlock. One canonical set of **77** items was built
gate by gate from both, against the standard's truth conditions.

- `../gex_pf_engine/backend/pf_engine/core/bankability_engine.py` — rules **3.0.0**.
  Achievement gates require achievements (G9 permits GRANTED, G10 CPs SATISFIED, G11
  tests PASSED, G8 audit OPINION); readiness gates (G1, G2, G3, G7) stay readiness at
  the maturity their stage allows, and every readiness instrument must be EXECUTED at
  G10. New **maturity axis** `INTENT < INDICATIVE < AGREED < EXECUTED < EFFECTIVE`: a
  VERIFIED item counts only at or above `REQUIRED_MATURITY` (24 instruments);
  undeclared maturity fails closed. `RETIRED_EVIDENCE` (26 keys, each with a named
  replacement — a retired key is never relabelled as its replacement). Metadata for
  all 77 items (was 19). Per-gate `determination` SATISFIED / BLOCKED / INCOMPLETE /
  WAIVED. Capital output adds `decision_eligible` (GEX makes a capital decision
  *eligible*; it does not commit capital) — `is_unlocked` kept as an alias. G3 and G7
  renamed ("Feedstock & Logistics Terms", "Insurability Confirmed"); their ids keep
  SECURED / BOUND for stability.
- `backend/app/core/bankability_engine.py` — registry **generated from** the engine;
  identical in evidence, names, maturity and retirement history. `EVIDENCE_GATE_MAP`
  resolves all 103 live + retired keys for authorization.
- `backend/alembic/versions/054_evidence_maturity.py` — `bankability_evidence.maturity`;
  `evidence_events.old_maturity / new_maturity`. **Applied** to the dev database.
- `backend/app/api/v1/routes_bankability_proxy.py` — write path accepts maturity;
  refuses retired keys (422 naming the replacement), unknown keys, unknown statuses and
  unknown maturities; **maker/checker**: producer-side statuses may declare or raise
  maturity, reviewer-side statuses may only confirm or lower it, and may not introduce
  one the submitter never declared. Every maturity change is audited, including one that
  leaves the status alone.
- **Pre-existing defect found and fixed:** `_ensure_tables` ran SQLite DDL
  unconditionally, so under `EVIDENCE_DB_BACKEND=postgres` it raised
  `syntax error at or near "AUTOINCREMENT"` on every call — **every evidence read and
  write on PostgreSQL failed** (evaluate, update, list, upload, audit trail, health).
  Hidden because ABAC's 403 ran first in the UI and every test pinned SQLite. Now
  SQLite-only; migrations own the PG schema.
- `frontend/src/features/finance/StageGatesPage.tsx` — maturity selector on submission
  (required for instrument items), evidence labels, maturity status per row, WAIVED
  badge, shortfall count. `UnlockChainPanel.tsx` — eligibility language, not "unlock".
  `api.ts` sends maturity.
- Measured effect on the stored data: 125 of 127 rows are demo seed; the two other rows
  are G1 studies and unaffected; all five projects are SPECULATIVE before and after.
  **Corrected 2026-09-26:** those two rows (Anna Keller, Rheinwerk; Thierry Groell,
  ETFuels) are real people with **invented content** — confirmed by the platform owner.
  All 127 rows were invented. See the next entry.

**2026-09-26 — invented evidence became real work for real people (migrations 055, 056)**

- The 127 invented rows were archived verbatim to `bankability_evidence_archive` and
  converted by `backend/scripts/convert_invented_evidence.py` (dry run by default; rules in
  `app/core/evidence_conversion.py`): **53** reset to open NOT_STARTED requests, **36** on
  retired keys replaced by **32** open requests for their successor keys (never relabelled),
  **38** on the owner-less `default` project removed. Result: **85 open requests**, zero
  statuses, submitters, verifiers or maturities carried over. Backup before the change:
  `files/db_backups/evidence_before_055_2026-09-26.sql`.
- Each request is assigned to an **ACTIVE account of the company that owns the project**, by
  the item's owner function (`bankability_engine.EVIDENCE_OWNER_FUNCTION` → `resolve_assignee`):
  ENGINEERING→ENGINEERING, SALES→COMMERCIAL, FINANCE/TREASURY→FINANCE_TREASURY, LEGAL/PROJECT→
  EXECUTIVE (accounts carry no such function), INDEPENDENT_ENGINEER→never (external party),
  missing function→EXECUTIVE, else **unassigned with the reason recorded**. Measured:
  HamburgOne 45 of 47 assigned (Lisa Friedrich 24, Mark Puntz 18, Lucie Mertz 3; 2 are IE items);
  Rheinwerk 1 of 1 (Anna Keller); **ETFuels 7 of 37** — ETFuels has only Commercial and
  Finance accounts, so its Legal, Project and Engineering items have no one to go to. That gap
  is the next onboarding action, not a defect to paper over.
- The 20 accounts were not modified. No vetting column was touched.
- Migration **055**: `assignee_user_id`, `assigned_by`, `assigned_at`, `due_date` on
  `bankability_evidence`; `old_assignee`/`new_assignee` on `evidence_events`; the archive table
  (FORCED RLS, same tenant policy as 034). `due_date` is never defaulted — a deadline is the
  client's commitment.
- Migration **056**: found while verifying 055 as `gex_app` — migration 031's DEFAULT PRIVILEGES
  give every new table full DML to the runtime, so the archive was deletable, and the
  "append-only" `evidence_events` was **updatable and deletable by the runtime since 034**.
  Revoked: archive SELECT-only, events SELECT+INSERT only. `tests/test_evidence_history_pg.py`
  failed before 056 and passes after. **Any new table inherits full DML — revoke explicitly.**
- API: `POST /bankability/evidence/assign` (owner company or platform admin only; assignee must
  be an ACTIVE account of the owner — routing to another tenant would disclose the project);
  `GET /bankability/evidence/assigned-to-me`; gate views carry `assignee_name`, `due_date`;
  the audit trail returns reassignments. Stage Gates "Owner" column shows the person.
  Verified live as Lisa Friedrich: 24 requests, names rendered, through RLS on PostgreSQL.
- The legacy SQLite file still held all 127 invented rows (25 VERIFIED) — flipping
  `EVIDENCE_DB_BACKEND` back to sqlite would have resurrected them. Mirrored from PostgreSQL
  with `--mirror-sqlite` after a `VACUUM INTO` backup; `test_evidence_slice` parity caught it.
- Tests: `test_evidence_conversion.py` (14), `test_evidence_assignment.py` (14),
  `test_evidence_history_pg.py` (7), registry agreement +1 (owner functions). Negative-verified:
  the IE routing rule, both tenant guards on assign, and the 056 revoke.

**Tests added 2026-09-25/26:** `../gex_pf_engine/backend/tests/test_bankability_gates.py`
(24 — the engine had **no tests of its own** before this), `tests/test_evidence_maturity_writes.py`
(19), `tests/test_evidence_pg_path.py` (3, runs **against PostgreSQL** — the only way the
AUTOINCREMENT defect could be caught), and `tests/test_gate_registries_agree.py` extended to
assert evidence, names, maturity and retirement are identical (T14). Every new guardrail was
negative-verified; one — the helper `maturity_meets` failing open — passed for a reason
nobody had checked until the mutation proved it, and got its own test.

**Tests added earlier:** 13 files, plus `tests/pg_support.py` (the single PostgreSQL entry point) — token lifecycle (18), TEA (19), account lifecycle (22),
projects canonical (14), RLS isolation, evidence (12), slice-5 characterization (41),
marketplace (10), entitlements (12), event store (10), fuel reference (9),
governance (17), tail slices (13).

---

## 7. Tests and guardrails

Run from `backend/` with `./venv/bin/python -m pytest tests/ -q`.

| Configuration | Result | Measured |
|---|---|---|
| `DATABASE_URL` → `gex_app` (the runtime role), **exported** | **487 passed, 0 failed, 12 skipped** — **stale**: predates `test_demo_header_fallback` (14) and `test_auth_store_isolation` (6). Not re-measured: PostgreSQL down, Docker not running | 2026-09-14, after restarting `files-postgres-1` (§8.10) |
| `DATABASE_URL` unset (all SQLite) | **407 passed, 0 failed, 112 skipped** | 2026-09-14 19:13 |
| `DATABASE_URL` → PostgreSQL, **exported, container stopped** | **407 passed, 0 failed, 112 skipped** | 2026-09-14 19:36 (Docker not running, :55432 closed) |
| **sibling** `gex_pf_engine`, own venv | **121 passed, 2 failed** (both pre-existing: `test_gabillon`, `test_offtake`; 103 passed before `test_tenor_label`'s 18) | 2026-09-14 19:36 |
| **frontend**, `npx vitest run` from `frontend/` | **114 passed, 0 failed** (14 files) | 2026-09-15 09:06 |

> **Counts move — this tree has concurrent writers.** On 2026-08-11 the suite went
> from 326 to 429 with no code change of mine: six test files (`test_client_billing`,
> `test_open_interest`, `test_throughput_billing`, `test_commitment_taxonomy`,
> `test_open_interest_routes`, `test_rating_engine_expiry_blindness`) appeared from
> another session, contributing exactly 103 tests. All pass. Re-measure rather than
> trusting a number you did not just run.

**Green in every configuration that could be measured on 2026-09-14/15** — but only after a
test of mine was corrected on 2026-09-14 (the alias entry below). Earlier that day the
platform suite stood at 1 failed. The PostgreSQL-up row was re-measured once the container
was restarted (previously 448 / 4 skipped, 2026-09-09), and is stale again: 20 tests have
landed since (§8.11, §8.12) and PostgreSQL was down for the 2026-09-14 evening re-measure.
Re-run it with the container up and `DATABASE_URL` exported before quoting it.

**`tests/pg_support.py` reads `os.environ`, not `.env`.** With PostgreSQL up but
`DATABASE_URL` only in `.env`, the suite silently runs the all-SQLite configuration
(407 passed, 112 skipped — measured 2026-09-14) and looks healthy. Export it first.

### The runtime no longer connects as a superuser (2026-08-10, migration 045)

`gex_app` was created by 031 and left NOLOGIN, usable only via `SET ROLE` from a
superuser session. 045 grants LOGIN and re-asserts its privilege envelope, including
`ALTER DEFAULT PRIVILEGES` so tables added by later migrations inherit it — otherwise the
runtime silently loses access to new tables and it looks like a bug in the feature.

The migration deliberately **does not set a password**: a password in a migration is a
credential in version control. Set one per environment:

```sql
ALTER ROLE gex_app WITH PASSWORD '<from your secret store>';
```

The local development password is `gex_app_password_dev`, committed in `backend/.env`
alongside the pre-existing `gex_password_dev` so a fresh checkout runs. **Both are
development-only.**

Three tests would have been unwritable before this change, because the runtime connected
as a superuser and tenant isolation was therefore unfalsifiable: a tenant sees a strict
subset of admin's rows; no tenant context reveals nothing; not every tenant sees every
project.

### The caller's tenant now reaches both database paths (2026-08-10)

`app/core/request_tenant.py` is the single derivation of "who is calling", plus the
request-scoped `ContextVar` the shim needs (it has no `Request` to read).
`ABACMiddleware` binds it once the JWT is verified and unbinds it in a `finally`;
`route_security` binds it for the three routes that authenticate by dependency instead.
Resolution order in the shim: **explicit argument → bound caller → deny sentinel.**

**A second defect was found while doing this.** `ABACMiddleware` set
`request.state.auth_user_payload`, but `db/session.py::_company_id_from_request` read
`request.state.user_payload` — a different attribute. `route_security` sets both, but is
imported in only three places, so for most of the 109 SQLAlchemy sites the payload was
never found and the tenant resolved to `'GUEST'`.

Under `gex_user` neither defect is visible, because RLS is not evaluated at all. Under
`gex_app` the first exposes everything and the second hides everything — an outage and a
breach, discovered on the same afternoon. The middleware now sets both names and
`payload_from_request` reads both, until one is retired deliberately.

Pinned by `tests/test_request_tenant.py` (11 tests) against a real ASGI stack, including
the load-bearing assumption that a `ContextVar` set inside a Starlette
`BaseHTTPMiddleware` reaches the route handler — true today, not documented API, so
asserted rather than reasoned about.

> **A guardrail here passed for the wrong reason, and negative verification is the only
> reason that is known.** The cross-request test originally claimed the `finally` reset
> was what prevented tenant leakage. Deleting the reset changed nothing: each request runs
> in its own asyncio task and a `ContextVar` set there dies with the task. Task-context
> isolation is the mechanism; the reset is defence-in-depth for callers that do not get a
> fresh task. The test now says so, and the reset's existence is pinned separately over
> the AST — because no HTTP-level test can see it.

### The shim's tenant-context default now fails closed (2026-08-10)

Found during the credential-architecture review. Every `*_connection()` accessor in
`app/core/db_backend.py` defaulted to `company_id=PLATFORM_ADMIN`, and an audit of all
**64 call sites found that not one overrode it**. 88 of the 93 RLS policies grant
`PLATFORM_ADMIN` full visibility.

So the day the eight switches flipped to PostgreSQL, those 64 sites would have read every
tenant's rows — while every RLS test still passed, because the tests set their own
context rather than exercising the application's. **Policies existing is not policies
binding.**

The default is now `NO_TENANT_CONTEXT = "__no_tenant_context__"`, which matches no
tenant-scoped policy. Measured under role `gex_app`:

| table | as PLATFORM_ADMIN | with the sentinel |
|---|---|---|
| `projects` | 14 | **0** |
| `finance_entitlements` | 838 | **0** |
| `fuel_catalog` / `fuel_unit_conversions` | 10 / 120 | 10 / 120 (unchanged) |
| `approval_policies` / `sod_conflict_pairs` | 8 / 8 | 8 / 8 (unchanged) |

Deliberately-public data is unaffected — its policies never consult the company. Auth
tables carry no RLS at all, so login is unaffected.

Seven call sites with a genuine bootstrap need — entitlement checks, governance policy
evaluation (`wae`, `sod`, `css`, `drpl`, `permission_engine`) and the audit-ledger write
path — now pass `company_id=PLATFORM_ADMIN` **explicitly**, and every such connection is
logged once per call site by `_tenant_context()`. Everything else gets no tenant context,
so a premature flip fails loudly instead of silently exposing data.

Pinned by `tests/test_tenant_context_default.py` (16 tests): no accessor may default to
admin (AST), the sentinel must deny tenant data *and* must not break public data, the
denial must be measurably stricter than admin (so an empty table can't pass it vacuously),
no real tenant may hold the sentinel value, and escalation must stay logged.

**This change is inert at runtime today** — all eight switches are on SQLite, and the
SQLite branch ignores `company_id`. Verified live: backend healthy, all switches `sqlite`.

### 2026-09-18 — `npm run build` had been red since the sibling rename, and nobody knew

Found while building the TEA screen, not by looking: **both frontend build gates were
failing**, for the same reason, since the `app` → `pf_engine` rename of 2026-09-09.

- `scripts/audit-causal-ways.mjs` read
  `gex_pf_engine/backend/app/core/bankability_engine.py` with a bare `readFileSync` and
  **crashed on ENOENT**. A crash, not a report: `npm run build` died before `tsc` ran.
- `scripts/audit-menu.mjs` read the same package for its §10 probe, got nothing, and
  concluded the PF engine had **no waterfall, no cash sweep, no sculpting** — flipping
  six rows to "absent" and declaring the generated doc stale, which also exits 1. Had
  anyone regenerated the doc in that state, `docs/menu-architecture-map.md` would have
  told the team the finance engine did not exist. (I did regenerate it in that state,
  saw the false rows, and reverted by fixing the probe: the doc is now byte-identical to
  what it was before.)

Both now try `pf_engine/` first and fall back to `app/`, and the causal-ways script warns
instead of dying when neither is readable — a missing sibling checkout is not a broken
build. **This is the third instance of one pattern** (see the 2026-09-09 entry, "a
guardrail silently stopped scanning the sibling"): a guardrail that reads the sibling by
path keeps passing, or dies, when the path moves. Anything reading across the repo
boundary should tolerate both names and say when it read nothing.

Also fixed, because it was the last thing standing between the tree and a green build:
`OnboardingWizard.tsx:383` reset `step1Data` without `power_basis` and `offtake_status`,
which failed `tsc` and would have left both fields undefined on a reset. `npm run build`
now exits 0.

### 2026-09-20 — Supabase cutover, increment 5: the key is out of the bundle

**The frontend no longer contains Supabase at all.** Not a call, not a client, not the
dependency. Verified against a clean build: the anon JWT literal that was in
`dist/assets/index-*.js` **is gone**, no `supabase` string survives anywhere in `dist/`,
and the main bundle dropped 4.05 MB → 3.66 MB.

- **Both realtime hooks removed, and both were already inert** — which is why this cost
  nothing:
  - `useCanvasLiveSync` was called as `useCanvasLiveSync(undefined, null)`, arguments that
    make its effect return before opening a channel, with its outputs replaced by local
    stubs. A comment records that it was disabled after feedback loops — applying a peer
    snapshot dirtied local state, which rebroadcast, which spammed "X updated the plant".
  - `useCanvasPresence` keyed presence on `me.userId` and skipped that key as "self".
    Every user is the stubbed `demo-user` (§8.17), so **every peer was filtered out as
    yourself**: it has been showing zero peers to everybody.
  - And since increment 2 the canvas is a per-user document, so two people cannot open the
    same one. There is no shared object left to be present on. `PresenceCursors` and
    `PresenceAvatars` went with the hooks; both rendered nothing already.
- **Deleted:** `backendClient.ts` (which held the baked-in URL and anon key), `envGuard.ts`
  (whose only export had no callers left after increments 2–4),
  `integrations/supabase/client.ts` (a stub nothing imported) and `types/supabase-js.d.ts`.
  `@supabase/supabase-js` removed from `package.json`; lockfile regenerated, 0 entries.
- **`audit-supabase.mjs` allowlist is now empty**, so the gate asks a simpler question:
  has anybody put it back?
- **A bug I introduced in increment 3, caught by opening the page.** Converting the canvas
  load from a loop over candidate paths to a single read left the loop's `return` outside
  the success branch, so it fired on a 404 too: a plant with no stored canvas hung on
  "Loading plant canvas…" forever instead of opening empty. Every automated check passed
  — `tsc`, 190 frontend tests, the build — because none of them opens the page. Fixed and
  re-verified in the browser: React Flow mounts, canvas renders, zero Supabase requests.
  The lesson is the one this session keeps repeating: the suite tells you the code is
  consistent, not that the product works.
- Suites: **530 backend / 190 frontend**, build green.

**THIS DOES NOT REVOKE THE KEY, AND THE KEY IS STILL LIVE.** Removing it from the source
stops it shipping *in future* builds. The value itself remains valid against the Supabase
project and is still recoverable from: this repository's **git history**, any **previously
deployed bundle**, and the **public Docker Hub images** under `jmlamay/`. Rotating it in
the Supabase dashboard is a step only Jim can take, and until it is taken the exposure
measured on 2026-09-19 stands. Enabling RLS on the seven tables remains worth doing as
defence in depth even after rotation — nothing in GEX reads them any more.

### 2026-09-20 — Password policy (there was none)

Measured before writing anything: **no policy existed at all.** Neither `auth.py` nor
`routes_auth.py` checked length, content or reuse, so the platform accepted any string —
including on `is_platform_admin` accounts, which `request_tenant.py:87` maps to
`PLATFORM_ADMIN`, disabling tenant isolation for the whole connection.

- **`app/core/password_policy.py`** — 12 characters minimum, **16 for a platform
  administrator**, a 1024 upper bound so an enormous input cannot burn CPU in the hash, a
  blocklist (common passwords plus deployment-specific terms: `greenearthx`, `gex`,
  `etfuels`, `hydrogen`…), a context check against the account's own name and address, and
  a triviality check for repeated characters and keyboard runs. Trailing years and
  punctuation padding do not rescue a blocked word: `greenearthx2026` and `greenearthx!!`
  both fail.
- **No composition rules, deliberately.** NIST SP 800-63B dropped "must contain an
  uppercase and a symbol" because it produces `Password1!` and drives reuse. A test
  asserting composition would pin the wrong behaviour, so none exists.
- **Enforced in `update_password` itself**, not only in the route — that function is what
  an operator calls from a shell when provisioning, which is the path with no human
  reading a validation message. It reads `is_platform_admin` from the row, so a caller
  cannot forget to ask for the stricter bar. Negative-verified: removing the call failed
  the structural test. Also enforced at staff registration
  (`routes_account_vetting.py`), **before** the duplicate-address probe, so a weak
  password is refused identically for a known and an unknown address — otherwise the
  difference would leak which is which, defeating that branch's whole purpose.
- **One exemption, stated in the module rather than hidden:** demo seeding hashes
  `DEMO_PASSWORD` directly and bypasses the policy, so `demo1234` still works for the 17
  seeded accounts. That is safe **only** because `GEX_SEED_DEMO_USERS=0` disables the seed
  set in production. If that variable is ever unset in a real deployment, the policy is
  irrelevant — there are seventeen accounts with a published password.
- **`scripts/set_password.py`** reads with `getpass`, so the password is not echoed, not
  in shell history and not in any transcript; asks twice; and tells the caller when the
  account is not ACTIVE, because the password is not the gate — vetting is.
- Tests: 20. Suite **530 passed / 112 skipped**.

### 2026-09-20 — Supabase cutover, increment 4: equipment equations, and the gate that keeps it shut

- **`/api/v1/equipment-equations`** (`routes_equipment_equations.py`,
  `equations_store.py`), `projects` domain: `GET ?plant_slug=&node_id=`, `PUT` upsert on
  (owner, plant, node, equation), `DELETE /{row_id}`. Row shape unchanged, so
  `StoredEquipmentEquation` did not move.
- **§8.16 closed.** The delete carries the owner predicate; a row that is not the
  caller's answers **404, not 403**, and a missing row and a foreign row return byte-identical
  responses so the status cannot confirm an id exists. Negative-verified by removing the
  predicate — the three delete-scoping tests failed. Verified live: Marwen deleting one of
  Jim's equations gets 404, and the equation is still there afterwards.
- Both live rows migrated (`admin-001` → `admin_greenearthx_com`, `rotterdam-rfnbo`).
- **`dealClient.ts` deleted** — it targeted `equation_engine_runs` and
  `v_latest_engine_run`, which do not exist in the project (404), and the only file that
  mentioned it was itself.
- **`seedInitialCanvas` also moved.** It was still uploading to the bucket, and refused to
  seed at all without a `userId` "because we cannot write to an unscoped path" — a
  constraint that disappears once the server derives the owner.
- **`scripts/audit-supabase.mjs`, wired into `npm run build`.** Fails the build on any
  `supabase.from(`, `.storage.from(`, `.channel(` or `.rpc(` outside a three-file
  allowlist, and reports allowlist entries that are no longer needed so the list can only
  shrink. Negative-verified by planting a violation: exit 1, naming file and line.
  This is what stops the cutover growing back one convenient call at a time.
- Tests: 11 backend, 5 frontend. **510 backend passed**, **190 frontend passed**, build green.
- **What is left before the anon key can be revoked:** only the two realtime hooks,
  `useCanvasLiveSync` and `useCanvasPresence` (`supabase.channel`). They are the
  allowlist's remaining entries and they carry no data — they are a live-cursor
  transport. §9 records the decision not to build WebSockets, so the options are the ones
  in the cutover document §7: drop them, or add the polled presence endpoint (~40 lines).

### 2026-09-20 — Supabase cutover, increment 3: canvas documents (and a two-year-old broken read)

**CORRECTION TO THIS DOCUMENT AND TO THE CUTOVER SCOPE.** I twice called the `plant-data`
bucket "public". It is not. `/storage/v1/object/public/plant-data/...` answers **404
"Bucket not found"**. What is true is worse in one way and better in another:

- the **anon key lists and reads the whole bucket**, and that key ships in the public
  bundle — so anyone with the JavaScript could read every user's canvas; but
- because the bucket is private, the frontend's own read path — `getPublicUrl()` then an
  unauthenticated `fetch` — **has never worked**. Verified live in the browser against the
  running app: 400, `NoSuchBucket`. Cloud saves succeeded, cloud loads always failed and
  fell through to localStorage without a word. **A user changing device did not get their
  canvas back.** Increment 3 is therefore a data-loss repair as much as a security fix.

- **`/api/v1/plant-canvas`** (`routes_plant_canvas.py`, `canvas_store.py`), `projects`
  domain: `GET/PUT/DELETE /canvas/{slug}`, `GET/PUT /canvas/{slug}/versions[/{id}]`,
  `GET/PUT /site/{slug}`, `GET/PUT /library`. Content on disk addressed by sha256 with
  metadata in `canvas_blobs` — the `development_packages` pattern. Identical content is
  stored once, and a file is unlinked only when the last row referencing it goes, so
  deleting one snapshot cannot blank an identical sibling.
- **There is deliberately no `getPublicUrl` equivalent.** An unauthenticated URL is the
  property that made the bucket a problem; the six call sites became authenticated reads.
- **Path traversal is the new hazard**, because `slug` reaches a filesystem path straight
  from a URL. Two layers: routing rejects encoded slashes, and `_safe()` strips the rest.
  Pinned by 8 parametrised hostile slugs. Negative-verified — and the **first version of
  that test was weak**: it scanned files *inside* the blob root, so a file written outside
  was invisible to it and the traversal cases passed vacuously. Strengthened to assert on
  the path the store *intends* to use; it then caught 4 cases instead of 3.
- **Migrated** 499 of 1,476 objects with `scripts/import_canvas_blobs.py` — 59 live
  documents plus the newest 30 snapshots per document (from 1,114), which is the retention
  rule the app already applied. 209 bucket-root objects were never imported: they are
  unscoped legacy seeds belonging to nobody. Same owner mapping as increment 2, same
  refusal to guess. 0 failures.
- **A real bug found by the live check:** `stored_path` was written relative, so it
  resolved against uvicorn's working directory. Start the service from anywhere else and
  every canvas reads as "content missing" while the files sit safely on disk. The blob
  root is now anchored on the backend package; the 499 existing rows were rewritten to
  absolute; `test_stored_paths_are_absolute` pins it. (`development_packages.py` has the
  same latent fragility with `PACKAGE_DOCS_DIR` — untouched, noted.)
- Tests: 25 backend. Suite **499 passed / 112 skipped**. Frontend `tsc` clean, build green.
- **Verified live end to end**, and this is the part that matters: anonymous 401; the
  owner loads `antwerp-methanol` with **29 nodes and 28 edges**; Marwen asking for the
  same slug gets 404; version history lists 4 snapshots and a past one reads back; the
  custom library and site infrastructure both return. Then the same through the Vite proxy
  using the app's own `canvasApi` module. **That is the first time a canvas has ever
  loaded from the server in this codebase.**

### 2026-09-20 — Supabase cutover, increment 2: plants (backend built, migration blocked on a decision)

- **`/api/v1/plants`** (`routes_plants.py`, `plants_store.py`), `projects` domain:
  `GET` list, `GET/PUT/DELETE /{slug}`, `POST /{slug}/touch`, and `PUT` for the whole
  portfolio. **No route accepts a `user_id`** in a path, query or body — the owner comes
  from the bearer token and nowhere else. Another owner's plant is **404, not 403**, so a
  status code cannot enumerate who has what.
- **No platform-admin bypass, deliberately.** An administrator who can silently read a
  customer's canvas is an access decision nobody took, so it is not written. Pinned by
  `test_a_platform_admin_does_not_see_other_portfolios`. Support access, if wanted, needs
  its own entitlement and audit trail.
- **§8.15 is closed at the backend.** `replace_all` does the delete and the insert in one
  transaction. Negative-verified by reinserting the exact old behaviour — a `commit()`
  between the two — and watching the rollback test fail. A second guard, `confirm_delete`,
  refuses a bulk replace whose deletion count the caller did not predict, so an empty body
  from a half-loaded client cannot mean "delete everything" (409, nothing removed).
- Tests: 15, all owner-isolation tests negative-verified by making `_owner` return a shared
  bucket — 8 of 15 failed. Suite **474 passed / 112 skipped**.
- **Migrated 2026-09-20 on Jim's mapping.** 38 of 53 plants into three accounts:
  `admin-001` → `admin_greenearthx_com` (21, Jim), `user-003` → `marwen_greenearthx_com`
  (11, Marwen Kadri), `etfuels-thierry` → `thierry_groell_etfuels_com` (6). Dropped as
  seed/test identities: `demo-user`, `b05dcc50-…`, `user-001`, `user-002` (15 plants).
  **Dropped means not migrated, not deleted** — the rows remain in Supabase and in the
  local export, so any of them can be brought over later by re-running with a mapping.
  The evidence they are seeds: `rotterdam-rfnbo` existed under **6** different owner ids
  and `northsea-hydrogen` under 5; 13 of 30 slugs were duplicated across owners.
  Verified live: Jim 21 plants, Marwen 11, Thierry 6, NordLB 0; Marwen asking for one of
  Jim's plants by slug gets **404** while Jim gets 200.
- **Two platform-admin accounts, and what that grant is.**
  `t-MarwenC@greenearthx.com` (Marwen Chaabouni) and `t-MohamedK@greenearthx.com`
  (Mohamed Kedim), both ACTIVE with `is_platform_admin=1`, created via
  `scripts/create_platform_admin.py`.
  The script states in its own docstring what the flag confers — `request_tenant.py:87`
  maps it to `PLATFORM_ADMIN`, which disables tenant isolation for the whole connection,
  so the holder reads **every customer's data**, can activate accounts, and can write
  reference data. Vetting was bypassed as a deliberate one-off, and the row records
  `activated_by='MANUAL_ADMIN_GRANT'` — deliberately **not** `SEED_GRANDFATHERED`, which
  must keep identifying only the 17 rows that predate vetting. The account is created
  with a random password that is hashed and discarded unread, so it cannot be logged into
  until its owner sets one with `update_password`.
- **THE DIRECTORY IS PROBABLY SYNTHETIC — this corrects an earlier alarm in this
  document.** The real people are `Marwen Chaabouni <t-MarwenC@greenearthx.com>`,
  `Mohamed Kedim <t-MohamedK@greenearthx.com>` and
  `Jean-Marie Lamay <jean-marie@greenearthx.com>`. The imported directory instead holds
  "Marwen **Kadri** <marwen@greenearthx.com>" and "Jean-Marie **Dupont**
  <jeanmarie@greenearthx.com>" — wrong surnames, wrong addresses, and a
  `firstname.lastname@` convention that is not GEX's (`t-FirstL@`). The other 15
  `@greenearthx.com` rows are one-per-nationality European names of the same shape.
  So the `team_users` table that answered anonymous requests was very likely **seed data,
  not 19 real people**, and the GDPR exposure I raised on 2026-09-19 is correspondingly
  smaller. The ETFuels pair may be the exception. **Not yet confirmed with Jim** — until
  it is, the rows are still treated as personal data, which costs nothing now that the
  endpoint is staff-only.
- **One account was created on a wrong address and removed.**
  `marwen@greenearthx.com` was created from the directory row before the real address was
  known; its 11 plants were moved to `t-marwenc_greenearthx_com` with an `UPDATE` (so
  `created_at`/`updated_at` survived) and the account row was deleted. Owner counts after:
  Jim 21, Marwen 11, Thierry 6.
- **Historical note on the original blocker.** The 53 rows carried seven owner ids —
  `admin-001` (21), `user-003` (11), `etfuels-thierry` (6), one uuid (5), `demo-user` (5),
  `user-001` (3), `user-002` (2) — and **none is an `auth_users.user_id`**; they are the
  stubbed `AuthContext` (§8.17) and older seed data. `scripts/import_plants.py` therefore
  takes `--map OLD=NEW` / `--drop OLD` and **refuses to write anything** while an owner id
  is unaccounted for. Guessing would hand a plant to the wrong account, which is the exact
  failure this cutover exists to prevent — so the importer refused until Jim supplied the
  mapping, and it will refuse again for any owner id a future export introduces.
- **Frontend cut over the same day.** `PlantBuilder.tsx`, `plantStore.ts`,
  `iterations.ts` and `useCanvasData.ts` now go through `lib/plantsApi.ts`. **No
  `supabase.from("plants")` call remains anywhere in the tree.** Every one of those
  functions lost its `userId` parameter — `useSyncedPlants()` takes none at all — so the
  stubbed `AuthContext` (§8.17) can no longer decide whose plants these are. `userId`
  survives only in the Supabase **Storage** paths, which are increment 3.
  - One bug introduced and caught while editing: the backend delete landed inside
    `if (isBackendConfigured())` in `deletePlantVariation`, which would have skipped the
    row delete whenever Supabase was unconfigured. Moved out; only the blob cleanup stays
    behind that guard.
  - Tests: 7 for the client, including one that asserts **no request URL or body ever
    contains `user_id`** — the client cannot name an owner even though the server would
    ignore it. Frontend **185 passed**, `tsc` clean, `npm run build` green.
- **Verified live in the browser**, backend and Vite both running, through the proxy:
  anonymous `GET /api/v1/plants` 401; Jim 21 plants; Marwen 11; Marwen asking for one of
  Jim's by slug 404 while Jim gets 200. Then signed in through the real login UI as a
  counterparty account (Lisa Friedrich, HamburgOne) and opened `/plants`: seven API calls,
  all 200, no Supabase PostgREST traffic, and the seeded defaults were written under
  **`lisa_friedrich_hamburgone_com`** — her own token-derived id. Under the old code that
  write would have gone to `demo-user` and pooled with everyone else's.

### 2026-09-20 — Supabase cutover, increment 1: the staff directory moves behind the backend

Scope and the remaining increments: `docs/supabase-cutover-endpoints.md`. Background: on
2026-09-19 every table behind the frontend's `supabase.from()` calls answered an
**anonymous** request under the anon key shipped in the bundle — `team_users` among them,
which is 19 real people's email and full name. **Corrected 2026-09-20 by the export:** I
had said "email and phone" from the column list; the `phone` column is **empty in all 19
rows**, and `organisation` is null in 14. What was actually exposed is 19 names, 19 working
email addresses — 17 `@greenearthx.com` and **2 `@etfuels.com`** — and the internal team,
role and permission-gate structure. The two external addresses matter on their own: they
name a business relationship and two individuals at a partner company.

- **`GET /api/v1/directory/{overview,members,gate-status}`** (`routes_directory.py`,
  `directory_store.py`) replaces the five tables `useTeamData` read from PostgREST. Shapes
  are the frontend's existing `TeamRow`/`RoleRow`/`TeamUserRow`/`PermissionGate`/
  `GateStatusRow` unchanged — this increment moves the transport, not the contract — and
  the three `.order()` calls are now server-side. `governance` domain.
- **`email` and `phone` are omitted, not nulled**, for any caller who is not
  `is_platform_admin`. A nulled key invites a UI to render "None" where a phone number
  belongs; an absent key cannot. The org chart itself is not secret — that is the screen's
  purpose. `has_platform_admin_access` is the single check, the same one
  `assert_activator_is_gex_staff` makes.
- **The identity question is now measured, and the answer reverses the advice.** Imported
  2026-09-20: **0 of 19** directory members match an `auth_users` account by email, and
  **0 of 17** accounts have a directory entry. The two populations are disjoint *by
  design*, not by drift — `auth_users` is the counterparty table (NordLB, ABN AMRO,
  Allianz, Zurich, Siemens Energy, the offtakers) plus one GEX address,
  `admin@greenearthx.com`; the directory is GEX's own 17 staff, none of whom hold a
  platform account, plus two ETFuels partners. Folding would mean minting 17 accounts for
  people who should not silently acquire one under the vetting gate. **Keep two tables**
  (scope doc §2, recommendation revised from fold to separate-with-bridge). The genuine
  overlap is **2 rows**: `felix@etfuels.com` and `thierry@etfuels.com` are
  `felix.leworthy@` and `thierry.groell@` in `auth_users` — the same two people under a
  short and a full address. `reconcile_with_auth_users()` reports those as **name
  candidates and refuses to link them**; two people can share a name, and auto-linking on
  one would hand a person somebody else's account. `test_the_directory_grants_nothing` fails if any module outside
  the directory starts consulting the store, so the read-model cannot quietly become a
  second authority.
- **PostgreSQL is refused, not created**: `init_db()` raises `PostgresMigrationRequired`
  when `GOVERNANCE_DB_BACKEND=postgres`, because a `CREATE TABLE IF NOT EXISTS` would put
  the PII table on a database where 89 of 98 tables are under FORCED RLS as the one
  unprotected exception. No ninth backend switch was invented.
- **Two defects found while reading the write paths**, both consequences of anon access and
  both logged in §8: `savePlantsToCloud` deletes every plant then inserts with no
  transaction (a failure between them wipes the portfolio), and
  `useEquipmentEquations.remove` deletes by id with no user scoping at all.
- **Supabase Storage is also in use** — bucket `plant-data`, 6 `getPublicUrl()` calls,
  which only work on a *public* bucket, holding the actual canvas content at guessable
  paths. Bigger than the tables, not covered by RLS, and it corrects §8.14: the platform
  does have file storage, in the frontend under the anon key. Increment 3.
- Tests: 14, suite **456 passed / 112 skipped**, zero failures. Both guards
  negative-verified — forcing `include_pii` true failed the non-staff test on *both* doors
  (`/members` and `/overview`), and removing the 401 check failed all three endpoints.
- **Cut over the same day.** Exported (8/31/19/7/32), imported via
  `scripts/import_directory.py`, and `useTeamData` rewritten onto the three endpoints —
  **one** authenticated request on mount where there were five unauthenticated ones, with
  the two long-standing refetches wired to the narrow endpoints and patched into the same
  cache entry. Verified end to end through the real app (`app.main:app`, real tokens, ABAC
  middleware and domain authorization in the path): no token 401, forged bearer 401, admin
  200 with `email`, a counterparty account 200 with the `email` key **absent** and the org
  chart intact. The five Supabase tables now have no caller; RLS can go on.
- **`TeamUserRow.email` and `.phone` are now optional, and that caught a real crash.**
  `TeamAlignmentPanel` called `u.email.toLowerCase()` in three places, unguarded. Served
  to a non-staff caller — which is every customer account — that is a `TypeError` and a
  dead panel. Typing the fields optional turned it into a compile error; negative-verified
  by restoring the unguarded call and watching `tsc` fail with TS18048. Mentions now
  resolve by name when no address is visible, and `emailHandle` returns `null` rather than
  `""` so a bare `@` cannot match the first member with no address.
- Frontend: 6 new tests, **177 passed**, `tsc` clean, `npm run build` green.
- **Found by the live check and fixed the same day — the directory is now staff-only.**
  The first version admitted any authenticated caller and withheld only addresses, so an
  ETFuels counterparty account could read GEX's whole org chart. **The rule, from Jim:
  no user of a paying customer may read GEX's internal directory in any instance** — not
  the names, not the teams, not the gates. All three endpoints now answer **403** to a
  non-staff caller, verified with real tokens for ETFuels, NordLB and ABN AMRO (403/403/403
  each, no names in the refusal body) against `admin@greenearthx.com` at 200.
  Negative-verified by removing the staff check: all three doors failed.
  - Organisation-scoping was considered and **rejected on the data** — `organisation` is
    null in 14 of 19 rows and holds values like "QA Verified" in others, so a string match
    would silently admit rows it could not classify. Fail closed instead.
  - The redaction rule survives *underneath* the access rule as defence in depth, pinned
    by a store-level test, so widening read access later cannot leak addresses by default.
  - **Consequence to know:** only `admin@greenearthx.com` holds `is_platform_admin`, and
    none of the 17 GEX staff have platform accounts — so the canvas @mention list is now
    empty for every account except the admin. That follows from the rule, and from the
    fact that GEX staff are not platform users. A 403 renders as "no directory", not as an
    error: `useTeamData` exposes `forbidden` so a working rule is never shown as a fault.

### 2026-09-18 — TEA report, increments 1 and 2 (the figures are finally visible)

Per `docs/tea-report-scope.md`, internal view only, name stays TEA.

- **`GET /api/v1/economics/snapshot/{project_id}`** (`routes_economics.py`) fills the four
  `economics.*` permission strings that had mapped to no route since the permission engine
  was written. It serves the **approved** `model_base_case` and nothing else: 404 with no
  live claim, **409 naming the state and carrying no figures** when the live claim is not
  approved, and a superseded or closed claim never wins over the live one. GHG claims
  follow the same rule per claim — an unapproved one contributes its state, not its value.
  Registered under the `finance` domain; behind `require_finance_entitlement`.
- **What it cannot serve, and says so:** cost stack, regime and sensitivity tornado are
  **not persisted** — the compute path stores the headline economics and the run's hash,
  and the evidence entry holds only `document_ref = cost_basis_hash`. They are named in
  `not_available` with the reason, because fetching them would mean recomputing, and a
  recomputed figure is not the figure that was approved. Persisting them is the next
  increment.
- **`/economics/:projectId`** (`EconomicsSnapshotPage.tsx`) renders the five states —
  approved, not approved, nothing computed, no access, unavailable — with the provisional
  `ascertained=false` banner on every approved view. No menu entry yet: placement is a
  product decision.
- **403 comes before 404** on the API, deliberately, so the status code cannot enumerate
  the portfolio. Pinned by a test.
- Tests: 14 backend, 9 frontend; suites **442 passed / 112 skipped** and **167 passed**.
  Seven guards negative-verified by reintroducing each fault (serving a provisional claim,
  leaking an unapproved GHG value, dropping the disclaimer, ignoring supersession, treating
  a 409 as data, collapsing 403 into 404, rendering an unapproved value).
- Verified live through the Vite proxy against a running backend: the route answered
  **403 with the entitlement reason** for a caller with no grant. The same run confirmed
  this morning's auth fix end-to-end — a forged bearer got 401 and the frontend ended the
  session rather than rendering a signed-in page.

### 2026-09-18 — Ecosystem Navigator: data structure v4.2 (specification, not code)

`Data_structure_local.docx` — the client's field dictionary for the map — was rewritten as
`~/Downloads/Data_structure_local_v4_2.docx`. It stays outside the repo because it is a
client document. Every v1 field keeps its characteristics (type, length, mandatory,
look-up) and carries a Kept / Updated / New / Moved marker saying what changed. Companions
in the repo: `docs/ecosystem-navigator-data-structure-review.md` (what was wrong with v1)
and `docs/news-to-project-truth-pipeline.md` (the pipeline this refines).

**What the specification now requires of any code that implements it:**

- **Lifecycle is four fields, not one list.** Declared phase (7 + Unknown), dated
  milestones, status, and the workstreams already modelled as gates G0–G11. The v1 list of
  12 stages mixed phases, a milestone (FID), a workstream (Permitting) and duplicates —
  Concept, Pre Feasibility and Feasibility are FEL 1–3 under older names. **The tree
  carries eight stage vocabularies** (logged as §8.13, with the measured table): plant
  builder (11 values), `PackageRegister` (6),
  `project_registry.VALID_PHASES` (4), ecosystem `ProjectStatus` (5),
  `instrument_registry` (8), Gantt config (5), the gates, and the docx. Settling them is a
  one-canonical-source item, not a cosmetic one. `abac_middleware._build_context` also
  hands every project to the policy as `SPECULATIVE`, whatever its stage.
- **Silence is derived, never stored.** No observed progress for 2 years reads as Shelved
  (inferred), 4 years as Presumed cancelled — Global Energy Monitor's published
  convention, adopted so their CC BY 4.0 data imports without a lossy mapping. Announced
  pauses and cancellations stay stored statuses. An earlier draft invented 24/18/6-month
  thresholds; they were withdrawn.
- **Evidence is its own ledger.** A claim carries many evidence rows (SUPPORT /
  CONTRADICT / SUPERSEDE) with a source locator and an **independence group**, so twelve
  reprints of one press release corroborate once. That is the syndication defect from the
  pipeline spec, fixed in the schema rather than in prose.
- **Ledgers versus projections.** Source, claim and claim–evidence are append-only.
  Organisations, projects, phases, assets, participants, milestones, lifecycle history and
  sites are projections rebuilt from accepted claims. Nothing writes a register directly,
  and a retraction recomputes projections rather than deleting history.
- **Counterparties are first-class.** An organisation dictionary keyed on GLEIF LEI, and
  one participation row per organisation per role, carrying agreement stage (an MoU is not
  a binding contract), dates, amount and visibility. v1 had a 200-character `Partners`
  string and no offtaker field at all.
- **Sites split** into project sites (optionally per phase) and asset sites, each with
  precision and confidence. The map must never draw a country centroid as a plot of land.
- **Thresholds are versioned rule sets** — exclusions, score weights, authority tiers,
  evidence bars, silence clocks, independence groups — so a figure published last quarter
  can still be explained.
- **The gate firewall is unchanged and absolute.** External intelligence is shown as
  context and never feeds a gate. A proposed wording of "never *automatically*" was
  rejected: the adverb would have opened a manual path from press coverage into G0–G11.

**Free sources named, licences checked 2026-09-18.** IEA hydrogen projects (CC BY 4.0; the
IEA **CCUS** database's licence is *not* confirmed — check its product page before
importing), Global Energy Monitor power and gas-infrastructure trackers (CC BY 4.0), GLEIF
LEI (CC0), UN/LOCODE (public domain), NGA World Port Index (US public domain),
OpenStreetMap via Protomaps (ODbL, attribution required). Software: Splink (MIT, and it
has a PostgreSQL backend, so no new datastore), feedparser, trafilatura (Apache 2.0 only
from v1.8), datasketch, rapidfuzz, cleanco, Pint, MapLibre. **Zingg is AGPL-3.0 — do not
adopt it in a hosted platform.** Paid services are excluded by the client's instruction, so
de-duplicating syndicated copies is GEX's own job. `external_corpus.import_snapshot`
already takes licence, attribution and retrieval date and turns snapshot diffs into status
transitions: it is the import path for all of these.

**What exists in code** (built by an earlier session; unchanged by this work):
`app/core/ecosystem_store.py` and `app/api/v1/routes_ecosystem.py`, 12 tests in
`tests/test_ecosystem_publication.py` — server-side publication, per-tenant enrichments,
soft-delete withdrawal, and the publisher's field visibility enforced against everyone
including `PLATFORM_ADMIN`. `frontend/src/lib/ecosystem/userProjects.ts` holds the
hardened four-rule matcher, 22 tests. **Nothing else in v4.2 exists**: no claim ledger, no
evidence table, no organisation dictionary, no site tables, no rule sets, no imports, no
map library in the frontend at all. `init_db()` in the ecosystem store still raises on
PostgreSQL, so an Alembic migration carrying RLS is owed before that switch can flip.

**Decisions the client owes:** D1–D14 in the docx; D12 (silence convention) and D13 (GEX
staff work the analyst review queue) were decided 2026-09-18. See §12.

### 2026-09-14 — duplicate tenor labels on `/pricing-curves` (sibling engine)

`term_structure()` labelled tenors with `tenor_m // 12`. `/term-curve` requests 18 and 30
months, so every molecule's curve carried two "1Y" and two "2Y" points at different prices
(e-Methane: "1Y" 113.93 and 137.24, "2Y" 115.06 and 138.13). React keys use
`tenor_months`, so nothing collided — the chart axis and the table were simply mislabelled.

**Convention, now authoritative:** whole years are `NY`; every other tenor is months
(`18M`, `30M`). Not `1.5Y`: a 15M tenor would read `1.25Y`. The engine's `tenor_label()` and
the frontend's `tenorLabel()` are **two copies of one rule**. `tenorLabel.engine-parity.test.ts`
holds them together: it runs the engine function under `gex_pf_engine/micro_service` and
compares every tenor 0–600 months. It **skips** where the sibling or its venv is absent
(docker staging), so a green run there proves nothing. The frontend's old `t / 12` produced
`1.5Y` rather than a wrong label, but a different convention from the engine's.

**Negative-verified.** With the old formula restored in memory only (no file edits), all
three engine checks fail and the curve check reproduces the exact duplicate list. The
frontend purge test goes red with `hasCurrentLabels()` removed. The parity test goes red
(538 mismatches, first at 13 months) with the frontend's old rule swapped back in.

**Stored published curves:** the purge is a safety net, not a clean-up of known damage.
The Pricing Admin page publishes `/calibrate` output or its seed curve, and both use tenors
`[1, 3, 6, 12, 24, 36, 60]` (`gabillon.py` `calibrate()`, both branches), which the old
rule labelled correctly. So the normal publish path could not have stored a mislabelled
curve. A correctly labelled published curve is kept (asserted).

**Live engine verified; signed-in page not.** Calling `:8001` exactly as
`routes_pricing_proxy._call_engine` does — `engine_auth_headers()`, a backend-minted service
token — returned 200 with `1M 3M 6M 9M 1Y 18M 2Y 30M 3Y 4Y 5Y` for e-Methane. The card was
not seen signed in: the Browser pane was signed out and no user token was minted. Whoever
next has a signed-in session: open e-Methane and expect `18M` and `30M`.

### 2026-09-14 — `/pricing-curves` rendered nothing for any signed-in user

`MoleculePriceCurve` was written against the `/calibrate` response shape but fetches
`/term-curve`, which the engine serves differently (§8.7). All eight responses passed
`isCurveSane()`, so the card rendered them and called `toLocaleString()` on an undefined
`capex_floor_eur`. There was no error boundary anywhere in `frontend/src`, so one card's
`TypeError` unmounted the whole route — heading and all.

**Why it looked environmental:** only signed-in users hit it. `main.tsx`'s fetch bridge adds
the bearer token; without one the call 401s and the card quietly draws its seed curve.

Reproduced before any edit — blank page, same `TypeError` — using a locally minted dev
token in the Browser pane, cleared afterwards. The regression test went red first (3 failed,
1 passed) and green after. The fix: one normaliser accepting both shapes; figures a response
does not carry stay null and render "—", never a default, because an invented half-life on
a pricing screen is worse than a gap; and a per-card error boundary, pinned by a test that
forces the chart to throw and checks that a sibling element survives. Verified live: 8 cards,
0 boundary fallbacks, no `undefined` or `NaN`, console clean after reload.

**Diagnostic trap:** a hand-minted token with `null` list claims made *every* signed-in
request 500 (§8.9), which briefly read as "PostgreSQL being down breaks everything". It does
not. Mint diagnostic tokens the way `auth.py:640-661` builds them — empty lists, not nulls.

### 2026-09-09 — the sibling's `app` alias, and a safety test that tested nothing

After `app` → `pf_engine`, `uvicorn app.main:app` was recalled from shell history three
times: twice into a bare `ModuleNotFoundError`, once into a tombstone that printed the right
command and still did not start the engine. The old name now works. `app/main.py`
re-exports `pf_engine.main.app` — the same object, not a second FastAPI instance — and
prints a deprecation notice.

What makes it safe is `app/__init__.py`: it **refuses to load when the platform backend is on
`sys.path`**, detected by `app/core/db_backend.py`, a file only the platform has. The hazard
is one process holding both trees with the sibling first, where `app.main` would silently be
the PF engine instead of the 56-router platform app.

**CORRECTED 2026-09-14.** The test for that guard inserted the platform *first* on
`sys.path`. In that order `import app` finds the platform's own package, the alias never
loads, and the test failed with `NO_GUARD` — reading as a broken guard. The guard was fine;
the test never reached it, and it went unnoticed for five days because the 2026-09-09
verification run was interrupted. Now the sibling-first case (the real hazard) must raise,
and platform-first is pinned separately. Negative-verified against a throwaway unguarded copy
— the snippet prints `NO_GUARD`, so the test fails without the guard — with the real alias as
the positive control. Deliberately *not* by editing the live sibling, whose `--reload` would
restart :8001.

**Also learned:** `--reload` binds the socket in the parent process. A worker that dies on
import leaves the reloader holding :8001, so `lsof` shows the port taken while `curl` gets
nothing.

### 2026-09-09 — a guardrail silently stopped scanning the sibling

`test_engines_verify_gex_identity_only` still named `gex_pf_engine/backend/app` after the
rename. The sibling is the one tree allowed to be absent, for partial checkouts, so the
missing path was absorbed as "not checked out": **39 sibling files left the Supabase scan**,
and `scanned >= 2` stayed satisfied by the two in-repo trees. The exemption now separates
*no sibling repo* (skip) from *sibling repo present, package gone* (a rename — fail), and
`scanned` must equal the number of trees actually present. Negative-verified both ways:
planting `supabase` in the sibling fails the test, and moving `pf_engine/` away fails it with
a message naming the rename.

### 2026-09-09 — a 500 where a 422 belonged (sibling engine)

`dscr: 1e400` sent to `/api/v1/model/covenant-check` returned **500**. Pydantic rejected the
value correctly; FastAPI's 422 body then echoed the raw `inf`, and serialising `Infinity`
raised. Fixed in `pf_engine/api/validation.py` (§6). Verified over HTTP with a real JWT: 422
with the input scrubbed, while a valid `dscr: 1.85` still returns `compliant: true`. With the
handler removed and the validator kept, the same request is a 500 again.

### 2026-09-09 — DSCR read as compliant when it was undefined (sibling engine)

**The defect.** `DSCR = CFADS / debt service` is undefined when debt service is zero —
after maturity, before first drawdown, or when a schedule is empty by mistake. The sibling
engine returned `float('inf')`, and `inf >= 1.30` is `True`. Measured before the fix:

```
calculate_project_metrics(revenue=10M, opex=4M, capex=0, debt_service=0)
  → dscr = inf,  dscr_compliant = True        ← passing a covenant it cannot have met
check_covenants({"dscr": inf}, {"dscr_minimum": 1.30})
  → compliant: True, severity: "ok", all_compliant: True
DebtSculptor(...).sculpt([...])   # 15y horizon on a 10y loan
  → sculpted_profile[10]["is_compliant"] = True
```

**A missing input produced maximum confidence** — the inverse of a covenant test, and the
same shape as the `PLATFORM_ADMIN` shim default removed the day before. `inf` also emits
the token `Infinity`, which is not valid JSON, so a strict client rejects the payload.

**The fix.** `gex_pf_engine/backend/pf_engine/core/dscr_guard.py` — one place decides:

- `meets(dscr, threshold)` — undefined **never** satisfies a covenant
- `breaches(dscr, threshold)` — undefined is **not** a breach either; with no debt service
  there is nothing to default on. Undefined is neither compliant nor in breach.
- `for_output(dscr)` — `None`, never `inf`

Applied at five decision points (`engine.py` ×3, `sculpting.py` ×2) and one output
boundary (`cfads.py`). **The sentinel itself was deliberately left as `inf`**: sixteen call
sites do `sum()`, `min()` and comparisons across the series, and swapping the type there
would trade a wrong answer for a crash. Every decision and every output fails closed.

**And the horizon is now rejected, not tolerated.** `DebtSculptor.sculpt()` raises when the
CFADS horizon exceeds the longest tranche tenor, naming the year the problem starts and
what to pass instead. The previous position — recorded in the sibling's own test as
"callers must clamp the horizon" — put the responsibility on every caller, and the one who
forgot shipped `Infinity`. Silently trimming would have been worse: a summary over a period
the caller never asked about. A shorter horizon is still allowed; only overrunning maturity
is refused. **`sculpt()` has no production caller today** (`DebtSculptor` is a known
zero-caller orphan), so nothing live changed behaviour.

Pinned by `backend/tests/test_dscr_llcr_characterization.py` (12 tests, cross-tree) and the
sibling's own `test_debt_sculptor_characterization.py`, whose defect test became three.

### 2026-09-09 — `gex_pf_engine` → `deal_engine` (name collision, not a duplicate)

Two different services shared one name. **Zero shared module names** — verified by diffing
the full file lists. The sibling (42 files) is the Gabillon PF engine on `:8001`; the
nested one (15 files) computes deals. 12 files rewritten, plus the architecture guardrail,
`deal.ts`, `engineClient.ts` and three docs. All 20 sibling references left untouched.

That guardrail skipped trees that do not exist, so a rename silently dropped one from the
scan — **verified by planting a typo, which changed nothing.** It now asserts the in-repo
trees exist, with the sibling the one tree allowed to be absent, plus a `scanned >= 2`
check so it cannot pass vacuously.

**The third collision — `app` — was fixed the same day.** Both repos had a top-level
package named `app`; whichever imported first won and the other's submodules became
unreachable. The **sibling** was renamed (`app` → `pf_engine`) because it is 19 files and
56 import lines against the platform's 152 files and 530 lines.

**The startup command changed by one token** and this is the only user-visible effect:

```bash
cd files/gex_pf_engine/backend
source ../micro_service/bin/activate
uvicorn pf_engine.main:app --reload --port 8001     # was app.main:app
```

Also updated: the sibling's `Dockerfile` CMD, and every `:8001` startup line across 11
documents. **The platform's own `uvicorn app.main:app --port 8000` was left alone** — the
two were distinguished by port, not by string, and 10 such references survive untouched.

The payoff: the cross-tree characterization test no longer needs its subprocess workaround.
All three packages — `app`, `pf_engine`, `deal_engine` — now import together in a single
interpreter, which was impossible that morning.

### 2026-09-08/09 — schema loss, rebuild, and a rename

**The PostgreSQL schema was found empty.** `gex_platform` contained only PostGIS's own
tables across `public`, `tiger` and `topology` — no `alembic_version`, no `gex_app` role,
no GEX table of any kind. It had held 98 tables at head 045 hours earlier. One container,
one volume, no other candidate. **The cause is not known and has not been invented.**

SQLite was untouched and is still the system of record, and all eight switches still read
`sqlite`, so the running product never noticed. That is the strangler pattern working: the
migration target was destroyed and the application was unaffected.

**Rebuilt** — migrations to head 045 (98 tables, 89 RLS), `gex_app` recreated and its dev
password reset (it lived only in the destroyed cluster), then eight of nine slice copiers:
53 tables, 6,622 rows.

**The ninth cannot run again.** `scripts/migrate_projects_collision.py` reads
`SELECT * FROM projects` from SQLite, and migration 033 retired that table. So `projects`
had no rebuild path. Migration 020 seeds 7; `project_registry.py` knows 12; the 5 in the
gap were runtime-created.

**`scripts/restore_registry_projects.py`** (new) restored those 5 plus 2 tenants. Sources
and judgment calls, all flagged on every run:

- Data comes from **`frontend/src/data/customerProjects.ts`**, not `project_registry.py`.
  The registry is an *access* profile — id, name, owner, jurisdiction — and carries
  neither `molecule` nor `status`, both `NOT NULL`. Restoring from it would have meant
  inventing commercial attributes.
- **`capex_eur: 0` → written NULL.** Two projects (90 MTPD SAF, 342 MTPD e-methanol) carry
  zero capex in the seed. That is a placeholder, not a price; a literal 0 could be consumed
  as real by blended WACC or the catalytic ratio. NULL says unknown, 0 says free.
- **`company_type = PRODUCER`** is derived, not guessed: every tenant owning a project in
  this database is PRODUCER, 7 of 7.
- **Pecos I capex carried as-is** — `capex_eur: 562000000` beside `capex_currency: "USD"`.
  Number written unchanged rather than applying an FX rate that cannot be sourced.

Dry-run by default, idempotent (verified by re-running: 0 written).

**Two projects are unrecoverable.** `proj_north_sea_e_methanol_203b51` and
`proj_wilhelmshaven_e_ammonia_f0dc91` have generated hex ids, were created via
`/projects/new`, and are defined in no seed, registry or migration. Their two evidence rows
are permanently unattributed, which is why `UNATTRIBUTED_BASELINE` moved **39 → 41** — for
a loss, not for new debt. The comment above it says so, and says to restore 39 if those
projects ever come back.

### Chain of Custody — the ledger renamed (2026-09-08)

`/api/v1/mass-balance` → **`/api/v1/chain-of-custody`**; API tag "Chain of Custody";
`domain_authorization.py` path mapping updated in the same change, since it maps path to
domain and a missed rename would have dropped the routes out of the sustainability domain.

**Tables keep `mass_balance_*` deliberately** — *mass balance* is the correct name for the
RED III chain-of-custody **method**; it is the wrong name for a **product**, because an
engineer reads it as conservation of mass and energy. The module performs two arithmetic
operations and no physics.

Registration is now **fail-loud**: the `try/except ImportError` that printed
`⚠️ mass_balance not found - skipping` is gone. A custody ledger that silently vanishes
while the API still answers 200 elsewhere is an audit surface disappearing quietly.
**56 other routers still use that pattern.**

`create_lot` now validates `project_id` against the canonical store, and **distinguishes
503 from 404**: `projects_store` fails soft, returning `None` both for "no such project"
and "database unreachable", so it probes the engine directly. Reporting an outage as 404
would tell an operator their id is wrong and they would invent another, anchoring custody
to nothing. Pinned by `tests/test_chain_of_custody.py` (7 tests), negative-verified.

### `tests/pg_support.py` — the one PostgreSQL entry point

Added 2026-08-10. Previously seven files each defined their own `_pg()` and 24 call sites
guarded database access with only a DSN *string* check, which says nothing about whether
anything is listening. Helpers that caught the connection error skipped; raw
`psycopg2.connect` sites raised it and **failed**. With the container stopped the suite
reported *8 failed, 209 passed, 70 skipped* — an outage that reads exactly like a
regression.

`pg_support.py` is now the only `psycopg2.connect` call site in the suite and exports
`pg_dsn`, `pg_connect`, `pg_admin` (the former `_pg`), `pg_as_tenant`, and `requires_pg`
(for tests that reach the database indirectly through the application shim). Reachability
is probed once per session and cached, so a down database costs one timeout rather than
seventy. **The rule: absent or unreachable is a SKIP; only a reachable database that
answers incorrectly is a FAILURE.**

Enforced by `test_pg_support_is_the_only_postgres_connect_site_in_the_suite`, which walks
the **AST** rather than the text — its own explanation contains both offending patterns
verbatim, and earlier guardrails in this repo repeatedly matched their own prose. It
excludes only itself, since a scanner must name the pattern it hunts. Negative-verified
in both directions: reintroducing a raw connect, and reintroducing a DSN-string guard,
each make it fail.

The 78 SQLite-mode skips are PostgreSQL-only guardrails (RLS, advisory locking,
cross-backend agreement) that correctly self-skip.

**The single failure is the same in both:**
`tests/test_architecture_guardrails.py::test_compose_runs_the_tree_that_tests_inspect`.
Long-standing and pre-existing. **Diagnosed 2026-08-09 — cause is now known.**

The test makes two assertions. The first (the blessed `REPO/docker-compose.yml` builds
and mounts from this backend tree) **passes**. The second fails, with exactly one
offender:

```
files/docker/gex-platform-enhanced/docker-compose.yml
  builds backend from files/docker/gex-platform-enhanced/backend
```

That is a **stale whole-platform copy**. Decisive evidence is content, not mtime (the
mtimes were reset by a copy operation and are misleading): the copy has **zero
migrations numbered 030+** and **no `account_lifecycle.py`**. It therefore predates the
entire auth slice, the vetting gate, and the whole PostgreSQL migration. Running it
would start a backend with no vetting and no RLS.

Nothing uses it: `docker ps` shows only `gex-pg-forward` (socat) and `files-postgres-1`
(postgis) — no container is built from that tree — and `docker/push.sh` contains no
compose reference.

**RESOLVED 2026-08-10 — deleted on Jim's instruction.** `files/docker/gex-platform-enhanced/`
was removed; `files/docker/` itself was kept (it holds the live production assets
`Dockerfile.*.prod`, `nginx.conf`, `push.sh` used by the Docker Hub flow). The guardrail
file now passes 13/13 and the full suite is green.

Before deleting, every non-code asset in the stale tree was confirmed to have a live
counterpart, and all 21 of its markdown docs were content-compared. Exactly one differed
— `postgres-migration-plan.md`, 3,370 bytes stale against 59,229 live, i.e. the live copy
is a superset. Nothing was lost.

Because neither `files/` nor `files/docker/` is a git repository, deletion was
unrecoverable, so the non-regenerable content (excluding venv/node_modules/caches — 319M
of the 356M was a virtualenv) was archived first to:

```
files/_retired/docker-gex-platform-enhanced-20260810.tar.gz   (4.3M, 806 entries)
```

`_retired/` is in the guardrail's `skip_parts`, so the archived compose files inside it
cannot re-trigger the test. Delete the archive once a release has passed.

**Guardrails to be aware of when editing:**
- SQLite ratchet, `BASELINE = 97`, currently at 68 — may only decrease.
- One-`.db`-file guardrail — flips to *no*-`.db`-file at the end of slice 7.
- `test_the_dead_tables_are_quarantined_not_dropped` — asserts both directions: none
  dropped, none revived under the original name. **Delete this test in the same commit
  that drops the quarantined tables.**
- `test_the_two_specific_energy_fields_are_different_quantities` — see §8/§9.
- Several guardrails deliberately match *definition lines* or strip docstrings rather
  than matching prose, because earlier versions passed on explanatory comments. Preserve
  that when editing them.

---

## 8. Known unresolved defects



1. **`contracts` exists in neither store.** `contracts_sqlite.py` queries it at lines
   150, 200, 258. Verified absent from both SQLite and PostgreSQL.
   `/api/v1/contracts/summary` returns 500. **This needs CREATE, not DROP** — it is
   routed and called, unlike the 12 quarantined tables.
2. **`_log_event` hash defect.** `development_packages.py:616` and `spend_wave.py:240`
   hash a typed object but store `str(new_val)`. The stored row therefore cannot
   reproduce its own digest. **7 of 18 existing package events are permanently
   unverifiable** — a fix helps future events only, and cannot repair history.
   (`projects_store.py:178` uses `str()` similarly but writes an unhashed audit row, so
   it does not share this defect.)
3. **No `app.current_user_id` GUC.** Keeps `permission_user_overrides` and
   `user_signing_keys` admin-only. Documented in migration 042 and asserted by a test so
   it stays discoverable.
4. **Both stores are live and diverging, and tests that compare them must account for
   it.** `finance_entitlements`: SQLite 1128 rows, PostgreSQL 838, watermark records 744
   actually copied. `test_a_sampled_entitlement_matches_column_for_column` sampled "first
   by `entitlement_id`" and demanded the row exist in PostgreSQL; on 2026-08-10 it picked
   a row created after the copy and reported drift where there was none. It now samples
   from the recorded `copied_keys` — the only population where fidelity can hold. **Any
   new cross-store comparison must do the same**; identical key sets is not a property
   that can hold while SQLite is still the active backend.

4. ~~PostgreSQL tests do not fail uniformly when the database is unreachable.~~
   **FIXED 2026-08-10.** See §7 — the suite now skips cleanly through an outage.

   Still open, related and operational: `files-postgres-1` exits (255) on its own —
   it did so twice during this work. Its healthcheck logs
   `FATAL: database "gex_user" does not exist` continuously because the probe omits the
   dbname and defaults to the role name. That is noise rather than the cause, but it
   buries the real cause. Worth fixing the compose healthcheck to pass `-d gex_platform`,
   and worth finding out why the container exits.
5. **`SECRET_KEY` is the dev default**, and `GEX_JWT_SECRET` on the TEA engine falls back
   to the same. Fine locally; blocking for any deployed environment.
6. **Nine frontend lib files still call Supabase `.from()` directly** —
   `dealClient.ts` (3: `equation_engine_runs`, `v_latest_engine_run`), `iterations.ts`
   (8), `backendClient.ts` (2), `projectAccess.ts` (2), `siteInfrastructure.ts` (2),
   `customLibrary.ts` (2), `equipmentCatalog.ts` (1), `plantStore.ts` (1),
   `seedInitialCanvas.ts` (1). Under decision §5.1 these must move behind backend
   endpoints. **`dealClient.ts` was not migrated** — the decision was taken but the work
   was not done. `projectAccess.ts` is the highest-risk of these, since it is an access
   path.
7. **One curve, two response contracts.** `GET /pricing/term-curve` names the floor
   `capex_floor_eur_t`, keeps `n_observations` under `governance`, and sends no half-life,
   seasonality or convenience yield; `POST /pricing/calibrate` sends all of them under the
   card's names. `MoleculePriceCurve` now normalises both (§7), but the split itself is
   untouched — the next consumer will meet it again. Settle one contract engine-side.
8. ~~**Duplicate tenor labels.** `gabillon.py` used `tenor_m // 12`, labelling 18M "1Y"
   and 30M "2Y".~~ **FIXED 2026-09-14** — see §7. The rule exists twice (engine
   `tenor_label()`, frontend `tenorLabel()`); a parity test holds them together but skips
   without the sibling checkout. Live engine verified; not yet seen on a signed-in page.
9. **A present-but-null list claim turns into a 500.** `abac_middleware.py:357-358` does
   `set(payload.get("nda_signed_with", []))`; `.get`'s default applies only when the key is
   absent, so `null` raises `TypeError` and the request dies as a plain-text 500 rather than
   a 401. Real login never emits null (`auth.py:659-661`, `817-818`) — found only through a
   hand-minted diagnostic token — but a malformed token should be refused, not crash.
10. **Operational, 2026-09-14: Docker Desktop was not running**, so `files-postgres-1` and
    :55432 were down. Easy to miss: sign-in and most signed-in pages still work, because
    `AUTH_DB_BACKEND=sqlite`. The symptom is `projects_store read failed (SELECT):
    (psycopg2.OperationalError) … port 55432 failed: Connection refused` (`e3q8`) in the
    backend log; the read falls back and the request still returns 200.
    **CORRECTED 2026-09-14 — starting Docker Desktop does not restore the database.**
    `gex-pg-forward` restarts on its own, so :55432 opens and *looks* up, but
    `files-postgres-1` has restart policy `no` and came back `Exited (255)`; connections then
    fail with "server closed the connection unexpectedly". `docker start files-postgres-1`
    is required. Done 16:03: healthy, `gex_app` connects, head 045, `projects` returns 0 rows
    with no tenant context (fail-closed, as intended). Worth giving the postgres service a
    restart policy. :8002 (TEA) was also not listening — cause not investigated.
11. ~~**An expired session looks signed in.**~~ **FIXED 2026-09-14** (frontend, then the
    backend gap below). Access tokens live 30 minutes
    (`ACCESS_TOKEN_EXPIRE_MINUTES`). `frontend/src/lib/authToken.ts` had no expiry check and
    no `status === 401` handler existed in `frontend/src`, so a tab left open kept
    rendering signed-in pages while ABAC answered every API call `401 Authentication
    required`. On `/pricing-curves` each card then silently drew its seed curve — no
    18M/30M points — which read as "the fix did not land". Seen as repeated batches of
    eight `/term-curve` 401s in the backend log.

    **Now caught three ways:**
    - **Clock.** `lib/authToken.ts` reads the JWT `exp` (stored `expiresAt` is the fallback;
      with neither, the server decides). Every getter treats an expired token as absent, so
      none is sent. `main.tsx` calls `discardExpiredSession()` before the first render —
      `UserRoleProvider` initialises from storage — so a tab reopened after expiry starts
      signed out. Verified live: seeded an expired session, loaded `/pricing-curves`, landed
      on `/login` with storage cleared and **0** term-curve requests.
    - **Navigation.** `RequireAuth` (moved to `components/RequireAuth.tsx`) no longer trusts
      `sessionTier` alone; it is set at login and outlives the token.
    - **Server.** The fetch bridge (moved out of `main.tsx` into `lib/fetchAuthBridge.ts`,
      because `main.tsx` renders on import and cannot be tested) ends the session on a 401 —
      only when the request carried the bearer that is *still* stored (not a guest, a
      caller-supplied token, or a request issued before signing in again), and never for the
      credential exchanges `/api/v1/auth/login`, `/auth/refresh`, `/account/register`
      (PUBLIC_ROUTES — their 401 means wrong credentials). Verified live: a forged bearer's
      401 from `/projects/visible` cleared the session; a wrong-password login 401 did not.

    `lib/sessionGuard.ts` `expireSession()` clears storage exactly as `logout()` does (both
    call `clearAuthSession()`) and does a full `location.replace('/login')` — a reload, since
    the session also lives in React state. Once per page load (eight parallel 401s → one
    redirect), and never while already on `/login` (no loop). No timer: a page that makes no
    call and no navigation stays rendered until it does. No clock-skew leeway.

    Tests: `authToken.test.ts` (+13), `fetchAuthBridge.test.ts` (10), `sessionGuard.test.ts`
    (5), `RequireAuth.test.tsx` (4) — vitest **114 passed, 0 failed, 14 files** (was 82 / 11).
    Every guard was negative-verified by breaking it on a scratch copy. One was decorative at
    first: the credential-exchange tests iterated `CREDENTIAL_EXCHANGE_PATHS` itself, so
    deleting `/auth/login` from the set still passed. They now name the paths literally, and
    also fail if the exemption is widened to the whole `/api/v1/auth/` prefix.

    **Backend gap — FIXED 2026-09-14. A presented `Authorization` header that fails is a
    401; `x-demo-user` is consulted only when no Authorization header was sent.** Before,
    `abac_middleware.py` `_extract_user` fell through to the demo header whenever the bearer
    failed to decode, and under `GEX_DEMO_MODE` (default `True`, `config.py:33`; not set in
    `backend/.env`) served the request as the seeded user that e-mail named. The bridge sends
    `x-demo-user` on every call. Measured with a forged JWT: `/pricing/term-curve/SAF` → 401
    with the bearer alone, **200** with the demo headers; `/projects/visible` → 401 either
    way. A session the *server* rejected (revoked, re-keyed) was served 200 and invisible to
    the frontend; the live redirect came only from `/projects/visible`'s 401, after 6.4 s.
    Clock expiry never depended on this — the session is cleared before sending, so neither
    bearer nor `x-demo-user` goes out.
    - **Same fall-through in `route_security.require_authenticated`** — the global
      dependency, and the only gate on ABAC-exempt routes or with
      `ENABLE_ABAC_MIDDLEWARE=False`. Same rule applied (`presented_credential`).
    - **Also fixed in `_extract_user`:** with `GEX_DEMO_MODE=False` a demo header made it
      return a `JSONResponse` *as the user*. A Response is truthy, so `dispatch`'s
      `if not user` passed and the request continued with **no identity** (200 as `None` in
      the test). It now returns `None` → 401.
    - **Behaviour change:** a non-`Bearer` Authorization header (e.g. `Basic`) plus demo
      headers used to authenticate as the demo user; it is now 401. The frontend sends none.
    - **Test:** `tests/test_demo_header_fallback.py`, 14 cases, each against the middleware
      and the dependency separately. Forged-unsigned, expired, garbage and `Basic`
      credentials + demo headers → 401 with the demo lookup **never called**; demo headers
      alone → the seeded user; a valid bearer beats demo headers; demo mode off → 401.
      **Negative-verified by running it on the unfixed code first: 9 failed, 5 passed** (all
      8 refusals answered 200 as the demo user, plus the demo-off middleware case); 14 pass
      after. Suite: **401 passed, 112 skipped, 0 failed** (387 / 112 before).
    - **Not re-measured live** — :8000 was not listening. Expected: forged bearer + demo
      headers → 401 on `/pricing/term-curve/SAF`, so the bridge ends the session on the
      first call rather than waiting for `/projects/visible`.
    - **Shadowed copy, left alone:** `routes_projects.py:812-835` (`/visible`) still falls
      through from an invalid bearer to `x-demo-user` in its own code. Unreachable while the
      middleware runs (it 401s first; `/visible` is not exempt), but it is a third copy of
      the rule. `/{project_id}/profile-intelligence` beside it already refuses correctly.
12. ~~**`isolated_store` does not isolate `app.core.auth`.**~~ **FIXED 2026-09-14.** `auth.py`
    **and `refresh_tokens.py`** (same defect) captured `DB_PATH = settings.SQLITE_DB_PATH` at
    import and called `auth_connection(DB_PATH)`; an explicit path beats `settings`, so the
    fixture's repointed path never reached the auth slice — and a first import *under* the
    fixture pinned it to the throwaway file for the rest of the process. `_load_user_by_email`
    runs `init_auth_db()` (DDL, 17 seed upserts, commit) on every call. Both `_get_conn()` now
    call `auth_connection()` with no path; neither module has a `DB_PATH`.
    - **Measured before the fix — latent, not exercised.** mtime could not answer it: the dev
      DB changed size between two reads with no process holding it (another session writing).
      So a pytest plugin wrapped `sqlite3.connect` in the test process, recorded every open of
      `gex_platform.db` by test and calling frame, and fingerprinted `auth_users` (each
      `_seed_user` re-salts `password_hash`) around every `isolated_store` test — read-only, no
      rows added. Full suite, all-SQLite (401 passed): 186 dev-DB opens, **0 during the 84
      `isolated_store` tests** (`test_client_billing` 26, `test_open_interest` 23,
      `test_throughput_billing` 21, `test_demo_header_fallback` 14); fingerprint unchanged in
      all 84. Same result with the four files alone and together. The billing/interest modules
      never call `auth`; the demo test stubs the lookup.
    - **Conftest now carries the real auth schema.** The stand-in `auth_users` (no `is_active`,
      no `password_hash`) crashed any real lookup under the fixture. `isolated_store` repoints
      first, then calls `auth._ensure_tables()` on the temporary store — the owner, not a copy.
    - **Test:** `tests/test_auth_store_isolation.py`, 6 tests. The dev DB is refused at
      `sqlite3.connect`, so a regression fails at the open, before any statement runs.
      `get_user_payload_by_email`, `authenticate_user` and the refresh-token DDL run under
      `isolated_store` with a positive control (a user present only in the throwaway store must
      be found); both modules must follow two successive paths at call time; an AST guardrail
      rejects any `*_connection(...)` handed a module-level `settings.SQLITE_DB_PATH` capture.
      **Negative-verified in memory, no file edited:** old capture at the dev path → 6 failed
      (5 on the guard, so no dev write; 1 on the AST scan naming both old patterns); old
      capture at a throwaway path, the reverse case → 6 failed (user not found, DDL missing,
      path mismatch).
    - `test_demo_header_fallback.py` dropped its `auth.DB_PATH` monkeypatch;
      `test_account_lifecycle.py` dropped a vestigial `DB_PATH` swap.
    - **Suite:** `./venv/bin/python -m pytest tests/ -q` → **407 passed, 112 skipped, 0 failed**
      (all-SQLite: `DATABASE_URL` not exported, Docker not running). Probe after: 0 dev-DB
      opens across 89 `isolated_store` tests.
    - **Still open.** (a) Importing `auth` writes the dev DB: `auth.py:938` runs
      `init_auth_db()` at import — 41 write statements, re-salting all 17 demo password
      hashes — in every pytest process, before any fixture exists. (b) 32 modules still capture
      `DB_PATH` at import; 28 hand it to raw `sqlite3.connect`, which `isolated_store` cannot
      reach and the new guardrail does not cover (it covers the shim accessors only).
13. **Eight project-stage vocabularies, and one of them is decorative.** Measured
    2026-09-18:

    | Where | Values |
    |---|---|
    | `NewPlantDialog.tsx:64`, `PlantSettingsDialog.tsx:230` | 11: Concept … Pre FEED, FEED, Permitting, Pre FID, FID … Operating |
    | `PackageRegister.tsx:32` | 6: FEL_1, FEL_2, FEED, FID, CONSTRUCTION, COD |
    | `GanttVisibilityConfig.tsx:65` | 5: ADVISORY, BUILD, FIN_CLOSE, CONSTRUCTION, OPERATIONS |
    | `project_registry.py:223` | 4: development, construction, commissioning, operating |
    | `types.ts` (`ProjectPhase` + `ProjectStatus`) | **split 2026-09-18**; was 5 mixed values: concept, planned, construction, operational, cancelled |
    | `instrument_registry.py:289` | 8: SPECULATIVE … FINANCEABLE, OPERATIONAL |
    | Bankability gates | G0 … G11 |
    | `Data_structure_local.docx` | 12, using FEL 1–3 |

    Three consequences, in rising order of seriousness. **(a)** The client document and the
    plant builder — the entry path that document names — already disagree: FEL 3 against
    FEED. **(b)** `ProjectStatus` puts phase and status in one field, so a cancelled project
    has no recordable phase and a "planned" project has no recordable status; any imported
    status (Global Energy Monitor, IEA) therefore needs a lossy per-screen mapping.
    **(c)** `abac_middleware.py:475` hands every project to the policy as
    `project_state="SPECULATIVE"`, whatever its real stage, so **any ABAC rule keyed on
    project state is decorative** — it cannot discriminate between two projects today. That
    is the one part with a runtime symptom, and it is silent.

    **One of the eight is fixed, 2026-09-18 — consequence (b).** `types.ts` now carries
    `ProjectPhase` (7 + `unknown`) and `ProjectStatus` (active, on_hold, cancelled,
    mothballed, decommissioned, superseded) as separate fields, so a project is cancelled
    *at* a phase. `normaliseLifecycle` reads rows in either vocabulary; the store gained a
    `phase` column with an additive `ALTER TABLE`, normalises on write and on read, and
    `routes_ecosystem` carries both fields. The plant builder publishes two selects instead
    of one. **The trap worth knowing:** `unknown` is a valid phase *value* but means "no
    phase recorded", which is also what the migration writes into every pre-split row — so
    reading the phase first silently discarded the legacy status. Both copies now test for
    it, and the tests were negative-verified by reintroducing exactly that bug.
    A parity test (`test_the_lifecycle_vocabulary_matches_the_frontend`) pins the Python
    copy of the vocabulary to `types.ts`, because the two exist only for as long as legacy
    rows do. Tests: 5 backend (17 in that file), 14 frontend; suites 428 passed / 112
    skipped and 158 passed. **Seven vocabularies remain**, and `project_state` is still a
    constant.

    Not a defect you can see on screen, which is why it has survived: each vocabulary is
    locally consistent.
14. **Evidence documents go in and cannot come out.** Measured 2026-09-18, correcting an
    earlier claim in this session that no file storage existed — it does, in two places:
    `development_packages.py:1101` (`POST /{package_id}/evidence`) and
    `routes_bankability_proxy.py:350`. The package path is sound where it counts: 25 MB
    cap, empty-file rejection, **content-addressed by sha256**, metadata in
    `package_evidence`, the hash appended to `evidence_refs` — which is what gates the
    `EVIDENCED` transition — and the event logged. Four gaps, in order of severity:

    - **No download route.** There is a list endpoint returning metadata and hashes, and no
      `FileResponse`/`StreamingResponse` anywhere in the module. A document can be attached
      and its hash can gate a package, but no reviewer can read it back through the API —
      only by reaching the server's disk. For an evidence workflow that is the whole point
      of the upload, this is the defect that matters.
    - **Local disk, not mounted.** `PACKAGE_DOCS_DIR` defaults to `data/package_docs`
      (`GEX_PACKAGE_DOCS_DIR` overrides). `docker-compose.yml` mounts volumes for
      PostgreSQL and Redis but **not** for this directory, so every container replacement
      loses the documents while the hashes that gate the packages survive in the database.
      A package would read as EVIDENCED with its evidence gone.
    - **No tenant scoping on the path.** Files land under `{package_id}/`, and the
      endpoints derive only an actor e-mail from the bearer. The global
      `require_authenticated` dependency covers them, but nothing observed checks that the
      caller's tenant owns the package.
    - **No content-type allow-list, no virus scan, no retention rule.** `safe_name` uses
      `os.path.basename`, so path traversal is handled; content is not.

    **Direction** (not yet decided, and not started): add the ABAC-checked download route
    first, mount the directory in compose second, and keep local disk until there is more
    than one backend replica — object storage (MinIO is free and self-hostable) is a
    deployment decision, not a code one, because the ledger already stores only hashes. It bites when two screens are compared, when third-party data is
    imported, and it blocks the v4.2 "evidenced stage" and any attrition metric, both of
    which need one ladder. **Fix direction** (§7, 2026-09-18): one canonical phase list
    (7 + Unknown) with status as a separate field, the other seven mapped onto it, and
    `project_state` either populated for real or removed from `ContextAttributes` rather
    than left as a constant that reads like a decision.

15. **The plant save path can wipe a portfolio.** `savePlantsToCloud`
    (`frontend/src/features/canvas/PlantBuilder.tsx:197‑199`) issues
    `delete().eq("user_id", userId)` and then `insert(rows)` as two separate PostgREST
    calls with **no transaction**. A network failure, a tab close or any error between the
    two leaves the user with nothing — the delete has committed and the insert never runs.
    PostgREST cannot make those atomic from the browser; one backend endpoint can.
    Measured 2026-09-20 by reading the call site; not reproduced against live data, and
    deliberately not — reproducing it would destroy the 53 rows. Fix: `PUT /api/v1/plants`
    (`docs/supabase-cutover-endpoints.md` §4), one transaction, with a guard refusing a
    body that deletes more than it writes unless the caller states the count.

16. **FIXED 2026-09-20 (increment 4).** Kept here because the defect is the reason the
    replacement looks the way it does. `DELETE /api/v1/equipment-equations/{id}` scopes on
    the owner from the token and answers **404** for a row that is not the caller's;
    verified live — Marwen deleting one of Jim's equations gets 404 and the row survives.
    Negative-verified by dropping the owner predicate: three tests failed.
    The original defect follows.

    **Equipment equations can be deleted by anyone, for anyone.**
    `useEquipmentEquations.remove` (`frontend/src/hooks/useEquipmentEquations.ts`) is
    `supabase.from("equipment_equations").delete().eq("id", id)` — **no user scoping**.
    Every other query in that hook filters on `user_id`; the delete does not. Under the
    bundled anon key, with RLS off, that deletes any row by id for any visitor. Only 2 rows
    exist today, which is the only reason this is small. Fix:
    `DELETE /api/v1/equipment-equations/{id}` returning **404, not 403**, when the row is
    not the caller's — a 403 would confirm the id exists.

17. **The canvas has no real identity — `AuthContext` is a stub.** Measured 2026-09-20.
    `frontend/src/contexts/AuthContext.tsx` returns a hard-coded
    `{ id: 'demo-user', email: 'demo@greenearthx.com' }` with `isAuthenticated: true`,
    and **there is no `AuthContext.Provider` anywhere in the tree** — every `useAuth()`
    consumer gets that default. Eight modules consume it, including `PlantCanvas`,
    `PlantBuilder`, `SiteInfrastructure`, `ComponentLibrary`, `useEquipmentEquations`
    and **`lib/projectAccess.ts`**, which decides `isAdmin` from
    `ADMIN_IDS.includes(user.id) || user.email === "marwen@greenearthx.com"` — i.e. an
    access decision evaluated against a fabricated identity. Consequences: every canvas
    user is the same person, so per-user plant ownership is fiction; and the live
    `plants` table's owner ids (`admin-001`, `demo-user`, `user-003`) are this stub and
    its predecessors, not accounts. The backend fix is in (increment 2 derives the owner
    from the bearer token and accepts no `user_id` from the client), but the **frontend
    still needs a real provider** wired to the session, and `projectAccess` should not be
    deciding admin rights client-side at all.

### Energy-economics constants — measured 2026-09-10/11, re-verified 2026-09-25

Found by an eight-family sweep of hardcoded constants; 135 raw findings, 64 put through an
adversarial verifier that re-derived the evidence and traced whether the number reaches a
screen. The ten below are the ones that survived verification and are **not** fixed. Five
siblings were fixed — see §6. Every item here was re-confirmed against the live tree on
2026-09-25, after the PostgreSQL cutover.

The recurring shape is worth more than any single entry: **one calculation living in two
places with only one of them fixed**, and **constants dressed as configurable parameters**.
The diagnostic for the second is cheap — grep the identifier across both trees and count.
If it appears only in its own definition and its own default, it is not overridable,
whatever the docstring says.

18. **The bankability route always returns 500, and fixing the crash makes it worse.**
    `POST /api/v1/finance/financial-model/run` (`app/api/endpoints/finance.py:339`,
    registered `main.py:679`) raises `NameError: name 'settings' is not defined` on every
    call, from `app/services/financial_model.py:289`. The only
    `from app.core.config import settings` sits **inside an 83-line string literal at lines
    6–88**, so it never binds — confirmed by AST, not grep.
    **Do not simply add the import.** That activates a route whose engine builds
    `ScenarioInputs()` from pure defaults — no project data, no match data — so every
    `match_id` returns a byte-identical DSCR and the handler emits *"Bankable. DSCR 1.72x
    exceeds 1.3x threshold. Proceed to settlement."* Its `power_price_index` is a
    dimensionless index pinned at 100 in the base case, so `power_drift` is always exactly
    zero: **electricity cannot move that DSCR by construction.** `FinancialModelRequest`
    declares `capex_index` and `subsidy_pct` as "optional overrides" and the handler passes
    only `match_id`. `state_machine.py:498` also imports it as a DD postcondition, so this
    is not cosmetic. It needs real project inputs or an honest refusal — a product call.
    Same shape as defect 1 above (`/api/v1/contracts/summary`), which is tracked; this one
    was not.
19. **The Cost DNA waterfall is built on three unsourced constants.**
    `../gex_pf_engine/backend/pf_engine/core/price_lineage.py` — `capex_proxy` share of
    LCOH `0.65` (:320, repeated inline at :339), `avg_tenor = 15` (:321), `risk_free = 0.03`
    labelled "ECB policy rate proxy" (:313). They produce the *Financing Spread*,
    *Concessional Absorption* and *Grace Period Benefit* rows of
    `frontend/src/features/pricing/MoleculeLineage.tsx`, rendered on the Dashboard, and the
    3.0% is quoted on screen as the authoritative basis.
20. **bps→DSCR transfer coefficients are unnamed literals.**
    `backend/app/core/structuring_engine.py:320` and `:390` (`0.0008`), `:633` (`0.0006`),
    `:634` (`0.0005`). `GET /api/v1/structuring/{id}/recommend` and `/gaps` render them
    through `PackageBuilder.tsx`, `StructuringTimeline.tsx` and `GapAnalysis.tsx`. Note
    `dscr_sensitivity.py`'s own docstring records that assumed elasticities were removed
    from the DSCR surface because they disagreed with the grid; this second implementation
    survived.
21. **One project, two headline capacities.** Enumerated 2026-09-25 across
    `frontend/src/**/*.ts{,x}`. Three screens annualise at **330** —
    `features/capacity/CapacityPage.tsx:63`, `features/marketplace/MarketplacePage.tsx:400`
    and `:982`, `features/finance/DemandPipeline.tsx:56`. Three annualise
    `capacity_mtpd` at **365** — `features/projects/ProjectsPage.tsx:168`,
    `features/projects/ProjectProfilePage.tsx:335`,
    `features/finance/FinanceDashboardPage.tsx:143` — plus two shared lib modules,
    `lib/narrative.ts:37` and `lib/capacityUnits.ts:1`
    (`CAPACITY_DAYS_PER_YEAR = 365`), both imported only by `ProjectProfilePage`.
    Separately `features/finance/RevenueOfftakePage.tsx:302` annualises a *contracted*
    daily volume at 365, which is a different quantity. 365/330 = 1.106, so the same
    project's headline annual capacity is **10.6% larger** depending on which screen is
    open. `lib/capacityUnits.ts` is the obvious single home; nothing currently forces its
    use.
22. **Every project is scored as a 100 t/day plant.**
    `../gex_pf_engine/backend/pf_engine/api/routes_model.py:328` —
    `production_mtpd=100.0,  # Would come from capacity` — inside
    `@router.post("/integrate/calculate-from-capacity")` (:310). The request model does
    carry a `production_mtpd` field (:33) and another route passes it through honestly
    (:143); this one ignores it. Feeds
    `result.cfads.utilization`, `uncontracted_capacity_mtpd` and the CFADS/DSCR built on
    `effective_production_mtpd`.
23. **45V accepts a temporal-matching parameter it never reads.**
    `backend/app/core/decision_twin.py:450` takes `temporal_matching: str = "annual"`;
    `evaluate_45v` has five checks — Molecule, Jurisdiction, Tier, Additionality,
    Prevailing Wage — and **no temporal or deliverability check at all**. Unlike its RED III
    sibling (fixed, §6) this is a *missing* pillar rather than a broken one; adding it needs
    a COD year the signature does not carry and a decision on the 2030 hourly cliff.
24. **Zero-carbon electricity is applied unconditionally.** `tea_engine/lca.py:58` sets
    `ELECTRICITY_EF["eu_renewable"]["ef"] = 0.0` gCO2e/kWh and `:63` maps **both** EU
    methods (`annex_v`, `annex_vi`) to it. Zero is defensible for genuinely additional,
    hourly- and geo-matched renewables, and the file is honest about its own status
    (`EF_VERIFIED_BY = None`, "Do NOT flip ascertained on the strength of these defaults").
    The defect is that it applies whether or not the project meets the three pillars, so a
    project failing additionality still gets zero-carbon electricity in its CI.
25. **A carbon-intensity conversion implies an LHV of 3.6 MJ/kg.**
    `frontend/src/engine/units/conversionFactors.ts:306` —
    `linear('gCO2e/MJ', 'kgCO2e/kg', 0.001 * 3.6)`. Hydrogen's LHV is 120 MJ/kg; 3.6 is the
    kWh→MJ factor from the line above, copied. ~33× on a number that decides certification.
    `unitFamilies.ts:55` declares `requiresContext: ['gwp_version','lhv_hhv']` — the
    registry has the slot and the conversion ignores it.
26. **Two places take a user's number and apply a different one.**
    **(a) TEA contingency is dropped on the real path.** `tea_engine/models/tea.py:38`
    declares `contingency_pct: float = 15.0`; the value is validated and unit-registered
    (`integrity.py:105`). But `_build_plant` (`compute/openpytea_runner.py:199-243`)
    assembles the OpenPyTEA config with **no `contingency` / `fixed_capital_factors`
    key**, so the real path silently falls back to OpenPyTEA's own process-type table
    (`venv/.../openpytea/plant.py:165-167`, `"X": 0.1`, applied at `:765-767`).
    Measured 2026-09-25 by building a Plant exactly as `_build_plant` does:
    contingency/(isbl+osbl) = **0.1 exactly** (isbl 255,458.49, osbl 76,637.55,
    contingency 33,209.60). Only the `_stub_numbers` path
    (`openpytea_runner.py:135`) honours the request. A user who sets 15% gets 10%.
    *(An earlier draft of this entry cited `:181-191` and was retracted as false; the
    line was wrong, the defect is real — `:181-191` is `_validate_equipment`.)*
    **(b) A sponsor's stated equity return is discarded.**
    `backend/app/api/v1/capital_bridge.py:193` `DEFAULT_EQUITY_COST = 0.12` overrides a
    user-supplied column at `:1113` and `:1128` — precisely: `rate_pct` is an optional
    user field on every tranche (`:249`, persisted `:429`), debt tranches use it
    (`:1105`), and `SEED_EQUITY` / `SPONSOR_EQUITY` tranches discard it for the 0.12
    constant in both WACC loops. So a sponsor who states their own equity return is
    ignored, while a lender's rate is honoured. Same family as the `power_opex_share`
    defect fixed in §6: the API advertises a control that does nothing.
    Related and unverified: `openpytea_runner.py:135` also carries a **`6200.0` €/unit
    capex intensity** that no request field can set.
27. **Two molecule price tables and four covenant floors.**
    `frontend/src/features/projects/ProjectsPage.tsx:45` and
    `features/marketplace/MarketplacePage.tsx:117` disagree — H2 4500 vs 5500, e-NG **1100
    vs 120**. Separately the DSCR covenant floor is 1.20 in `DSCRHeatmap.tsx`, 1.25 in
    `FinanceDashboardPage.tsx:297`, 1.30/1.10 bands in `CovenantsPage.tsx` and `CFOReport`,
    and 1.2 in `DebtCashflowWaterfall` — four screens, four breach thresholds.

**Not in this list, deliberately.** 71 of the 135 findings carry only one agent's
judgement — the verifier pass ran out of budget before three families — and are leads
rather than defects. 5 were false positives, all of them the §6 plant-builder fix being
correctly detected as already remediated. The full dossier and the verifier verdicts were
rebuilt from workflow journal `wf_21cc0cd0-1f5`.

### Found during the rules-3.0.0 work — measured 2026-09-26

28. **Seeded projects display gate data the engine does not produce.**
    `frontend/src/data/customerProjects.ts` hand-writes gate summaries — names,
    completion percentages, blocking items — for demonstration projects, and the UI
    renders them instead of engine output. It gives **19 names for 12 gates**, and some
    are the wrong gate: five G11 entries carry *certification* content (45V, RFNBO, SAF
    mandate) under "GHG Pathway Verified", and seven G3 entries carry *EPC/technology*
    content under "Technology Vendor Locked". The ETFuels Rattlesnake Gap header shows
    "Structurally Bankable" while the engine rates that project SPECULATIVE. **Do not
    rename in place** — renaming G11 to "COD & Stabilization" would put 45V LCA text
    under a Commercial Operation gate. Replace the fixture with engine output.
29. **The gates screen does not use the real upload endpoint.** `POST
    /bankability/evidence/document` stores files with a SHA-256; `StageGatesPage`
    attaches documents with `URL.createObjectURL` and never calls it, so
    `document_hash` is never populated from the UI.
30. **The evidence write handler has no authorization of its own.** (The new assign
    endpoint does check the caller's company; `POST /evidence` still does not.) The maturity
    maker/checker rule is enforced by status transition, not by actor, so a party that
    can write can still move its own item to VERIFIED. Binding verification to actor
    class, organisation and project role is the remaining P0 in the standard.
31. **Operational: the admin account reads as a guest.** ABAC refuses project
    bankability to `admin@greenearthx.com` — "Guest users may only access PUBLIC
    resources. Complete KYC verification". Correct behaviour for an account with no KYC;
    it means the gates screen cannot be exercised with that account.
32. **ETFuels has 30 unassignable evidence requests.** Its only accounts are Commercial and
    Finance/Treasury; Legal, Project and Engineering items on Rattlesnake Gap and Pecos have
    no one to go to. Onboard an Executive and an Engineering account through the vetted
    `/register` path, then run `scripts/convert_invented_evidence.py --assign-open --apply
    --mirror-sqlite`. Simulated read-only 2026-09-26: the Executive takes 16 (legal +
    project), the Engineer 12; 2 are Independent Engineer items and stay unassigned by
    design. Do not route them to an account of another company.
33. **Due dates — BUILT 2026-09-26 (migration 057); now waiting on the clients.** Assignment
    creates a request; the **assignee alone** accepts it by committing to a date
    (`POST /bankability/evidence/commit`, today or later — not even a platform admin can
    commit for someone). Until then the item shows **"Not yet committed"**. Reassignment
    clears the date (it was the previous person's word). Moving a date is allowed and
    audited (`old_due_date`/`new_due_date`), so a slip stays visible. State is derived at
    read time in `app/core/evidence_due_dates.py` — UNASSIGNED / NOT_COMMITTED / COMMITTED /
    OVERDUE / DONE — so overdue never goes stale. Gate headers show "N overdue" and "N not
    yet committed"; `GET /evidence/assigned-to-me` sorts overdue first. Stage Gates has
    **Commit to a date** (assignee only) and **Reassign** (owner company or GEX admin; list
    from `GET /evidence/assignable`, owner's ACTIVE accounts only). The platform never
    defaults a date — **no request in the database has one yet**, and none was entered on a
    client's behalf during verification. Tests: `test_evidence_due_dates.py` (10),
    `test_evidence_assignment.py` (now 24); assignee-only and overdue boundary
    negative-verified. `fetchAPI` now shows a structured refusal's message instead of
    "[object Object]".

### Evidence rules 4.0.0 — built 2026-09-27/28

34. **Rules 4.0.0 — BUILT (engine + platform + migration 058); now waiting on the
    clients' commitment terms.** Decision: `docs/GEX-Twelve-Gates-Multi-Party-Review.docx`.
    Still twelve gates. Financing scope moved from gates to items (23 lender-protection
    items; G6 and G8 waived whole for balance-sheet funding, G4/G7/G10 no longer are);
    offtake ladder O0–O7 and EPC ladder E0–E6, derived — never entered; ten coherence
    checks C1–C10 (a FAIL blocks its gate; "data missing" blocks nothing and is never a
    pass); post-FID triggers T1–T3; lenses PRODUCER/OFFTAKER/CAPITAL/CERTIFIER on every
    item; OFFTAKER persona; 16 items added (77 → 93); G1 renamed "Power, Utilities &
    Technology Basis"; each state also names the commitment it makes possible. Engine
    detail in `../gex_pf_engine/README.md`.
    - **Commitment cards** (`offtake`, `epc`, `schedule`, `supply`, `model`): migration
      **058** — `commitment_terms` (runtime may SELECT/INSERT/UPDATE, not DELETE) and
      `commitment_terms_events` (SELECT/INSERT only), both under FORCED RLS. Validation in
      `app/core/commitment_terms.py` against `COMMITMENT_CARD_FIELDS`, which
      `test_gate_registries_agree.py` holds identical to the engine's. `GET/PUT
      /bankability/terms` (owner company or GEX admin writes; `can_edit` tells the screen),
      `GET /bankability/terms/events`. Every evaluation sends the cards as `terms`.
    - **Screen:** Stage Gates shows the state's commitment label, the O/E levels with the
      engine's definitions and reasons (read from `/bankability/rules`, not duplicated), a
      coherence summary, a "View as" lens filter, per-gate commitment chips, "Also
      blocked" reasons, a coherence/trigger section, and a spec-driven **Commitment terms**
      editor. Not-applicable items now render as "Not required" — before this they fell
      back to Not Started with a **Start** button.
    - **State of the data:** no card has been entered for any project (0 rows), so every
      project reads O0/E0 and 9 of the 10 checks are NOT_EVALUABLE. Nothing was entered
      on a client's behalf during verification.
    - **Tests:** engine `test_bankability_gates.py` 86; platform
      `test_commitment_terms.py` 25, `test_commitment_terms_pg.py` 7, registry agreement
      +5; every new guard mutation-tested. Full suite 2026-09-28: **844 pass, 17 skip,
      0 fail** with both exports.
    - **Open:** reconcile the offtake card with `OfftakeContract` (registered in
      `COMMITMENT_OBJECT_ROLES` as a projection, not a contract register); the cards are
      the producer's statement and are not checked against the documents.
35. **Six requests on items that do not apply — found and contained 2026-09-28.** The
    2026-09-26 conversion (item 32) raised requests without an applicability check,
    because the platform had no copy of the engine's power-model scoping: four ask
    HamburgOne people (Mark Puntz ×3, Lisa Friedrich ×1) for behind-the-meter generation
    evidence on a grid-connected plant; two unassigned ones ask Rattlesnake Gap (off-grid)
    for grid-connection evidence. They inflated "not yet committed" (G1 showed 16 against
    15 applicable items). Now: `EVIDENCE_POWER_MODELS` + `inapplicability()` mirror the
    engine (agreement test covers every item under every premise); such requests are not
    counted, cannot be committed to (409), cannot be (re)assigned (422
    `ITEM_NOT_APPLICABLE`), are listed apart under `not_required` in `assigned-to-me`, and
    `--assign-open` skips them. The owner may **withdraw** one (button on the row). **The
    six rows are untouched** — withdrawing is the owner's call, not done on their behalf.
37. **Rules 4.1.0 — BUILT 2026-09-29.** Evidence: `docs/master-reconciliation/00_market_evidence_gate_timing.md`
    (dated deals 2022–2026, EU Hydrogen Bank IF25 terms). COMMERCIALLY_PLAUSIBLE now needs offtake
    terms (O2+) for ≥ 60 % of planned output (new offtake-card field `planned_output_tonnes_per_year`;
    EPC guaranteed capacity as fallback; unknown fails closed). Capital decisions carry labels
    (`CAPITAL_TYPE_LABELS`, mirrored in the platform registry, agreement-tested);
    `SENIOR_DEBT_COMMITMENT` reads "Senior Debt Credit Approval (conditional)", CREDIT_APPROVED
    "Credit approved — conditional until financial close". The finance screen's senior-debt text
    no longer claims G6/G7/G9 gate it or that insurance is bound at G7. Engine tests 96 (7
    mutations caught); registry agreement +1 (2 mutations caught). Checked on the live screen
    after the 30 Sep rebuild (item 38): the G8 chip reads "Senior Debt Credit Approval
    (conditional)" and an offtake without a card reads "O0 · coverage not recorded".
38. **The development PostgreSQL database was reset — 28 Sep 2026, 16:14 local.** `gex-demo-compose.yml`
    was edited at 16:10 and the compose project `files` (postgres, redis, backend, pf_engine,
    frontend) recreated at 16:14 with a new `files_postgres_data` volume; the container log shows a
    fresh `initdb`. The database now has one public table, no migration history and no `gex_app`
    role, so the backend refuses to start ("password authentication failed" — server detail: role
    does not exist). Who ran it is not recorded. No full `pg_dump` exists (`files/db_backups` holds
    an evidence-only dump and a SQLite copy, both 26 Sep).

    **REBUILT 2026-09-30 on JML's instruction.** Backend starts; **844 pass, 18 skip, 0 fail**
    (the pre-reset baseline was 844 pass / 17 skip). Schema is identical to the pre-reset
    measurement — 120 tables, 113 FORCED RLS, head 058 — and RLS reproduces the documented
    invariant exactly: `projects` returns 14 as `PLATFORM_ADMIN`, **4** as `etfuels_sa`, 0 with
    no tenant context, against a BYPASSRLS ground truth of 14. **103 of 114** tables match
    `backend/db_backups/pg_after_kyc.json` (23 Sep) row for row. The rebuild order and its four
    traps are written up in `.claude/CLAUDE.md` — read that before rebuilding again.

    **Recovery option (a) was never available, and the claim above was wrong.** `Docker.raw` is
    **excluded from Time Machine** (Docker Desktop sets the exclusion; `tmutil isexcluded` confirms),
    so no backup of the volume has ever existed. The `Sept-26-Time-machine` destination is also
    unattached. Nobody should spend time on that route again — **`pg_dump` is the only backup that
    works for this database.** There is still no scheduled one; that remains open.

    **What the rebuild cost, measured not estimated.** Eight tables sit below the 23 Sep baseline:
    `entitlement_audit` −145, `finance_entitlements` −38, `auth_user_project_roles` −6,
    `project_context` −3, `project_context_events` −4, `project_currency` −1, `auth_users` −1,
    and `bankability_evidence` 127→85. **The evidence number is not a loss** — it is the 26 Sep
    conversion (§9), and 85 open requests is the correct current state. Three tables sit *above*
    it, because SQLite had run ahead of PostgreSQL: `evidence_events` 17→176, `mass_balance_lots`
    68→72, `bankability_snapshots` 9→10. That divergence is now in the system of record.

    **The one account lost is `u_admin`** — the unattributed admin row this file and
    `.claude/CLAUDE.md` both flagged as satisfying none of the four activation requirements and
    being invisible to the `SEED_GRANDFATHERED` search. It was PostgreSQL-only and is gone.
    **Three platform admins survive** (`admin_greenearthx_com`, `t-marwenc_greenearthx_com`,
    `t-mohamedk_greenearthx_com`, all ACTIVE), so nothing is locked out. Recreating `u_admin`
    would restore the separation-of-duties hole — **JML's call whether it comes back at all, and
    if so through activation rather than an unmarked insert.**

    **`bankability_evidence_archive` is empty and cannot be refilled** from either local source
    (absent from SQLite, and `evidence_before_055_2026-09-26.sql` predates 055). That dump *does*
    hold the pre-conversion 127 rows if the archive is ever wanted back — but §9 forbids restoring
    them to the live table, and they were invented, so this is a lost audit trail of invented rows,
    not lost client data. `test_evidence_history_pg.py:69` is the 18th skip because of it.

    **Two routes 500 against the rebuilt database, both pre-existing, neither caused by the reset:**
    `capital_bridge.py:1255` (`list_projects_for_user`) selects `p.id` and `p.stage` from
    `projects`, which are the SQLite column names migration 033 retired — PostgreSQL has
    `project_id` and `status`; and `/api/v1/ecosystem/projects`, which is `ecosystem_store`'s
    unguarded SQLite path whose tables exist in neither store (already documented as dormant).
    Do not naively "fix" either without reading §4 on the projects collision.

    **The first is FIXED 2026-09-30, and it was worse than one route.** `p.stage` has never
    been a column of `projects` in EITHER shape: the retired SQLite one had `phase`, measured
    from `data/db_backups/gex_platform.pre-projects-collision.20260807.db`, and `p.id` was
    `project_id` there too. So this was not code written against the old shape and left
    behind — it was written against a shape that has never existed, and has returned 500
    since the day it was added. That is why it has no frontend caller and had no test.

    **Four sites in `capital_bridge.py`, eleven routes.** Besides the two listings
    (`list_projects_for_user`, `list_projects_for_company`), `WHERE id=?` sat in
    `get_full_project` and in `_project_exists` — the FK gate **eight write routes** call, so
    all eight raised `column "id" does not exist` instead of validating a project id, and
    could never reach their 404 branch. Measured after the fix on a real instance:
    `users/{id}/projects` 200 with 4 and 5 rows for two seeded users, `projects/{id}/full`
    200 on a real id and **404** on a bogus one, `capital-stack/bootstrap-defaults` **404**
    on a bogus one.

    **Keys are the canonical `project_id`/`status`, not aliases back to `id`/`stage`.** Swept
    first: zero hits in `frontend/src`, zero in `backend/tests`, so there is no contract to
    keep. `get_full_project` in the same module already returns the canonical names via
    `SELECT *`, and `stage` is a word this platform's project vocabulary does not use —
    `VisibleProject` carries `status` and `phase`. Aliasing would have kept a retired
    vocabulary alive in a JSON contract nobody depends on.

    **RLS contains the route, and that was measured, not assumed.** It takes `user_id` from
    the path and authorizes nothing, so the database filter IS the access control — the same
    shape as the project-activity hole fixed 2026-09-24. `auth_user_project_roles` carries no
    RLS; the INNER JOIN to `projects` is what contains the read. As tenant `etfuels_sa`,
    asking for an Allianz user's projects returns **0 rows**; with no tenant bound, **0 rows**
    and a 200, not a 500.

    **The real finding is the coverage, not the columns.** 844 tests passed while eleven
    routes were dead. `tests/test_capital_bridge_projects_routes.py` (9 tests) now pins them,
    negative-verified: restoring the original file fails **7 of 9**. Two of the nine
    deliberately pass either way — they assert PostgreSQL still REJECTS `p.id` and `p.stage`,
    so the file cannot go quietly green if `projects` ever grows those columns.

    **The sweep found no second instance.** Every raw query against `projects` across
    `backend/app/` was checked: `tenant_context.py`, `tenant_admin.py`, `projects_store.py`,
    `adjacency.py` and `lineage.py` all use `project_id` correctly. `contracts_sqlite.py`'s
    `p.id` joins `capacities`, which genuinely has an `id` column. `routes_projects.py:854`
    is a Pydantic attribute, not SQL. `capital_bridge.py` was the only offender.
36. **Two engine API tests have failed since 2026-09-09, unrelated to gates.**
    `test_gabillon.py::test_curve_api_contracts_include_provenance_and_memory` and
    `test_offtake.py::test_offtake_api_reuses_cached_calibration` get **401**: `main.py`
    put every endpoint behind the GEX JWT guard after these tests were last touched, and
    they send no token. Engine suite otherwise 209 pass. **FIXED 2026-09-28** by a separate
    session: `tests/conftest.py` signs real service tokens (the guard is untouched) and
    `pf_engine/auth/gex_jwt.py` now fails closed in production without a trusted key
    (`tests/test_gex_jwt_fail_closed.py`). Engine suite 239 pass on 2026-09-29.
39. **GREENEARTHX's implementation-status audit — re-verified 2026-09-30 and moved here.** The
    section "The Future and where the current project development is now" and its "Bottom
    Line" (GREENEARTHX v4.5, status as of v4.2, 14 May 2026) contradicted itself — rows marked
    IMPLEMENTED with the note "Not built" — and the tree. Decision D9
    (`docs/master-reconciliation/04_decisions_for_JML.md`) moves build status out of the spec;
    the GREENEARTHX redline deletes the section as a tracked change and points here.
    Re-verified by reading the tree, not by running anything:

    | Claim in GREENEARTHX | Verified 2026-09-30 |
    |---|---|
    | "PostgreSQL migrations DEFERRED" | **False.** Alembic chain to head 059 (`backend/alembic/versions/059_append_only_privileges_restored.py`); 120 tables, 113 FORCED RLS (`.claude/CLAUDE.md`). |
    | Engine path `../gex_pf_engine/backend/app/core/` | **Stale.** Package renamed `app` → `pf_engine` on 2026-09-09: `../gex_pf_engine/backend/pf_engine/core/`. GREENEARTHX's own "Namespace correction (v4.3)" describes `deal_engine`, a different service. |
    | `adjacency.py` "Not built … none exist anywhere in gex_pf_engine" | **False.** `pf_engine/core/adjacency.py` defines `compute_proximity_matrix`, `density_score`, `cohort_benchmark`, `compute_weighted_proximity`. |
    | Adjacency backend "complete (nightly computation + cache + benchmark endpoint)" | **Exists, broken on PostgreSQL.** `api/v1/adjacency.py` has `POST /compute-all` and `GET /{project_id}/benchmark`, but opens SQLite four times with no backend switch, reading PostgreSQL-owned `adjacency_cache`, `evidence_ledger`, `projects`. |
    | `lineage.py` "does not exist", and elsewhere "complete (8-source DB fan-out)" | **Exists (443 lines), broken on PostgreSQL.** Queries `offers`, `capital_bridge`, `projects`, `development_packages`, `sovereign_instruments`, `tokens`, `evidence_ledger`, `carbon_attribution_events` through three unguarded `sqlite3.connect` calls. |
    | WACC "in capital_bridge.py" | **True.** `blended_debt_wacc`, `project_wacc`, `all_commercial_wacc` are computed in `api/v1/capital_bridge.py`; `catalytic_ratio` is in the engine (`cfads.py`, `debt/tranche.py`). |
    | DFI hierarchy as tranche subtypes (`CONCESSIONAL_EIB` …) | **Not built.** `TrancheType` is SENIOR, JUNIOR, MEZZANINE, GREEN_BOND, ESG_LINKED, CONCESSIONAL, CONCESSIONAL_FIRST_LOSS; DFIs via `DFIProvider`, which now includes BPI and DFC. |
    | Decomposed certainty stack "RESOLVED in v4.2" | **True in the platform registry engine** (`app/core/bankability_engine.py`: `CertaintyDimension`, `certainty_stack` computed from gate results), rendered by `DecomposedCertaintyStack.tsx` on `BankabilityScorePage.tsx`. The runtime engine (:8001) has no sub-scores; its readout is gate determinations, O/E levels and coherence results. D4: scores are derived, never typed, and none appear in client material. |
    | ABAC "15" vs "16" actor types | **15** members in `ActorType` (`app/core/abac.py`). |
    | Verification taxonomy | `app/core/verification.py` implements UNVERIFIED / SUBMITTED / CONFIRMED / AUDITED. The master glossary maps it to gate status and maturity. |
    | Development-package fields | `currency`, `fx_hedge_id`, `aace_class_history`, `personnel_breakdown`, `verification_state` now present in `development_packages.py`; `cost_p50` is still `cost_amount`. |
    | Token schema | `tokens_sqlite.py` carries `provenance_hash`, `lifecycle_state`, `mass_balance_lot_id`. |
    | The nine "missing entities" | All present as `api/v1/` modules (`drawdown_schedule`, `dfi_criteria`, `mass_balance`, `settlement_events`, `carbon_attribution`, `sovereign_instruments`, `evidence_ledger`, plus `spend_wave`, `capital_bridge`). Which of them read the switched backend is not re-checked here; `.claude/CLAUDE.md` lists the unguarded readers. |
    | Seven design primitives; "remaining: DFI dashboard frontend" | All seven exist in `frontend/src/components/primitives/`; `features/finance/DFIDashboard.tsx` exists, so "remaining" is false. "Fully connected to live backend data" is false for Adjacency and Lineage (above). |
    | `pre_cod_metrics.py` | `api/v1/pre_cod_metrics.py` (875 lines). Two metric sets exist (this and Bridge v6's) with conflicting thresholds; none is canonical (D11). |
    | "~90% of the documented specification"; Decision Twin "8 schemes incl. SOVEREIGN_ESG with debt-for-nature"; "all 5 core modules have FX handling" | **Not re-verified.** No single measure exists for the first; the other two need a code read beyond this pass. Treat as unverified. |
40. **Documents reconciliation — 2026-09-29/30.** Deliverables in `docs/master-reconciliation/`
    (`00`–`05` notes, glossary, engine export, redlines). JML accepted decisions D1–D17 on 29 Sep.
    The master redline (`GEX-Gates-Master_v2_redline.docx`) was built 30 Sep 11:37 and validated
    (XSD, IDs, relationships, comment markers; 1,316 changes, all tracked, author Claude). **JML
    then edited it in Word with Track Changes off** (saved 14:38; §1 only so far). That file is
    now JML's working copy: never rebuild over it or regenerate it. Any further change goes on
    top of JML's latest save as a tracked edit, after JML has finished a pass. The build scripts
    are copied to `docs/master-reconciliation/tools/`. **Superseded 21–22 Oct (item 44):** the
    accepted result is `docs/GEX-12Gates-Multi-Party-Review_Good.docx`; the master redline now
    exists only in `co-work`'s git history.
41. **Producers can verify their own evidence — Critical, found 2026-09-30 (adversarial Attack A).**
    `POST /bankability/evidence` with `new_status=VERIFIED` is classified as WRITE, not VERIFY
    (`abac_middleware.py:113–121` checks the URL for "/verify"), so R5's certifier-only verify
    rule never runs and every gate owner can verify its own claims. The evidence-event actor is
    the body's `submitted_by`, so it can be spoofed, and VERIFIED needs no document on the server.
    Reproduced twice in a throwaway store: 22 self-verified writes moved a TEST project to
    TECHNICALLY_PLAUSIBLE with Grants & TA and Seed / VC eligible, and 5 more lifted the EPC to E4.
    Report and re-runnable harness: `docs/adversarial/`. The harness never touches PostgreSQL:
    its `DATABASE_URL` cannot connect. First-use comprehension script for the gates:
    `docs/usability/`.

    **FIXED 2026-10-01, and the reviewer table SETTLED 2026-10-02.** JML: "each may verify the
    relevant and linked gate: the certifier, the independent engineer, the lenders' adviser, the
    insurer." `abac.REVIEWER_GATES` — certifier G2, G11; independent engineer G0, G1, G3, G5, G6,
    G11; lenders' adviser G0, G4, G7, G8, G9, G10; insurer G7. **The GEX desk-review role built on
    10-01 was removed on 10-02** (`GEX_REVIEWER` gone from the enum, `GATE_VISIBILITY` and
    `ACTOR_CLASS_MAP`): all four reviewers are independent of GEX, which enforces the standard and
    verifies nothing itself. 898 pass / 18 skip, unchanged by the swap; widening the insurer to G10
    fails 2 tests. Consequences, both deliberate and recorded in `.claude/CLAUDE.md`: G0, G1 and G3
    now need an appointed independent engineer, and insurance *bound* at G10 stays with the
    lenders' adviser because gate-level scope cannot isolate that one item.

    **2026-10-21, option (b) (JML):** at the early gates the capital provider's own reviewer
    verifies the gate that makes its decision eligible — `GRANT_ASSESSOR` G0,
    `SEED_INVESTOR_ADVISER` G1, `STRATEGIC_INVESTOR_ADVISER` G3. 962 pass / 18 skip.
    **Appointment flow BUILT the same day (JML: GEX staff appoint, on instruction).** Routes
    `/api/v1/projects/{id}/reviewers` (POST / DELETE / GET), policy in
    `app/core/reviewer_appointments.py`, "Who verifies" panel on Gates & Evidence; details in
    `.claude/CLAUDE.md`. 987 pass / 18 skip. Verified live on a second backend (:8010, launch.json
    `backend-verify` / `frontend-verify`) with reads and refusals only — no live appointment was
    made, so none exists yet. Found on the way, both flagged as their own tasks:
    (1) `POST /auth/refresh` reads accounts from the stale SQLite file (19 rows vs 23 in
    PostgreSQL) and checks `is_active`, not `account_state`; (2) the RLS policy on
    `project_access` has no separate write check, so a tenant can insert a row granting itself
    access to any project — reproduced as Madrid2 on HamburgOne (47 evidence rows readable),
    rolled back. Not reachable through an app route; needs migration 062.
    **Both FIXED the same evening.** (1) refresh loads the account through
    `auth.load_user_for_refresh` under the sign-in vetting rule and revokes all refresh tokens
    on refusal. (2) Migration 062: only PLATFORM_ADMIN writes `project_access`; reads unchanged.
    Head 062; 999 pass / 18 skip; backup taken after the migration.

    **The comprehension-test fixture is loaded — 2026-10-02, JML's route (a labelled TEST project,
    not a restored copy).** `proj_TEST_gates_reference`, owner `hamburgone_com`, 32 synthetic
    VERIFIED rows and three commitment cards, written by
    `backend/scripts/load_comprehension_test_project.py` (`--verify` / `--execute` / `--remove`).
    Live API and engine both return Appendix B exactly: Technically plausible, G0–G3 satisfied,
    three capital decisions eligible, offtake O2 at 55% coverage, EPC E3, C6 failing, 33.7%
    complete. Tenant isolation holds (Madrid2 gets 403). Participants sign in as a HamburgOne
    account whatever their profession — a runtime project grants nothing to other companies at the
    ABAC level, so the bank and insurer demo accounts cannot open it. Suite 899 pass / 18 skip.
    Details and the parity exception: `.claude/CLAUDE.md`.
42. **The gate screens tell the engine's story — DONE 30 Sep 2026 (item 28, on four screens).**
    Inventory, decision and results: `docs/master-reconciliation/06_gate_screens_inventory.md`.
    /projects, State & Blockers (`/bankability-scores`, was "Status & Blockers") and Capital
    Eligibility (`/finance/bankability`, was "Project Readiness") read one cached engine readout,
    `GET /bankability/projects/{id}/bankability/EXECUTIVE`, which runs the engine and **writes
    nothing**. Gates & Evidence (`/stage-gates`, was "Verification Status") keeps `/evaluate`. Each
    shows "Declared phase · Evidenced state · n of m verified". Removed from client view: the
    BB/63.2 letter rating, every score, the random trajectory, the typed deal-killer plan, the
    fixture capital figures, the pre-COD panel (D11) and the port/proxy messages. `fetchAPI` errors
    now carry `status`; gate screens show 4xx reasons, never 5xx internals. 22 tests, ten
    deliberate breaks all caught. **Still open:** `useVisibleProjects.ts:89` still merges the
    fixture block for 15 other files and for `useGateAccess` screen locks; `deal_killers.py` and
    `project_truth.py` still feed TaskRouter, Evidence Hierarchy and the IC-pack export check. Also
    found: HamburgOne's two runtime projects lost their project context in the 28 Sep reset, so the
    engine evaluates them with no premise. These screens show the engine faithfully, so item 41
    matters here: a self-verified item moves the state they display.

43. **The development PostgreSQL database was lost a second time. It was RESTORED FROM DUMP on
    13 Oct 2026, on JML's instruction.** The backend failed at startup in `init_auth_db()` with
    `server closed the connection unexpectedly` on :55432. This was not the familiar "container
    stopped" case. `files-postgres-1` was **absent** from `docker ps -a`, and the
    `files_postgres_data` volume was gone. The only volumes left were two anonymous 4 KB ones
    holding no data. Only `gex-pg-forward` survived. Docker had started at 09:45 UTC that day,
    and the 12:30 scheduled backup failed with code 12 ("container does not exist"). **What
    removed them is not recorded.** The candidates are a Docker Desktop reset,
    `compose down -v`, or a prune with `--volumes`. That is the open question this item leaves.

    **Restored from `files/db_backups/daily/gex_platform_2026-10-12_1236.dump`.** That was the
    newest of 7 daily and 3 weekly dumps, verified by a full read. **Writes made after
    12 Oct 12:36 local are lost.** Unlike item 38, nothing was rebuilt. No Alembic, no copiers
    and no registry scripts ran, because the dump carries schema and rows together. The
    restore took about 5 minutes against two days for the 30 Sep rebuild. The scheduled
    `pg_dump` is what made the difference. The exact sequence is in `.claude/CLAUDE.md` under
    *Backups*, including one trap: a `-Fc` dump does not carry `GRANT CONNECT ON DATABASE` or
    `ALTER DATABASE ... SET app.current_company_id`, so both must be re-applied after the
    promotion.

    Measured after the restore: **120** tables, **113** FORCED RLS, head **059**, **20,080**
    rows. Append-only grants are correct: archive `SELECT`, `evidence_events` and
    `commitment_terms_events` `INSERT, SELECT`. `gex_app` is not a superuser, and `projects`
    returns 0 with no tenant context. `/health` returns 200. A fresh dump,
    `gex_platform_2026-10-13_1240.dump`, verified clean. Test suite with both URLs exported:
    **899 pass, 18 skip, 0 fail**. That is identical to the 2 Oct run. All 18 skip reasons were
    read with `-rs`, and none is "database unreachable" or "variable unexported".

    Counts moved since `.claude/CLAUDE.md` last measured them. These are not restore damage:
    they are what the 12 Oct dump holds. `projects` **16**: the FortaVerde fixture
    `proj_TEST_fortaverde_pecem` was loaded 12 Oct. `auth_users` **23**: 17 grandfathered,
    4 `MANUAL_ADMIN_GRANT`, and 2 FortaVerde stand-ins (one ACTIVE by `--activate`, one
    PENDING). `bankability_evidence` is **117**, unchanged. **`u_admin` is absent from the
    dump.** Nothing records when it went. Both files are updated to match.

44. **The gate documents brought to rules 4.1.0 — 21–22 Oct 2026, on JML's instructions.** Three
    documents remain, all clean (no tracked changes), identical in the working folder and in
    `co-work` (last commit `ab9d651`):

    | Document (`docs/`) | Role | State |
    |---|---|---|
    | `GEX-12Gates-Multi-Party-Review_Good.docx` | **The reference.** Front section + Annex C state the rules; §§1–9 keep the 27 Sep challenge as the reasoning | Rules re-verified against the engine 21 Oct. Added: "Who verifies" (all seven reviewer roles), "Open challenges" (§9). Removed: JML's second §11 (it contradicted §10). Fixed: stale §1.2/§2 facts, fused text from rejected tracked changes, the 8–10% guarantee figure, four body paragraphs styled as headings. TOC rebuilt (48 entries); §2's G1 heading renamed |
    | `WHY  12GATES-easily explained.docx` | Client onboarding guide, the plain-language version | Was rules 3.0.0. Evidence tables generated from the engine's `EVIDENCE_META` (93 items: 20 added, 14 marked project finance only, two G10 rows replaced); "Confirmed by" = `abac.REVIEWER_GATES` (G5 is the independent engineer, not the owner's engineer); new §5 on the O/E ladders, coherence checks and triggers; TOC added on page 2 |
    | `GEX-Why-Twelve-Gates-Prospect-Brief.docx` | One-page sales brief | Technology basis, independent verification, the two waivable gates (G6, G8), version 4.1.0 |

    **Archived** (outside git, `files/docs/archive/*_SUPERSEDED.docx`, recorded in
    `files/docs/README.md`): the three rules-3.0.0 documents `GEX-Bankability-12Gates`,
    `GEX-Twelve-Bankability-Gates` and `GEX-Why-Twelve-Gates` (the guide's 3.0.0 original).
    `co-work` commit `f86827b` removed ten Word files that were pending deletion;
    `GEX-Gates-Master_v2_redline.docx` (item 40), `…_JML modified.docx` and `WHY TWELVE GATES.docx`
    now exist only in git history. That commit's message calls them all superseded — wrong for the
    prospect brief, which `e5e653f` brought back.

    **How it was done, for the next rules version.** Every text change went in as a tracked change
    (author Claude) via `master-reconciliation/tools/redline_lib.py`, was validated with the docx
    skill's `validate.py`, and was accepted only on JML's word. Neither Word nor LibreOffice is
    on this machine, so acceptance used `tools/accept_all.py`, checked by comparing the text with
    `accepted_view.py`. Tables of contents were rebuilt in the XML with the field marked dirty:
    **page numbers appear only when Word updates the field** (accept its prompt, or right-click
    → Update Field). Before installing any edit, the target's hash was checked against the
    version the edit was built from, and the original was backed up.

    **Watch for Word.** Word held the review open from 21 Oct 15:44 with the pre-edit version.
    Saving from such a window silently overwrites every later edit. Ask JML to close it without
    saving before trusting the file on disk.


45. **The market chain runs end to end — 23 Oct 2026 (gap register P0, G-01 to G-05).** JML's
    decisions the same day: listings are **anonymised** for every vetted company (names and
    terms revealed to the two parties once matched), and a match needs **both** parties to
    accept. Migrations **063** (`rfqs`, `contracts`, match snapshot and two-sided acceptance,
    `tokens.holder_company_id`, buyer-readable settlements) and **064** (trading-book tenancy)
    are applied; head **064**, 125 tables, 118 FORCED. Backup taken first
    (`gex_platform_2026-10-23_1336.dump`).

    `app/core/market_engine.py` performs every cross-company step on a PLATFORM_ADMIN market
    connection, **after** authorising the Party from the token — a new, justified PLATFORM_ADMIN
    site. GEX (`is_platform_admin`) trades nothing (`GEX_DOES_NOT_TRADE`). Routes:
    `/api/v1/market/*`; the older `/marketplace`, `/matching`, `/contracts`, `/trader/rfqs` and
    `/settlements` routes delegate to it. Token: listing MINTED→RESERVED, both accept →MATCHED,
    payee confirms →SETTLED with title to the buyer.

    The trading book was bound to the **SQLite file** while its tables lived under 036's
    admin-only lock in PostgreSQL; both stores held 0 rows. It now runs on PostgreSQL as
    `gex_app` when `MARKET_DB_BACKEND=postgres`, with the tenant set on **every** transaction
    (`main.py`, SQLAlchemy `after_begin`), because a handler's commit ends SET LOCAL. 064's first
    draft recursed (contract ↔ link policies); the lookups are SECURITY DEFINER functions with a
    pinned search_path, 036's pattern.

    Frontend: Market Discovery and RFQs replace placeholders; five screens lost their sample
    arrays. GreenMesh feedstock pooling has no backend — its tab now says so.

    Tests: backend **1031 pass, 18 skip, 0 fail** (999 + 8 + 4 + 6 + 2 − 1 + 7 + 6); frontend
    224 pass, 1 FAIL — `EconomicsSnapshotPage.test.tsx` "surfaces a transport failure", which
    fails identically with the pushed `api.ts` and is not caused by this work. Every new guard was
    negative-verified. The live database was left with 0 rows in every market table.

    **Later the same day, JML: RFQs (and the chain) stay in PostgreSQL only.** The engine's
    SQLite fallback and `core/market_schema.py` are gone; with `MARKET_DB_BACKEND` not
    `postgres` the engine refuses (`MARKET_REQUIRES_POSTGRES`). `test_market_chain.py` now runs
    in a throwaway database `gex_test_market`, migrated from scratch and dropped afterwards
    (`pg_support.throwaway_pg_database`). Building it exposed a rebuild defect: 036 creates
    `tb_*` from the CURRENT models, so 064's ADD COLUMN failed on a fresh database — 064 now adds
    only what is missing. A fresh build matches live except PostGIS's `spatial_ref_sys`.
    Backend **1033 pass, 18 skip, 0 fail** at that point.

    **Then, JML: PostgreSQL only everywhere in the market and trading area.** Capacities,
    tokens, offers, RFQs, matching and buyer mandates, contracts, settlements, carbon
    attribution, chain of custody and the trading book: every SQLite branch, runtime CREATE
    TABLE and PRAGMA is gone. Each module calls `db_backend.require_postgres()`;
    `PostgresRequired` becomes **503 POSTGRES_REQUIRED** (handler in `main.py`). `init_db()` of
    settlement, carbon attribution and chain of custody is a no-op, so startup never fails on a
    switch. The trading book's tenant-scoped session moved into
    `trading_book.api.tenant_session_dependency`, used by `main.py` and its test alike. Deleted:
    the legacy `RFQ` ORM model (and `Match.rfq_id`) in `app/db/models.py`, and the unused
    `app/services/matching_engine.py` that imported it.
    Tests: `conftest.pg_store`, the PostgreSQL counterpart of `isolated_store`, builds ONE
    throwaway database per session (`gex_test_suite`, migrated from scratch, dropped at the end)
    and pins every switch to postgres. `test_market_chain`, `test_trading_book_api` and
    `test_chain_of_custody` use it; the last two now pass through RLS as the owning tenant
    (TEST tenants and projects exist only in the throwaway database). Guards: no `sqlite3` in 12
    modules, each refuses without PostgreSQL — both negative-verified.
    **Backend 1051 pass, 18 skip, 0 fail** (same 18 skips). Dev database unchanged.

    **Not yet PostgreSQL-only:** the other slices (auth, evidence, domain tail beyond these
    three modules, workspace, …). Their switches read `postgres`, but their SQLite branches
    remain. Retiring them is §11 action 5.

46. **Trading-book revision: JML's decisions and step M1 — 23 Oct 2026.** Spec:
    `Downloads/GEX_Trading_Book_Revision_Claude_Code_Spec.md` (from Claude chat; §0 report given
    first). **Decisions:**
    1. **One contract model** — the spec's terms → legs → flows. The market engine moves onto
       it (M3/M4); offers, rfqs, matches and the market `contracts` are replaced, not kept beside
       it. Their `double precision` prices go with them (D8: Numeric).
    2. **No automated matching** until counsel confirms GEX would not be a trading venue.
       `MARKET_AUTO_MATCHING` (config, default off): `/matching/run` → 409
       `AUTO_MATCHING_SUSPENDED`. Matching is bilateral — a company proposes one of its own RFQs
       or listings to a specific counterpart (`POST /api/v1/market/matches`; GEX's score is
       recorded, no longer a gate); it binds only when both accept. Market Discovery shows
       "Propose a match" per listing; the Matching page only shows the company's matches.
    3. **Contract token** separate from the capacity token, referring to the capacity tokens it
       delivers (`tb_contract_version_token`), minted at **confirmed**. **One token per contract
       for its whole life (JML, later the same day): a change is a new contract version AND a
       modification of that same token, never a new token.** `tb_contract.token_ref` is unique
       and fixed once set; each version's `token_event_ref` records the token operation that
       carried its terms hash (v1 the mint, later versions a modification) and is fixed once
       written; a later version cannot record a modification before the contract has a token
       (triggers `tb_refuse_token_rewrite`, `tb_require_contract_token`). 065 was rolled back,
       amended and re-applied for this (tables empty; backup `…_2254.dump`). Technology and
       issuer are still open, so both references stay NULL; the terms hash is computed regardless.
    4. Default `quantity_basis` = **delivered**; capacity counts as **long** product for the
       producer, demand as **short** for the offtaker (in `v_position` at M5); order visibility
       = **platform**, anonymised (decided earlier the same day).

    **M1 done — migration 065** (additive; backup `gex_platform_2026-10-23_1721.dump` first;
    round-tripped; head **065**, **137** tables, **130** FORCED). New: `tb_commodity` (5 seeded,
    mapped to the market's molecule codes: EMEOH↔e-Methanol, ENG↔e-NG, H2, NH3, SAF),
    `tb_counterparty_restriction`, `tb_terms`, `tb_leg`, `tb_flow` (CHECKs per flow type),
    `tb_rfq`, `tb_order`, `tb_order_invitee`, `tb_order_event` (append-only), `tb_fill`,
    `tb_contract_version`, `tb_contract_version_token`; views `v_party_leg`, `v_party_flow`,
    `v_position` (security_invoker, so RLS applies; "planned" joins at M5). Touched:
    `tb_counterparty.company_id` (resolves payer/receiver to a tenant), `tb_index_definition.commodity_id`,
    and `tb_contract` — legacy columns nullable, new columns `contract_ref`, `trade_status` (the
    spec's `status`; the legacy enum keeps that name until M6), `verification_state`, `fill_id`,
    and a CHECK that a row is wholly legacy or wholly `contract_type = 'terms'`. Frozen terms are
    immutable for every role (trigger; its first version errored on legs and flows instead of
    refusing — caught by T12). Code: `trading_book/{conventions,terms,validation,canonical,pricing}.py`.
    Also fixed: 036 built `tb_*` from the CURRENT models, so any new model would be created early
    on a rebuild and collide with its migration; 036 now builds only its original eight tables.

    Tests: `test_trading_terms.py` (25: T01 every rule V01–V13 failing and passing, T02, T03,
    T04, T05, T06, T07, T08, V13 for T09), `test_trading_terms_pg.py` (8: T12, order privacy,
    contract visible to both parties only, the signed derived book, append-only trail, one-model
    CHECK, an amendment modifies the same token, the token is never replaced or shared). T12 and
    the token rule negative-verified. **Backend 1084 pass, 18 skip, 0 fail.**

    **Next: M2** (JTI → terms converter, idempotent with `--dry-run`; nothing to convert today),
    **M3** (order/RFQ API and acceptance in one transaction — `SELECT … FOR UPDATE`, T09, T11,
    T14; move the market engine and its token steps onto it), **M4** (cashflow engine dispatch
    on `flow_type`, `as_party`, the Rotterdam TEST fixture, T10), **M5** (capacities columns;
    `asset_id` cannot be backfilled — `tb_asset` is empty), **M6** (drop JTI). Four-eye
    `TRADE_CONFIRM` does not exist yet in `core/wae.py`; it is M3's.

47. **Pre-push audit: no placeholders, data in PostgreSQL — 23 Oct 2026 (JML).** Before syncing
    to `co-work`, every file in the push was swept for placeholders and for data held in code.
    JML's decisions on what was found:
    - **Marketplace constants → PostgreSQL, UNVERIFIED.** Migration **066** (`project_sales_detail`,
      `project_input_line`, `input_classification`, `tb_commodity.registry_pathway`); loaded by
      `backend/scripts/load_marketplace_unverified_20261023.py` from
      `scripts/data/marketplace_unverified_20261023.json`, the four constants extracted verbatim
      (8 sales details, 33 input lines over 11 projects, 10 classifications; **re-run it after an
      Alembic rebuild**, a dump restore carries the rows). Spot prices are reference-registry
      rows, keys `market_spot_price` / `market_spot_price_energy`, state **proposed** (5) — not in
      force until someone confirms the source and approves. `GET /api/v1/market/project-economics`
      reads them AS THE CALLER (RLS: the project's companies only). The page shows UNVERIFIED on
      every unconfirmed figure, a banner, and "—" where nothing is recorded. Also removed from
      that page: the synthetic chart (sine "seasonality", noise, ramps, a formula labelled
      "Gabillon Forward", the input-consumption chart), the 1,000 fallback price, the 330-day year
      (now nameplate × 365), a "contracted ⇒ CONFIRMED" badge, and a zero cost where no input is
      recorded.
    - Also fixed in the push: molecule lists from `tb_commodity` (`GET /api/v1/market/commodities`);
      the trading book's placeholder `get_db` (fake DSN) removed; the trader dashboard's invented
      figures ("10,000 MT/month", "4 producer offers", "Q1 2027", "RotterdamOfftake4"); Capacity's
      invented "available" (330 days × 80 %); Matching rebuilt on what a match records (the
      credit, logistics, certificate, carbon and tenor screens had no data).
    - **Counterparties built** on `tb_counterparty` (`/counterparties`, in the menu with Market
      Discovery and RFQs). **15 placeholder routes removed** (Finance Reports; Trader Analytics;
      six Regulator, seven Executive screens) — none was in the menu; their addresses now render
      nothing. `PlaceholderPage` deleted.
    - **Kept in code by decision:** the match threshold (60) and score weights — the method, not
      data (documented at both sites).
    - **Next task, not in this push:** project data still partly in code — the frontend merges
      the server's projects with `frontend/src/data/customerProjects.ts` (bankability, gates, …)
      and the backend's `project_registry.PROJECT_ACCESS_PROFILES` is a Python dictionary.
      Also vocabulary lists in `trading_book/schemas.py` (KNOWN_*).
    Tests: `test_marketplace_records_pg.py` (4, incl. a source guard negative-verified),
    `CounterpartiesPage.test.tsx` (2), Market Screens updated. Head **066**, **140** tables,
    **133** FORCED. **Backend 1088 pass, 18 skip, 0 fail**; frontend 226 pass, 1 FAIL (the
    pre-existing `EconomicsSnapshotPage` refusal test). Backups `…_2254.dump`, `…_2319.dump`.

---

## 9. Rejected and superseded — do not reintroduce

**Invented evidence (2026-09-26) — REJECTED:**

- **Presenting the 125 seed rows as real people's submissions.** They were written by one
  generator; there are no people behind them, and attributing documents to ETFuels or
  HamburgOne that they never produced is fabricated evidence in the lenders' system of
  record. They became open *requests* instead — the work is real, the claims are gone.
- **Backfilling vetting columns** (phone, agreement) to make accounts look complete —
  the NULLs are how unvetted accounts are found.
- **Assigning a request to an account of another company** because the owner lacks the
  function — it discloses the project. Unassigned with a reason is the correct state.
- **Loosening `test_evidence_slice` parity** when it failed after the conversion — the
  SQLite fallback really did still hold the invented rows.

**Evidence rules 3.0.0 (2026-09-25/26) — the obvious fixes that are wrong:**

- **Adopting the platform registry's 69-key evidence bar verbatim — REJECTED.** It is
  the obvious "stronger bar", and it was weaker in G2 (no additionality), G3 (a
  strategy counted as inputs secured), G8 (no audit in "Audit-Grade") and G10 (no legal
  opinions), and it deadlocked G7. The canonical 77 items were built gate by gate.
- **Requiring insurance BOUND, or lenders as loss payee, before FINANCEABLE — REJECTED.**
  Lenders who have not approved credit cannot be named on a policy; on a strictly
  sequential ladder that makes every later state unreachable.
  `test_no_gate_requires_evidence_before_the_state_at_which_it_can_exist` fails if it
  returns.
- **Relabelling retired evidence rows as their replacements — REJECTED.** Mapping
  `eia_submission` to `eia_permit_granted` would manufacture achievement evidence out of
  intention evidence — the exact false positive 3.0.0 removes. Retired rows stay as
  history; no gate scores them.
- **Backfilling a maturity on existing evidence rows — REJECTED.** That would be the
  engine inventing a fact about a document nobody has examined. NULL fails closed.
- **Letting a reviewer set or raise maturity — REJECTED.** Verification confirms what an
  instrument is; it must never turn a term sheet into a contract.
- **Encoding maturity only in the evidence key's name — SUPERSEDED.** That was the
  pre-3.0.0 state and it is not a control: an LOI in an `..._executed` slot satisfied it.
- **Running `_ensure_tables` DDL on PostgreSQL — REMOVED.** It raised on every call.
  Migrations own the PG schema.

**CORRECTED 2026-09-08 — GEX *does* perform engineering mass balance.** An earlier version
of this document said it did not. That was an audit of the backend only. The frontend
equation engine (`frontend/src/engine/`) carries the conservation residual
`r = Σṁ_in − Σṁ_out` (`F_MASS_BALANCE_RESIDUAL_V1`), electrolysis stoichiometry (9 kg H₂O
and 8 kg O₂ per kg H₂ — both correct), splitter and separator balances, recycle and purge:
20 formulas, 31 consistency checks, wired to the PlantBuilder canvas. Three layers use the
phrase "mass balance" and **they are not duplicates**:

| layer | where | what |
|---|---|---|
| engineering / process | `frontend/src/engine/` | conservation residual, stoichiometry, recycle, purge |
| techno-economic | `tea_engine/` :8002 | OpenPyTEA + CEPCI; stub labels itself `engine="stub"` |
| custody | `backend/.../mass_balance.py` | `allocated += v`, `remaining = total − allocated` |

**Nothing connects them.** A lot's volume is never checked against the process model, and
the process model is never checked against metered output. That gap is the real finding.
Both files now carry a comment naming the other and saying: same words, different layer,
do not merge.

**CORRECTED 2026-09-08 — `files/docker/` is a BUILD STAGING AREA, not a fossil.** It was
read as an abandoned copy and deleted on my advice. `sync-to-docker.sh` does
`rsync -a --delete` from this repo into it before publishing to Docker Hub, and the next
sync recreated it — which is how the staging role was discovered. It is now in the compose
guardrail's `skip_parts`, because a staging copy is a copy *by construction* and flagging
it inverted the guardrail's purpose. **The accepted risk is stated in the test: nothing
catches a stale staging copy.** Run `sync-to-docker.sh` immediately before `docker build`.



- **WebSockets / real-time push for the evidence workflow — NOT BUILT, deliberately
  (2026-09-18).** The February 2026 handoff listed "no WebSocket infrastructure for live
  data" as a gap. It is not one at this stage. Evidence is human-paced: a document is
  uploaded, an analyst or IE reads it, a gate moves — minutes to days apart, not seconds.
  A socket layer would add a stateful connection, reconnection logic, auth on upgrade and
  fan-out across replicas, to save a page refresh. **What to build instead when it is
  actually needed:** conditional polling (ETag / `If-None-Match`) on the few screens that
  watch a queue, and server-sent events only if one-way push turns out to matter.
  **The trigger that changes this:** two or more people working the same review queue at
  once, where a stale screen means duplicated or contradictory decisions.

- **Patching `dealClient.ts` by wiring it to Supabase PostgREST — REJECTED.** Replace
  with backend deal endpoints. Recorded here because it is the obvious quick fix and it
  is the wrong one.
- **Leaving Supabase — REJECTED.** See §5.10.
- **Trusting a self-registered account — REJECTED.** See §5.2.
- **Voiding a `SETTLED` token, or any recovery path out of `RETIRED` — REJECTED.**
  Error correction is `ANNULLED`, terminal and non-claimable.
- **Relying on `UNIQUE(previous_hash)` alone to prevent chain forks — SUPERSEDED.** SQL
  UNIQUE permits many NULLs, so two events could both claim to be first; and rejection
  loses audit events. The advisory lock is the mechanism.
- **The empty-string GUC bypass in the 020 policies — REMOVED in 032.** An unset
  `app.current_company_id` must not grant visibility.
- **DROPping the 12 dead tables — SUPERSEDED by quarantine.** Reversible, free (they
  were empty), and proves absence of callers over a release cycle rather than by grep.
- **Merging the two "specific energy" fields — REJECTED, and actively guarded.**
  `fuel_catalog.specific_energy_value` is the fuel's own LHV in kWh/kg and *varies*
  (H2 33.3 · NH3 5.2 · e-methanol 5.5 · SAF 11.9).
  `FUEL_DEFAULTS[...]["specific_energy_kwh_per_kg_h2"]` is the *electrolyser's*
  consumption and is *constant* at 50.0. They read alike and are different physics.
  Merging them corrupts either every fuel's energy content or the production formula.
- **Copying a WAL-mode SQLite database by copying the `.db` file — DOES NOT WORK.**
- **An unguarded `app` alias in the sibling — REJECTED.** Re-exporting `pf_engine` as
  `app` with no check restores the collision the rename removed: in any process holding
  both trees, whichever `app` loads first silently supplies the other's modules. The
  alias exists only because it refuses to load beside the platform backend.
- **A tombstone that raises with the correct command — SUPERSEDED 2026-09-09.** It named
  the fix and still did not start the engine; the old command was recalled from shell
  history a third time. Legible failure was the wrong trade for a start command.

---

## 10. Current task

**2026-10-23 (late):** pre-push audit done (§8 item 47): Marketplace data moved to PostgreSQL
UNVERIFIED (066), placeholders removed, Counterparties built. **Next: project data out of code**
(`customerProjects.ts`, `PROJECT_ACCESS_PROFILES`), then trading-book M2.

**2026-10-23:** the market chain runs end to end in PostgreSQL only (§8 item 45). The
trading-book revision is under way: JML decided the four open questions, automated matching is
switched off, and step M1 (migration 065) is done — §8 item 46. **Next is M2, then M3** (the
order/RFQ API and acceptance, which moves the market engine onto the new model). Still open
for JML: the contract token's technology and issuer; counsel's answer on automated matching.
Nothing is synced to `co-work` yet.

**2026-09-28:** evidence rules 4.0.0 shipped end to end (§8 items 34–36). Nothing in
flight; the next move is the clients' — commitment cards, and HamburgOne's call on the
four not-applicable requests. Docker Desktop's restart again left `files-postgres-1`
stopped (restart policy `no`, as on 2026-09-14); `docker start files-postgres-1` brought
it back at head 058 with nothing lost. The paragraphs below are older.

**Nothing is in flight (as of 2026-09-18).** The duplicate tenor labels (§8.8) were fixed 2026-09-14 in the
sibling engine, with the frontend aligned and a parity test between them; the live engine
serves the new labels, not yet seen on a signed-in page.

The 2026-09-08 schema loss is recovered: 98 tables at head 045, 12 projects, 17 tenants,
6,622 rows across 53 watermarked tables — last verified 2026-09-09. PostgreSQL was
unreachable on 2026-09-14 until Docker Desktop was started *and* `files-postgres-1` was
started by hand (§8.10); healthy at head 045 since 16:03.

Recent work, most recent first: **Ecosystem Navigator data structure v4.2** (2026-09-18) —
a specification, not code: lifecycle split into phase, milestones, status and gates;
stopped projects recordable at last; counterparties as organisations and participations;
evidence as its own ledger with independence groups; registers as projections of accepted
claims; free open sources named with their licences (§7) · **duplicate tenor labels** — 18M and 30M no longer read as
whole years; one convention in engine and frontend, stale stored curves purged ·
**`/pricing-curves` was blank for every signed-in user** —
a response-shape mismatch with no error boundary to contain it · the alias safety test
corrected · the sibling's old start command restored as a guarded alias · a guardrail that
had silently stopped scanning the sibling · 500 → 422 on non-finite engine input ·
undefined DSCR no longer reads as covenant-compliant, and an over-long CFADS horizon is
rejected · `gex_pf_engine` → `deal_engine` · PostgreSQL rebuild and project restore ·
Chain-of-Custody rename · guest landing page rebuilt.

All eight backend switches remain on SQLite by design. The next migration step is slice 7
(flip and retire), still blocked on the Supabase credential from Jim.

**Scoped 2026-09-18, not started: the TEA report** (`docs/tea-report-scope.md`). The
compute exists on :8002 and is approved through `model_base_case`, but the four
`economics.*` permissions map to **routes that were never written**, no screen shows CAPEX,
OPEX or LCOP, `/reports/banker/{id}` returns hard-coded strings, and
`/ic-pack/{id}/export/pdf` always raises 409 behind a "pretend" comment. Increment 1 is one
project-scoped endpoint serving the **approved** claim — never recomputing, never falling
back to a provisional run. Decided the same day: internal view only (so no stored artefact,
and §8.14 stays off the path), and the name stays **TEA** — "EAT" is not adopted.

---

## 11. Recommended next five actions

1. ~~Fix `contracts`.~~ **DONE 2026-10-23** (migration 063, PostgreSQL only; §8 item 45).
   *Was:* **Fix `contracts` (unblocked, ~1 hour).** A live 500. Create the table in PostgreSQL
   via a new migration and in SQLite, derived from the columns
   `contracts_sqlite.py` actually selects. Do not drop the route.

2. **Replace `dealClient.ts`'s Supabase path with backend endpoints (unblocked).** The
   decision is made and the code still contradicts it. Add
   `GET/POST /api/v1/deals/engine-runs` (and the `v_latest_engine_run` equivalent) behind
   ABAC, then delete the three `.from()` calls. Do `projectAccess.ts` next — it is an
   access path, so a direct client call is a policy bypass, not just an inconsistency.

3. **Obtain the Supabase service-role `DATABASE_URL` and run slice 7.** Set it
   server-side in `backend/.env` — Jim sets it; it must never be the anon key and must
   not be pasted into a chat or committed. Then: re-run every migrator against the target
   (all idempotent, all record watermarks), verify watermark counts, and flip the eight
   switches **one at a time**, running the suite between each. `AUTH_DB_BACKEND` last —
   it is the one that can lock everyone out.

4. ~~Move the runtime connection to `gex_app`.~~ **DONE 2026-08-10** (migration 045).
   Three tests did depend on superuser visibility, as expected — whole-store fidelity
   comparisons that read through the shim with no caller bound. They now declare
   `as_platform_admin()` explicitly, the same way the seven production bootstrap sites do.

5. **Fix the `_log_event` hash and retire SQLite.** *(2026-10-23: retired for the whole market
   and trading area — §8 item 45; the rest below still stands.)* Hash exactly what is stored in
   `development_packages.py` and `spend_wave.py`; record in the migration that the 7
   historical events remain unverifiable. Then ratchet the SQLite baseline to 0, remove
   `SQLITE_DB_PATH`, drop the quarantined tables, and delete
   `test_the_dead_tables_are_quarantined_not_dropped` in that same commit.

---

## 12. Assumptions requiring Jim's decision

1. **The Supabase target and its credential.** Which project, and the service-role
   connection string. Slice 7 cannot start without it and I must not handle it.
2. ~~`files/docker/` disposition.~~ **RESOLVED** — and the 2026-08-10 resolution was
   wrong about what it was. `files/docker/gex-platform-enhanced/` is build staging that
   `sync-to-docker.sh` regenerates with `rsync --delete`; see §9. No decision outstanding.
3. **Whether `app.current_user_id` is worth introducing.** Without it, two governance
   tables stay admin-only and users cannot read their own permission overrides. It is a
   real product limitation, not just a schema one.
4. **What `contracts` should contain.** I can infer columns from the queries, but not
   whether it should be seeded, nor whether the route was ever meant to ship.
5. **How far the "no direct Supabase from the frontend" rule reaches.** Deal data is
   settled. Whether it also covers canvas/iteration state (`iterations.ts`, 8 calls;
   `seedInitialCanvas.ts`; `plantStore.ts`) is a scope call — those are editor state, not
   commercial records, and routing them through the backend is real work.
6. **Whether the seed accounts should be re-vetted.** Every account that exists — all 17
   in `auth_users` — is `ACTIVE` via `SEED_GRANDFATHERED`, with no telephone verification
   and no signed agreement. Under §5.2 not one of them would qualify today. The vetting
   pipeline has therefore never been exercised end-to-end on a real applicant.
7. **Ecosystem Navigator, D1–D14** (§7, 2026-09-18; the list lives in the docx). Twelve
   are open, and four of them block schema work rather than wording: how v1
   "Feasibility" maps (pre-FEED or FEED); the production-pathway vocabulary, which the
   document and the code disagree on; whether a client's published value outranks an
   ingested one on descriptive fields; and the lawful basis for publishing contact details,
   which needs counsel rather than engineering. **Decided 2026-09-18:** D12, the 2-year and
   4-year silence convention; D13, GEX staff work the analyst review queue — the turnaround
   target and the fate of cases nobody reaches are still unset.
8. **Where clients enter Layer 1 fields.** The plant builder is an equipment and costing
   engine and holds almost none of the dictionary's fields, yet the document assumes it is
   the entry form. Either a project-details form is built, or Layer 1 states plainly that
   most of it arrives by import and only a slice from clients.
