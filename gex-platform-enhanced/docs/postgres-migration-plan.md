# PostgreSQL Migration Plan (ADR 2026-07-06)

**Decision:** PostgreSQL is the committed system of record. SQLite
(`backend/gex_platform.db`, the single canonical file) is transitional.

**Doctrine already enforced by CI** (`backend/tests/test_architecture_guardrails.py`):
no hidden database, no relative path, no second database, no module-owned
path, and a ratchet that only lets raw `sqlite3.connect` call sites decrease
(baseline 98 on 2026-07-06).

## Assets already in place — do not rebuild

| Asset | Location | Status |
|---|---|---|
| Async engine + RLS session dependency | `backend/app/db/session.py` | Written, unused — this is the target layer |
| RLS policies + hardening | `migrations/20260518120001_sprint1_rls_hardening.sql`, `migrations/setup_postgres_rls.sql` | Written |
| Alembic scaffold | `backend/alembic/` (10 versions) | Needs reconciliation with live SQLite schema |
| Postgres service (postgis 15) | `../docker-compose.yml` | Provisioned, healthchecked |
| Tenant identity for RLS | `request.state.user_payload`, set by `app/core/route_security.py` on every authenticated request | Live as of 2026-07-06 |

## Strangler sequence

Migrate **one module per slice**; each slice ends with the ratchet baseline
lowered and the module's tables live in Postgres.

1. **Schema truth first.** Autogenerate an alembic revision from the live
   SQLite schema (89 tables) so Postgres DDL matches reality, not the stale
   10 revisions. Park unused tables in a `legacy` schema rather than dropping.
2. **Identity & auth tables** — ✅ **DONE 2026-08-07** (see "Auth slice" below). (`auth_users`, `auth_login_history`,
   `auth_user_project_roles`, refresh tokens). Small, hot, security-critical,
   and owned by 3 modules (`auth.py`, `refresh_tokens.py`, `routes_auth.py`).
   Proves the sync-session path (`get_sync_db_for_company`).
3. **Projects + project_access + project_context** (`project_registry.py`,
   `project_truth.py`, `routes_projects.py`). This is the slice that turns
   RLS on for real — the policies in migration 020 target exactly these
   tables. From here, every later slice inherits tenant isolation for free.
4. **Evidence & bankability** (`bankability_evidence`, `bankability_snapshots`,
   `evidence_*`). Highest business value under RLS (investor-facing data).
5. **Capital bridge + development packages** (biggest modules, 1,200+ lines
   each — write characterization tests BEFORE migrating these).
6. **Marketplace/trading tail** (`*_sqlite.py` modules, trading_book). Bulk
   but low coupling; mechanical.
7. **Retire SQLite.** Ratchet baseline reaches 0; delete `SQLITE_DB_PATH`
   from config; the guardrail test flips from "at most one .db file" to
   "no .db file".

## Per-slice checklist

- [ ] Alembic revision for the slice's tables (+ data copy script from SQLite)
- [ ] Module rewritten against `get_db` / `get_sync_db_for_company`
- [ ] RLS policy exists for any tenant-scoped table in the slice
- [ ] Ratchet baseline lowered in `test_architecture_guardrails.py`
- [ ] Dual-run smoke: read parity between SQLite backup and Postgres

## Rules during transition

- New tables go to Postgres only. The guardrail forbids new raw SQLite sites.
- No module may read both stores; a slice migrates atomically.
- `DATABASE_URL` comes from environment in deployed contexts (compose already
  injects it); the dev default in config.py is for local convenience only.


---

## Auth slice — completed 2026-08-07

**Status: dual-backend, not yet flipped.** SQLite remains the default and the
live system of record; Postgres is populated, verified and one env var away.

| Artefact | Where |
|---|---|
| Schema | `alembic/versions/030_auth_slice.py` — **independent root**, branch `auth_slice`. Apply with `alembic upgrade auth_slice@head` |
| Data copy + parity | `scripts/migrate_auth_slice.py` (dry-run by default; `--execute` to write) |
| Backend selector | `app/core/db_backend.py` — `AUTH_DB_BACKEND=sqlite\|postgres` |

**Why 030 is an independent root.** `alembic upgrade head` against a fresh
database dies on `relation "bankability_evidence" does not exist` — revisions
010+ target tables from other, unmigrated slices. That is the stale-revisions
problem in step 1. The auth slice genuinely does not depend on them, so
chaining would encode a false dependency. Merge the branches when the
schema-truth revision lands.

**Type fidelity is deliberate.** Timestamps are TEXT and booleans INTEGER,
matching SQLite, because `auth.py` compares ISO strings as strings. Migrating
storage and rewriting the type system in one change makes failures ambiguous.
Modernise in a separate revision, with the application code, later.

**RLS is deliberately NOT enabled.** `auth_users` is the table that
*establishes* tenancy, so it cannot be filtered by it — the login lookup runs
when `app.current_company_id` is `GUEST`, and a naive company policy would
deny the credential check. Needs an authentication-path exemption, which
belongs with slice 3 where the policy model is built. Enabling it wrongly
would read as protection while breaking login or permitting everything.

**Verified**
- Copy parity: column-by-column, all 4 tables (17 / 38 / 78 / 78 rows). Idempotent.
- Dual-run: `authenticate_user`, `issue_login_response`, payload assembly and
  project-role resolution produce **byte-identical output** on both backends.
- Full suite: **141 passed on SQLite and on Postgres** (same single pre-existing
  `files/docker/` failure).
- Vetting flow (register → 403 → queue → telephone → agreement → SoD refusal)
  behaves identically on Postgres.
- Ratchet lowered **98 → 97**.

**Portability fixes made**
- `INSERT OR REPLACE` → standard `ON CONFLICT … DO NOTHING` (both engines support it).
- `datetime('now')` removed from the one runtime query that used it.
- `_ensure_tables` / `ensure_refresh_token_table` no-op on Postgres — alembic owns that schema.
- `app/db/session.py` engines made **lazy**; it previously raised
  `ModuleNotFoundError: asyncpg` at import, making even the sync path unusable.

**To flip:** set `AUTH_DB_BACKEND=postgres` and `DATABASE_URL`. To roll back,
unset. Re-run the copy script first if SQLite has moved on.

**Open items**
- Types (TEXT/INTEGER → TIMESTAMPTZ/BOOLEAN) with the code that reads them.
- RLS for auth tables, with slice 3.
- `requirements.txt` drift: `asyncpg` and `alembic` were declared but not
  installed; `psycopg 3.3.2` is declared but `psycopg2` is what is installed.

---

## Slice 3 — projects + RLS (2026-08-07, PARTIALLY VERIFIED)

### The finding: RLS was enabled and completely inert

Migration 020 enables RLS on `projects`/`project_access`, marks both FORCE ROW
LEVEL SECURITY, and writes correct policies keyed on `app.current_company_id`.
All true. Isolation still did not happen, because:

    connected as : gex_user   SUPERUSER=True

**Superusers bypass RLS unconditionally, and FORCE does not apply to them.**
Measured, before the fix:

| tenant context | projects visible |
|---|---|
| PLATFORM_ADMIN | 12 |
| etfuels_sa | 12 |
| nordlb | 12 |
| **acme_totally_unrelated** (does not exist) | **12** |
| **GUC never set** | **12** |

"RLS is enabled" is not evidence that RLS works. Only a filtered query, run as
the role the application actually uses, is evidence.

