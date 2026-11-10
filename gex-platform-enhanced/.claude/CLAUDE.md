# GEX platform — working notes

Everything here was verified against the tree or the live database on
**2026-09-24**. Where a number is stated it was measured, not remembered. If
something below contradicts the code, the code wins — and fix this file.

Deeper background: `docs/CLAUDE_HANDOFF.md` (current state, defects, open
decisions). `../docs/CLAUDE.md` is an older architecture reference — useful for
product intent, stale on infrastructure, and **not** auto-loaded.

---

## Services

| Port | Service | Tree |
|---|---|---|
| 8000 | GEX backend (FastAPI) | `backend/` |
| 8001 | PF engine — project finance | **`../gex_pf_engine/backend`** (sibling repo) |
| 8002 | TEA engine — techno-economic | `tea_engine/` (stateless, no database) |
| 3000 | Frontend (Vite/React/TS) | `frontend/` |
| 55432 | PostgreSQL | container `files-postgres-1` |

**Port 55432 is not a typo.** A different, non-GEX PostgreSQL occupies `:5432`
on this machine; `55432` is a socat forwarder to the GEX container. Do not
"correct" it to 5432 — you will read or migrate the wrong database.

**`gex_pf_engine` and `deal_engine` are DIFFERENT services, not copies.**
`../gex_pf_engine` (sibling) is the Gabillon project-finance engine serving
`:8001` — cfads.py, waterfall.py, debt/sculpting.py. `./deal_engine` (renamed
2026-09-09 from `gex_pf_engine`, which is why the confusion existed) computes
deals — pre-COD, phases, ratios, COD test, TEA adapter. **They share not one
module name.** `deal_engine` has no launch.json entry and no caller: dormant,
not dead. Do not delete either as "the duplicate".

### Starting the services

Frontend, backend and TEA engine have `.claude/launch.json` entries — start those via the
Browser pane, not `Bash`.

**The PF engine has NO launch.json entry.** It is a sibling repo with its own virtualenv
and this is the agreed sequence — do not substitute another venv, port or path:

```bash
cd files/gex_pf_engine/backend
source ../micro_service/bin/activate     # gex_pf_engine/micro_service, not a repo venv
uvicorn pf_engine.main:app --reload --port 8001
```

**The package moved 2026-09-09: `app` → `pf_engine`**, so the command is
`pf_engine.main:app`, not `app.main:app`. Both repos previously had a top-level
package called `app`; whichever imported first won and the other's submodules
became unreachable. The sibling was renamed because it is 19 files against the
platform's 152. Nothing else about the sequence changed.

`micro_service` lives inside `gex_pf_engine/`, is excluded from `sync-to-docker.sh`, and is
the only interpreter this service runs under. If a future note says "run servers via
launch.json", it does not apply here — there is nothing there to run.

---

## Database — two credentials, never one

```
DATABASE_URL          gex_app    runtime.  No SUPERUSER, no BYPASSRLS,
                                 no CREATE on schema public. RLS APPLIES.
ALEMBIC_DATABASE_URL  gex_user   DDL and migrations only.
```

