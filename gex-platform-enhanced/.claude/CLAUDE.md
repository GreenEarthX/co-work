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
**2026-11-13: head is 112 — a project's sales and input records are its OWNER's** (handoff §8 item 79).
`project_sales_detail` / `project_input_line` read = `PLATFORM_ADMIN OR app_company_owns_project`. Before,
any company with project access (a prospective buyer) read the producer's supplier prices, break-even and
other buyers' deals. Project access is not ownership: use `app_company_owns_project` for anything commercial.
**Head is 113 (same day):** a `project_dataset` row of kind `demand_buyers` (the project's buyer names) is read
by GEX, the owner, or a company with `project_access.access_role = 'MANDATED_LENDER'`
(`app_company_is_mandated_lender`, SECURITY DEFINER). Every other kind keeps 069's rule. Widen the list
only on JML's word, by adding an access_role, never by falling back to "may see the project".
Still on the "may see the project" rule: the other `project_dataset` kinds (`deal_inputs` holds DSCR and
offtake % and is not routed), `project_profile`, `project_risk_flag`, `tb_asset`.
**2026-11-14: head is 115 — the capacity rule is the database's.** Deferred constraint trigger `tokens_capacity_guard`: at commit, locks the capacity and refuses any day whose live tokens exceed `capacity_mtpd`, whoever writes them. A fixture that seeds tokens must size its capacity for them. The mint route runs the constraint early so a refusal comes before its event.
**2026-11-13 (latest): head is 114 — discovery Phase 0: honest mints, exact market quantities, idempotent creates** (handoff §8 item 81; backup `gex_platform_2026-11-13_2321.dump`; round-tripped).
- **Mint** (`POST /api/v1/tokens/`): a declared `verification_state` other than UNVERIFIED is 422; the capacity row is locked (`FOR UPDATE`, which also makes a non-owner 403); capacity is the peak rate on any day of the window (SPLIT parents and VOIDED excluded); the event is written after the row, before commit.
- **Carving** (`core/token_partition.carve`): a listing reserves exactly its rate and window, an acceptance contracts exactly min(listing, RFQ) over the overlap; remainders go back to MINTED. Recorded in `token_split` (reason `market_listing` / `market_acceptance`, `order_id`, piece). `token_split_consistent` now also refuses a market split whose pieces don't sum to the parent's tonnes. Never move a whole token for a partial quantity again.
- **Custody kg of a carved token is `app_token_kg`** (the split's kg), never "allocations made to this token": the draw guard and `delivery_record` use it, and the closed-period check goes through `delivery_title.root_of`. The evidence pack walks splits to the allocated token (pack version **3**).
- **Idempotency** (`core/idempotency.run`, table `idempotency_record`, RLS per company): capacity, mint, listing, listing open, RFQ, proposal, acceptance, settlement. Same key + same request replays (`Idempotent-Replayed: true`); same key + other request 422; refusal releases the key. The RFQ form sends one key per form.
- `frontend/src/api.ts` `fetchAPI` now spreads `options` BEFORE the merged headers (a caller's `headers` used to replace auth and JSON headers).
**2026-11-11: Docker Hub `gex-backend`/`gex-frontend` v1.10.0 (+latest), compose pinned** (handoff §10). In zsh write `"${r}:${t}"`: `$r:latest` is the `:l` modifier and pushed two PUBLIC stray repos (deleted). Prune the build cache after building: four images leave ~2.2 GB free on the VM disk.
**2026-11-10 (latest): head is 096 — Phase 5: party signatures, recorded and verified, NOT required** (handoff §8 item 61).
- A CONFIRMED/DISPUTED event MAY carry ed25519 over `"GEX-CONTRACT-EVENT-v1:" + event_hash`, beside
  the hash (hashes and anchors unchanged).
- Two calls: `signature_intent: true` returns the hash and writes NOTHING; then send `signature`.
- Only the first act of the caller's company inside `record.party_act` is signed.
- Keys: `/api/v1/trading-book/party-keys`, screen on `/account`. An executive proposes, a SECOND executive activates;
  each step is in the ledger before commit.
- `REQUIRE_PARTY_SIGNATURE` defaults to false.
- A pg_store test's manual rollback on the shim connection drops its tenant setting: reopen it.
- Platform **1433 pass / 15 skip**, frontend **266**. **151** tables, **144** FORCED.
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
**2026-11-03 (16:05): blank login page for a PENDING account — FIXED.** The client's CEO (contact P2, Möhring) signed in with the correct password; `/auth/login` answered 403 with an OBJECT `detail` (`account_not_active`, `account_state` PENDING, `reason`), which `LoginPage` rendered as a React child: it threw, and with no error boundary the page went blank. Every earlier account was ACTIVE, so this path had never run. `loginErrorText()` now shows `reason` (or a string `detail`). `LoginPage.test.tsx` +3 (the 403 case negative-verified: the old call site reproduces the crash). Frontend **247 pass / 1 skip** (run in a Linux copy, not on this Mac). Backup of the two files and this one: `files/_claude_backups/2026-11-03_login_blank_screen/`. P2's account is registered and PENDING (server's answer at 16:05); P1's state was not checked.
**2026-11-03 → RETIRED 2026-11-11: the FortaVerde demo sign-ins and the TEST fixture are gone (JML: FortaVerde is the real client, tenant `mohring_energie`).** `create_fortaverde_demo_accounts.py`, `load_fortaverde_test_project.py` and their test are deleted; the fixture (`proj_TEST_fortaverde_pecem`, tenant `test_fortaverde`, two stand-ins, two named demo sign-ins and its 077 premise row) was removed after a backup. The real accounts follow vetting (onboarding doc §5–6) and the client creates its own project (§7). The knowledge record and the onboarding doc are LOCAL ONLY — git-ignored, never placeholdered: GitHub `co-work` is PUBLIC. Lesson kept: any script that loads the knowledge record binds the platform's `app` first (the validator puts `gex_pf_engine/backend` first on sys.path).
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

**RETIRED 2026-11-11 (`projects` is back to 15, `auth_users` 23):** ~~A second TEST fixture: FortaVerde (Pecém), loaded 2026-10-12~~ by
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

**2026-11-17: pre-FID access adds one more — `api/v1/development_packages.py` `_package_ref`.** It reads
only `project_id` and `phase_required` of one package to decide who may see it, the same bootstrap reason as
entitlements. The rule itself is `core/pre_fid_access.py`: the owner (`projects.owner_tenant_id`) reads its
pre-FID packages and spend wave; anyone else needs the owner's per-section share (`DEVEX_SHARE:<SECTION>` in
`finance_entitlements`), and a shared read is made in the OWNER's tenant, not the caller's.
If you need it in a test, use `as_platform_admin()` from `tests/pg_support.py`.

**2026-11-17: structuring takes gate scores and state from the gate engine** (`core/structuring_context.py`),
identity from `projects`, and only nine inputs from `project_dataset` `structuring_context`. Breizh SAF is a
reference case only (`tests/fixtures/reference_cases/breizh_saf.json`); `tests/test_no_breizh_data_points.py`
fails if application code carries any of its data points. Bremen's copy was quarantined and removed on 17 Nov
(handoff §8 item 92): the load file no longer holds it or the derived fields, so no strip re-run is needed.

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

**2026-11-17 (later): head 123, rules 4.9.0 — handoff v4** (branch `readiness-returns-v4`, UNCOMMITTED; handoff §8 item 92). One readiness authority (`core/readiness.py`); policy values are registry rows, all **proposed** (`core/decision_policy.py`, `GET /api/v1/decision-tests`) — never type a floor in a screen; published returns cases (123, `/api/v1/returns-cases`); `no-store` on pre-FID and returns paths (`core/no_store.py`). **After an Alembic rebuild run `scripts/propose_decision_policies_20261117.py --execute`.** The PF engine has no `--reload`: after engine changes, `launchctl kickstart -k gui/$UID/com.gex.pf-engine`. Platform **1975 pass / 15 skip / 0 fail** (both exported, run alone), engine **376**, frontend **314**, `tsc` and both audits clean.

**2026-11-18: findings A–D decided by JML (same branch, uncommitted; handoff §8 item 93).** Demo seeding is OFF unless `GEX_SEED_DEMO_USERS` is set, only CREATES missing accounts, and production refuses it (`config.py`). `/projects/visible` lists owner-shared projects (`disclosure`, nothing else) and sets `viewer_is_owner`; write controls render on it alone. One DEVEX Brief page (`/finance/devex-shared` redirects). Platform **1986 pass / 15 skip / 1 fail / 1 error**: the error is a :55432 timeout; the fail is `test_compose_runs_the_tree_that_tests_inspect`, tripped by ANOTHER session's sibling copy `files/gex-platform-enhanced-part-a/` (branch `greenmesh-part-a`, created 18 Nov 00:32) whose `docker-compose.yml` builds its own backend — not this branch's code. Frontend **318**.

**2026-11-18 (later): head 124 — the calculation chain** (handoff §8 item 94; backup `gex_platform_2026-11-18_1234.dump`). Saved Cost Basis (`/api/v1/cost-basis`) -> TEA run FROM a saved version -> review by someone else (`/api/v1/tea-review`; INDEPENDENT or OWNER_INTERNAL, labelled) -> financing case -> returns published from the chain (`/api/v1/calculation-chain`); the version stores source versions, checks and remaining assumptions, and a bank with a RETURNS share sees them. Chain figures are never typed (`CHAIN_CONFLICT`). Rules: `core/calculation_chain.py`. **176** tables, **169** FORCED. Demonstrated on North Sea (rows permanent, share to ABN AMRO active). The legacy `/tea/base-case/{claim}/approve` still trusts `x-demo-user` (open, for JML). Full backend suite not re-run since; new tests 20 pass; frontend **321**.

**2026-11-18 (latest): a THIRD test fixture — Foxwell Survey UK (test independent engineer, JML).** Tenant `foxwell_survey_uk` ("TEST — Foxwell Survey UK", THIRD_PARTY, GB) and account `ewan_stewart_foxwellsurvey_com` (ewan.stewart@foxwellsurvey.com, ENGINEER/ENGINEERING, demo seed password), ACTIVE with `activated_by = 'TEST_FIXTURE_FOXWELL'`: vetting BYPASSED, no telephone. `scripts/load_foxwell_test_reviewer.py [--remove] --execute`. NOT appointed on any project: appointment is GEX staff's act, and JML's chosen instructor (the owner HamburgOne) is refused by `OWNER_CANNOT_INSTRUCT` — open. Also mid-way (handoff item 94, uncommitted): migration **125** (`returns_case_withdrawal`, `model_base_case.tea_inputs`; 177 tables, 170 FORCED), TEA quote mode, the withdrawal route. v1's ABN AMRO share is NOT yet revoked. **Instructor decided (JML): ABN AMRO.** Test instruction letter `docs/test_fixtures/foxwell/GEX-TEST-IE-NSEM-001_instruction_Foxwell.pdf` (synthetic, marked TEST, reproducible by `make_instruction.py`), sha256 `d8a0347b88ddb50fc6e832018f79e5fcd34c2d912e0f41f5beba60f1c800f982`. Appointment to be made by GEX staff on "Who verifies" (not yet done). **Head 125; chain repaired (handoff item 95).** v1 withdrawn, ABN AMRO share revoked. `co2_feedstock_price` DE €208/t APPROVED by JML (**after an Alembic rebuild run `scripts/propose_co2_feedstock_price_20261118.py --execute`, then approve it on the GEX staff console** (19 Nov: scripts no longer approve)). v2 TEA `CLM-MBC-61f3a1083e` all checks PASS, awaiting Foxwell. Platform **2029 pass / 15 skip / 1 fail** (the part-a guardrail), measured before the CO₂ step. After it: the 90 chain/returns/TEA/catalogue tests pass; frontend **322**. Corrected-process document (Claude Docs): https://claude.ai/artifact/BTbRrvUvpLi33c4CBobJU5; screens `docs/screenshots/handoff_v4/chain_v2/` (`annotate_chain_v2.py`).

**2026-11-19: the Cost Basis and TEA workbook (no migration; handoff §8 item 96).** `core/cost_workbook.py` (template `gex-cost-tea-1`): CATALOGUE / QUOTE / AGGREGATE lines, the PLANT BOUNDARY stated first and checked against lines and TEA feedstocks, a blank is unknown (never 0), external results kept as attributed `EXTERNAL_ASSESSMENT`. Upload = preview (writes nothing) then commit of exactly that file (`expected_file_sha256`). Export of one TEA run: `GET /api/v1/calculation-chain/{p}/tea/{claim}/workbook` and `…/openpytea-config`. `cost_basis_vs_tea` now fails a TEA that buys what the boundary says is made on site. Read rows by the grey key in column A, never by position. Tests: platform **2049 pass / 15 skip / 1 fail** (the part-a guardrail) over the 26 chain/TEA/returns/route/guardrail files, both exported; frontend **324**.

**2026-11-19 (later): head is 126 — the workbook's Financing and Offtake tabs (handoff §8 item 97).** `workbook_import` (126) holds what a tab declared beside the record it saved (capital stack, offtake sources); INSERT-only, FORCED. Preview returns `tabs`; commit takes `tab` and that tab's function. Offtake saves through `routes_bankability_proxy.save_card` (PUT /terms uses the same). **178** tables, **171** FORCED.

**2026-11-19 (latest): head is 127 — draft cases, atomic workbook saves, stable ids (handoff §8 item 98).** A financing case has a stable `case_id` and is DRAFT or ELIGIBLE (only ELIGIBLE feeds returns; promotion is a new version, on an independently reviewed TEA run). A cost basis is DRAFT (open issues; no TEA runs from it) or READY. Workbook writes are one transaction (`_insert_many`, `save_card(also=)`). Re-imports match by GEX ids in the workbook, never by names.

**2026-11-19 (night): the legacy TEA approval bypass is closed; OSBL counted once; a person approves reference values on screen (handoff §8 items 99-100).** Approvals take identity from the token and authority from an appointment on that project (`core/reviewer_authority.py`); a TEST fixture account's review is TEST and unlocks nothing. The chain's TEA sets OpenPyTEA's OSBL factor to 0 when the cost basis prices OSBL lines (check "OSBL counted once"); canonical mode refuses a stated contingency. Reference values are approved on the GEX staff console; no script approves.

**2026-11-20: head is 128 — the funding plan lives in the financing case; the CFO workbook journey passes 8/8 on `proj_TEST_workbook_journey` (handoff §8 item 101).** Reconcile the SELECTED case only (`core/funding.reconcile`); pipeline is never counted; gearing is reported with its owner, never a GEX hurdle. The TEA engine prices in 2024 EUR (CEPCI to 2024): a 2026-dated quote is refused. Re-run the journey with `scripts/load_workbook_journey_project.py --remove --execute`, `--execute`, then `scripts/workbook_journey_20261119.py` (JOURNEY_EMAIL / JOURNEY_PASSWORD from the demo seed).

**2026-11-20 (later): the CEPCI forward (handoff §8 item 102).** A quote dated after the last published CEPCI year (2024) is converted with an APPROVED `cepci_forward_<year>` reference row: the Gabillon P-forward calibrated on the CEPCI history by the PF engine (`POST /pf/index/forward`), proposed by `scripts/propose_cepci_forward_20261120.py`, approved by a person on the staff console. A published value always wins. Never feed a live calibration into a TEA run: the cost basis hash must stay deterministic.

**2026-11-20 (latest): the TEA cost base is 2026** (handoff §8 item 103). `settings.TEA_COST_BASE_YEAR`; the bridge sends `cost_base_year` + the APPROVED `cepci_forward_<year>` rows; the engine injects them per run (`escalation.request_scope`) and refuses a year with neither a published CEPCI nor an approved forward. **Until `cepci_forward_2026` is approved on the staff console, every TEA run is refused** (fail-closed, deliberate). Never make a forward process-global: it would price runs that did not send it and break `cost_basis_hash`.

**2026-11-20 (latest): OpenPyTEA 3.1.0 and a results view per TEA run** (handoff §8 item 104; no migration). 3.1.0 starts fixed cost with production (3.0.0 charged it while building) and charges no working-capital interest: reference e-methanol LCOP 2.307 -> 2.0785. A chain TEA run stores `tea_inputs.analysis` (breakdown, tornado with stated ranges, Gabillon index band from `POST /tea/index-band`); `core/tea_report.py` gives each run a fixed `GEX-TEA-…` reference and the inputs check. The screen is `TeaRunReport.tsx` on Calculation chain step 2. No Monte Carlo on that screen (JML): the band is Gabillon's, and it never covers power. Never put a route helper between `@chain_router.get` and its function (`test_tea_report.py` pins it). North Sea re-run `CLM-MBC-6cdd261cbd` supersedes v2 (351.0 -> 270.0 M EUR: v2 double-counted OSBL). OpenPyTEA 3.2.3 refuses canonical mode until three category names are renamed; quote mode is identical. Platform **2110 pass / 15 skip / 0 fail**, frontend **336**.
**2026-11-21: head is 129 — OpenPyTEA 3.2.3, Gabillon beside each TEA run, administrator screens** (handoff §8 item 105; branch `tea-323-console`). 3.2 renamed three correlation categories: use "Compressors, fans, & blowers" and "Absorption, adsorption, & membrane separation"; an old name is translated and LISTED in `defaults_used`, never silent (`tea_engine/correlation_set.RENAMED_CATEGORIES`). Each chain run records `analysis.market_reference` (the product's Gabillon price levelised like the LCOP; SEED says so). The exported TEA workbook opens with the report sheets (`core/tea_report_workbook.py`). GEX administrators (token `is_platform_admin`) get top-bar buttons to `/gex-console`, `/gex-console/gabillon`, `/gex-console/tea-parameters` (read only, 403 otherwise). Result tables use `frontend/src/lib/houseStyle.ts`. Platform **2124 pass / 15 skip / 0 fail**, frontend **346**. North Sea's open TEA run is `CLM-MBC-6c2bc77c3e` (3.2.3; supersedes 6cdd261cbd): Foxwell reviews that one.
**2026-11-17 (main made current development): 1896 pass, 15 skip, 0 fail** at head **120**, both exported, run alone (23 min). The first run of the day was 1892 / 15 / 3: one database timeout on :55432 (passes on re-run) and two `test_project_records.py` tests still expecting stored gate scores; updated to the 17 Nov structuring rule, +1 test. Same 15 skips (7 auth isolation, 7 plant builder, 1 evidence archive). Frontend **305**, `tsc` and the menu audit clean.

**2026-11-16 (requirements pins): 1782 pass, 15 skip, 0 fail**, both exported, run alone (= the 1797 collected; same 15 skips). `requirements.txt` pins now match `backend/venv` (pydantic 2.5.3 → 2.12.5 and 14 others; `cryptography==46.0.6` pinned, as newer releases have no Intel-macOS wheel and need Rust). A clean Python 3.14 `pip install --dry-run` resolves with no source build EXCEPT `matrix-nio[e2e]` → `python-olm`, which needs `brew install libolm cmake` (imported by nothing; unchanged).

**2026-11-16 (connector acceptance cases, mapping v0.3): `test_connector_fixtures.py` now 73 (+31 for 15 acceptance cases, +4 for the cross-company disclosure rule, §5.11; ten more breaks caught).** Earlier the same day: **+38 `test_connector_fixtures.py`** — offline, no database, synthetic (`tests/fixtures/connectors/`, mapping v0.2 §7). Run alone: 38 pass, 0 skip; negative-verified six ways. **Full suite NOT re-run**: 1797 tests collect. The UDB XSD check needs `lxml`, declared in `requirements.txt` the same day (`lxml==6.1.1`, JML); without it the check FAILS, it does not skip. Docker images rebuilt after this carry it (check free VM disk first).

**2026-11-12 (GreenMesh Step 5): 1520 pass, 15 skip, 0 fail** at head 099 = 1513 + 7
(`test_evidence_pack_pg.py`), same 15 skips.

**2026-11-12 (GreenMesh Step 4): 1513 pass, 15 skip, 0 fail** at head **099** = 1501 + 12
(`test_rfnbo_correlation_pg.py`), same 15 skips.

**2026-11-12 (GreenMesh Step 3): 1501 pass, 15 skip, 0 fail** at head **098** = 1477 + 24
(`test_metered_reconciliation_pg.py`), same 15 skips.

**2026-11-12 (GreenMesh Step 2): 1477 pass, 15 skip, 0 fail** at head **097** = 1446 + 30
(`test_custody_periods_pg.py`) + 1 (the physics guard now parametrized over two modules), same 15
skips. No frontend or engine change.

**2026-11-12 (GreenMesh Step 1): 1446 pass, 15 skip, 0 fail** at head 096 = 1438 + 8
(`test_greenmesh_retired.py`), same 15 skips. Engine 278 (275 + 3). Frontend 265, unchanged.

**2026-11-12 (GreenMesh Phase 1 baseline): 1438 pass, 15 skip, 0 fail** at head 096, both
exported, run alone. +5 against the 11-10 record of 1433, from a session not recorded here.
Skips listed under GreenMesh Step 0.

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

## GreenMesh Phase 1 — "Fix the evidence base first" (brief from Claude.ai, 2026-11-12)

Source of this brief: `../docs/product/GreenMesh_Description_and_Vision.md` (draft for
decision), sections *What the GEX code already covers*, *Weaknesses* and *Way forward*.
Everything below was read from the tree on 2026-11-12; if the code disagrees, the code wins
— fix this section.

**JML decision on G-12 (2026-11-12):** GreenMesh is KEPT as one thing only — the
physical-delivery and clearing extension of the market engine (`core/market_engine.py`) and
the chain-of-custody ledger (`api/v1/mass_balance.py`). The separate engine is retired; its
useful logic is ported. Netting (FlowFusion™) is Phase 3 and is NOT built now.

**Gate that closes Phase 1:** one synthetic RFNBO trade runs end to end on PostgreSQL and
produces an evidence pack in which every compliance item is VERIFIED from data, not DECLARED.

### Step 0 — before any change

1. **There is no git repository** (checked 2026-11-12 at `files/` and
   `files/gex-platform-enhanced/`). `git init` both trees in use, commit the baseline, work on
   a branch `greenmesh-phase1`. Until then: back up every file you touch to
   `../_claude_backups/2026-11-12_greenmesh_phase1/` (existing convention).
2. Export `DATABASE_URL` and `ALEMBIC_DATABASE_URL` (see *Database* and *Tests* above), run
   the full suite, record pass/skip/fail and migration head (096 expected) here. Re-run at the
   end of every step; a skip is not a pass (`-rs`).
3. No deletions without JML. Retired files go to `../_claude_backups/.../_to_delete/` and are
   listed in the step report.

**Step 0 done 2026-11-12.** `files/` itself is not a repository (its `.git/` holds only vexp
hooks) and was not initialised: it holds `.env`, dumps and client documents. Initialised
instead: `gex-platform-enhanced/` (baseline `64b5171`, 1056 files) and `../gex_pf_engine/`
(baseline `9355b04`, 61 files), both on branch `greenmesh-phase1`, **no remote, never push**.
Each has a `.gitignore` adapted from co-work's (secrets, databases, dumps, client files, venvs,
`frontend/dist`). co-work, the public repository, is not the reference for this work. If it is
synced again, the rsync must add `--exclude='.git'` (`sync-to-docker.sh` already has it).
Baseline, both URLs exported, run alone: **head 096**, 151 tables, 144 FORCED; platform
**1438 pass / 15 skip / 0 fail** (245 s). The 15 skips read with `-rs`: 7
`test_auth_store_isolation.py` (auth has no SQLite path on postgres), 7
`test_plant_builder_energy.py` (catalogue electrolysers state no SEC), 1
`test_evidence_history_pg.py` (archive empty). Frontend and PF engine suites not run.

**2026-11-17 (JML): main is current development.** Each new step or phase starts as a branch from
main and goes back into main once its tests pass and JML approves. No remote, never push.
`greenmesh-phase1` and `greenmesh-phase2` are kept as history; main was set to
`greenmesh-phase2`'s tip (`6dc75e9`) the same day.

### Step 1 — one name, one meaning (G-12, G-13)

- `api/v1/greenmesh.py`: imported in `main.py` (`HAS_GREENMESH`) but never mounted; every
  handler is a TODO stub. Do NOT mount it. Remove the import; move the file to `_to_delete`.
- `core/greenmesh_engine.py` (v5.1, called by nothing): port `CertificationPremium` into the
  reference catalogue with its sources labelled (BNEF 2024, ICIS 2025 per the docstring) and
  marked as indicative; drop the rest (mass balance and GoO retirement duplicate live code;
  netting is Phase 3).
- `core/greenmesh_bankable.py`: keep as the design source for Phase 2 (quality verification
  before title transfer, take-or-pay, availability guarantee, penalties). Move it to
  `docs/design/greenmesh_physical_layer_reference.py` with a header saying it is not wired.
- Frontend: menu label `'GreenMesh (Capacity & Logistics)'` → `'Capacity & Logistics'`
  (`frontend/src/config/menuArchitecture.ts`, id `greenmesh-netting` → `capacity-logistics`,
  check every reference and frontend test). `CapacityPage.tsx`: heading "GreenMesh" →
  "Capacity & Logistics"; the "How GreenMesh Aggregation Works" box claims procurement savings
  of "typically 5–15%" with no source — remove the figure. `helpText.ts` `// ── GreenMesh ──`
  keys stay (they describe GoO value, mass balance, netting) but the netting entry must say
  "planned (Phase 3)".
- PF engine (`../gex_pf_engine`, sibling repo): the "GreenMesh rollup" is a portfolio rollup
  of offtake contracts. Rename to `portfolio_rollup`; keep the old route as a deprecated alias
  for one release; update `frontend/src/api.ts` `greenmeshRollup` and
  `features/pricing/hooks.ts` `useGreenmeshRollup`.
- Documents (G-13): `../docs/product/Vademecum_v4.4.md` lines 337, 353, 368, 420, 451 (API is
  not "✅ Built"; `greenmesh_bankable.py` is not Matrix/Synapse — that is
  `services/matrix_service.py`); `GEX_Platform_Technical_Reference_v3.md` (both copies) lines
  37, 96 and the `core/greenmesh_bankable.py` section; `docs/menu-architecture-map.md` and
  `docs/menu-architecture/GEX_menu_architecture_views.md` labels. Update gap register G-12/G-13
  status.
- **Acceptance:** `grep -rni greenmesh backend/app frontend/src` returns only the Phase 2
  placeholder text and helpText; suite counts unchanged apart from the tests you add or
  intentionally retire (list them).

**Step 1 done 2026-11-12** (handoff §8 item 62). Acceptance grep: only the two
`// ── GreenMesh ──` helpText headers (frontend and the stray copy in `backend/app/config/`).
- Retired to `../_claude_backups/2026-11-12_greenmesh_phase1/_to_delete/`: `api/v1/greenmesh.py`,
  `core/greenmesh_engine.py`, `frontend/.../producer/ProductionDashboard.tsx` (imported by
  nothing; its only data were the never-mounted `/api/v1/greenmesh/*` routes) and the PF
  engine's empty `pf_engine/core/greenmesh.py`. Import blocks removed from `main.py` and `A_main.py`.
- Premiums: 5 catalog keys `certification_premium_{rfnbo,red_iii,45v,certifhy,corsia}`
  (COST_PER_MASS, "INDICATIVE"); 13 rows `proposed` by `CERT_PREMIUM_PORT_20261112`, source
  class `gex_assumption`, none in force. **After an Alembic rebuild run
  `scripts/load_certification_premiums_20261112.py --execute`** (a dump restore carries them;
  backup `gex_platform_2026-11-12_1003.dump` taken before the write). The 45V row's €300/t is a
  tenth of `subsidy_45v_max` (USD 3.28/kg): its note says so; check before approving.
- PF engine: `portfolio_rollup`, `POST /pf/offtake/portfolio-rollup`; `/pf/offtake/rollup` and the
  `greenmesh_rollup` config key are deprecated aliases for one release (the new key wins).
  Platform proxy: `/pricing/offtake/portfolio-rollup` (old paths deprecated); frontend
  `pricingAPI.portfolioRollup`, `usePortfolioRollup` (no caller).
- Also outside the brief's list: `demand_aggregation.py` and `task_router.py` no longer say
  "via GreenMesh" / "GreenMesh / FlowFusion logic"; helpText's certification premium says
  indicative.
- Tests: +8 platform (`test_greenmesh_retired.py`), +3 engine (`test_offtake.py`); four breaks
  caught (a greenmesh import, a key not INDICATIVE, the alias not deprecated, the old key
  ignored). None retired. Platform **1446 / 15 skip / 0 fail**, engine **278**, frontend
  **265** (= its baseline, measured on this Mac), `tsc` and the three build audits clean.

### Step 2 — chain of custody to RED III grade (`api/v1/mass_balance.py`, migration 097)

The module's own docstring lists the gaps. Close them, PostgreSQL only, RLS like the rest:

- **Accounting periods.** `coc_period` per facility: start, end, status OPEN/CLOSED. Inputs and
  withdrawals belong to a period. Closing produces a period statement: opening + inputs ×
  conversion − withdrawals = closing. Closed periods are immutable (trigger, like
  `tb_contract`). Negative balance at any point is refused by default; scheme-specific rules
  (period length, carry-forward) are parameters to confirm with the certifier — do not invent
  values.
- **Input consignments.** `coc_input`: period, input type (electricity MWh, CO₂, N₂, water),
  quantity, unit, characteristics, evidence reference (PPA id, GO id, supplier PoS id).
- **Conversion factors.** Per facility, pathway and molecule, versioned with `valid_from`
  (e.g. kWh per kg H₂, kg H₂ per kg NH₃). A lot whose output exceeds inputs × factor beyond a
  tolerance parameter is flagged, not silently accepted.
- **Characteristics.** Replace the single `carbon_intensity_gco2e_mj` with a validated
  characteristics object (GHG intensity, pathway, scheme, certificate id, country of origin,
  production window, RFNBO flag, additionality basis). Keep the old column readable.
- **No duplicate lifecycle.** Link lot allocations to tokens; claim/retirement stays in
  `tokens_sqlite.py` (MINTED → RETIRED).
- Extend the hash chain to inputs and period close.
- **Tests (pg_store):** withdrawal beyond period balance refused; period statement arithmetic;
  closed period immutable; conversion mismatch flagged; invalid characteristics refused;
  existing `test_chain_of_custody.py` still green.

**Step 2 done 2026-11-12 — head 097** (handoff §8 item 63; backup `gex_platform_2026-11-12_1036.dump`
taken first; round-tripped 097 → 096 → 097). **155** tables, **148** FORCED.
- Tables: `coc_scheme_rule` (EMPTY by design — the certifier's values), `coc_period`, `coc_input`
  (hash-chained per period by `seq` from the period's `open_hash`), `coc_conversion_factor`
  (declared input per kg output, versioned by `valid_from`); lots + `period_id`, `facility_id`,
  `characteristics`, `conversion_check`, `conversion_detail`; allocations + `period_id`.
- Logic in `app/core/custody_ledger.py`; routes under `/api/v1/chain-of-custody/periods`,
  `/conversion-factors`, `/scheme-rules`. Credit = min over required input types of CERTIFIED
  inputs / factor in force on the input's day; the conversion check uses ALL inputs. No rule →
  no carry-forward, no negative balance, length unchecked, said in the statement. A period never
  closes in deficit.
- Triggers: a CLOSED period never changes, no period is deleted, periods of one key never overlap;
  inputs, factors and allocations are append-only (UPDATE/DELETE/TRUNCATE revoked from `gex_app`,
  asserted); a period lot's declaration is fixed and nothing touches it once its period closes.
- **Behaviour changes:** allocations were PLATFORM_ADMIN-only (043: no `project_id`), so no producer
  could ever allocate; now owner/GEX write and project access reads, through the lot. An
  allocation needs a real token of the lot's project, not RETIRED/ANNULLED/VOIDED, not backed by
  another lot, and links it (`tokens.mass_balance_lot_id`). Lots without a period still work
  (`custody_grade: NO_PERIOD`); the 72 pre-existing lots keep `period_id` NULL.
- **Tests changed on purpose:** `test_chain_of_custody` no longer forbids the word
  `conversion_factor` (declared ratios are required now; the process terms stay forbidden, and the
  guard now covers `custody_ledger.py` too). `test_tail_slices` tampered with allocations as
  `gex_app` and, once refused, LEFT 3 ROWS IN THE DEV DATABASE (removed the same minute as the
  superuser); for append-only ledgers it now proves the runtime is refused, tampers and cleans up
  as the superuser. It still writes the dev database for the other six ledgers (pre-existing).
- New: `test_custody_periods_pg.py` (30, `pg_store`). Five breaks caught (balance guard, conversion
  flag, unknown characteristics keys, chain ignoring content, the closed-period trigger).
- Open, in the gap register: G-19 (72 `created_by='test'` lots on `proj_etf_pecos1`), G-20 (actors
  from the request body), G-21 (lots writable by project-access holders).

### Step 3 — reconcile lots against metered output

- Source: `plant_data` via `core/ot_boundary.py` (`PRODUCTION_VOLUME`, `POWER_CONSUMPTION`).
  Units are free text today ("m³/h H2, t/day NH3"). Require an explicit unit on ingest,
  normalise to kg and MWh per interval, refuse unknown units.
- On lot creation and period close, compare declared volume with metered production for the
  same facility and window → `RECONCILED`, `VARIANCE` (tolerance = parameter, value to agree
  with certifier or independent engineer) or `UNVERIFIED` when no meter data exists. Never
  pass silently. Expose the status on the lot response.
- **Tests:** each of the three outcomes; unit refusal.

**Step 3 done 2026-11-12 — head 098** (handoff §8 item 64; backup `gex_platform_2026-11-12_1057.dump`
first; round-tripped 098 → 097 → 098). **156** tables, **149** FORCED.
- Ingest: PRODUCTION_VOLUME and POWER_CONSUMPTION need `quantity`, `unit`, `interval_start`,
  `interval_end` (with a UTC offset) and, for production, `molecule`; stored normalised to kg or
  MWh for the interval (rates x hours). Units: kg, t, kg/h, t/h, kg/d, t/d | kWh, MWh, GWh, kW, MW.
  **A volume (m3, Nm3, m3/h) is refused**: no density has been agreed (gap G-22).
- A gateway now has a `facility_id`; a reading's project must be its gateway's (validated, and by
  trigger for every data type — before 098 the body's `project_id` was trusted), a metered reading
  takes its gateway's facility, and one gateway's readings of one type and molecule never overlap.
  `plant_data` is append-only for `gex_app`. `store_plant_data` RAISES on failure (it used to log
  and answer "accepted"); the route maps that to 409 / 403 / 503.
- `app/core/meter_reconciliation.py`: RECONCILED / VARIANCE / UNVERIFIED with a reason. Windows are
  whole UTC days; only meter intervals wholly inside count (straddling ones reported, never
  prorated); coverage below 100% is UNVERIFIED; lots with the same window are added, a partly
  overlapping window is UNVERIFIED. Tolerance from `coc_meter_tolerance` (EMPTY: no row = ZERO).
- Lots: `meter_check`/`meter_detail` (at creation, fixed with the declaration) and
  `meter_reconciliation` (live, on every read). Period statement: `meter_reconciliation` for
  production and electricity (declared ELECTRICITY inputs vs POWER_CONSUMPTION).
- Tests: `test_metered_reconciliation_pg.py` (24, `pg_store`); four breaks caught (coverage, tolerance,
  unknown units, the overlap trigger). `ot_boundary` had no test at all before.

### Step 4 — compute correlation, do not accept flags

- `core/decision_twin.py` `evaluate_red_iii(...)` takes `temporal_matching: str` and
  `geographical_correlation: bool` from the caller. Keep that path only as `DECLARED`.
  Add a computed path:
  - **Temporal:** match electrolyser consumption against contracted renewable generation per
    interval (monthly or hourly). Generation data is not in `ALLOWED_DATA_TYPES` — add
    `PPA_GENERATION` (MWh per interval, PPA id, generator bidding zone, commissioning date), or
    define a provider interface (hourly-matching services exist; adapter later).
  - **Geographic:** compare electrolyser and generator bidding-zone codes.
  - **Additionality:** from PPA metadata and commissioning dates.
- **Defect to fix:** the temporal check accepts `monthly` with no date limit. Under DA
  2023/1184 Art. 6 as written, monthly is acceptable until 31 Dec 2029 and hourly from
  1 Jan 2030. The DA is under targeted review (autumn 2026), so put the rule in a versioned
  rule table with `valid_from`/`valid_to`, not in code.
- **Tests:** computed pass/fail for monthly and hourly; date-dependent rule; declared input is
  labelled DECLARED in the result.

**Step 4 done 2026-11-12 — head 099** (handoff §8 item 65; backup `gex_platform_2026-11-12_1111.dump`
first; round-tripped 099 → 098 → 099). **159** tables, **152** FORCED.
- `rfnbo_rule` (versioned, append-only, read by all, GEX writes), seeded AS WRITTEN in 2023/1184 by
  `MIGRATION_099`: temporal MONTHLY to 2029-12-31, HOURLY from 2030-01-01 (Art. 6); additionality
  36 months (Art. 5) and the transition (electrolyser before 2028-01-01, exempt to 2037-12-31,
  Art. 11); geographic = same bidding zone (Art. 7, alternatives NOT evaluated). Every row's note:
  confirm with counsel or the certifier — the DA is under review. **Change the rules by adding
  rows, never in code.**
- `coc_facility_profile` (bidding zone, electrolyser commissioning), `coc_ppa` (generator, zone,
  commissioning, evidence), and the metered type `PPA_GENERATION` (MWh, `ppa_ref` resolved to a
  registered PPA of the facility; trigger checks it).
- `app/core/rfnbo_correlation.py`, `GET .../periods/{id}/rfnbo-correlation`: temporal (UTC month or
  hour buckets by the rule on the reading's day; straddling readings UNVERIFIED, never prorated),
  geographic (other-zone PPAs reported, not counted), additionality per PPA; overall PASS / FAIL /
  UNVERIFIED, `basis: COMPUTED`, with `rules_used`. The period statement records it.
- `decision_twin.evaluate_red_iii` keeps the caller's flags as `basis: DECLARED`; "monthly" now
  depends on `as_of` (default today) through the rule table, and an unreadable rule FAILS the
  declared check instead of passing it. The API takes `as_of`.
- Tests: `test_rfnbo_correlation_pg.py` (12); two breaks caught (shortfall ignored, other zones
  counted). Hydrogen supplied as an input (H2 in coc_input) has no correlation check yet.

### Step 5 — lender evidence pack per contract

- `GET /api/v1/evidence-pack/contract/{contract_id}` assembling: contract record and ledger
  anchor hashes (`core/ledger_anchor.py`); token lineage; lots, allocations and period
  statement; meter reconciliation status; RED III results with the rule-table version used;
  settlement events (`api/v1/settlement_events.py`); `evidence_ledger` entries.
- JSON first, with a SHA-256 manifest. Every item is labelled `VERIFIED`, `DECLARED` or
  `MISSING`. A declared value is never shown as verified.
- **Gate test (end to end, pg_store):** synthetic RFNBO project → metered production → lot →
  token → contract → settlement → evidence pack with zero `DECLARED`/`MISSING` items in the
  compliance section.

**Step 5 done 2026-11-12 — head stays 099, no migration** (handoff §8 item 66).
- `GET /api/v1/evidence-pack/contract/{id}` (`app/core/evidence_pack.py`, `routes_evidence_pack.py`,
  domain `sustainability`). Sections: contract (record, recomputed event chain, anchor receipts),
  tokens (lineage through `tokens.mass_balance_lot_id` and the recomputed allocation chain), custody,
  **compliance** (per period: custody_period, conversion, metered_production, metered_electricity,
  temporal_correlation, geographic_correlation, additionality — read from the CLOSED, re-verified
  statement), declared_characteristics, settlement, evidence_ledger; SHA-256 per section and
  `pack_sha256` (generated_at excluded, so the same records give the same manifest).
- Each item: label VERIFIED | DECLARED | MISSING (provenance) and result PASS | FAIL. An open period
  makes every compliance item DECLARED. Lot characteristics (GHG intensity, certificate, RFNBO flag)
  are DECLARED and OUTSIDE compliance: Phase 1 verifies no LCA or certificate. Anchor receipts are
  DECLARED (re-check with `scripts/verify_anchor.py`). A non-party gets 404 (tb_contract RLS).
- **The gate** (`test_evidence_pack_pg.py::test_the_phase_1_gate…`): custody, meters, PPAs and
  correlation through the real routes → 7 compliance items VERIFIED and PASS, none DECLARED or
  MISSING. **Gate closed 2026-11-12 (later):** the contract and settlement now come from the
  REAL market flow (listing → RFQ → proposal → both accept → four-eye confirmations →
  `POST /market/settlements` → payee confirms), on the token allocated from the custody lot. Still
  synthetic: the other six pack tests keep a directly inserted contract row (they probe the pack).
  The settlement section stays DECLARED, as before.
- Tests: 7; two breaks caught (characteristics shown VERIFIED, an open period treated as final).

**2026-11-12 (Phase 1 gate, market leg): 1520 pass, 15 skip, 0 fail** at head 099; the gate test was rewritten, no test added.

**2026-11-16: head 120 — D-A, certificate validity over delivery, check 9, F15** (handoff §8 item 91; backup `gex_platform_2026-11-16_1646.dump`).
- A Marketplace record is CONFIRMED only with `evidence_sha256` and a confirmer other than its importer (trigger). The 51 unprovenanced confirmations are UNVERIFIED with `quarantine_reason`. `marketplace_record_history` keeps them; only the trigger writes it.
- **After an Alembic rebuild:** `apply_marketplace_decisions_20261025.py` now quarantines and never confirms.
- The 5 spot prices (F08) are untouched: JML's approval, and the registry has no withdrawal.
- Certificates count only over the whole delivery window.
- "Changed since you looked" is `market_engine._changed_since`. An acceptance stores its assessment.
- Availability is `project_economics.token_windows` (owner/GEX only), never the stored percentages.
- R12 and D-H: proposals in `docs/discovery/GEX_Discovery_Decisions_R12_DH_2026-11-16.md`, nothing built.
- Platform **1828 pass / 15 skip / 0 fail** (1782 + 35 connector tests added later on 16 Nov + 11 here), frontend **305**.

**2026-11-14 (Phase 1 closed): check 10 passes** — `test_discovery_journey_pg.py` runs publish → search → compare → enquiry → consent → proposal through the real routes (handoff §8 item 89). Platform **1744 pass / 15 skip / 0 fail** (1743 + 1; a first run lost PostgreSQL on :55432 mid-way, 130 skips, and was rerun), frontend **298**. Open (corrected 16 Nov; D-G and the Interest board are Phase 2): D-A, R12, check 9, certificate validity on delivery dates, F15, D-H; then the detail panel, labels, §5.4 errors; then navigation.

**2026-11-14 (Phase 1 step 6): head 119 — the non-binding enquiry (D-D)** (handoff §8 item 88). `core/enquiry.py`: one listing or RFQ; badges and "you/them" only until the RECEIVER shares contact, which releases both identities to both and is `enquiry.contact_shared` in the ledger; decline releases nothing. `market_enquiry_message` is append-only. Screens: Market Discovery "Ask (non-binding)", `/deals`. Platform **1743 pass / 15 skip / 0 fail** (1729 + 14), frontend **298**.

**2026-11-14 (Phase 1 step 5): head 118 — compatibility, eligibility before price** (handoff §8 item 87). `core/compatibility.py` alone decides Compatible / Incompatible / Needs evidence per requirement, on the ANONYMOUS listing (`market_engine._public_listing`); one mandatory Incompatible excludes at any price; no claim is Needs evidence, never Incompatible. A seller's proposal against a mandatory requirement is 409 `REQUIREMENT_NOT_MET`; the buyer may waive its own. `compatibility_assessment` (118) is append-only for every role and stored with each proposal. `GET /market/rfqs/{id}/compatibility` (owner only; Compare ≤ 4). Platform **1728 pass / 15 skip / 1 fail** (the 1 = `test_change_password` losing its connection through the :55432 forwarder mid-run; no PostgreSQL restart in its log; the file passes alone 9/9; 1712 + 17 = 1729 closes), frontend **293**.

**2026-11-14 (Phase 1 step 4): the listing wizard `/listings/new?project=`** (handoff §8 item 86; no migration). Project → capacity → token (+ evidence) → terms → anonymous preview → draft or publish; resumes from saved drafts. Every create sends an `Idempotency-Key`. "List on Market" and "List supply" lead here. Platform **1712 pass / 15 skip / 0 fail** (1710 + 2), frontend **289**.

**2026-11-14 (Phase 1 step 3): head 117 — D-C listings and RFQ requirements** (handoff §8 item 85). What an anonymous member sees is `OFFER_LISTING_FIELDS` / `RFQ_LISTING_FIELDS` plus `product_record.listing_summary` — add to those allowlists deliberately, never a raw row. RFQ requirements are validated only in `core/requirements.py`. Platform **1710 pass / 15 skip / 0 fail** (1699 + 11), frontend 282.

**2026-11-14 (Phase 1 step 2): head 116 — product records** (`core/product_record.py`, `/api/v1/products`, handoff §8 item 84). A certificate is verified ONLY by an appointed CERTIFIER/INDEPENDENT_ENGINEER of an independent company (D-F); expiry is derived from `valid_until`, never stored; scope says whether it covers the organisation, the site or this quantity. Platform **1699 pass / 15 skip / 0 fail** (1689 + 10).

**2026-11-14 (Phase 1 step 1, D-B role policy): 1689 pass, 15 skip, 0 fail** at head 115 = 1675 + 14 (`test_market_policy_pg.py`); frontend **278**. **Who may act in the market is `core/market_policy.py` and nowhere else:** Commercial acts, the CEO or CFO approves TRADE_CONFIRM, Operations may declare capacity. Test parties need a `business_function`; a fixture's acting account is COMMERCIAL and its approver EXECUTIVE. Screens read `GET /market/policy` via `useMarketPolicy`.

**2026-11-14 (buttons retargeted, F17): frontend 275** (+6 `MarketLinks.test.tsx`); backend unchanged. Links into the market go through `lib/marketLinks.ts` (`marketDiscoveryPath`, `useCanOpen`): never hand-write `/matching` as a discovery target.

**2026-11-14 (capacity guard, 115): 1675 pass, 15 skip, 0 fail** at head **115** = 1673 + 2 (`test_token_mint_pg.py`); frontend 269. Same 15 skips.

**2026-11-13 (discovery Phase 0, 114): 1673 pass, 15 skip, 0 fail** at head **114** = 1654 + 8 (`test_token_mint_pg.py`) + 10 (`test_market_split_and_idempotency_pg.py`) + 1 (carved delivery); frontend **269** (+2 `RfqIdempotencyKey.test.ts`). Same 15 skips.

**2026-11-13 (buyer list, 113): 1654 pass, 15 skip, 0 fail** at head **113** = 1648 + 6 (`test_demand_buyers_access_pg.py`); frontend **267**. Same 15 skips.

**2026-11-13 (stakeholder economics leak, 112): 1648 pass, 15 skip, 0 fail** at head **112** = 1646 + 2 (`test_marketplace_records_pg.py`); frontend **267** = 265 + 2 (`WithheldEconomics.test.tsx`). Same 15 skips.

**2026-11-13 (Phase 2 Step 6): 1646 pass, 15 skip, 0 fail** at head **111** = 1640 + 6 (`test_registry_connectors_pg.py`). Same 15 skips.

**2026-11-13 (Phase 2 Step 5): 1640 pass, 15 skip, 0 fail** at head **110** = 1635 + 5 (`test_evidence_pack_delivery_pg.py`). Same 15 skips.

**2026-11-13 (Phase 2 Step 4): 1635 pass, 15 skip, 0 fail** at head **110** = 1622 + 13 (`test_take_or_pay_pg.py`). Same 15 skips.

**2026-11-13 (G-23 upstream proof): 1622 pass, 15 skip, 0 fail** at head **110** = 1616 + 6 (`test_upstream_proof_pg.py`). Same 15 skips.

**2026-11-13 (Phase 2 Step 3, sub-step 5): 1616 pass, 15 skip, 0 fail** at head **109** = 1604 + 12 (`test_delivery_title_pg.py`); frontend 265, engine 278. Same 15 skips. Step 3 stopped before SETTLED.

**2026-11-13 (Phase 2 Step 3, sub-steps 3–4): 1604 pass, 15 skip, 0 fail** at head **108** = 1581 + 17 (sub-step 3, head 107: `test_quality_sheet.py` 9, `test_delivery_inspection_pg.py` 8) + 6 (`test_delivery_dispute_pg.py`). Same 15 skips.

**2026-11-13 (Phase 2 Step 3, sub-step 2): 1581 pass, 15 skip, 0 fail** at head **106** = 1573 (G-25, head 105: 1568 + 5 `test_order_book_token_pg.py`) + 8 (`test_delivery_risk_pg.py`). Same 15 skips.

**2026-11-12 (Phase 2 Step 3, sub-step 1): 1568 pass, 15 skip, 0 fail** at head **104** = 1552 + 16 (`test_contract_clauses.py` 13, `test_contract_clauses_pg.py` 3); frontend 265, engine 278. Same 15 skips.

**2026-11-12 (Phase 2 Step 2): 1552 pass, 15 skip, 0 fail** at head **103** = 1543 + 12 (`test_delivery_record_pg.py`) − 3 (delivery cases retired from `test_custody_write_policies_pg.py`); frontend 265, engine 278. Same 15 skips.

**2026-11-12 (Phase 2 Step 1): 1543 pass, 15 skip, 0 fail** at head **102** = 1520 + 23; frontend 265, engine 278. Same 15 skips.

### Out of scope for Phase 1

Deliveries, routes and title transfer (Phase 2, gap G-08); UDB and scheme-registry
connectors (Phase 2); netting (Phase 3).

### Reporting

After each step: append a dated line under *Tests* with the measured counts and head, update
`docs/CLAUDE_HANDOFF.md`, and update the gap register (G-12, G-13 and any new gap). State
what is verified and what is declared; do not overclaim.

---

## GreenMesh Phase 2 — brief, D0–D8 decided, Step 1 done (2026-11-12)

The brief is in `docs/GREENMESH_PHASE2_BRIEF.md`. It covers deliveries and title transfer after
quality verification (G-08), take-or-pay shortfall (part of G-11), registry and scheme
connectors, and an ammonia corridor pilot. Steps 1 and 2 are built (heads 100–103); nothing after them.

- **Reference:** v2 of `../docs/product/GreenMesh_Description_and_Vision.md` (12 Nov 2026) is the
  reference description. It is the master; the Word file is generated from it. Nothing is built from
  it directly.
- **Economics:** its economics section (netback to IRR) is SCENARIO only until JML answers decisions
  E1–E9. Build no economics code. **Re-confirmed by JML on 2026-11-13** after reading the FlowFusion
  integration plan (`Downloads/FlowFusion_Integration_and_Value_Plan_2026-11-13.md`) and the
  standalone solver `GreenMesh_Fixed_Code_v0_2` (networkx min-cost flow; not in either venv; not run
  here). Both are design input only. The plan's Increment A ("build decision support now") does not
  apply. Its permissioned upstream proof is the candidate fix for G-23, which is platform work, not
  economics.
- **E1, E2 and E5 decided (JML, 13 Nov; `docs/GREENMESH_ECONOMICS_DECISIONS_E1_E9.md`):**
  - E1, the baseline: the best confirmed offer; before FID, a labelled forecast.
  - E2, the objective: producer netback, no-worse-off with zero tolerance.
  - E5, where it lives: the PF engine via a new authorised snapshot endpoint; IRR built in the engine;
    networkx now, HiGHS later.

- **E3, E4, E6, E7, E8 and E9 decided too (JML, 13 Nov), all as recommended.** E8 is kept as written:
  economics code starts only after the certifier pre-assessment of a Phase 1 pack, which has NOT
  happened.

  **The rule still holds until then.** The decisions are in
  `docs/GREENMESH_ECONOMICS_DECISIONS_E1_E9.md`. The first increment is the read-only, SCENARIO-labelled
  PF-engine module. Level 2 (swaps) waits for the certifier's answer to E9.
- **Step 3:** Phase 2 Step 3 follows the brief's "Step 3 — amendment (12 Nov 2026)", not the original
  Step 3 text (`docs/GREENMESH_PHASE2_STEP3_PROMPT.md`).

**JML decided D1–D8 on 2026-11-12:**
- **D1:** an independent inspector (SGS or similar), appointed by either party and agreed by both.
  GEX does not appoint it.
- **D2:** the quality spec sheet comes from confirmed terms only.
- **D3:** off-spec cargo passes title only with a waiver both parties confirm, shown as DECLARED
  and FAIL.
- **D4:** an Incoterm and a named place on the contract.
- **D5:** CertifHy or ISCC first, the UDB last, the interface open to further actors.
- **D6:** export only.
- **D7:** an ammonia corridor into North-West Europe, FortaVerde with the client's consent.
- **D8:** the density is an approved reference row; G-19's lots are archived, then deleted after a
  backup.

**D0 (JML, later the same day): start Step 1 now.**

**Step 1 done 2026-11-12, head 102** (handoff §8 item 68; branch `greenmesh-phase2`).
- G-19: the test lots were archived and deleted.
- G-20: custody actors come from the token.
- 100: lots and deliveries take owner/GEX writes only (G-21).
- 101: `coc_input.source_lot_id` carries the upstream hydrogen's correlation (`upstream_hydrogen`).
- 102: hydrogen Nm³ converts only with an APPROVED density.
**After an Alembic rebuild run `scripts/propose_h2_density_20261112.py --execute`.** The density
row is PROPOSED (0.08988 kg/m³, not checked): approve it only after confirming it against NIST and
the meters' reference conditions. New gap G-23: cross-company hydrogen lots.

**Step 2 done 2026-11-12, head 103 — the delivery record** (handoff §8 item 69; backup
`gex_platform_2026-11-12_1914.dump`).
- Each state change is a contract event `DELIVERY_<state>`. The event carries `delivery_id`, which is
  in the hash only when set.
- **No second history:** `deliveries` holds the current state, which a trigger checks at COMMIT
  against the latest event.
- **Who acts:** the seller schedules and dispatches, the buyer receives, either party inspects or
  disputes.
- **Not built:** ACCEPTED, REJECTED, TITLE_TRANSFERRED and SETTLED are refused by trigger until
  Step 3.
- **Limits:**
  - draws ≤ the tokens' custody allocation;
  - nothing dated inside a CLOSED custody period;
  - the Incoterm and place are read from the confirmed terms only (market trades carry none: G-24).
- **Writes** go through the operator connection after `core/delivery_record.py` authorises the
  party. Routes are under `/api/v1/trading-book/records/{id}/deliveries` and `/deliveries/{id}`.
- `flows.py` prices a delivered-basis payment from the buyer's receipt.
- **Tests:** a test reading `os.environ["DATABASE_URL"]` under `pg_store` hits the DEV database:
  `pg_store` patches `settings`, not the environment. Use the fixture's URL.

**Step 3, sub-step 1 done 2026-11-12, head 104 — typed clauses** (handoff §8 item 70).
- **Three records, three clauses** (`trading_book/clauses.py`):
  - risk: a typed `delivery` clause (incoterm, named_place, shipment_point);
  - title: a `title` clause (104 admits the type; there is no default);
  - payment: a typed `payment` clause (trigger, quantity_basis).
- **V15** refuses an invalid typed clause or two of a kind in one scope. Free text is never typed.
- **The Incoterm governs risk only (R1):** a delivery reports risk, title and payment bases separately.
- **Waiting on JML:** whether "no payment clause, no figure" applies to market trades, which can't
  carry one (P1).

**G-25 closed 2026-11-13, head 105:** an order-book sell order names one own MINTED token (firm,
all-or-nothing). `tb_order.origin_book` keeps it out of market listings.

**Step 3, sub-step 2 done 2026-11-13, head 106 — risk** (handoff §8 item 71).
- `DELIVERY_FACT_RISK_PASSED` is derived (actor `system:incoterm`, no company) and written with the
  act that passes risk:
  - EXW and F/C terms: at dispatch;
  - DAP and DDP: on arrival;
  - DPU: on the buyer's unloading record.
- A C term needs its `shipment_point`, and no Incoterm means no risk.
- Facts (`DELIVERY_FACT_*`) never move the state.
- `delivery_document`: documents on file by GEX-computed sha256, append-only.

**Step 3, sub-step 3 done 2026-11-13, head 107 — quality before title** (handoff §8 item 72).
- Spec sheet: `quality_spec.parameters`, checked by V16.
- Inspector: proposed by one party and agreed by the other with four eyes (WAE `DELIVERY_CONFIRM`,
  TRADE_CONFIRM's rules). Never seller, buyer, GEX or an inactive company.
- Certificate: the agreed inspector's; PASS gives a derived ACCEPTED (VERIFIED).
- FAIL: a waiver both parties confirm (DECLARED / FAIL), or the buyer's REJECTED, which releases
  the draws.
- TITLE_TRANSFERRED and SETTLED are still refused.

**Step 3, sub-step 4 done 2026-11-13, head 108 — the DISPUTED exit** (handoff §8 item 73).
- A resolution is proposed by one party and confirmed by the other with four eyes; the state then
  moves derived. GEX arbitrates nothing.
- R4: ACCEPTED only with the agreed inspector's certificate; with none, only REJECTED.

**Step 3, sub-step 5 done 2026-11-13, head 109 — title and the token split. Stopped before SETTLED.**
(handoff §8 item 74)
- `deliveries.title_passes` holds the title clause. The holder moves at the later of ACCEPTED and the
  clause's trigger (T1). ON_PAYMENT_IN_FULL and a missing clause are refused (G-27).
- Partial title: the part goes SPLIT and gets two children, which sum exactly (`token_split`,
  `app_token_kg`). The buyer's part becomes SETTLED.
- SPLIT tokens are frozen; the holder changes only on the operator connection.
- R2: market settlement leaves delivery contracts' tokens alone.

**G-23 closed 2026-11-13, head 110 — the upstream proof** (handoff §8 item 75).
- An H2 input may name `source_token_id`, a SETTLED hydrogen token its company holds.
- `core/upstream_proof.py` carries the upstream period's re-verified RFNBO result through, on the
  operator connection after a holder check. It is one more PLATFORM_ADMIN call site, alongside
  `market_engine` and the delivery modules that use its operator connection.
- A cited token can no longer be RETIRED.

**Phase 2 Step 4 done 2026-11-13 (no migration) — take-or-pay shortfall + G11 evidence** (handoff §8 item 76).
- The shortfall is read from the TRADE's typed `commitment` clause and its physical flows (not the frame
  cards: their sub-legs carry no deliveries). JML confirmed this on 2026-11-13.
- Deliveries count in the year of the flow they fulfil. An amount only with a stated price; waivers
  count DECLARED.
- No availability or penalty: no such terms exist.
- G11: the seller files the acceptance record as evidence. GEX verifies nothing.

**Phase 2 Step 5 done 2026-11-13 (no migration; pack version 2) — deliveries in the evidence pack**
(handoff §8 item 77).
- Per delivery: quality (VERIFIED only with the agreed inspector's certificate; a waiver is DECLARED /
  FAIL), title (VERIFIED from the chain), route and Incoterm (DECLARED).
- The pack's tokens also come from delivery draws.
- `compliance_complete` needs every delivery VERIFIED and PASS.
- Settlements are not linked to deliveries yet; the pack says so.

**Phase 2 Step 6, head 111 — EXPORT FOUNDATION COMPLETE; external adapters and inbound verification
OUTSTANDING** (corrected 15 Nov; handoff §8 items 78 and 90; `docs/GREENMESH_CONNECTORS_RESEARCH.md`).
- **Built:**
  - one connector interface;
  - `gex_export_v1` (GEX's internal format, not a registry's; VERIFIED items only);
  - seller-only export behind the VERIFIED gate;
  - the append-only `registry_outbox`; `REGISTRY_CONNECTOR_BACKEND` = `none` only.
- **The 13 Nov research overstated what is unpublished.** Public: the AIB XSDs (v80, SD03 9.1), the
  UDB Exchange Model, and the G-REX API manual. Review them before designing an adapter; it needs no
  partner account.
- **Inbound** is three tasks: extraction, matching, authoritative confirmation.
- **D5 must name the scheme:** CertifHy NGC is book-and-claim disclosure, not RFNBO compliance.

---

**2026-11-15 (JML): GreenMesh is an OPTION, fuel-neutral, its parameters role-owned** (`docs/GREENMESH_OPTIN_FUEL_NEUTRAL_PLAN.md` v0.2, §6; nothing built yet).
- **Opt-in per project**, proposed by Operations/Commercial and confirmed by an executive (four eyes). Never needed by any trade, listing, settlement or gate. A module the project has not chosen drops out of the evidence pack; it is not shown as MISSING.
- **Fuel-neutral:** `fuel_catalog` is the one fuel master (`tb_commodity` references it). No fuel name goes in code. Any catalogue fuel may be an upstream intermediate. Bio pathways are in scope; the RFNBO checks answer `NOT_APPLICABLE` where they don't apply.
- **Roles (§3C):** live in `core/market_policy.py`. A value with no confirmer is DECLARED. A meter tolerance stays zero until a certifier or independent engineer confirms it.
- **Screens:** a GreenMesh section of Capacity & Logistics.
- **Order:** opt-in, roles, fuel-neutral, screens, then the evidence allocation ledger. FlowFusion inherits all of this.

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