### The fix

`alembic/versions/031_rls_app_role.py` — least-privilege role `gex_app`
(DML only; no SUPERUSER, no BYPASSRLS, no ownership), created NOLOGIN so no
secret lives in a migration. Deployment grants LOGIN + password out of band and
points `DATABASE_URL` at it.

    gex_user  -> owner/migrator, runs alembic, keeps superuser
    gex_app   -> the APPLICATION connects as this; RLS applies

### Guardrail

`backend/tests/test_rls_isolation.py` — 7 tests. Asserts the role exists, is
neither SUPERUSER nor BYPASSRLS, that RLS is enabled AND forced, and — the one
that matters — that an unknown company and an unset GUC both see **zero**
projects. Skips cleanly when Postgres is unavailable.

### Status

| Step | State |
|---|---|
| 020 re-parented onto 030, applied | DONE (was chained behind 010, which needs `bankability_evidence` from an unmigrated slice) |
| JSONB server_default bug fixed in 020 and 021 | DONE — the quoted-string form rendered as tripled quotes; neither revision had ever been applied |
| 021 applied | DONE |
| Seed: 15 tenants, 12 projects, 22 access rows (`tenant_admin sync`) | DONE |
| RLS inertness demonstrated | DONE (measured) |
| 031 (app role) written | DONE |
| **031 applied + isolation re-measured** | DONE — see "Verified" below |
| 032 — mutual policy recursion fixed | DONE (defect surfaced only once RLS actually applied) |

### Verified (2026-08-07)

Measured as `gex_app`, 12 projects in the database:

| tenant context | sees |
|---|---|
| PLATFORM_ADMIN | 12 |
| etfuels_sa (owner) | 4 |
| nordlb (granted access) | 1 |
| hamburgone_com | 1 |
| acme_totally_unrelated | **0** |
| empty-string GUC | **0** |
| GUC never set | **0** |

`gex_user` (SUPERUSER) still sees 12 — expected, and exactly why the
application must connect as `gex_app`.

Guardrails: 6 passed / 1 skipped. Negative-verified against four breaks —
granting BYPASSRLS, granting SUPERUSER, `NO FORCE`, and `DISABLE ROW LEVEL
SECURITY` each fail the suite. Full backend suite: **147 passed on both
backends**; live login unaffected.

### 032 — the recursion defect

Turning RLS on for real immediately produced:

    infinite recursion detected in policy for relation "projects"

020's two policies referenced each other (`projects` → `project_access` →
`projects`). Never observable while a superuser bypassed them — the policies
had literally never been evaluated. Fixed with two `SECURITY DEFINER` helpers
(`app_company_has_project_access`, `app_company_owns_project`), STABLE, with
`search_path` pinned to `public, pg_temp` (a mutable search_path on a
SECURITY DEFINER function is a privilege-escalation vector), EXECUTE granted
to `gex_app` only. Policy semantics unchanged.

**Also removed: the `''` bypass.** 020 read
`current_setting(...) IN ('', 'PLATFORM_ADMIN')`, so any session setting the
GUC to an empty string saw every row. An *unset* GUC yields NULL and fails
closed correctly, but `''` was a silent full bypass reachable by an ordinary
caller, with no legitimate use — admin access has its own sentinel.

### Still to do

- Resolve the **`projects` table name collision**: SQLite has a `projects`
  table (2 rows: project_id/name/molecule/country/capacity/capex, written by
  the `/projects/new` on-ramp, with `owner_company_name` as a *name* and no
  tenant FK) while Postgres 020 has a different `projects` (owner_tenant_id FK,
  status, jurisdiction, JSONB metadata). Same name, different shape, different
  purpose. One canonical shape must win before the modules are pointed at
  Postgres.
- `project_registry.py` remains the seed source (12 static profiles);
  `tenant_admin.py sync` is the loader. Keep — do not rebuild.
- Point `project_registry` / `project_truth` / `routes_projects` at Postgres.

---

## The `projects` collision — RESOLVED 2026-08-07

**Ruling (user): the PostgreSQL shape wins.**

| | SQLite (retired) | PostgreSQL (canonical) |
|---|---|---|
| owner | `owner_company_name` — a NAME, no FK | `owner_tenant_id` FK -> tenants |
| RLS | none | enabled + forced |
| written by | `/projects/new` on-ramp | `app/core/projects_store.py` |
| rows | 2 | 12 seed + 2 migrated |

### What was done

- **033** adds `location`, `country`, `created_by` to `projects` (real data with
  no home in the 020 shape — not buried in `metadata_json` because ABAC reads
  them by name), and moves `project_context` + `project_context_events` to
  Postgres **with RLS delegating to the 032 helpers**.
- `scripts/migrate_projects_collision.py` — explicit field-by-field mapping,
  dry-run by default, parity-checked. 2 projects, 3 context, 4 events. OK.
- `app/core/projects_store.py` — the single accessor. `create_project()` writes
  all three tables in **one transaction in one store** (verified: a rejected
  duplicate left no partial write).
- `project_registry.ensure_project_table()` is now an explicit **no-op**, not a
  deletion — `CREATE TABLE IF NOT EXISTS` is silent, so a surviving caller would
  quietly recreate the second table.
- SQLite table **renamed**, not dropped: `projects_retired_pg_collision_20260807`
  (+ `data/db_backups/gex_platform.pre-projects-collision.20260807.db`).

### Deliberate decisions

- **`country` and `jurisdiction` are now separate columns.** The old runtime
  code served `country` ("DE") AS the profile's jurisdiction; downstream ABAC
  compares against that. Behaviour is preserved (still returns `country`), but
  the columns are split so it CAN be untangled without a silent authz change.
- **`power_model` / `financing_model` / `phase` did NOT travel to `projects`.**
  The SQLite table duplicated what `project_context` already owns. That
  duplication was not carried over; `projects.status` holds the lifecycle value.

### CONSEQUENCE — runtime projects now REQUIRE PostgreSQL

Without `DATABASE_URL` pointing at the GEX Postgres, runtime-created projects
are invisible (HamburgOne drops 3 -> 1). Static seed profiles still resolve, and
the failure is logged loudly, never silent. **The live backend must be started
with `DATABASE_URL` set.**

### Guardrails

`backend/tests/test_projects_canonical.py` — 7 tests: no module creates a SQLite
`projects` table, `ensure_project_table` is a no-op, the registry issues no SQL
against a local projects table, the retired table is renamed not deleted, every
store read sets a whitelisted tenant context, and `create_project` is one
transaction in one store. Negative-verified.

**Suite: 154 passed on both backends.**

---

## Slice 3 — routes pointed at the store (2026-08-07)

### A split I had introduced, now closed

Migration 033 moved `project_context` / `project_context_events` to PostgreSQL,
but `routes_projects.py` still wrote the SQLite copies. For a short window
`create_project()` wrote Postgres while `PATCH /{id}/context` wrote SQLite —
two stores, diverging, no error. Both copies held 3 and 4 rows respectively.

Now on the canonical store:

| caller | was | now |
|---|---|---|
| `project_registry.get_effective_context` | SQLite | `projects_store.fetch_context` |
| `PATCH /{id}/context` | SQLite INSERT + event INSERTs | `projects_store.update_context` (one transaction) |
| `GET /{id}/context/events` | SQLite | `projects_store.fetch_context_events` |