Migration 045 made this real. Before it, the runtime connected as a superuser
and every RLS policy was decorative. Measured on a live `gex_app` connection:
`projects` returns 14 rows as `PLATFORM_ADMIN`, **4** as tenant `etfuels_sa`,
**0** with no tenant context. (Naming the tenant matters — the number is that
tenant's, not a constant.)

**Do not collapse these back into one variable.** DDL is not subject to RLS, so
a migration running with the runtime credential — or a runtime holding DDL
rights — turns any injection into a full read of every tenant. Pointing
`DATABASE_URL` at a superuser to make a permissions error go away will be caught
by `tests/test_gex_app_runtime_role.py`, which asserts against whatever
`DATABASE_URL` is actually configured.

### Traps that cost real time

- **`ALEMBIC_DATABASE_URL` must be EXPORTED**, not merely present in `.env`.
  pydantic's `env_file` populates `settings`, *not* `os.environ`, and Alembic
  reads `os.getenv`. `alembic.ini` no longer carries a working fallback: its
  `sqlalchemy.url` is the sentinel `EXPORT_ALEMBIC_DATABASE_URL_FIRST://` so an
  unexported run aborts. It used to hold a REAL dsn on port **5432** — a
  different, non-GEX PostgreSQL that is usually listening — so an unexported
  migration did not fail, it silently migrated the wrong database.
- **`DATABASE_URL` must be exported too, for the TEST SUITE.** Same mechanism,
  different victim: ~20 tests gate on `os.environ["DATABASE_URL"]`, so running
  the documented pytest line with only `.env` present silently skips **125**
  tests — including the RLS and tenant-isolation ones — and still reports green.
  Export both before measuring anything.
- **Alembic uses branches.** `030` is an independent root labelled `auth_slice`.
  Upgrade with `alembic upgrade auth_slice@head`, never bare `head`.
- **`Settings` forbids extra inputs.** A new environment variable must be
  declared in `app/core/config.py` or the app refuses to start.
- **WAL-mode SQLite.** Copying only the `.db` file does not capture state; the
  `-wal` sidecar carries changes forward and silently reverts part of a restore.
  Copy/remove `-wal` and `-shm` too, or use `VACUUM INTO`.

### Migration state

**2026-10-13: the database was RESTORED FROM DUMP after a second loss.** By 09:45 UTC on
13 Oct, both `files-postgres-1` and the `files_postgres_data` volume no longer existed —
only `gex-pg-forward` survived, so :55432 accepted connections and then dropped them
("server closed the connection unexpectedly"). What removed them is not recorded. It was
restored from `db_backups/daily/gex_platform_2026-10-12_1236.dump`; **writes after 12 Oct
12:36 local are lost.** This time no migrations and no copiers ran — the dump carries schema
at 059 and every row. See `docs/CLAUDE_HANDOFF.md` §8 item 43 and the restore steps under
*Backups* below.
**When the container is MISSING, `docker start` cannot fix it.** Check `docker ps -a` and
`docker volume ls` first. If the volume is gone, restore from the newest dump. Do not run the
Alembic rebuild drill.

**2026-09-30: the database was REBUILT after the 28 Sep reset.** It was empty from
28 Sep 16:14 (compose project `files` recreated on a new `files_postgres_data` volume,
fresh `initdb`) until 30 Sep. `docs/CLAUDE_HANDOFF.md` §8 item 38 records the rebuild and
what it cost. Schema is back to the pre-reset measurement exactly; **103 of 114** tables
match the 23 Sep baseline (`backend/db_backups/pg_after_kyc.json`) row for row.

**A Time Machine restore of the volume was never possible.** Item 38 used to offer one.
`Docker.raw` is **excluded** from Time Machine — Docker Desktop sets that exclusion itself —
so no backup of the volume has ever existed on this machine. Verify with
`tmutil isexcluded ~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw`
before anyone proposes that route again. **`pg_dump` is the only backup that works here.**

**2026-10-19: head is 061** (branch `reference-data-registry`). 060 added
`screen_access_rules`; 061 adds `reference_parameter` and `reference_version`, the
reference data registry (`app/core/reference_registry.py`, `/api/v1/reference`). Measured
after 061 by `pg_class relkind='r'`: **123** tables, **116** FORCED. 061's value columns are
immutable for every role (trigger); `gex_app` holds SELECT, INSERT and column-level UPDATE
on the lifecycle columns only. Seed rows carry `proposed_by = 'MIGRATION_061'`; four were
seeded `proposed`, not approved, because their source could not be confirmed on 10-19.
JML's decisions the same day were applied through the lifecycle by
`backend/scripts/apply_reference_decisions_20261019.py` (idempotent; **re-run it after an
Alembic rebuild**, a dump restore already carries it): `ehb_premium` base 0.40 -> **0.20**
(new row, valid from 10-20), and `debt_gearing` 0.65 approved with OIES kept. Versions 1-3;
three rows remain `proposed` (IEA capex ROW and CN, 45V).

**2026-10-28: head is 078** (072–075 are the TEA session's). 076 bankability reports, 077 premise
changes (document + second party), 078 contract tokens (only counterparty/reviewer-confirmed terms
reach the engine). PF engine rules **4.2.0** (UNRESOLVED). Gate figures come from the engine only
(`app/core/engine_view.py`); `project_profile` holds no assessments. **After an Alembic rebuild**:
the 076–078 tables start empty; 077 records the pre-rule premises itself. Handoff §8 item 52.
Tests: **1202 pass, 15 skip, 0 fail**, both exported, run alone (never beside another pytest: they
share `gex_test_suite`).
**2026-11-06: head is 084 — one contract record, Phase 1** (handoff §8 item 56; `docs/CONTRACT_RECORD_PHASE0.md`).
- **Agreed matches:** an agreed market match now creates its contract in 065/083
  (`trading_book/record.py`, the one writer) in the same transaction. `contracts` (063) is no
  longer written.
- **Order book:** `/api/v1/trading-book/{orders,rfqs,records}`. TRADE_CONFIRM is four eyes
  inside each party (`core/wae.py`).
- **Do NOT redefine `app_company_can_see_capacity`:** despite its name it is the generic "may
  see this PROJECT" helper used by eight policies (063–069). Capacities resolve through
  `app_company_sees_capacity` / `app_company_owns_capacity` (084).
- **Parity check:** `backend/scripts/engine_parity_snapshot.py --out after.json --compare
  before.json` is the read-only gate-engine parity check. It also compares the contract-token
  readout. Run both sides the same day.
**2026-11-06 (later): head is 085 — Phase 2: the 078 contract tokens live in the one record.**
- The gate engine reads `v_engine_contract_terms`.
- `core/contract_tokens.py` and `/api/v1/contract-tokens` are a DEPRECATED compatibility layer
  (same shapes, same refusals).
- The 078 tables are read-only history; Phase 3 drops them.
- A card save and its version are ONE transaction (503 `CONTRACT_RECORD_UNAVAILABLE` on
  failure), so card tests need `pg_store`.
- **A `pg_store` module must save, reset and restore `app.db.session._sync_engine`** (see
  `test_commitment_terms._seeded`), or the throwaway URL leaks into every later module.
- Platform **1351 pass / 15 skip**.
**2026-11-10: head is 091 — Phase 3 M3–M6: one contract model, the old stores dropped** (handoff §8 item 58).
- 086 capacities for `v_position`; 087 the market on the order model (listing = firm sell
  `tb_order`, RFQ = `tb_rfq`, proposal = invited `tb_order`); M4 `trading_book/flows.py` prices
  record flows (T10: the old engine's 180 lines to the cent).
- **Dropped:** 088 the JTI contract model (subtype tables, ten `tb_contract` columns);
  089 `contracts` (063); 090 the 078 tables (downgrade rebuilds them from the record);
  091 `offers`/`rfqs`/`matches`. Each refuses while anything is unconverted.
  `test_marketplace_slice` pins that they stay dropped. **151** tables, **144** FORCED.
- Platform **1361 pass / 15 skip** (both exported, run alone).
- **036 builds from `trading_book/models_036.py`** (frozen). Never point it back at the live
  models: a fresh rebuild then fails at 036. Never edit `models_036.py`.
- A link (`tb_project_finance_link`) admits a PARTY to the contract (seller: revenue; buyer: a
  cost), not only `owner_company_id`. A projection states `withheld_contract_count` for linked
  contracts the caller may not read (a `trade` is party-only, Q5).
- On a database still holding `offers`/`rfqs`/`matches` rows, run
  `python -m app.trading_book.migrate.market_to_orders --execute` at 090, before 091.
**2026-11-10 (later): head is 093 — Phase 3 step 4** (handoff §8 item 59).
- **The offtake frame (092):** an offtake card with `buyers` is one record with a `card` sub-leg
  per buyer; each buyer confirms its own (`/contract-tokens/{p}/offtake/buyers/{c}/confirm`). The
  engine reads ONE offtake card from `v_engine_offtake_buyers` by JML's conservative aggregate
  (`contract_tokens.frame_engine_card`). A buyer reads only its own sub-leg (092's RLS).
- **Adverse facts are events (Q10):** reported with a document on file, applied at once, cleared
  by two other companies; `BUYER_INSOLVENT` drops one buyer. A card that says true still applies.
- **The cards ARE the record (Q9, 093):** `commitment_terms` is gone. Read cards with
  `contract_tokens.card_view` / `card_terms`; a save writes versions only. Fixtures write cards
  through `scripts/_fixture_record.py`. Never write a card anywhere else.
- **Novation (Q13):** three confirmations (producer, outgoing, incoming) on the frame's chain.
- `/finance/contracts` lists the record contracts the caller's company sells.
- **Q6.4 (094, JML: lock it, keep as trade):** with a planned output recorded, an accepted
  market trade becomes the buyer's LOCKED sub-leg of its project's frame (it names the trade;
  the card cannot change or drop it; its buyer confirms it with the four-eye TRADE_CONFIRM); an
  acceptance past the planned output is refused. Without one it stays a trade. Head **094**.
- Platform **1394 pass / 15 skip**, frontend **260**.
**2026-11-10 (latest): head is 096 — Phase 5: party signatures, recorded and verified, NOT required** (handoff §8 item 61).
- A CONFIRMED/DISPUTED event MAY carry ed25519 over `"GEX-CONTRACT-EVENT-v1:" + event_hash`, beside
  the hash (hashes and anchors unchanged).
- Two calls: `signature_intent: true` returns the hash and writes NOTHING; then send `signature`.
- Only the first act of the caller's company inside `record.party_act` is signed.
- Keys: `/api/v1/trading-book/party-keys`. An executive proposes, a SECOND executive activates;
  each step is in the ledger before commit.
- `REQUIRE_PARTY_SIGNATURE` defaults to false.
- A pg_store test's manual rollback on the shim connection drops its tenant setting: reopen it.
- Platform **1433 pass / 15 skip**, frontend **264**. **151** tables, **144** FORCED.
**2026-11-10 (earlier): head is 095 — Phase 4: the ledger anchor, built and OFF** (handoff §8 item 60).
- Every contract event writes one `ledger_anchor_outbox` row BY TRIGGER, in its own transaction.
  `gex_app` reads it (the record's RLS) and writes nothing.
- New role **`gex_anchor`** (setup script; restore step 5 grants it CONNECT too): SELECT on the
  outbox and UPDATE on its anchoring columns only.
- `tb_contract.pseudo_id` = HMAC(`LEDGER_ANCHOR_SALT`, contract_ref), fixed by trigger. **The salt
  never rotates** and lives in `.env` only.
- `LEDGER_ANCHOR_BACKEND = none | hedera_testnet` (default none: no worker). Mainnet is not a value.
- `scripts/drain_anchor_outbox.py`, `scripts/verify_anchor.py`. A fixture removal deletes its
  outbox rows too.
- Platform **1422 pass / 15 skip**, frontend **263**. **150** tables, **143** FORCED.
**2026-11-05: a paused Docker Desktop used to hang the sweep and the suite** (port 55432 accepts, nothing answers). `app/core/config.py` defaults `PGCONNECT_TIMEOUT=10`; the sweep has a thread watchdog (exit 4). Check `docker info` first. Platform **1307 pass / 15 skip**, engine 275.
**2026-11-03:** tenant `mohring_energie` created (`scripts/onboard_fortaverde_client.py`; users not yet registered, no telephone numbers). The Project Profile no longer invents verification: a recorded value is SUBMITTED, a missing one UNVERIFIED, nothing is CONFIRMED there and its click-to-confirm is gone. A missing CAPEX or coordinate is null end to end, not 0. A 401/403 readout now says "No access to this project's gates", not "Gate engine unavailable". **GEX staff read-only (JML, same day):** ABAC rule **R0P**, before R0, lets `is_platform_admin` READ `GATE_EVALUATION` and `EVIDENCE` on every project — nothing else: writes, verification, export, share, financial models, contracts, data rooms and activity still meet R0 (an admin with no project role is GUEST there). `tests/test_platform_read_only.py` (25), negative-verified three ways. Platform **1259 pass / 15 skip**, frontend 233.
**2026-11-03 (later): GEX staff console** (`/gex-console`, CISO menu, service type PLATFORM only; JML). `routes_gex_console.py` (`/api/v1/gex-console`, domain `platform`) is GET-only and `is_platform_admin`-only: admins, companies (TEST flagged), staff rights (from R0P and `REVIEWER_GATES`), per-company onboarding steps read from the records (a registered account is matched by its `pending_…` id + company name). Its actions post to the existing `/api/v1/account/{id}/…` endpoints, which enforce separation of duties. A read failure answers 503, never zeros. **Temporary password (JML exception to the onboarding rule):** `onboard_fortaverde_client.py --register --temporary-password --execute` reads one at a getpass prompt and writes `account.temporary_password_set`; Still blocked on the two telephone numbers. Platform 1267 / 15 skip (`test_gex_console_pg.py` 8, negative-verified three ways), frontend 238.
**2026-11-03 (latest): owners change their own password** at `/account/password` (key button in the top bar). `POST /auth/change-password` existed with no caller and no test: a policy refusal was a bare 500, the same password passed, other sessions survived and nothing reached the ledger. Now: 422 with the policy's reason, same password refused, every refresh token revoked and a new one returned for this session, `account.password_changed` in the ledger. `GET /auth/password-status` states the rule and whether a GEX-chosen temporary password is still in force (last of `temporary_password_set` / `password_changed`); a banner asks on every screen until it is changed. `tests/test_change_password.py` (8, negative-verified four ways), `ChangePasswordPage.test.tsx` (5). Platform **1275 pass / 15 skip**, frontend **243**.
**2026-11-04: head is 082 — the PF engine keeps nothing in SQLite (JML).** It had two SQLite uses: its pricing run log (`gex_pf_engine/backend/engine_model_runs.db`, 665 runs + 1 parameter change, outside every backup) and the fuel catalogue, read from the platform's retired `gex_platform.db` with `gex_fuel_catalog.json` as fallback. Now: **082** adds `engine_model_runs` and `engine_param_change_events`, append-only, FORCED RLS, written by a new role **`gex_engine`** that holds SELECT + INSERT on those two tables and nothing else; `gex_app` holds nothing on them (082 asserts both). The engine reads `GEX_ENGINE_DATABASE_URL` from `gex_pf_engine/backend/.env` (git-ignored, random password), which `start_pf_engine.sh` loads; without it runs are stamped `run_logged: false`, never written elsewhere. The offered fuels come from the platform's public `/api/v1/onboarding/reference-data/fuels` (cached 60 s, 503 `FUEL_CATALOGUE_UNAVAILABLE` if it cannot answer; no fallback). That route's `"source"` said "sqlite" unconditionally; it now names the store read. The 665 runs were copied by `gex_pf_engine/backend/scripts/migrate_run_log_to_postgres.py` (idempotent, verifies); the SQLite files are kept as `*.migrated-2026-11-04`. **`gex_engine` is a role, so a restore needs it first:** `setup_postgres_rls.sql` now creates it, and step 5 below grants it CONNECT; its password is then reset with `ALTER ROLE gex_engine PASSWORD` to match the engine's `.env`. That script also REVOKEs `gex_app` from the two tables unconditionally (its grant loop would otherwise hand them over). Tests: platform `test_engine_run_log_pg.py` (12, rolled back), +2 in `test_fuel_reference_slice.py`; engine `test_run_log_and_fuels.py` (9) and an autouse guard in its conftest that keeps every engine test off the dev database and the live platform; four deliberate breaks all caught. Platform **1304 pass / 15 skip**, engine **275**. The :8000 backend currently runs with `--reload`. Docker images: `pf_engine` needs `GEX_ENGINE_DATABASE_URL` and `GEX_PLATFORM_API_URL` (→ the backend service) in compose, and the rebuilt image carries psycopg2.

**2026-11-04 (latest): `gex-pf-engine:v1.10.0` pushed, compose pinned to it.** Compose's engine also needed `GEX_JWT_SECRET` = the backend's `SECRET_KEY` — without it every backend→engine call was 401. Clean-pull test passed (run logged, 669 → 670). **The Docker VM disk is only 7.8 GB and PostgreSQL shares it:** an image build filled it and PostgreSQL crashed into recovery twice (data intact, backup `gex_platform_2026-11-04_1641.dump`). Check free space before building; `docker builder prune -a -f`. `tea_engine` had the same gap; compose now sets its `GEX_JWT_SECRET` and `GEX_JWKS_URL` (→ backend), tested 200 / 401 / 401. Handoff §8 item 55.
**2026-11-04 (later): the Docker backend runs as `gex_app` on PostgreSQL** (`files/gex-demo-compose.yml`). It connected as `gex_user`, the superuser, and set none of the ten `*_DB_BACKEND` switches, which all default to `sqlite` in `config.py` — so the container kept most data in a SQLite file inside itself and every tenant policy was moot. Now `DATABASE_URL` and `CANONICAL_DATABASE_URL` use `gex_app` and all ten switches are `postgres`, as on the development backend. Passwords come from `files/.env` (`GEX_APP_DB_PASSWORD`, `GEX_ENGINE_DB_PASSWORD`; git-ignored, mode 600), never from the compose file. Verified by starting only `backend` (`up -d --no-deps`): connected as `gex_app` (no superuser, no BYPASSRLS), `projects` 0 with no tenant and 4 as `hamburgone_com`, no errors; then stopped again.

**2026-11-03 (last): head is 081 — `auth_users.telephone`** (backup `gex_platform_2026-11-03_1414.dump` taken first; round-tripped). Registration writes it (the `vetting_note` text stays the record of what was supplied); the owner reads/changes it with GET/PUT `/auth/telephone`, on the existing `/account` page (key button); each change is `account.telephone_changed` WITHOUT the numbers. The staff console shows it and prefills "Number called". **PostgreSQL only (JML):** no SQLite mirror of the column; registration, every vetting step (`routes_account_vetting._conn`) and the account self-service routes (`routes_auth._require_postgres`) answer 503 `POSTGRES_REQUIRED` unless AUTH_ and EVENTSTORE_DB_BACKEND are postgres. `test_telephone.py` (10) and `test_change_password.py` (9) run on `pg_store`, not `isolated_store`; guards negative-verified. Both Möhring users carry the same telephone number in `fortaverde_client_accounts.json` (JML; one number for both). That file holds real client contact data and is kept out of git (`co-work/.gitignore`, JML 2026-11-04); registration not yet run. Note: `/account` (features/auth/AccountPage.tsx) still has a 2FA button that does nothing and invents three sign-ins when the history call fails.
**2026-11-03 (16:05): blank login page for a PENDING account — FIXED.** Jan Block (Möhring) signed in with the correct password; `/auth/login` answered 403 with an OBJECT `detail` (`account_not_active`, `account_state` PENDING, `reason`), which `LoginPage` rendered as a React child: it threw, and with no error boundary the page went blank. Every earlier account was ACTIVE, so this path had never run. `loginErrorText()` now shows `reason` (or a string `detail`). `LoginPage.test.tsx` +3 (the 403 case negative-verified: the old call site reproduces the crash). Frontend **247 pass / 1 skip** (run in a Linux copy, not on this Mac). Backup of the two files and this one: `files/_claude_backups/2026-11-03_login_blank_screen/`. Jan Block's account is registered and PENDING (server's answer at 16:05); Sascha Möhring's state was not checked.
**2026-11-03 (16:45): FortaVerde demo sign-ins under the contacts' names (JML's decision, overriding the 12 Oct "no real names" rule for these two).** `scripts/create_fortaverde_demo_accounts.py` (dry run by default; `--execute` asks ONE demo password at a getpass prompt and checks it against `password_policy` for each account, so demo1234 is refused; `--remove --execute`) writes `usr_demo_fv_moehring` / `usr_demo_fv_block` = "Sascha Möhring (demo)" / "Jan Block (demo)", `…@fortaverde.test`, EXECUTIVE, ACTIVE, `activated_by = DEMO_FORTAVERDE_NAMED`, in the fixture tenant `test_fortaverde` (they see `proj_TEST_fortaverde_pecem`). Vetting bypassed and the row says so; vetting_note starts with `TEST_FIXTURE_FORTAVERDE`, so the fixture's `--remove` (and its `--execute`, which removes first) deletes them too: re-run this script after reloading the fixture. Refuses to touch any row it did not write; never reads or touches the real accounts (tenant `mohring_energie`). Login page: group "FortaVerde Pecém (TEST) · own password"; "fill" puts in the address only. Tests: `tests/test_fortaverde_demo_accounts.py` (3, pure, marker check negative-verified), `LoginPage.test.tsx` +2 (fill negative-verified); frontend 249 pass / 1 skip in a Linux copy; tsc not run (timed out there). First `--execute` (16:55) stopped before writing: `fx.Knowledge.load` runs `validate_fortaverde_knowledge.py`, which puts `gex_pf_engine/backend` first on sys.path, so a later `import app` hit the PF engine's alias guard. Fixed by importing the platform's `app.core` modules before the fixture module; a 4th test pins the order (negative-verified). Lesson for any script that loads the knowledge record: bind the platform `app` first.
**2026-10-31 (head is 080, rules 4.8.0):** `REFINANCING_ELIGIBLE` = G11 + 12 months since `schedule.actual_cod_date`; `project_gate_clock` records each gate's first satisfaction (append-only). Engine 266, platform **1234 pass / 15 skip**, frontend 232. The :8000 backend has no --reload — restart it after backend changes.
**2026-10-31 (rules 4.7.0):** G10's `equity_injected` reads "Funds Committed to This Project" — a board approval alone does not count. Engine 261.
**2026-10-31:** a gate shows "N submitted, not independently verified" beside its verified count (engine `submitted_count`; counts for nothing). Engine 260, platform **1228 pass / 15 skip**, frontend 232.
**Stack self-start (INSTALLED 2026-10-31, with the expiry sweep; check `launchctl list | grep gex`):** `files/start_stack.sh` + `com.gex.stack-up.plist` bring PostgreSQL back after a Docker restart (never recreating a missing container: exit 12), `start_pf_engine.sh` + `com.gex.pf-engine.plist` keep the PF engine on :8001. Install commands in each plist.
**Expiry sweep:** `files/com.gex.expiry-sweep.plist` is installed (2026-10-31; remove commands in its header). It needs PostgreSQL and the PF engine up; exit 2 = database unreadable, 3 = a project not re-evaluated.
**2026-10-31: rules 4.6.0** — the instruments that lapse in practice (lease, permits, grid reservation, credit support and EPC security, insurance) default to 12 months from verification and count for nothing with no date at all (`EXPIRY_REQUIRED`). Engine 259, platform **1219 pass / 15 skip**, frontend 230.
**2026-10-30 (latest): head is 079, rules 4.5.0** — evidence expires: `bankability_evidence.valid_until`; engine 252, platform **1215 pass / 15 skip**, frontend 230; backup taken before 079. `scripts/expire_evidence.py` is the sweep (not scheduled). After an Alembic rebuild nothing special: the column is nullable.
**2026-10-30 (later): rules 4.4.0** — an advisory never blocks a gate; the "warning" tier is labelled "Required" (identifier unchanged). Engine 246, platform 1205 pass / 15 skip, frontend 230. 92 open evidence requests (56 assigned) since the 7 raised for Rheinwerk by scripts/raise_requests.py. The EPC security package is reviewed independently, not verified by the contractor's confirmation.
**2026-10-30: rules 4.3.0** (handoff §8 item 52): `CREDIT_APPROVED` reads "Ready for credit decision", G6/G8's sponsor-protecting items apply to balance-sheet projects too (no gate is waived wholesale), a state is never reached on waivers alone, and the offtaker's confirmation no longer verifies `credit_support_package`. Measured: **1203 pass, 15 skip, 0 fail**; engine 243; frontend 230/230. If PostgreSQL refuses connections after a Docker restart, `docker start files-postgres-1` (it was stopped on 30 Oct; nothing lost).

**2026-10-25 (part 3): head is 071** — `project_dataset` takes the 16 kinds the screens held in
code; `GET /api/v1/projects/{id}/datasets/{kind}`. **After an Alembic rebuild also run
`move_frontend_datasets_20261025.py --execute`** (last). WAE and CSS now act as the token's
account in its tenant. Handoff §8 item 51. 145 tables, 138 FORCED.

**2026-10-25 (earlier): head is 070** — `information_barrier` for the CISO workspace, which now
serves real data only; **145** tables, **138** FORCED. GEX staff open a client's CISO view with
header `x-ciso-company` (never `x-demo-company`: the fetch bridge sets that on every request).
Handoff §8 item 50.

**2026-10-25 (later): head is 069** — `project_dataset` and `project_id_alias`; **144** tables,
**137** FORCED. Add `move_project_datasets_20261025.py` to the after-rebuild list below (last).
A project with no recorded dataset gets none: deal-killers active, structuring 404
`STRUCTURING_CONTEXT_NOT_RECORDED`. Handoff §8 item 49.

**2026-10-25: head is 068.** 067 records who confirmed a Marketplace record; 068 adds
`project_profile` (jsonb) and `project_risk_flag`. **142** tables, **135** FORCED. Project data is
PostgreSQL only — no backend dictionary, no frontend array (a TEST fixture lives in
`frontend/src/test/fixtures/`). **After an Alembic rebuild run, in order:**
`load_marketplace_unverified_20261023.py`, `apply_marketplace_decisions_20261025.py`,
`move_project_registry_20261025.py`, `move_project_profiles_20261025.py` (all `--execute`,
idempotent; a dump restore carries their rows). Handoff §8 item 48.

**2026-10-23 (late): head is 066** — Marketplace records (`project_sales_detail`,
`project_input_line`, `input_classification`, `tb_commodity.registry_pathway`), all UNVERIFIED.
**140** tables, **133** FORCED. Rows come from
`backend/scripts/load_marketplace_unverified_20261023.py --execute` — **re-run it after an Alembic
rebuild** (a dump restore already carries them). Its five spot prices are registry rows in state
`proposed`, never in force until approved. Handoff §8 item 47.

**2026-10-23 (later): head is 065** — the trading-book revision's M1: terms → legs → flows,
orders, RFQs, fills, contract versions, frozen-terms trigger, per-party views (security_invoker).
**137** tables, **130** FORCED. JML's decisions and the remaining steps M2–M6: handoff §8
item 46. Automated matching is OFF (`MARKET_AUTO_MATCHING`) pending counsel. **036 now builds only
its original eight `tb_*` tables** — never let a migration create tables from the live models
wholesale: a later model would be created early on a rebuild and collide with its migration.

**2026-10-23: head is 064.** 063 creates `rfqs` and `contracts` and lets the buyer read its
own matches, contracts, settlements and the token it bought (`holder_company_id`); 064 gives
`tb_asset` a `project_id` and `tb_contract` an `owner_company_id` and replaces 036's admin-only
`tb_*` lock with real policies (SECURITY DEFINER lookups — the first draft recursed). Both
round-tripped. Measured after: **125** tables, **118** FORCED. Handoff §8 item 45.

**2026-10-21: head is 062.** 062 replaces `project_access`'s single FOR ALL policy (no
WITH CHECK, so the read rule was the write rule) with a SELECT policy keeping the old read
rule and INSERT / UPDATE / DELETE policies that require `PLATFORM_ADMIN`. Before it, a
tenant could insert a row granting ITSELF access to any project — reproduced as madrid2_com
on proj_hamburgone_emethanol, 47 evidence rows then readable (rolled back) — and every
policy that calls `app_company_has_project_access` fell with it. Granting access is GEX
administration (only `tenant_admin` and `reviewer_appointments` write it, both as
PLATFORM_ADMIN; fixture scripts run as gex_user and are unaffected); an owner cannot grant
either, deliberately. The migration asserts the four policies and FORCED RLS; round-tripped
down to 061 and back. Measured after: 123 tables, 116 FORCED.
`tests/test_project_access_writes_pg.py` (6) failed 4 before 062 and passes after. The other
access tables were scanned the same day: GEX-only, or a company's own settings, or grants on
projects it owns — none has this flaw. Note `auth_user_project_roles` and `auth_users` carry no
RLS by design, so role rows are protected by the application alone.

**2026-10-21: 061 was MISSING and has been re-applied.** The 20 Oct recovery (a
`down -v` wiped the volume) restored `gex_platform_2026-10-19_1721.dump`, but 061 was
applied *after* 17:21 that day — its file is stamped 17:19 — so the restore came back at
**060** and no dump since carried the registry. Symptom: 5 FAILs in
`test_reference_routes.py` (`relation "reference_parameter" does not exist`) and 23 extra
skips, i.e. 934 pass / 41 skip / 5 fail. Fixed by `alembic upgrade auth_slice@head` and
`apply_reference_decisions_20261019.py --execute` (backup taken first): head 061, 123 tables,
116 FORCED, registry 10 approved / 3 proposed / 1 superseded, versions 1-3. **Lesson: after
any restore, compare `alembic_version` with `alembic heads` — a dump can predate the last
migration even when it postdates the migration's file.**

PostgreSQL holds **120** tables in schema `public` (incl. `alembic_version`) at head
**059**, **113** under FORCED RLS — measured 2026-09-28 before the reset and again
2026-09-30 after the rebuild, by `pg_class relkind='r'`; both runs agree. 058
added the two commitment-card tables (rules 4.0.0; `docs/CLAUDE_HANDOFF.md` §8 item 34).
059 adds no table — it only restores privileges, so the count is unchanged.
(This file once said 119 at 053 by another method. Re-measure rather than reconcile.)

**Rebuilding is a known drill — it has now been done twice** (2026-09-08 and 2026-09-30).
The order matters and two steps are easy to get wrong:

1. `scripts/setup_postgres_rls.sql` runs **FIRST, before Alembic, and ONCE** — 24
   migrations reference `gex_app`. It creates the role with its own default password; if
   `.env` carries a different one (it did), set the `.env` password or the runtime still
   cannot log in and the failure reads as "password authentication failed".
   **Do not re-run it after Alembic.** Its own comment used to invite that, and doing so
   on 30 Sep silently re-granted UPDATE on three append-only audit tables, undoing
   migrations 056 and 058 — see the Tests section. The script is now safe to re-run
   (it grants only to tables holding no `gex_app` privilege at all), but the migrations,
   not this script, are the authority on privileges. If you re-run it, re-check grants:

       docker exec files-postgres-1 psql -U gex_user -d gex_platform -c "SELECT table_name, \
         string_agg(privilege_type, ', ' ORDER BY privilege_type) FROM \
         information_schema.role_table_grants WHERE grantee='gex_app' AND table_name IN \
         ('evidence_events','bankability_evidence_archive','commitment_terms_events') \
         GROUP BY 1;"

   Correct answer: archive `SELECT`, the other two `INSERT, SELECT`. Any `UPDATE` there
   means the append-only guarantee is off again.
2. `alembic upgrade auth_slice@head`, **never `heads`**. There are two roots: `auth_slice`
   (030→059) and a legacy `001→011` whose tables 042/044 already own. Upgrading `011`
   fails on `relation "matrix_rooms" already exists` — that is correct, not a problem.
   `alembic_version` holds **059 alone**. `cutover_postgres.py:116` corroborates the
   branch point in a comment ("auth_slice@head, never 'heads'") — it names no revision
   number, so it does not go stale as the head moves.
3. `scripts/cutover_postgres.py --execute` runs 8 copiers. It does **not** run
   `migrate_directory_slice.py` or `migrate_workspace_slice.py` — run those separately or
   `directory_roles`, `canvas_blobs` and `user_plants` stay at 0.
4. **Do not override `DATABASE_URL` for `migrate_workspace_slice.py`.** It copies with
   `ALEMBIC_DATABASE_URL` but verifies with `DATABASE_URL`, which must be the `gex_app`
   runtime role — 050's policies have no admin clause. Verified as `gex_user` it reports
   4× the rows (500→2000: every owner seeing all 500, summed over 4 owners) and claims the
   owner policy does nothing. Both are artifacts of the wrong verify role, not bad data.
5. `scripts/restore_registry_projects.py --execute` returns 5 projects + 2 tenants from
   `frontend/src/data/customerProjects.ts`, then
   `scripts/restore_retired_collision_projects.py --execute` returns the last 2 from
   SQLite's `projects_retired_pg_collision_20260807`. 7 (migration 020) + 5 + 2 = **14**.

**Docker Desktop restarts leave PostgreSQL stopped.** `files-postgres-1` has restart
policy `no`; after a Docker restart the forwarder on 55432 is up but refuses queries.
`docker start files-postgres-1` (happened 2026-09-14 and 2026-09-28, nothing lost).

**New tables inherit full DML for `gex_app`.** Migration 031 set DEFAULT PRIVILEGES, so a
`GRANT SELECT` on a new table restricts nothing — only `REVOKE` does. 056 found the
"append-only" `evidence_events` updatable and deletable by the runtime since 034.

**One project in the database is a TEST fixture, and 32 evidence rows with it.**
`proj_TEST_gates_reference` ("TEST — Gates Comprehension Reference (synthetic)", owner
`hamburgone_com`) was loaded 2026-10-02 on JML's instruction for the first-use comprehension test
(`docs/usability/`). That is why `projects` holds **15** and `bankability_evidence` **117** — the
85 real open requests are untouched. Every fixture row carries
`submitted_by = 'TEST_FIXTURE_COMPREHENSION'`; that marker is how you find them, and
`backend/scripts/load_comprehension_test_project.py --remove --execute` deletes the lot by project
id. The item list is derived from the running engine, so the fixture cannot drift from the rules;
`--verify` re-checks it against the published answer key, and caught a prefix bug the first time
it ran (`"G10"[:2] == "G1"` had pulled G10 and G11 into the fixture). The rows exist in
PostgreSQL only, which is the single tolerated break in SQLite↔PostgreSQL evidence parity:
`test_evidence_slice.py` excludes the marker and a second test pins the exception to projects
named `proj_TEST_`. Both were negative-verified. **Do not treat a fixture row as a client
submission**, and do not copy them into SQLite to "restore parity".

**A second TEST fixture: FortaVerde (Pecém), loaded 2026-10-12** by
`backend/scripts/load_fortaverde_test_project.py` from `fortaverde_knowledge_v2.json` (route
chosen by JML 2026-10-09). It adds project `proj_TEST_fortaverde_pecem` (tenant
`test_fortaverde`) and two stand-in accounts, `usr_test_fv_p1` and `usr_test_fv_p2`, and
**no** evidence rows. That brings `projects` to **16**; `bankability_evidence` stays at
**117**. `usr_test_fv_p1` is ACTIVE on purpose (`--activate`, JML 2026-10-12). It bypasses
vetting and its row records that with `activated_by = 'TEST_FIXTURE_FORTAVERDE'`.
`--remove --execute` deletes the fixture. Measured in the 13 Oct restore.

**All evidence rows before 2026-09-26 were invented** — the 125 `demo_seed` rows and the two
under Anna Keller's and Thierry Groell's names alike. They are archived in
`bankability_evidence_archive`; the live table holds 85 open requests assigned to real
accounts (`scripts/convert_invented_evidence.py`). Do not restore them, and do not treat
any archived row as a client submission.

**The switches are done — the cutover is not.** All **ten** backend switches now
read `postgres`: `AUTH_`, `CAPITAL_`, `DOMAIN_`, `ENTITLEMENT_`, `EVENTSTORE_`,
`EVIDENCE_`, `FUELREF_`, `GOVERNANCE_`, `MARKET_`, `WORKSPACE_DB_BACKEND`. (This
file previously said all eight read `sqlite`; there are ten, and none do.)

**2026-10-23: the market and trading area has no SQLite path at all** (JML). Capacities,
tokens, offers, RFQs, matching/mandates, contracts, settlements, carbon attribution, chain of
custody and the trading book call `db_backend.require_postgres()` and answer 503
`POSTGRES_REQUIRED` rather than open `gex_platform.db`. The `_sqlite` in their file names is
historical. Do not add a SQLite fallback back — `test_marketplace_slice.py` will fail.

**One module is switch-blind; the real defect is elsewhere.** An earlier version
of this file named four — `ecosystem_store`, `ot_boundary`, `adversarial_reviews`,
`canonical_ledger` — from a `grep` for `sqlite3.connect` that did not check
whether the call sites were guarded. Three of the four were already correct
(verified by AST 2026-09-24):

- `ot_boundary` and `adversarial_reviews` both open with
  `if domain_is_postgres(): return domain_connection()` and both `init_*_db()`
  return early on postgres because **044** owns their tables. Their remaining
  `sqlite3.connect` lines are the SQLite *branch* of that conditional.
- `canonical_ledger` takes its SQLite path only under `if sub == "sqlite-dev"`,
  and `substrate()` *refuses* that waiver when `domain_is_postgres()` — it was
  written to prevent exactly this split-brain. It currently resolves to
  `unconfigured` (no `CANONICAL_DATABASE_URL`), so it raises `SubstrateError`
  rather than touching SQLite at all. Note that means `routes_tea.py` paths
  through it fail closed.
- `ecosystem_store._conn()` **is** unguarded. Its `init_db()` correctly refuses
  to create tables on postgres ("refusing to create them unprotected") but its
  data path always opens SQLite. Its switch is read with `os.getenv
  ("ECOSYSTEM_DB_BACKEND")` and is **not** declared in `config.py`, so it is not
  one of the ten. Its two tables exist in neither store, so it is dormant.

**The defect that matters is unguarded READS.** 8 modules read **18**
PostgreSQL-owned tables out of SQLite with no `*_is_postgres()` check:

    api/v1/adjacency.py               adjacency_cache, evidence_ledger, projects
    api/v1/lineage.py                 capacities, carbon_attribution_events,
                                      development_packages, evidence_ledger, offers,
                                      projects, sovereign_instruments, tokens
    api/v1/next_best_action.py        drawdown_schedules, model_base_case, pathway_claims
    api/v1/routes_project_activity.py bankability_evidence, bankability_snapshots
    api/v1/routes_project_truth.py    capacities
    api/v1/marketplace_analytics.py   offers
    api/v1/contracts_sqlite.py        matches
    core/ecosystem_store.py           (tables in neither store)

`test_no_module_opens_sqlite_without_consulting_a_backend_switch` does **not**
catch these, and that is deliberate, not a false green: it is scoped to modules
that *write* a PostgreSQL-owned table, and it is satisfied module-wide by any one
`*_is_postgres()` call. Reads were out of scope when it was written for the
write-divergence defect. Do not "fix" it by widening it blindly — several of
these tables are absent from SQLite, so those reads already fail rather than lie.

**The tenant-isolation hole — FIXED 2026-09-24.**
`GET /api/v1/project-activity/{project_id}` (`main.py:759`) takes `project_id`
from the path and performs no project-level authorization in the handler, so the
database filter *is* the access control. It read `bankability_evidence` and
`bankability_snapshots` from SQLite, which has no RLS. The SQLite copy held **127**
rows across **5** projects owned by **three** tenants — `hamburgone_com`,
`etfuels_sa`, `rheinwerk_industries_ag` — all readable by any authenticated caller
who could guess a project id.

Both readers now go through `_evidence_store()` -> `evidence_connection()` (034
owns those tables). Measured against `proj_hamburgone_emethanol` (49 rows, owner
`hamburgone_com`):

    before, any caller, no tenant context  49 rows readable
    after,  as etfuels_sa                  BLOCKED
    after,  as rheinwerk_industries_ag     BLOCKED
    after,  as hamburgone_com (owner)      allowed
    after,  as PLATFORM_ADMIN              allowed, and logged by _tenant_context
    after,  no tenant bound                BLOCKED (deny sentinel)

Two portability points the port had to handle, and the next one will too:
`sqlite_master` does not exist on PostgreSQL (the `_table_exists` probe is now
SQLite-only, since 034 owns the tables there), and `ORDER BY datetime(updated_at)`
is a SQLite function that `_to_pg()` does **not** rewrite — it only handles
`datetime('now')`. Every stored value is ISO-8601 and text ordering was verified
byte-identical before the `datetime()` wrapper was dropped. Check that before
copying this pattern; do not assume it.

**Still unfixed — 7 modules, same shape:** `adjacency`, `lineage`,
`next_best_action`, `routes_project_truth`, `marketplace_analytics`,
`contracts_sqlite`, `ecosystem_store`. Of these, `lineage` reads eight PG-owned
tables and is the largest. Note `projects` is ABSENT from the SQLite file, so
`adjacency` and `lineage` reading `FROM projects` fail rather than lie — they are
broken, not leaking.

### Where the bytes actually are

The database is **not a file you can copy**. It is a Docker named volume:

    container   files-postgres-1  (postgis/postgis:15-3.3)
    defined in  files/gex-demo-compose.yml   <- NOT gex-platform-enhanced/docker-compose.yml
    volume      files_postgres_data
    reached at  localhost:55432 -> container gex-pg-forward -> 5432

`docker inspect` reports the mount as `/var/lib/docker/volumes/.../_data`, but
**that path does not exist on macOS** — it is inside the Docker Desktop VM. On
the host the bytes live in one blob,
`~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw`. So back up
with `pg_dump`, never `cp`; `docker volume rm files_postgres_data` or a Docker
Desktop factory reset destroys the database outright.

### Backups — where they land and how to restore one

`files/backup_postgres.sh` is the backup. It dumps with `pg_dump -Fc` out of the
container, **verifies the dump, and only then** installs it. Run it by hand any
time; it is also the thing the scheduler runs.

    files/db_backups/daily/    gex_platform_<YYYY-mm-dd_HHMM>.dump   keep 7
    files/db_backups/weekly/   gex_platform_<ISOweek>_<stamp>.dump   keep 4
    files/db_backups/backup.log

Weekly is a **hardlink** to the first good daily of each ISO week, so the four
weekly copies cost no extra disk. A dump is ~1.0 MB, so the whole rotation is
~8 MB. The pre-existing loose dumps at the top of `db_backups/` are untouched.

**Verification is two steps, and the second is the one that counts.**
`pg_restore -l` reads only the archive TOC. Measured 2026-09-30 against a
known-good dump: a copy missing its **last 500 bytes**, and a copy with a
**byte-flip at 60%**, BOTH passed `pg_restore -l` with exit 0. Only a full read
(`pg_restore -f /dev/null`, which decompresses every data block) caught them. So
the script does both. Do not "simplify" it back to `-l` alone.

A dump is staged in `db_backups/.staging/` and moved into `daily/` **only after
it verifies**, so a failed run leaves no file that could be mistaken for a
backup. Verify any existing dump without changing anything:

```bash
files/backup_postgres.sh --verify files/db_backups/daily/<file>.dump
```

**It dumps as `gex_user`, and it must.** 113 of 120 public tables carry FORCED
RLS, which applies even to the table owner; `gex_user` is SUPERUSER + BYPASSRLS
so it reads every tenant's rows. Dumping as `gex_app` would silently produce a
partial database. This does **not** change `DATABASE_URL`, which stays `gex_app`.

**Failures are loud and distinguishable** — never a 0-byte file and exit 0:

    10 docker CLI not found      20 pg_dump failed
    11 Docker Desktop not up     21 empty / not a PGDMP archive
    12 container missing         22 TOC unreadable
    13 container STOPPED  <-     23 too few TABLE DATA entries
    14 up but refuses queries    24 truncated or corrupt (full read failed)
                                 30 could not install   40 another run in progress

13 is the recurring one: `files-postgres-1` has restart policy `no`, so a Docker
Desktop restart leaves it stopped while the forwarder on :55432 still accepts
connections and refuses queries. Fix with `docker start files-postgres-1`.

**To restore.** Restore into a THROWAWAY database first and compare — never
straight over `gex_platform`:

```bash
docker exec files-postgres-1 psql -U gex_user -d postgres -c "CREATE DATABASE gex_restore_test;"
docker exec -i files-postgres-1 pg_restore -U gex_user -d gex_restore_test --no-owner < files/db_backups/daily/<file>.dump
```

Verified end to end 2026-09-30: restored clean (exit 0, zero errors), **120 of
120 tables, 19,984 rows**. The only two tables that differed from live —
`auth_login_history` and `refresh_tokens`, +3 rows each — were writes that
happened *after* the snapshot (live rows timestamped 08:17–08:18 UTC against an
08:16 UTC dump). That is a correct point-in-time snapshot, not data loss; expect
the same shape when you compare.

To promote a restore over the live database, drop and recreate `gex_platform`
itself — `pg_restore -c` into a live database leaves RLS policies and grants in
a half-replaced state. Re-run `scripts/setup_postgres_rls.sql` **before** the
restore if the roles are gone, and do not run migrations as part of a restore:
the dump already carries schema at its own head.

**Done for real 2026-10-13, after the container and volume were deleted** (handoff §8
item 43). The steps were:

1. `docker compose -p files -f files/gex-demo-compose.yml up -d postgres`. Use project
   `files` because the forwarder dials `files-postgres-1` on `files_gex_net`.
2. `setup_postgres_rls.sql` into the empty `gex_platform`. It creates only the roles. Then
   `ALTER ROLE gex_app PASSWORD` to match `.env`.
3. Restore into `gex_restore_test` and check it: table count, FORCED RLS count,
   `alembic_version`, and the append-only grants query above.
4. Promote it: `DROP DATABASE gex_platform; ALTER DATABASE gex_restore_test RENAME TO
   gex_platform;`. This skips a second restore.
5. **Re-apply the database-level settings. A `-Fc` dump does not carry them.**
   `GRANT CONNECT ON DATABASE gex_platform TO gex_app, gex_admin, gex_engine, gex_anchor;` (gex_engine
   since 082 — the PF engine's run log; gex_anchor since 095 — the ledger anchor worker) and
   `ALTER DATABASE gex_platform SET app.current_company_id = 'GUEST';`. Without the first,
   the runtime cannot connect. Without the second, the RLS default changes.
6. Take a fresh backup straight away.

Result: 120 tables, 113 FORCED, head 059, 20,080 rows. `gex_app` connects through :55432
as a non-superuser, and `projects` returns 0 with no tenant context.

Note: `backup_postgres.sh --verify` itself needs the container running. It runs
`pg_restore` inside `files-postgres-1`, so with the container gone it exits 13. You cannot
pre-check a dump before step 1.

**Scheduling.** `files/com.gex.postgres-backup.plist` is a launchd agent, daily
at 12:30 local. Note it is **not installed unless someone ran the two commands
in it** — check with `launchctl list | grep gex`. Install / remove:

```bash
cp files/com.gex.postgres-backup.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.gex.postgres-backup.plist
launchctl unload ~/Library/LaunchAgents/com.gex.postgres-backup.plist && rm ~/Library/LaunchAgents/com.gex.postgres-backup.plist
```

Three things about this job were learned the hard way on 2026-09-30, all
verified by running it:

- launchd gives jobs `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, which does **not**
  contain `docker` — `/usr/local/bin/docker` is a symlink into Docker.app. The
  script resolves docker by absolute path itself, which is why it works under
  launchd. Keep that if you rewrite it.
- **`ProcessType` must stay `Standard`.** It was first written as `Background`
  (with `LowPriorityIO` and `Nice 5`), which makes the job eligible for
  aggressive CPU and I/O throttling: one run was still unfinished after 2m09s
  having consumed 0.31s of CPU, and a second took 27s, against ~4s by hand.
  With `Standard` the scheduled run finishes in ~9s. Do not add those keys back.
- **The lock is stale-aware, and must stay that way.** `db_backups/.lock` is
  taken per run and carries the holder's pid. A run killed with SIGKILL, or a
  reboot mid-dump, leaves the directory behind; the first version then exited 40
  on every subsequent run, which would have quietly stopped backups on this
  machine forever. `take_lock()` now clears a lock whose holder is not running
  and logs that it did. A lock held by a *live* process is still respected.

Check a scheduled run afterwards with `launchctl list | grep gex` — second
column is the last exit status, and the codes above say what a non-zero one
means. `db_backups/launchd.err` catches anything that fails before the script
can log.

---

## Tenant isolation — how the caller reaches the database

Two paths, one identity. `app/core/request_tenant.py` is the single derivation;
`ABACMiddleware` binds a request-scoped `ContextVar` and unbinds it in a
`finally`.

- `Depends(get_db)` — SQLAlchemy, **115** sites (was ~109 on 2026-08-10)
- `*_connection()` — the shim in `app/core/db_backend.py`, **~121** call sites
  across **48** files, excluding the shim's own definitions (was ~64)

Shim resolution is **explicit argument → bound caller → deny sentinel**. The
default is `NO_TENANT_CONTEXT`, which matches no tenant-scoped policy, so code
with no caller reveals nothing. It used to default to `PLATFORM_ADMIN` and no
call site overrode it.

**`PLATFORM_ADMIN` disables tenant isolation for a whole connection.** Pass it
only for a genuine bootstrap — reading the rules you are using to decide access.
**Nine** call sites do, not seven, and the composition has changed — measured
2026-09-24 by `_connection\([^)]*PLATFORM_ADMIN`:

    core/entitlements.py      core/permission_engine.py   core/sod.py
    core/css.py               core/event_store.py         core/wae.py
    core/drpl.py              core/break_glass.py         core/open_interest.py

**2026-10-23: a tenth — `core/market_engine.py`.** A trade crosses two tenants (seller's
project, buyer's RFQ), so the engine authorises the Party from the token first, then performs
the step on a PLATFORM_ADMIN market connection. Base tables stay tenant-scoped; listings are
anonymised by the engine. GEX itself trades nothing (`GEX_DOES_NOT_TRADE`).

Each says why, and every use is logged by `_tenant_context`.
If you need it in a test, use `as_platform_admin()` from `tests/pg_support.py`.

Auth tables carry no RLS, so login works regardless of tenant context. Reference
data (`fuel_catalog`, `approval_policies`, …) is deliberately readable by all —
failing closed must not blackhole it.

---

## Accounts are vetted, not self-served

`POST /register` creates a **`PENDING`** account and nothing else.
`LOGIN_PERMITTED_STATES` is `{ACTIVE}` only. Activation requires GEX staff,
telephone verification, a signed usage agreement, and separation of duties
(activator ≠ claimant). See `app/core/account_lifecycle.py`.

`auth_users` now holds **23** rows (measured 2026-10-13, in the restore of the 12 Oct
dump):

    17  ACTIVE   activated_by = 'SEED_GRANDFATHERED'        predate vetting
     4  ACTIVE   activated_by = 'MANUAL_ADMIN_GRANT'        t-marwenc, t-mohamedk (09-20),
                                                           you_, jean-marie_ (10-11)
     1  ACTIVE   activated_by = 'TEST_FIXTURE_FORTAVERDE'   usr_test_fv_p1, vetting bypassed
     1  PENDING  (none)                                    usr_test_fv_p2, fixture stand-in

Do not backfill the grandfathered rows' NULL phone/agreement columns; that marker
is how you find them. None of the four `MANUAL_ADMIN_GRANT` rows has a phone or
agreement date either.

**`u_admin` no longer exists.** On 2026-09-24 it was the one account with no
marker at all. In the 12 Oct dump it is absent. The platform admins are
`admin_greenearthx_com` (`SEED_GRANDFATHERED`) and the four `MANUAL_ADMIN_GRANT`
accounts. Nothing records when `u_admin` went or whether it was re-keyed, so
the separation-of-duties question it raised is closed only if someone confirms
that.

Deal and product data belongs **behind the backend**, not the frontend's
Supabase `.from()`. Do not "fix" a frontend data path by wiring it to PostgREST.

---

## Evidence review — who may verify (Attack A, decided 2026-10-01)

A producer could walk its own claims to VERIFIED
(`docs/adversarial/2026-09-30_attack_A_producer_advance.md`). Since 2026-10-01:

- A reviewer status (UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED) on
  `POST /bankability/evidence` is a **VERIFY**, classified from the body
  (`abac_middleware._is_evidence_review`). The URL test (`"/verify" in path`)
  never matched it, so R5 was never reached.
- **Who reviews which gate is JML's decision**, settled 2026-10-02:
  `abac.REVIEWER_GATES` — **certifier** (G2, G11), **independent engineer**
  (G0, G1, G3, G5, G6, G11), **lenders' adviser** (G0, G4, G7, G8, G9, G10),
  **insurer** (G7). Four roles, every one independent of GEX: the platform
  enforces the standard and verifies nothing itself. A GEX desk-review role was
  built on 10-01 and removed on 10-02 — do not reintroduce it. Change the table
  only on JML's word, together with `DECIDED` in
  `tests/test_evidence_review_separation.py` (mirrored, and negative-verified:
  widening the insurer to G10 fails 2 tests).
  **2026-10-21, option (b):** the capital provider's own reviewer verifies the
  gate that makes ITS decision eligible — `GRANT_ASSESSOR` G0 (Grants & TA),
  `SEED_INVESTOR_ADVISER` G1 (Seed / VC), `STRATEGIC_INVESTOR_ADVISER` G3
  (Strategic Equity). Before that, G0, G1 and G3 needed an independent engineer,
  whom nobody appoints at concept stage, so an early project could verify
  nothing. Literal on purpose — one gate each: a seed adviser cannot verify G0.
  Negative-verified both ways (widening the seed adviser to G0 fails 1 test;
  removing the grant assessor fails 2). And **insurance
  bound at G10** (`insurance_certificates_delivered`) stays with the lenders'
  adviser, because gate-level scope cannot hand the insurer that one item
  without also handing it the legal opinions and the security package.
- Never the submitter or its company (`_independence_refusal`, in the handler),
  and never the project owner's company (R5). The actor is the token's user id;
  the body's `submitted_by` is ignored. VERIFIED must name the sha256 of a
  document on file (`POST /evidence/document`).
- A reviewer reads `GET /evaluate` (resource type `GATE_EVALUATION`) and the
  evidence and documents of its own gates, nothing else. Other gates' items are
  withheld from its screen.
- **Assigned** = the role on the project (`auth_user_project_roles`) AND the
  project in `assigned_audits`. On PostgreSQL its company also needs a
  `project_access` row, or RLS refuses the write. **No live account is assigned**
  (measured 2026-10-21), so nobody can verify yet. That is fail-closed, not a bug.
- **Appointing a reviewer (JML, 2026-10-21): GEX staff appoint, on the instruction
  of a named party.** `POST /api/v1/projects/{id}/reviewers` (GEX platform admin
  only), `DELETE …/reviewers/{user_id}?role=` with a reason, `GET …/reviewers` for
  staff, stakeholders and the project's reviewers. Policy in
  `app/core/reviewer_appointments.py`; it writes all three records in ONE
  transaction (`project_access` with `access_role='REVIEWER'`, PostgreSQL only)
  and never commits — the route does, then writes `REVIEWER_APPOINTED` /
  `REVIEWER_REVOKED` to the event ledger, and UNDOES an appointment whose event
  cannot be written. Refused: a non-reviewer role, no instructing party, no
  instruction sha256, the owner's company as appointee, the owner as instructor,
  any GEX account, self-appointment, a non-ACTIVE account, an unregistered tenant
  (refused, never created). Takes effect at the reviewer's next sign-in (the token
  carries roles and audits). Screen: "Who verifies" on Gates & Evidence
  (`ReviewersPanel.tsx`); the form appears only when the server returns
  `can_appoint`. That menu entry now opens to ENGINEER, INSURER, LEGAL, DFI and
  PLATFORM (GEX staff) as well — navigation only. Tests:
  `test_reviewer_appointments.py` (23, incl. end to end: cannot verify → appointed
  → verifies its own gate only → revoked → cannot), `_pg.py` (2, rolled back),
  `ReviewersPanel.test.tsx` (4); five backend breaks and one frontend break all
  caught. **Open:** grant assessors and investors' advisers have no service type
  in the menu, so they reach Gates & Evidence only as an EXECUTIVE of a matching
  company type. (RLS on `project_access` letting a tenant grant itself access
  was closed by migration 062 the same day.)

---

## Tests

```bash
cd backend && ./venv/bin/python -m pytest tests/ -q
```

Export `DATABASE_URL` and `ALEMBIC_DATABASE_URL` FIRST — see the traps above.
Without them the same command reports **593 pass, 140 skip**, having silently
skipped the entire PostgreSQL path while looking green.

**844 pass, 17 skip** against PostgreSQL as `gex_app` with both exported, zero
failures — measured 2026-09-28. (Counts move — this tree has more than one session
writing to it; re-measure rather than trust a number you did not just run.)

**2026-09-30: 853 pass, 18 skip, 0 fail** at head **059**. The arithmetic against
the 28 Sep row closes exactly: 844 + **9** new
(`tests/test_capital_bridge_projects_routes.py`) = 853. The 18th skip is the
empty `bankability_evidence_archive` (`test_evidence_history_pg.py:69`, handoff
item 38).

**2026-10-01: 898 pass, 18 skip, 0 fail**, both exported. 853 + **45**
(`tests/test_evidence_review_separation.py`, the Attack A fix) = 898; same 18 skips.

**2026-10-02: 899 pass, 18 skip, 0 fail.** 898 + **1**
(`test_evidence_slice.py::test_the_only_divergence_is_the_labelled_fixture`). The reviewer-table
swap (insurer in, GEX desk review out) changed no count. The +1 pins the one deliberate
PostgreSQL-only divergence — see the comprehension fixture below.

**2026-10-19: 956 pass, 18 skip, 0 fail** at head 061, both exported. 899 + **57**
(`test_reference_registry_pg.py`, `test_reference_catalog.py`, `test_reference_routes.py`,
two guardrails in `test_fuel_reference_slice.py`). The same 18 skips, read with `-rs`.

**2026-10-25 (part 3): 1115 pass, 18 skip, 0 fail** at head 071; frontend 227/227. +8
`test_governance_identity_pg.py`, +5 `test_frontend_datasets_pg.py`.

**2026-10-25 (CISO): 1102 pass, 18 skip, 0 fail** at head 070; frontend 227/227. The CISO seed
test was replaced by `test_ciso_real_data_pg.py` (12).

**2026-10-25 (earlier): 1098 pass, 18 skip, 0 fail** at head 069; frontend 227/227.

**2026-10-25 (earlier): 1094 pass, 18 skip, 0 fail** at head 068. 1088 + 6
(`test_project_records.py`). Frontend 227/227.

**2026-10-23 (earlier): 1088 pass, 18 skip, 0 fail** at head 066. 1084 + 4
(`test_marketplace_records_pg.py`).

**2026-10-23 (before that): 1084 pass, 18 skip, 0 fail** at head 065. 1051 + 25
(`test_trading_terms.py`) + 8 (`test_trading_terms_pg.py`, on `pg_store`). **One token per
contract (JML):** an amendment is a new version and a modification of the same token —
`tb_contract.token_ref` and each version's `token_event_ref` are fixed once written (triggers).

**2026-10-23 (earlier): 1051 pass, 18 skip, 0 fail.** The market and trading area is
PostgreSQL only (JML): +12 "no sqlite3" guards and +7 refusal checks, −1 superseded guard.
Tests for those modules use the `pg_store` fixture (conftest): ONE throwaway database per
session, migrated from scratch and dropped — the PostgreSQL counterpart of `isolated_store`.
`isolated_store` pins every switch to sqlite, so it cannot be used for these modules any more.

**2026-10-23 (before that): 1033 pass, 18 skip, 0 fail.** +2 guards: the market engine has no
SQLite path and refuses without PostgreSQL (JML: RFQs stay in PostgreSQL only).
`test_market_chain.py` runs in a throwaway database built by the migrations — see
`pg_support.throwaway_pg_database`, the pattern for tests whose code commits.

**2026-10-23 (earlier): 1031 pass, 18 skip, 0 fail** at head 064, both exported. 999 + 8
(`test_market_chain.py`) + 4 (its legacy-route tests) + 6 (`test_market_chain_pg.py`) + 2
(parity, parametrized) − 1 (the pinned "contracts missing" test it replaces) + 7
(`test_trading_book_api.py`) + 6 (`test_trading_book_pg.py`). Same 18 skips.

**2026-10-21 (earlier): 999 pass, 18 skip, 0 fail** at head 062. 987 + **6**
(`test_refresh_reads_the_auth_store.py`) + **6** (`test_project_access_writes_pg.py`). Same
18 skips. `POST /auth/refresh` now loads the account through `auth.load_user_for_refresh`
(the auth slice's own store, the sign-in vetting rule) instead of opening the SQLite file and
checking `is_active`; a refused account loses every refresh token. Before the fix a
SUSPENDED or PENDING account renewed its session — the restored old body fails 3 of the 6.

**2026-10-21 (later): 987 pass, 18 skip, 0 fail.** 962 + **25** (reviewer appointments:
23 route tests, 2 PostgreSQL tests in rolled-back transactions). Same 18 skips, read with
`-rs`. Dev database row counts identical before and after.

**2026-10-21: 962 pass, 18 skip, 0 fail** at head 061, both exported. 956 + **6**
(option (b): three rows in `DECIDED`, three verifications). The same 18 skips, read with
`-rs`. Measured after 061 was re-applied — see Migration state.

**2026-10-13: 899 pass, 18 skip, 0 fail**, run against the database restored from the
12 Oct dump with both URLs exported. The counts are unchanged from 10-02, and the same 18
skips were read with `-rs`.

**The three append-only failures are FIXED (migration 059).** Earlier the same
day this file recorded 850 pass / 3 FAIL, the failures being the `UPDATE`
variants of the parametrized append-only tests in `test_commitment_terms_pg.py`
and `test_evidence_history_pg.py`. Head was 058 and both 056 and 058 had run, yet
`gex_app` held `INSERT, SELECT, UPDATE` on `evidence_events`,
`bankability_evidence_archive` and `commitment_terms_events`, with DELETE and
TRUNCATE correctly gone.

**The cause was NOT 031's DEFAULT PRIVILEGES, and NOT a missing REVOKE in 058.**
Both guesses were written here and both were wrong; `058:79` does
`REVOKE UPDATE, DELETE, TRUNCATE ON commitment_terms_events`, and 056 revokes the
other two. A REVOKE is atomic, so nothing "half-applied" — DELETE surviving while
UPDATE came back means something re-GRANTed UPDATE *after* Alembic, and granted
UPDATE without granting DELETE. Exactly one thing in this tree does that:

**`backend/scripts/setup_postgres_rls.sql` was re-run after Alembic during the
30 Sep rebuild.** Its second block looped over every table in `public` running
`GRANT SELECT, INSERT, UPDATE ON <tbl> TO gex_app`, exempting only a hardcoded
list — `audit_log`, `commitment_records`, `verification_log` — and only from
UPDATE. Its own comment invited the re-run ("Run this block again after every
Alembic migration adds new tables"). The proof it ran against a populated schema:
`gex_admin` holds ALL PRIVILEGES on **120** tables, which it can only have got
from that same loop. The resulting grant shape was that script's output exactly —
UPDATE back everywhere except `commitment_records`, the only name on its list
that exists in this database, and DELETE nowhere, because the loop never granted
DELETE. Confirm the diagnosis on any future recurrence with:

    SELECT c.relname, c.relacl FROM pg_class c JOIN pg_namespace n
      ON n.oid = c.relnamespace WHERE n.nspname='public' AND c.relkind='r'
      AND c.relname IN ('evidence_events','bankability_evidence_archive',
                        'commitment_terms_events','commitment_records');

`arw` (INSERT, SELECT, UPDATE) with no `d` is the signature of that script; full
`arwd` would instead mean the table really was dropped and recreated. **The tables
were never dropped and recreated** — had they been, 031's DEFAULT PRIVILEGES would
have handed back DELETE too, and it was absent.

Both ends are now closed:

- **Migration 059** restores the three revokes, and *asserts* afterwards that
  `gex_app` holds no UPDATE/DELETE/TRUNCATE on any of them, so a silent re-grant
  cannot pass unnoticed again. Its downgrade returns the database to the
  `INSERT, SELECT, UPDATE` state 059 found, not to 031's full DML.
- **`setup_postgres_rls.sql` can no longer undo a migration's revoke.** Its grant
  loop now touches only tables on which `gex_app` holds *nothing*, and its
  append-only set is REVOKEd unconditionally. A REVOKE can only be more
  restrictive, so a stale list there under-protects but can never un-protect —
  the asymmetry the old blanket GRANT lacked. Verified by re-running the script
  against the live database after 059: the revokes survived.

`commitment_terms` deliberately KEEPS UPDATE — cards are replaced in place (058
grants it on purpose). Only its *history* is append-only.

**Known conflict, not fixed here:** `app/core/css.py:272` issues
`UPDATE commitment_records` on the countersign path, and `commitment_records` has
had UPDATE revoked since well before 059 (by the old script's hardcoded list).
That path cannot have worked as `gex_app` on PostgreSQL. 059 did not cause it and
does not change it — it is a genuine design question (is countersigning a state
transition or a rewrite of history?) and needs its own decision.

`isolated_store` is **module-scoped**: every test in a file shares one throwaway store.
A new test must not assume an empty table or a key no earlier test has touched —
run it alone *and* in its file before believing it.

Three conditions, all measured 2026-09-24. The middle one is the trap:

    exports + database up        716 pass,  17 skip,  0 fail
    NO exports + database up     591 pass, 142 skip,  0 fail   <- 125 skipped
    exports + database absent    592 pass, 141 skip,  0 fail

**Zero failures with the database absent — restored.** It held on 2026-08-10,
had broken by 2026-09-24, and is fixed. The two offenders were in
`tests/test_open_interest_routes.py`:

    test_confidentiality_identity_is_not_the_tenancy_identity
    test_the_admin_flag_is_carried_but_still_does_not_bypass_confidentiality

They reach PostgreSQL *indirectly through the app* —
`roi.viewer_from_request` -> `_profile_columns` -> `psycopg2.connect` — and the
file called `requires_pg()` zero times, so an unreachable database FAILED them.
The cost was never the red: it was that two *confidentiality* tests read as "the
admin bypasses confidentiality" when the only real problem was a stopped
database. Both now call `requires_pg()`.

Note what that guard gates on: the `DATABASE_URL` **environment variable**, not
reachability. So these two also skip when the database is up but the variable is
unexported — that is the 593 -> 591 difference in the middle row above.
`requires_pg()` buys the absent-database invariant at the price of needing the
export. Export it.

The other two `viewer_from_request` tests in that file need no guard: they pass
payloads with no `company_id`, and `viewer_from_request` returns
`ViewerProfile(company_id=None)` before it reaches `_profile_columns`.

- `tests/pg_support.py` is the only place that **calls** `psycopg2.connect`
  (the architecture guardrail names the pattern in prose, which is why that
  guardrail matches the AST rather than the text). An absent or
  unreachable database is a **SKIP**; only a reachable database answering
  incorrectly is a FAILURE. Tests reaching PostgreSQL indirectly through the app
  must call `requires_pg()`.
- Guardrails match the **AST, not the text** — several here discuss the very
  pattern they forbid, and earlier versions repeatedly matched their own prose.
- **Tests must not write the dev database.** Use the `isolated_store` fixture in
  `tests/conftest.py`.
- Negative-verify a new guardrail: break the thing deliberately and confirm it
  fails. One in this repo passed for a reason nobody had checked until it was.
- **A guardrail can be killed by the fix it was written to check.**
  `test_rls_isolation.py::test_platform_admin_sees_everything_and_a_tenant_sees_less`
  gated on `SELECT count(*) FROM projects` taken on the fixture connection. When
  045 repointed `DATABASE_URL` from superuser to `gex_app`, that count became 0
  via the deny sentinel, so the test skipped unconditionally — "no projects
  seeded" against 14 projects — from 045 until 2026-09-24. RLS working correctly
  was what disabled the test that checks RLS. Fixed to gate on PLATFORM_ADMIN
  visibility, with the "sees EVERY project" assertion taken against a BYPASSRLS
  count via `pg_support.pg_bypassrls_connect()`. **A skip is not a pass.** Read
  skip reasons with `-rs` before believing a green run.

---

## Style

Function over design. Concise and direct. Incremental changes over monolith
patterns.

---

## vexp — context-aware orientation <!-- vexp v2.5.3 -->

Canonical vexp guidance lives in the parent `files/.claude/CLAUDE.md`, which
also loads. It is not repeated here — this file previously carried a stale
v2.0.12 copy that contradicted it.

In short: `run_pipeline({ "task": "..." })` for orientation when a task does
**not** name the files or symbols to touch. If it does, skip vexp and use your
normal tools. `get_skeleton` for structure you only need to understand;
`verify_done` once before declaring a multi-file task complete.

Anchor queries on real identifiers or paths:
`run_pipeline({ "task": "fix JWT expiry in AuthService.validateToken" })`

<!-- /vexp -->
<!-- The marker pair above delimits a vexp-managed block. Keep the vexp section
     LAST in this file: if vexp regenerates it, only the trailing block is
     replaced and the GEX notes above survive. An unclosed opening marker risks
     a rewrite swallowing everything to end-of-file. -->