`update_context()` writes the state row and its audit events in ONE
transaction. A context change recorded without its audit row — or an audit row
without the change — is precisely what an append-only events table exists to
prevent.

SQLite copies retired by rename, not drop:
`project_context_retired_pg_collision_20260807`,
`project_context_events_retired_pg_collision_20260807`.
`ensure_context_tables()` is now an explicit no-op for the same reason
`ensure_project_table()` is — `CREATE TABLE IF NOT EXISTS` is silent.

### project_truth.py — NOT in this slice

It reads a static `PROJECT_TRUTH` dict plus `bankability_evidence` from SQLite.
It touches neither `projects` nor `project_context`, so there is nothing to
point at the projects store. `bankability_evidence` belongs to **slice 4
(Evidence & bankability)** and moves with it.

### Guardrails

`tests/test_projects_canonical.py` grew to 11, negative-verified against three
breaks: writing context to SQLite from the routes, reintroducing the SQLite
context DDL, and splitting the state/audit writes out of one transaction.

**Suite: 158 passed on both backends.**

### Still open

- `routes_projects.py` risk-flag handlers (4 remaining `sqlite3` sites) — a
  different table family, not part of the projects slice.
- The live backend still needs `DATABASE_URL` set, or runtime projects and
  their context are invisible.

---

## DATABASE_URL set, and the silent regression it exposed (2026-08-08)

`backend/.env` now carries `DATABASE_URL` (port **55432**, not 5432 — :5432 is a
different, non-GEX PostgreSQL that rejects these credentials; a `gex-pg-forward`
socat container bridges 55432 -> `files-postgres-1`:5432, set to restart
automatically). `AUTH_DB_BACKEND` is a declared `Settings` field now, because
Settings forbids extra inputs and pydantic does not export `.env` into
`os.environ` — putting it in `.env` without declaring it broke startup.

### Runtime projects had silently vanished

`_runtime_visible_projects()` queried the retired SQLite `projects` table and
swallowed `sqlite3.Error` into an empty list. After the table was renamed, every
runtime project disappeared from the list it had just been created for — no
error, no log, just fewer rows. HamburgOne saw 1 project instead of 3.

Three separate filters had to be fixed:

| site | defect |
|---|---|
| `_runtime_visible_projects` | read retired SQLite, swallowed the error |
| `_visible_ids_from_jwt` | walked only the STATIC registry — and it doubles as the **per-project authorization check**, so a runtime project's own creator was denied access to it |
| `_profile_to_visible` | returned `None` when static `_PROJECT_META` had no entry |

All three now read the canonical store. `list_projects()` added to
`projects_store.py`.

### No fabricated coordinates

The old code sent `lat=0.0, lng=0.0` for projects whose coordinates were never
collected — a map pin in the Gulf of Guinea. `VisibleProject.lat/lng` are now
`Optional[float] = None` and both construction sites omit them.

The first version of that guardrail asserted only `not is_required()`, which
`lat: float = 0.0` also satisfies — the exact bug passed the test. It now
constructs a `VisibleProject` and asserts the value **is None**. A second
version checked one function and missed the create handler; it now scans the
whole module.

### Verified live

| user | sees | runtime leaked |
|---|---|---|
| HamburgOne (owner) | 3 | — |
| ETFuels | 4 | none |
| NordLB | 1 | none |
| platform admin | 14 | both (correct) |

Full on-ramp round-trip: `POST /api/v1/projects` -> Postgres -> visible
immediately, `lat=None`.

**Suite: 161 passed on both backends.** Guardrails: 14 in
`test_projects_canonical.py`, each negative-verified individually.

---

## Slice 4 — Evidence & bankability (2026-08-08)

Migration **034**. In scope, as the plan specifies:

| table | rows | note |
|---|---|---|
| `bankability_evidence` | 116 | the evidence grid behind every gate |
| `bankability_snapshots` | 8 | last evaluated gate state per project |
| `evidence_documents` | 3 | uploaded artifacts (sha256 + path) |
| `evidence_events` | 4 | append-only status transitions |
| `evidence_ledger` | 0 | hash-chained immutable ledger |

Deliberately out: `package_evidence` (slice 5 owns it), `pre_cod_snapshots` /
`pre_cod_metric_snapshots` (derived metrics, not evidence), `gateway_registry`
(OT boundary).

All five are project-scoped, so each gets a tenant-isolation policy that
**delegates to the 032 SECURITY DEFINER helpers** rather than restating the
visibility rule.

### The hash chain was the risk, and it is verified

`evidence_ledger` is tamper-evident: the digest covers the row's fields, BOTH
actors, BOTH state axes, and `prev_hash`. It was empty, so no existing chain
needed preserving — but a chain that cannot be validated in its new store is
worse than no chain. Proven in PostgreSQL:

- 3-entry chain written and validated
- silent `verification_state` upgrade -> chain invalid
- `submitted_by` rewritten -> chain invalid
- `prev_hash` tampered -> chain invalid

### Read parity across backends

`EVIDENCE_DB_BACKEND` is a **separate** switch from `AUTH_DB_BACKEND` — the
point of a strangler is that slices flip independently. Both return identical
results:

    sqlite   : {IN_PROGRESS:25, NOT_STARTED:42, SUBMITTED:18, UNDER_REVIEW:7, VERIFIED:24}
    postgres : {IN_PROGRESS:25, NOT_STARTED:42, SUBMITTED:18, UNDER_REVIEW:7, VERIFIED:24}

### Unattributed evidence — a ratchet, not a fix

`bankability_evidence.project_id` defaults to the literal string `'default'`, so
**38 evidence rows + 1 snapshot** belong to a project that does not exist. Under
RLS they match no tenant and are PLATFORM_ADMIN-only — effectively invisible.

They were copied anyway: losing evidence is worse than losing visibility, and
inventing a project to attribute them to would be a fabrication. Instead
`UNATTRIBUTED_BASELINE = 39` is a **ratchet** — the debt may be paid down, never
added to. The migration script reports the count so it is a decision, not a
surprise.

### Verification

`tests/test_evidence_slice.py` — 12 tests, negative-verified against four
breaks: digest no longer covering `verification_state`, RLS un-forced, policy
widened to `USING (true)`, and unattributed rows growing. Each fails.

**Suite: 173 passed across all four backend combinations** (auth × evidence,
sqlite × postgres). Live login unaffected — both slices still default to SQLite.

### Still open

- Slice 5 (capital bridge + development packages) — the plan warns: write
  characterization tests BEFORE migrating those 1,200-line modules.
- Neither slice is flipped. `AUTH_DB_BACKEND` / `EVIDENCE_DB_BACKEND` stay
  `sqlite` until `DATABASE_URL` points at the real Supabase target.

---

## Slice 5 — characterization tests written FIRST (2026-08-08)

Per the plan's own warning about these two modules:

    capital_bridge.py         1234 lines, 20 endpoints, 8 tables
    development_packages.py   1398 lines, 13 endpoints, 3 tables

`backend/tests/test_slice5_characterization.py` — **35 tests, no migration yet.**
They pin what the code DOES, not what it should, so that a store swap can be
proven behaviour-preserving.

### ⚠ A confirmed defect found while writing them, and PINNED not fixed

`capital_bridge._compute_production()` is **wrong by a factor of 1000**. It omits
the MWh -> kWh conversion:

    energy = MW x 8760 x availability        [MWh]
    kWh    = that x 1000                     <-- MISSING
    H2 kg  = kWh / SEC (kWh per kg)
    H2 t   = kg / 1000

Correct reduces to `MW x 8760 x avail / SEC` tonnes; the code computes
`MW x 8760 x avail / SEC / 1000`. For 300 MW at 95%, SEC 55:

| | H2 t/yr | annual revenue |
|---|---|---|
| expected | 45,392.7 | ~EUR 160M |
| actual | **45.4** | **~EUR 160k** |

The docstring's own formula produces the same wrong number, so the error is in
the INTENT, not a mistranslation. Every capital-bridge figure derives from this.

**It is pinned, deliberately.** Fixing a defect inside a storage migration
destroys the only signal that separates a copy bug from an intended change. Fix
it as its own change and update the pinned value in the same commit.

A side-effect worth noting: because the outputs are 1000x too small, the
`round(..., 2)` in that function is a MATERIAL fraction of the value — 100 MW
gives 15.77 t/yr but 1000 MW gives 157.68, not 157.70. The linearity test
therefore needs a loose tolerance, which is a symptom of the bug, not of the
maths. Tighten it to `rel=1e-6` when the units are fixed.

### What else is pinned

- **Economic constants** — `DEFAULT_CAPITAL_STACK_PCT` sums to exactly 1.0 (an
  invariant, not just a golden value) and every share is pinned; senior/ECA/equity
  rates; **every DFI rate must stay below commercial senior** (a broken
  inequality would flatter every blended cost of capital).
- **Both state machines** — the 12-state workflow as a strict forward-only chain
  with PROPAGATED terminal, the 6-state capital ladder likewise, and that the two
  ladders' VALUES never overlap (lowercase vs UPPERCASE) so one cannot be
  mistaken for the other.
- **Hashing** — `_hash_package` determinism, key-order independence, and a fixed
  vector, so a store returning columns in a different order cannot change it.
- **Transition guards** — EVIDENCED-requires-evidence and
  DRAWABLE-requires-unlock-evidence.
- **Stored data golden master** — row counts for all 11 tables (equality, not a
  ratchet: a drop is a lost row, a rise means the app wrote to the old store
  after cutover), the real workflow-state distribution
  (`identified: 2, evidenced: 1` — so one package has already passed the evidence
  guard), and referential integrity that SQLite never enforced.
- **`fuel_defaults` table vs in-code `FUEL_DEFAULTS`** — two sources for the same
  numbers; pinned that they AGREE today so the migration cannot let them drift.

### Also observed (not a defect, but a trap)

`DEFAULT_CAPITAL_STACK_PCT` mixes `TrancheType` enum members with raw strings —
the six DFI entries have no `TrancheType`. It works only because `TrancheType`
is a `str` enum. Any caller doing `key.value` over that dict would crash on the
six strings.

### Verification

Negative-verified against six deliberate breaks, each caught:
"fixing" the 1000x bug, perturbing a stack share, raising a DFI rate above
commercial senior, adding a rollback transition, dropping `sort_keys` from the
hash, and removing the EVIDENCED guard.

**Suite: 208 passed across all four backend combinations.** No migration
performed — that is the next step, and these tests are the gate.

---

## The 1000× units bug — FIXED 2026-08-08, as its own change

`capital_bridge._compute_production()` omitted the MWh → kWh conversion. Fixed
before the slice-5 migration, deliberately separate from it.

### What changed

    energy_mwh   = mw * 8760 * avail          [MWh/yr]
    energy_kwh   = energy_mwh * 1000          [kWh/yr]   <-- was missing
    h2_annual_kg = energy_kwh / sec           [kg/yr]
    h2_annual_t  = h2_annual_kg / 1000        [t/yr]

Each intermediate now names its unit, because the original error was exactly a
conflation of MWh with kWh in an unnamed intermediate. The docstring carried the
same mistake and was rewritten.

### Impact — 300 MW at 95%, SEC 55

| | before | after |
|---|---|---|
| H2 | 45.39 t/yr | **45,392.73 t/yr** |
| product | 246.94 t/yr | **246,936.44 t/yr** |
| revenue | EUR 160,509 | **EUR 160,508,684** |
| EBITDA | deeply negative | **EUR ~130M** |

The consequence was not merely small numbers: with revenue three orders of
magnitude below OPEX, **every capital stack built on this was unfundable by
construction**.

### Safe to fix cleanly

`_compute_production` is the single site (3 call sites, one definition), there
is no parallel implementation in the backend or frontend, and the outputs are
**derived on read, never persisted** — `project_control` holds 0 rows. So no
stored data needed reconciling.

### Tests updated in the SAME change

- `test_compute_production_is_pinned` — golden values updated, defect note kept
  as history. Test renamed (it no longer pins a bug).
- `test_production_matches_an_independent_dimensional_calculation` — NEW.
  Recomputes from units rather than repeating the implementation, so a
  reintroduced conversion error is caught by arithmetic rather than by a golden
  value someone might "update to make it pass". Mirrors the 2-decimal rounding
  contract instead of loosening tolerance.
- `test_a_utility_scale_plant_produces_a_plausible_tonnage` — NEW. The magnitude
  guard that would have caught this immediately: a 300 MW electrolyser makes tens
  of thousands of tonnes a year, not tens.
- `test_compute_production_scales_linearly_with_capacity` — tolerance tightened
  from `abs=0.05` back to `rel=1e-9`; the loose bound had been a symptom of the
  bug, not of the maths.

Negative-verified: reverting the conversion fails 4 tests; a subtler 10x slip
(`* 100` instead of `* 1000`) still fails 3.

**Suite: 210 passed across all four backend combinations.**

---

## Slice 5 — MIGRATED 2026-08-08

Migration **035**. Eleven tables:

| | rows |
|---|---|
| `development_packages` | 3 |
| `development_package_events` | 18 |
| `fuel_defaults` | 5 |
| `package_evidence` | 2 |
| `project_control`, `capital_stack_tranches`, `spend_wave`, `drawdown_quarters`, `personnel_plan`, `post_cod_schedule`, `dfi_criteria_status` | 0 |

Ten are project-scoped and get tenant-isolation policies delegating to the 032
helpers. `fuel_defaults` is REFERENCE DATA — RLS enabled with a read-open
policy rather than left off, so "deliberately public" is distinguishable from
"forgotten".

### A second hash chain — already broken before the migration

`development_package_events` carries event_hash/prev_hash over 18 real rows.
**7 of them could not be verified BEFORE any migration.** Checked first, on
purpose: had the copy run first, the move would have taken the blame.

Cause — `_log_event` hashes `new_val` as a typed Python object but persists
`str(new_val)`:

    hashed:  json.dumps({... "new_value": ['G1_GRID_WATER'] ...})  -> ["G1_GRID_WATER"]
             EstimateClass.CLASS_4 serialises as "CLASS_4"
    stored:  str(new_val)                                          -> "['G1_GRID_WATER']"
                                                                   -> "EstimateClass.CLASS_4"

They coincide only for plain strings. All 7 failures are `package.updated`
events with a float, list or enum value; all 9 string-valued events verify,
which is what confirms the diagnosis. **Links are intact (0 broken)** — ordering
is sound, only the per-row self-hash is uncheckable.

Fixing `_log_event` will NOT repair the 7: their pre-image was never persisted,
so they are permanently unverifiable. A fix should hash `str(new_val)` — the
form actually stored — and makes FUTURE events verifiable. Separate change.

The migration copied them **faithfully**: 7 before, 7 after. A migration that
silently repaired them would be rewriting audit history.

### Deliberately not done in this migration

- **No FK** from `package_evidence.package_id` to `development_packages`. SQLite
  never enforced it and the characterization test confirms zero orphans today,
  but adding the constraint in the same change would make an FK rejection look
  like a copy failure.
- **`fuel_defaults` duplication preserved.** It duplicates the in-code
  `FUEL_DEFAULTS` dict; the tests pin that they agree. Collapsing to one source
  is its own change.
- CHECK constraints on `workflow_state` / `capital_status` WERE added — those
  pin the domain, which the characterization tests already assert in Python.

### Verification

Parity, both backends, through the module's own `get_db`:

    packages by state : {'evidenced': 1, 'identified': 2}
    events            : 18, unverifiable=7, broken links=0
    fuel_defaults SEC : identical

`CAPITAL_DB_BACKEND` is a third independent switch (auth / evidence / capital).

Guardrails: `test_slice5_characterization.py` now **41 tests**, negative-verified
— "repairing" one event hash fails 2 tests, dropping a package row fails the
parity gate.

**Suite: 214 passed across all EIGHT backend combinations.** Live login 200.

### Migration status

Slices 2–5 are migrated and verified. **None are flipped** — all three switches
remain `sqlite` until `DATABASE_URL` points at the real Supabase target.
Remaining: slice 6 (marketplace/trading tail) and slice 7 (retire SQLite).

---

## Slice 6 — Marketplace / trading tail (2026-08-08)

Migration **036**. Thirteen tables, 5 rows: `capacities` (5), `tokens`,
`offers`, `matches`, `buyer_mandates`, and the eight `tb_*` trading-book tables
(all empty).

The plan calls this slice "mechanical". The **copy** was. The **RLS was not**.

### Tenancy is implicit in an overloaded primary key

None of these tables has a `project_id`. But `capacities.id` **IS** a project
id — all five rows are real registry projects — and nothing in the schema says
so: no FK, no naming, no comment. The rest of the marketplace hangs off it:

    capacities.id (= project_id)
        <- tokens.capacity_id
             <- offers.token_id
                  <- matches.offer_id

`app_company_can_see_capacity()` resolves it and delegates to the 032 helpers;
the downstream policies chain through it. SECURITY DEFINER with a pinned
`search_path`, so the chain neither recurses nor becomes an escalation vector.

Worth doing now, while empty: `tokens` is the object that carries the green
claim. It is the last table where tenant isolation should be an afterthought.

Measured, three joins deep, with a seeded chain on `proj_bremen_h2`:

| company | capacities | tokens | offers | matches |
|---|---|---|---|---|
| PLATFORM_ADMIN | 5 | 1 | 1 | 1 |
| heliosnord_gmbh (owner) | 1 | 1 | 1 | 1 |
| allianz (has access) | 4 | 1 | 1 | 1 |
| etfuels_sa | 0 | 0 | 0 | 0 |
| unknown company | 0 | 0 | 0 | 0 |

An **orphan token** (null/dangling capacity_id) is visible to no tenant — fails
closed, which is right: a token whose provenance cannot be established must not
leak.

`buyer_mandates` is COMPANY-scoped, not project-scoped — its policy compares
`buyer_id` directly.

### The trading book is admin-only, deliberately

`tb_asset.id` is a UUID with no external reference — the same gap that makes
the trading-book cashflow endpoint reject GEX project slugs with a 422. There
is no honest tenant policy to write, so the eight tables are locked to
PLATFORM_ADMIN rather than left unprotected (reads as an oversight) or given a
policy that only appears to isolate. A guardrail asserts they do NOT claim
project-based isolation.

### `contracts` — a live 500, NOT fixed here

`contracts_sqlite.py` is routed and queries a `contracts` table with **no DDL
anywhere in app/**, present in neither store. `/api/v1/contracts/summary`
returns **500** today.

Not created during the migration: that would make PostgreSQL work while SQLite
still failed, breaking the backend-parity gate. Pinned symmetrically
(`test_the_contracts_table_is_still_missing_on_BOTH_backends`) so the stores
cannot silently diverge, and the test tells whoever fixes it to delete the test.

### Verification

`tests/test_marketplace_slice.py` — 10 tests, negative-verified against four
breaks: widening the tokens policy, stripping `search_path` from the resolver,
dropping the token lifecycle CHECK, and giving the trading book a fake
project policy. Each fails.

The 2026-08-07 token-lifecycle ruling is now enforced in the database too — a
CHECK constraint pins the seven-state domain, and PostgreSQL rejects an unknown
state outright.

**Suite: 224 passed**, all-sqlite / all-postgres / mixed. Live login 200.

### Remaining

`MARKET_DB_BACKEND` is the fourth independent switch. All four remain `sqlite`.

Slice 7 (retire SQLite) is not reachable yet: **79 tables were still outside the
migrated set before this slice**, of which 12 hold data. The largest are
`entitlement_audit` (2493), `finance_entitlements` (672),
`fuel_unit_conversions` (120) and `platform_events` (the event store) — none of
them marketplace, so they belong to slices the plan never enumerated.

---

# Slice 6b — inventory of what the plan never enumerated

Taken 2026-08-08, after slice 6. **66 tables remain outside PostgreSQL; 11 hold
data.** The original plan jumped from slice 6 (marketplace) to slice 7 (retire
SQLite) — these are what actually sits between them.

Grouped by owning module, because a slice that spans owners is a slice that
cannot be reviewed.

## 6b-1 — Entitlements  ·  2 tables, **3,330 rows**  ·  BIGGEST, DO FIRST

| table | rows | scope |
|---|---|---|
| `entitlement_audit` | 2,622 | project |
| `finance_entitlements` | 708 | project |

Owner: `core/entitlements.py`. Both project-scoped, so the RLS pattern from
slices 3–5 applies directly. This is **97% of all remaining data** in two
tables from one module — the highest value-to-risk ratio left.

`entitlement_audit` is an audit table: verify append-only behaviour before and
after, as with the package-event chain.

## 6b-2 — Event store  ·  1 table  ·  HIGHEST RISK

| table | rows | scope |
|---|---|---|
| `platform_events` | 0 | project, **HASH-CHAINED** |

Owner: `core/event_store.py`. **10 modules write to it** — account vetting,
tokens, TEA, packages, everything. Migrating it touches every slice already
done.

It is empty as of this inventory (it held 4 events, all artefacts of this
session's own testing against deleted accounts; removed, so the chain restarts
clean rather than dangling). Empty is the ideal moment to move it — the same
argument that made the token-retirement fix cheap.

Do this SECOND, alone, with the chain verified before and after.

## 6b-3 — Reference data  ·  2 tables, 130 rows  ·  MECHANICAL

| table | rows |
|---|---|
| `fuel_unit_conversions` | 120 |
| `fuel_catalog` | 10 |

Owner: `core/fuel_catalog.py`. Unscoped reference data — same treatment as
`fuel_defaults` in 035: RLS on with a read-open policy, so "deliberately
public" stays distinguishable from "forgotten".

Watch for the same duplication `fuel_defaults` has: check whether these agree
with any in-code constant before moving them.

## 6b-4 — Governance / access control  ·  7 tables, 16 rows

`approval_policies` (8), `sod_conflict_pairs` (8), `approval_requests`,
`sod_action_log`, `permission_user_overrides`, `user_signing_keys`,
`data_residency_policies`.

Owners: `core/wae.py`, `core/sod.py`, `core/permission_engine.py`, `core/css.py`,
`core/drpl.py`. Mixed scope — some company, some user, some global.

Small but **security-relevant**: these decide who may approve what. Treat like
the auth slice, not like the marketplace tail.

## 6b-5 — Hash-chained domain ledgers  ·  7 tables, all empty

`carbon_attribution_event_log`, `dfi_criteria_events`, `drawdown_schedule_events`,
`settlement_event_log`, `sovereign_instrument_events`, `spend_wave_events`,
plus their parent tables.

All empty. Each needs the same treatment as `evidence_ledger` and
`development_package_events`: **verify the chain in PostgreSQL, then tamper and
confirm detection.** Cheap now, expensive once they hold claims.

## 6b-6 — Domain tables, all empty  ·  ~25 tables

`additionality_assessments`, `adjacency_cache`, `adversarial_reviews`,
`commitment_records`, `mass_balance_lots`, `matrix_*`, `model_base_case`,
`pathway_claims`, `plant_data`, `settlement_events`, `sovereign_instruments`,
`spend_waves`, `dfi_criteria`, `dfi_impact_kpis`, `drawdown_schedules`,
`carbon_attribution_events`, `gateway_registry` (1), `pre_cod_snapshots` (2),
`risk_flag_status` (1), `risk_flag_events` (2), …

Genuinely mechanical: project-scoped, empty, one policy shape.

## 6b-7 — Decide before migrating  ·  17 tables with NO owning module

**5 are queried but have no DDL anywhere in `app/`** — the same defect class as
`contracts`. These will 500 the moment they are hit:

    deliveries (5 refs) · production_readings (2) · availability_reports (1)
    offtake_contracts (1) · quality_certificates (1)

**12 have no DDL and no queries at all** — candidates for deletion, not
migration:

    covenant_compliance · drawdown_tranches · equity_contributions
    financial_metrics · pre_cod_metric_snapshots · project_events
    project_stakeholders · project_states · reserve_accounts · service_calls
    state_transitions · workflow_checkpoints

Note `project_events` is hash-chained and dead — worth confirming it is not a
predecessor of `platform_events` before dropping.

**Do not migrate this group.** Migrating a dead table makes it look alive.
Decide per table: create the missing DDL, or drop.

## Recommended order

1. **6b-1 entitlements** — 97% of remaining data, one module, known pattern
2. **6b-2 event store** — highest blast radius, do it alone while empty
3. **6b-3 reference data** — mechanical
4. **6b-4 governance** — small, security-relevant, deserves its own review
5. **6b-5 chained ledgers** — verify each chain
6. **6b-6 domain tail** — bulk, mechanical
7. **6b-7 triage** — decide create-or-drop; NOT a migration step

Only then is slice 7 (retire SQLite, ratchet to 0) reachable.

## Known defects to fix outside the migration

- `contracts` — routed, no DDL, `/api/v1/contracts/summary` returns 500
- the 5 queried-but-undefined tables above, same shape
- `_log_event` hashes a typed object but stores `str(new_val)` — future package
  events unverifiable until fixed (the existing 7 cannot be repaired)

---

## Slice 6b-1 — Entitlements, MIGRATED 2026-08-09

Migration **037** (+ **038**, see below). `finance_entitlements` and
`entitlement_audit` — ~3,385 rows at copy time, **97% of everything that was
still outside PostgreSQL**, from one module (`core/entitlements.py`).

Both project-scoped, so the standard delegation to the 032 helpers applies.
Switch: `ENTITLEMENT_DB_BACKEND` (fifth).

Isolation verified against the data rather than assumed: every entitlement
belongs to `proj_etf_pecos1`, so `etfuels_sa` (owner) sees all 720 and every
other company sees **0**. A permissions table that leaks is worse than a data
table that leaks.

### The problem this slice exposed: BOTH stores are live

The first verification failed, and it was the TEST that was wrong, twice.

**Attempt 1 — assert the two stores hold the same rows.** They never can. The
suite writes an `access_allowed`/`access_denied` row on every finance-access
decision, into whichever backend it is pointed at. The all-SQLite run therefore
added rows to SQLite that the snapshot copy had never seen, and the subsequent
all-PostgreSQL run reported them as "missing".

**Attempt 2 — infer a watermark from `max(timestamp)`.** Also wrong.
`entitlement_audit.at` has SECOND precision and many rows share a value, so
`at <= max` swept in source rows written in the same second that were never
copied.

**Fix — record the watermark (migration 038).** `migration_watermarks` stores,
per table, exactly which primary keys a copy wrote. Verification then asserts
two things that are actually true:

- every key the copy RECORDED is present in PostgreSQL (nothing lost since)
- every SQLite row NOT recorded post-dates the copy (nothing skipped)

Neither depends on the two stores agreeing, which they cannot while both are
live. **This applies to every remaining slice** — 6b-2 onward should record
watermarks the same way.

### Deliberately not done

`entitlement_audit` is append-only **by convention** — `_audit()` only INSERTs,
and no UPDATE or DELETE against it exists anywhere in `app/`. No database-level
guarantee was added: doing so in the same change as the move would make a
permission error indistinguishable from a copy failure. A guardrail asserts the
code property instead; the constraint is a follow-up.

### Noted, not acted on

All 720 entitlements are for a single project and 120 audit rows reference
`proj_nope` (a test fixture, all `access_denied`). Copied faithfully — filtering
an access log is editing it.

### Verification

`tests/test_entitlements_slice.py` — 12 tests, negative-verified against five
breaks: widened policy, lost audit rows, dropped action CHECK, deleted
recorded rows, and an under-reporting watermark.

**Suite: 236 passed on all-SQLite AND all-PostgreSQL.** Live login 200.

### Remaining after this slice

**64 tables, 8 with data** — `fuel_unit_conversions` (120), `fuel_catalog` (10),
`approval_policies` (8), `sod_conflict_pairs` (8), `pre_cod_snapshots` (2),
`risk_flag_events` (2), `gateway_registry` (1), `risk_flag_status` (1).

The data volume problem is solved. What is left is breadth, plus the 6b-7
create-or-drop triage.

---

## Slice 6b-2 — Event store, MIGRATED 2026-08-09

Migrations **039** + **040**. `platform_events` — the append-only, hash-chained
ledger that **ten modules** write to. Done alone, and while empty.

### The migration would have introduced a regression. It was measured, not guessed.

`append_event()` is a read-then-write against a GLOBAL chain (one chain for the
whole platform, not one per stream):

    SELECT event_hash FROM platform_events ORDER BY id DESC LIMIT 1
    INSERT ... previous_hash = <that>

No lock between them. **SQLite hides this** by serialising writers.
**PostgreSQL does not.** Measured on PostgreSQL before any fix, 12 concurrent
appends:

| | |
|---|---|
| written | 9 / 12 |
| **rejected** (UniqueViolation) | **3 — audit events LOST** |
| **forks** (two events, one predecessor) | **1** |

The unique constraint alone was not a fix: it converted a forked chain into
lost events, which for an audit ledger is no better. And it could not stop the
fork at the ROOT, because SQL `UNIQUE` permits many NULLs — two appends against
an empty table both wrote `previous_hash = NULL`.

**Fix, shipped with the slice:**

- a transaction-scoped **advisory lock** (`pg_advisory_xact_lock`) around the
  read-then-write — the mechanism
- `UNIQUE(previous_hash)` (039) — backstop against a fork
- a **partial unique index** on `(previous_hash IS NULL) WHERE previous_hash IS
  NULL` (040) — at most one root

After, on 30 concurrent appends: **30 written · 0 rejected · 0 forks · 1 root ·
0 broken links.**

This is included in the migration rather than deferred because the migration is
what exposes it — the same reasoning that moved `project_context` alongside
`projects` in 033 to preserve atomicity. Deferring would have shipped a known
regression.

### Also fixed

`init_event_store()` emits `AUTOINCREMENT` (SQLite dialect) and runs at MODULE
IMPORT — unguarded, it broke every PostgreSQL import outright. Guarded, along
with `_ensure_platform_event_schema()`.

### Verification

`tests/test_event_store_slice.py` — 10 tests. The central one runs 24 REAL
concurrent appends and checks all four failure modes together: lost events,
forks, multiple roots, broken links.

Negative-verified: removing the advisory lock fails it; dropping either the
root index or the fork constraint fails its guard.

**Suite: 244 passed on all-SQLite AND all-PostgreSQL.** Live login 200. Ledger
left clean — no test events in either store.

### Remaining

**63 tables, 8 with data**: `fuel_unit_conversions` (120), `fuel_catalog` (10),
`approval_policies` (8), `sod_conflict_pairs` (8), `pre_cod_snapshots` (2),
`risk_flag_events` (2), `gateway_registry` (1), `risk_flag_status` (1).

Next: 6b-3 (reference data), 6b-4 (governance), 6b-5 (chained ledgers),
6b-6 (domain tail), 6b-7 (create-or-drop triage).

---

## Slice 6b-3 — Fuel reference data, MIGRATED 2026-08-09

Migration **041**. `fuel_catalog` (10) and `fuel_unit_conversions` (120).
Switch: `FUELREF_DB_BACKEND` (seventh). The most mechanical slice — with two
things that were not.

### A real foreign key, carried over

`fuel_unit_conversions.fuel_id -> fuel_catalog.fuel_id ON DELETE CASCADE`
genuinely exists in SQLite, unlike `package_evidence` in slice 5 where no
constraint existed and inventing one would have made an FK rejection look like
a copy failure. **Preserving a real constraint is not the same as adding one**,
so it came across — CASCADE and the `UNIQUE(fuel_id, from_unit, to_unit)` rule
included. Copy order matters: parent table first.

Both are tested for effect, not just presence: an orphan insert and a duplicate
conversion rule are each rejected.

### A naming collision that must NOT be reconciled

The inventory flagged "check for the duplication `fuel_defaults` has". There is
one — but it is a collision, not a duplication, and my first comparison got it
wrong:

| field | is | value |
|---|---|---|
| `fuel_catalog.specific_energy_value` | the FUEL's energy density (LHV) | H2 33.3 · NH3 5.2 · MeOH 5.5 · SAF 11.9 kWh/kg — **varies** |
| `FUEL_DEFAULTS[...]["specific_energy_kwh_per_kg_h2"]` | the ELECTROLYSER's consumption per kg H2 | **50.0 for all five** |

Different physics, similar names. Naively "reconciling" them would corrupt
either every fuel's energy content or the production formula fixed on
2026-08-08.

A guardrail pins the distinction from BOTH directions: FUEL_DEFAULTS must stay
constant across fuels, `fuel_catalog` must stay varying, and hydrogen must
remain the densest per kg. Negative-verified by setting the catalog to a flat
50.0 — two tests fail.

### RLS: open on purpose, not by omission

Both tables get RLS **enabled** with an explicit read-open policy plus an
admin-only write policy. A conversion factor is nobody's secret, and locking it
down would break unit maths for every tenant — but RLS OFF would be
indistinguishable from an oversight. A guardrail asserts a tenant CAN read it.

### Verification

`tests/test_fuel_reference_slice.py` — 9 tests, negative-verified against four
breaks: dropping the FK, flattening the catalog's specific energy, locking
reference data to admin, and dropping the duplicate-conversion guard.

**Suite: 253 passed on all-SQLite AND all-PostgreSQL.** Live login 200.

### Remaining

**61 tables, 6 with data**: `approval_policies` (8), `sod_conflict_pairs` (8),
`pre_cod_snapshots` (2), `risk_flag_events` (2), `gateway_registry` (1),
`risk_flag_status` (1).

Next: 6b-4 (governance — small but security-relevant), 6b-5 (chained ledgers),
6b-6 (domain tail), 6b-7 (create-or-drop triage).

---

## Slice 6b-4 — Governance / access control, MIGRATED 2026-08-09

Migration **042**. Seven tables, 16 rows. Switch: `GOVERNANCE_DB_BACKEND`
(eighth). Small, but these decide **who may approve what**, so they got
auth-slice scrutiny rather than domain-tail treatment.

### Four RLS shapes, because the scopes genuinely differ

Every earlier slice used one shape. Using one here would have been wrong four
different ways:

| scope | tables | policy |
|---|---|---|
| **global rules** | `approval_policies`, `sod_conflict_pairs` | READ-OPEN + admin writes |
| **project** | `approval_requests`, `sod_action_log` | delegate to the 032 helpers |
| **user** | `permission_user_overrides`, `user_signing_keys` | **admin-only — a known limitation** |
| **company** | `data_residency_policies` | `company_id` compared directly |

**Why the rules are readable by everyone.** A user who cannot read "payments
over X need two approvers" gets a refusal the UI cannot explain. A compliance
rule you cannot read is a trap, not a control. Readable by all, curated by
admin — a tenant must not be able to rewrite the rules it is judged by.

**Why user-scoped is admin-only, and why that is a limitation not a design.**
These rows belong to a USER, but the only tenant GUC is
`app.current_company_id`. There is no `app.current_user_id`, so "a user may read
their own row" cannot be expressed. Admin-only is safe today because both are
consumed platform-internally — `permission_engine.py` evaluates overrides *while
deciding* authorisation, so it cannot be filtered by that decision.

Critically they must **not** be widened to company scope: that would let a
colleague read another user's permission overrides. A guardrail asserts exactly
that, and another asserts the missing GUC stays documented in the migration so
the constraint remains discoverable.

`user_signing_keys` holds PUBLIC keys and fingerprints only — no private key
material. Not a secrets migration.

### Two coherence constraints added

- `min_approvers >= 1` — a policy demanding zero approvers is not an approval
  policy.
- `action_a IS DISTINCT FROM action_b` — an action conflicting with itself is
  not segregation of duties, it is a lockout.

Both verified against existing rows first (0 violations), so neither could turn
a copy failure into a constraint failure.

### Verification

`tests/test_governance_slice.py` — 17 tests, negative-verified against four
breaks: widening user-scope to company, hiding the rules from tenants, letting
tenants rewrite them, and permitting a zero-approver policy.

All five `init_*` functions guarded — they use `executescript()`, which does not
exist on the PostgreSQL adapter and would error rather than no-op.

**Suite: 270 passed on all-SQLite AND all-PostgreSQL.** Live login 200.

### Remaining

**54 tables, 4 with data**: `pre_cod_snapshots` (2), `risk_flag_events` (2),
`gateway_registry` (1), `risk_flag_status` (1).

Next: 6b-5 (chained ledgers, all empty), 6b-6 (domain tail), 6b-7 (the
create-or-drop triage — a decision, not a migration).

---

## Slices 6b-5 and 6b-6 — MIGRATED 2026-08-09

Migrations **043** (7 hash-chained ledgers) and **044** (35 domain tables).
42 live tables; all but four empty.

**Generated from the live SQLite schemas, then reviewed.** Hand-writing 42
tables invites transcription errors; the generator reads `PRAGMA table_info`
and the stored DDL, so column names, NOT NULLs, composite primary keys,
AUTOINCREMENT and `UNIQUE(...)` come from the source rather than from memory.
Spot-checked against the original DDL before applying.

**RLS:** 32 project-scoped tables get the standard delegation; the 10 with no
`project_id` get admin-only — the same call as `tb_*` in 036. A policy that only
appears to isolate is worse than none.

**Chain verification (6b-5):** each of the 7 ledgers gets a 3-link chain written
into the real PostgreSQL table, validated, then tampered with to confirm
detection. Everything is DERIVED from the schema — the first version hardcoded
the columns and failed on five of seven, because each ledger carries its own
required foreign key (`criterion_id`, `drawdown_id`, `settlement_id`,
`instrument_id`, `spend_wave_id`, `lot_id`) and `mass_balance_allocations`
names its digest `allocation_hash`, not `event_hash`.

`tests/test_tail_slices.py` — 13 tests, negative-verified against four breaks:
opening an unscoped table, un-FORCEing RLS, adopting a dead table, and dropping
a ledger's `prev_hash`.

**Suite: 283 passed on all-SQLite AND all-PostgreSQL.** Live login 200.

---

# Slice 6b-7 — the triage. NOT a migration.

**12 tables remain outside PostgreSQL. All are empty. All are dead.**

    covenant_compliance      drawdown_tranches       equity_contributions
    financial_metrics        pre_cod_metric_snapshots project_events
    project_stakeholders     project_states          reserve_accounts
    service_calls            state_transitions       workflow_checkpoints

### Evidence

No `CREATE TABLE`, no `SELECT/INSERT/UPDATE/DELETE`, anywhere in `app/`.

Two apparent signals were **self-generated and false**:

- *"referenced by 4-6 alembic revisions"* — those were my own 043/044 exclusion
  lists and their `.pyc` files.
- *"referenced in docs"* — this plan.

Five had source hits that are **identifier collisions, not table usage**:

| table | apparent hit | what it actually is |
|---|---|---|
| `covenant_compliance` | DebtCashflowWaterfall.tsx | a JSON field on an API response type |
| `financial_metrics` | onboarding.py | a dict key in a response payload |
| `project_stakeholders` | abac.py | a `Set[str]` dataclass field |
| `reserve_accounts` | enhanced_orchestrator.py | an enum VALUE string |
| `pre_cod_metric_snapshots` | capital_bridge.py | a comment in a docstring |

### `project_events` — a superseded predecessor

Shares **10 of 18 columns** with `platform_events` and carries
`event_hash`/`previous_event_hash` against platform's
`event_hash`/`previous_hash`, plus project-specific columns (`event_sequence`,
`previous_tr_level`, `new_tr_level`, `actor_type`, `actor_role`).

It reads as an earlier, project-scoped event store that `platform_events`
generalised. Both empty. This was flagged before 6b-5 and is now answered:
it is a predecessor, not a live parallel ledger.

### Recommendation — quarantine, do not DROP

All 12 hold zero rows, so nothing is at stake either way. The precedent set by
the `projects` collision applies: **rename, don't drop.** Reversible, costs
nothing, and proves the absence of callers over a real release cycle rather
than by grep alone.

    ALTER TABLE <t> RENAME TO <t>_quarantined_20260809;

If nothing breaks by the next release, drop them. **Not executed — this is a
subtractive change and every other slice was additive.**

### Separately: `contracts` is the opposite problem

`contracts_sqlite.py` is routed and queries a `contracts` table that exists in
NEITHER store and has no DDL anywhere. `/api/v1/contracts/summary` returns 500
today. That one needs CREATE, not DROP, with a schema derived deliberately —
and it is pinned symmetrically in `test_marketplace_slice.py` so the two stores
cannot diverge in the meantime.

### 6b-7 EXECUTED 2026-08-09 — quarantined, not dropped

All 12 renamed with a dated suffix, after confirming each still held **0 rows**:

    <table> -> <table>_quarantined_20260809

Backup taken first: `backend/data/db_backups/gex_platform.pre-quarantine.20260809.db`

Reversible by design. Drop at the next release if nothing breaks — and delete
`test_the_dead_tables_are_quarantined_not_dropped` in the same commit.

The guardrail now asserts BOTH directions: none may be dropped, and none may
reappear under its original name. Negative-verified against both.

**A gotcha worth recording:** restoring a WAL-mode SQLite database by `cp`-ing
only the `.db` file does NOT work — the `-wal` sidecar still carried both test
mutations, leaving 11/12 quarantined and one dead table revived. Repaired
forward from the pre-quarantine backup. Copy or delete `-wal`/`-shm` alongside
the main file, or use `VACUUM INTO`.

**Verification:** 283 passed on all-SQLite AND all-PostgreSQL. Live app
unaffected — login, `/projects/visible`, project context and TEA canonical all
200.

---

# Migration status after slice 6b

**Every live table is now in PostgreSQL.** 98 tables, 89 under RLS.

| slice | switch | state |
|---|---|---|
| 2 auth | `AUTH_DB_BACKEND` | migrated |
| 3 projects | — (canonical store) | migrated |
| 4 evidence | `EVIDENCE_DB_BACKEND` | migrated |
| 5 capital bridge | `CAPITAL_DB_BACKEND` | migrated |
| 6 marketplace | `MARKET_DB_BACKEND` | migrated |
| 6b-1 entitlements | `ENTITLEMENT_DB_BACKEND` | migrated |
| 6b-2 event store | `EVENTSTORE_DB_BACKEND` | migrated |
| 6b-3 fuel reference | `FUELREF_DB_BACKEND` | migrated |
| 6b-4 governance | `GOVERNANCE_DB_BACKEND` | migrated |
| 6b-5/6 tail | (covered by the above) | migrated |
| 6b-7 dead tables | — | quarantined |

**All eight switches still default to `sqlite`.** Nothing is flipped, by
design — the flip waits until `DATABASE_URL` points at the real Supabase
target, so identity and evidence are not migrated twice.

## Before slice 7 (flip and retire)

1. Point `DATABASE_URL` at the Supabase project (service-role, server-side).
2. Re-run every migrator against it — all are idempotent and record watermarks.
3. Flip the switches one slice at a time, verifying between each.
4. Then retire SQLite: ratchet to 0, drop `SQLITE_DB_PATH`, flip the
   one-.db-file guardrail to no-.db-file.

## Known defects, deliberately left for their own change

- **`contracts`** — routed, queried, exists in neither store.
  `/api/v1/contracts/summary` returns 500. Needs CREATE, not DROP.
- **`_log_event` hashes a typed object but stores `str(new_val)`** — 7 of 18
  package events are permanently unverifiable; a fix helps future events only.
- **`test_compose_runs_the_tree_that_tests_inspect`** — the one long-standing
  failure, `files/docker/` disposition still undecided.
- **No `app.current_user_id` GUC** — keeps two user-scoped governance tables
  admin-only.
