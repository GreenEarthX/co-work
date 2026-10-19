# Hand-off brief: reference data registry and cash-flow completion

For: a Claude Code session on the Mac, opened in the GEX git repository.
From: review session of 19 October 2026 (Hydrogen FM review and GEX software check).
Companion files, kept alongside this brief:
- `golden_hydrogen_fm.json`: acceptance inputs, expected outputs and tolerances.
- `replica_reference.py`: the independent Python model that produced those numbers.
Context: `claude/Hydrogen_FM_Review_and_GEX_Software_Check.md` in the Green Earth X project.

---

## 0. What this work must achieve

GEX holds price and technology knowledge in code constants. Updating it needs a release, and projects never learn that a reference moved. This work makes the database the single source of reference values. Each value is versioned, dated, sourced and approved, and projects are flagged, never overwritten, when the reference moves. It then closes the cash-flow gaps the review found: stack replacement, degradation, tax, a true IRR, one integrated lender case, subsidy eligibility, price dates on costs, and peer cost benchmarks.

## 1. Before writing any code

1. **Consolidate the copies.** The newest edits (19 Oct) are in the top-level `gex-platform-enhanced`, which is not under git. The git repository is `co-work/gex-platform-enhanced` (last commit `b8ae71b`, 12 Oct). Bring the top-level edits into the git copy, commit them as their own commit, and confirm with Jean-Marie which copy is the master from now on. `gex_pf_engine` is identical in all three copies.
2. **Create a branch:** `reference-data-registry`.
3. **Record the baseline:**
   - Run the backend tests (`backend/tests`) and the PF engine tests (`gex_pf_engine/backend/tests`), and record which pass.
   - Record the current outputs of `/api/v1/model/example/green-h2` (or wherever `example_green_h2` is routed) and of one capital-bridge project. Later changes are then visible as deliberate.
4. **Respect the existing characterisation tests:** `test_dscr_llcr_characterization.py`, `test_debt_sculptor_characterization.py`, `test_model_invariants.py`. Where this work changes a pinned number, update the test in the same commit and state the reason in the commit message. Never edit a test silently to make it pass.

## 2. Design rules (non-negotiable)

- **Reference data and project data are different things.** Reference values are curated and the same for every tenant. Project values belong to the project and are only ever changed by the sponsor.
- **Code holds no reference numbers.** The constants in `capital_bridge.FUEL_DEFAULTS` and the defaults in `tea_engine/models/tea.py` become a last-resort fallback. They are used only when the registry has no approved value, and each use is logged and marked `model_default`.
- **Startup must not overwrite the database.** Today `capital_bridge.init_db()` UPSERTs `FUEL_DEFAULTS` into `fuel_defaults` on every start. Change it to insert-if-missing, then retire `fuel_defaults` in favour of the registry (WP1).
- **Append-only versions.** A reference value is never updated in place. A new row supersedes the old one, as in the hash-chained ledgers of migration 043.
- **No automatic change to project inputs.** When the reference moves, a project gets a flag. The sponsor decides.
- **Follow the house migration pattern** (see 041 and 043): Alembic revision 061 after 060; TEXT timestamps, INTEGER booleans; RLS enabled and forced; read-open policy; writes only when `app.current_company_id = 'PLATFORM_ADMIN'`; grants to `gex_app`. No tables created at runtime.
- **Do not merge different quantities that share a name.** Migration 041 already warns that `fuel_catalog.specific_energy_value` (fuel energy density, LHV) and electrolyser specific energy consumption (kWh per kg of H2 produced) are different. The registry must keep them as distinct parameters. Extend the existing guardrail test to cover the registry.

## 3. Work packages, in order

### WP1. Reference registry (migration 061)

**Table `reference_parameter`.** One row per value version:

| Column | Type | Note |
|---|---|---|
| ref_id | TEXT PK | UUID |
| parameter_key | TEXT NOT NULL | e.g. `electrolyser_installed_capex`, `electrolyser_system_sec`, `stack_life_hours`, `stack_replacement_pct_capex`, `h2_price_rfnbo`, `ppa_price_solar`, `subsidy_45v_max`, `ehb_premium` |
| pathway | TEXT | `H2_PEM`, `H2_ALK`, `NH3`, `E_METHANOL`, `SAF`, or `ANY` |
| region | TEXT | ISO country, `EU`, `CN`, `ROW`, or `ANY` |
| value_low | REAL | |
| value_base | REAL NOT NULL | |
| value_high | REAL | |
| unit | TEXT NOT NULL | Must exist in the unit families already used by the frontend |
| currency | TEXT | ISO 4217 when the unit is monetary |
| price_base_date | TEXT | ISO date the prices refer to; required when monetary |
| source_class | TEXT NOT NULL | `public_source`, `gex_cohort`, `gex_assumption` |
| source_name | TEXT NOT NULL | |
| source_url | TEXT | |
| retrieved_at | TEXT NOT NULL | |
| valid_from | TEXT NOT NULL | |
| supersedes_ref_id | TEXT | FK to self |
| state | TEXT NOT NULL | `proposed`, `approved`, `rejected`, `superseded` |
| proposed_by / approved_by | TEXT | |
| approved_at | TEXT | |
| note | TEXT | |

Unique constraint: one `approved` row per (parameter_key, pathway, region) at a time.

**Table `reference_version`.** A named snapshot (version_id, created_at, list of ref_ids). Projects pin a snapshot, not individual rows.

**API, under `/api/v1/reference`:**
- `GET /parameters?key=&pathway=&region=&as_of=` returns the approved value in force at `as_of`.
- `POST /parameters` creates a `proposed` row (admin or analyst).
- `POST /parameters/{ref_id}/approve` and `/reject` are PLATFORM_ADMIN only. Approve supersedes the previous approved row and creates a new `reference_version`.
- `GET /versions/{version_id}`

**Seed** (state `approved`, version 1). Values are from the 19 Oct review; check each link before seeding.

| parameter_key | pathway / region | low / base / high | unit | price date | source |
|---|---|---|---|---|---|
| electrolyser_installed_capex | ANY / ROW | 2000 / 2300 / 2600 | USD/kW | 2024 | IEA Global Hydrogen Review 2025 |
| electrolyser_installed_capex | ANY / CN | 600 / 900 / 1200 | USD/kW | 2024 | IEA Global Hydrogen Review 2025 |
| electrolyser_installed_capex | H2_PEM / US | 1500 / 2000 / 2500 | USD/kW | 2022 | US DOE Hydrogen Program Record 24005 |
| electrolyser_system_sec | H2_PEM / ANY | 55.2 / 57.0 / 57.5 | kWh/kg H2 | n/a | DOE Record 24005 (55.2 beginning of life, 57.5 lifetime average) |
| stack_life_hours | H2_PEM / ANY | — / 40000 / — | h | n/a | DOE Record 24005 |
| stack_replacement_pct_capex | H2_PEM / ANY | — / 0.11 / — | fraction of installed capex | n/a | DOE Record 24005 |
| output_degradation_pct_per_year | ANY / ANY | — / 0.01 / — | fraction/yr | n/a | `gex_assumption`: to be sourced. DOE gives 4.8 mV/khr stack voltage, not an output rate |
| h2_price_rfnbo | H2 / EU | 7.0 / 8.2 / 10.0 | EUR/kg | 2025 | ACER European hydrogen market monitoring 2025 (HYDRIX average) |
| h2_price_grey | H2 / EU | — / 2.0 / — | EUR/kg | Jan–Oct 2025 | ACER 2025 |
| ppa_price_solar | ANY / EU | — / 56.59 / — | EUR/MWh | Q2 2026 | LevelTen Q2 2026 (European average) |
| ehb_premium | H2 / EU | 0.20 / — / 0.60 | EUR/kg | 2025 | EU Hydrogen Bank round 2 results, general topic |
| subsidy_45v_max | H2 / US | — / 3.28 / — | USD/kg | 2026 | 45V top tier after OBBBA; construction must begin before 2028-01-01 |
| debt_gearing | ANY / ANY | 0.60 / — / 0.70 | fraction | n/a | OIES ET21 |

**Acceptance:**
- (a) Migration upgrades and downgrades cleanly on PostgreSQL.
- (b) RLS: a tenant can read but cannot write; PLATFORM_ADMIN can write.
- (c) Approving a new value supersedes the old one and creates a new version; the old row is still readable with `as_of`.
- (d) Restarting the backend changes nothing in the registry.

### WP2. Project pinning and drift flags

- **Pinning:** add `reference_version_id` to the capital-bridge project control, plus a per-field provenance map `{field: source_class}` with values `sponsor_assumption`, `reference`, `model_default`.
- **Bootstrap:** `bootstrap_from_fuel` reads the registry (latest approved version), not `FUEL_DEFAULTS`, and pins that version.
- **Drift endpoint** `GET /api/v1/reference/drift/{project_id}` lists each field where:
  - the value is outside the current low–high band; or
  - the pinned version has been superseded for that parameter; or
  - the reference row is older than 12 months (staleness).
  It returns current value, reference band, source and date.
- **Acceptance:**
  - A project created at SEC 50 kWh/kg is flagged against band 55.2–57.5.
  - Approving a new capex value flags every project pinned to the old version.
  - No project field changes.

### WP3. Cost engine defaults from the registry

- **Resolve defaults from the registry:** `tea_engine/models/tea.py` FinancialAssumptions defaults (`hydrogen_eur_t` 3000, `electricity_eur_mwh` 60, `capacity_factor` 0.6, `discount_rate_pct` 8, `contingency_pct` 15) are resolved from the registry when the caller omits them. Keep the existing `input_provenance` labelling: `model_default` when the value came from the registry or fallback, `sponsor_assumption` when it came from the request.
- **Fix the stale hydrogen price first:** €3/kg becomes the registry value (base 8.2 EUR/kg, EU).
- **Acceptance:** a compute call with no assumptions returns `hydrogen_eur_t` = 8200 with provenance `model_default` and the registry `ref_id` recorded in `input_provenance`.

### WP4. Stack replacement and degradation (gex_pf_engine)

- **Inputs:**
  - `stack_life_hours` and `stack_replacement_pct_capex`, from the registry unless the project overrides them;
  - `availability_factor` (exists in the capital bridge);
  - degradation mode: `output` (output falls at constant power) or `efficiency` (SEC rises, so power cost rises at constant output);
  - `degradation_pct_per_year`, which resets to zero after each stack replacement.
- **Schedule:** operating hours per year = 8760 × availability. A replacement falls in the year cumulative hours cross a multiple of `stack_life_hours`, and never in the final operating year. Cost = `stack_replacement_pct_capex` × installed electrolyser capex, escalated if escalation is on.
- **Funding:** through the maintenance reserve that already exists in `waterfall.py`. Required balance = next replacement cost, built up evenly over the years before it. Add an option for no reserve (paid from CFADS in the year), which the golden test uses.
- **Acceptance (no-reserve mode, against `golden_hydrogen_fm.json`):**
  - `stack_replacement_unfunded`: equity IRR 7.52%, minimum DSCR −1.59x;
  - `output_degradation_1pct`: equity IRR 8.30%;
  - with the reserve on, minimum DSCR must not be negative for the same case. Report the value; there is no golden number for it.

### WP5. Tax in CFADS

- **Change** `gex_pf_engine/core/cfads.py`. Today tax = rate × (EBITDA − maintenance capex), with no depreciation, interest deduction or losses.
- **Add:**
  - straight-line depreciation (life input), with MACRS as an option later;
  - interest deduction (geared tax) and ungeared tax for project returns;
  - loss carry-forward, unlimited by default with an optional cap;
  - capitalised versus expensed financing fees, as an input.
- **Acceptance (base case, golden):** geared tax 7,618,590; ungeared tax 7,965,090; total interest 1,650,000; lifetime CFADS 45,310,410 (each within USD 1).

### WP6. One integrated lender case and true IRR

- **Wire the lifetime model in order:** `model_project_lifetime` in `pf_engine/core/engine.py` calls, in sequence:
  - production with degradation (WP4);
  - revenue with offtake and subsidies (WP7);
  - opex with escalation;
  - tax (WP5);
  - CFADS;
  - sculpting (`debt/sculpting.py`) or the fixed profile as an option;
  - DSRA and maintenance reserve (`waterfall.py`);
  - distributions.
- **Returns:** equity IRR, project IRR (after tax, ungeared), equity NPV and project NPV on dated annual flows. Replace `equity_irr_proxy` in `backend/app/services/financial_model.py`: keep the field, deprecated, pointing to the new value.
- **LLCR convention used in the golden file:** PV at the debt rate of CFADS over the loan tenor, ÷ debt at financial close.
- **Acceptance:**
  - **Base:** equity IRR 12.37%, project IRR 10.06%, equity NPV 9,331,361 at 5%, minimum DSCR 1.68x, LLCR 1.89x.
  - **Stress cases:** all match `golden_hydrogen_fm.json` within tolerance.
  - **Break-even:** USD 4.35/kg for 10% equity IRR and USD 5.91/kg for 1.30x minimum DSCR in the combined case.

### WP7. Subsidy eligibility

- **Instrument fields:** add `jurisdiction`, `eligible_from`, `construction_start_deadline`, `credit_years` (sunset after N years of operation), `stackable_with` (list) and `currency` to `backend/app/core/instrument_registry.py` instruments.
- **CFADS subsidies:** apply only when the project's jurisdiction, construction-start date and operating year qualify.
- **Initial data:**
  - **45V:** jurisdiction US; deadline 2028-01-01; 10 credit years; top tier from the registry.
  - **EU Hydrogen Bank:** jurisdiction EU; fixed premium per kg for 10 years; amount per project.
- **Stacking:** reject US–EU combinations unless `stackable_with` allows them.
- **Fix the example:** `example_green_h2` in `routes_model.py` uses `subsidies={'45V': 3.0, 'RED_III': 0.5}` in a euro project. Make it EU-only.
- **Acceptance:**
  - A US project whose construction starts in 2028 gets no 45V.
  - The example no longer stacks 45V with RED III.

### WP8. Price base date on cost figures

- **Fields:** add `price_base_date` and `currency` to development-package cost lines and to the capital-bridge `total_capex_eur`.
- **Normalisation:** expose the cost engine's CEPCI routine (`tea_engine/cepci_extension.py`) as a shared helper, and normalise to a target year on read, never on write.
- **Migration:** existing rows get `price_base_date = NULL` and are flagged `undated`. Don't backfill guesses.
- **Acceptance:** a 2022 cost line normalised to 2026 matches the CEPCI ratio used by `tea_engine` for the same years.

### WP9. Peer cost benchmark

- **Cohort benchmark:** extend `adjacency.py` (PF engine and platform) with capex per kW (installed electrolyser) and opex per kg, each at P25/P50/P75 within the existing cohort dimensions.
- **Minimum cohort:** 5 projects (Data Structure v5, decision D15).
- **Visibility:** respect `Benchmark-only` from v5. Such projects count in the statistics and are never shown individually.
- **Write-back:** approved cohort statistics can be proposed to the registry as `source_class = gex_cohort`. This is the self-improvement loop.
- **Acceptance:**
  - With fewer than 5 peers the endpoint returns `insufficient_cohort`.
  - With 5 or more it returns quartiles, and no individual benchmark-only value is visible.

### WP10. RFNBO power shares (phase 2, design only in this session)

v5 supply links (input, share, correlation basis, carbon origin) feed both the electricity cost and the certification check in `plant_builder.py`. Write the table design and an Alembic stub. Don't build this until WP1–WP9 are merged.

## 4. Out of scope, and things not to do

- No automatic update of any project input.
- No new tables created at runtime.
- No reconciling of SEC with fuel LHV.
- No change to gate logic in `bankability_engine.py`.
- No silent edits to characterisation tests.
- No external data scraping in this branch. Proposals are entered by an analyst; a scheduled collector is a later piece of work.

## 5. Hand-back

Return a short report:
- branch and commits;
- tests before and after, with every changed pinned number and its reason;
- golden-case results against `golden_hydrogen_fm.json`;
- migration 061 up/down log on PostgreSQL;
- open questions.

Bring the report back to the review session (or to Jean-Marie) to check against this brief.

---

## 6. Status and decisions log

### 19 Oct 2026: section 1 and WP1 accepted

- **Work done:** branch `reference-data-registry` on the `co-work/` git copy; commits `9f59126`, `a195d68`, `e8c3ba3`, `589e8a0`. Backend tests 899 → 956 pass, PF engine 239 pass, no pinned number changed.
- **Working arrangement:** the top-level copy stays the working master and is rsynced into `co-work/` at each commit point.
- **Checked by the review session in the code:**
  - Migration 061 (down_revision 060).
  - Triggers refuse value changes and deletes.
  - `gex_app` has SELECT and INSERT, plus UPDATE on the lifecycle columns only.
  - The approver must not be the proposer (`reference_registry.py`).
- **Departures from this brief accepted:**
  - lifecycle-only updates;
  - pathway `H2`;
  - region fallback DE → EU → ROW → ANY, with CN never falling back to ROW;
  - three new unit families;
  - a closed parameter catalogue with the SEC > LHV test;
  - insert-if-missing at startup;
  - `/api/v1/reference` mapped to governance.
- **JML decisions:**
  - Hydrogen Bank premium base 0.20 EUR/kg (lowest winning bid; version 2).
  - Debt gearing 60/65/70%, OIES ET21 (version 3). The 65% base is the midpoint, not a sourced figure.
  - No platform analyst role yet.
  - Four-eye adoption for WP2: two different CEO/CFO-level users of the client company.
  - Drop `fuel_defaults` once nothing reads it.
  - Price dates are the first day of the period. When such a price is used as a spot quote in Gabillon, treat it as mid-period.

### Answers to the open questions (19 Oct 2026)

1. **45V: approve.** IRS Notice 2026-41 (Internal Revenue Bulletin 2026-29, 13 July 2026) sets the 2026 inflation adjustment factor at 1.0929, which gives a base of USD 0.656/kg for the < 0.45 kg CO2e/kg tier. The 5× prevailing-wage-and-apprenticeship multiplier gives USD 3.28/kg. Approve it as source IRS Notice 2026-41 with that note. Add the four tiers as separate rows (0.656 / 0.219 / 0.164 / 0.131 base, × 5 with the wage and apprenticeship requirements met), and the construction-start deadline 2028-01-01.
2. **IEA capex: keep proposed.** The IEA GHR 2026 web pages reached from the review session give no installed USD/kW figures, and the secondary report (China H2 World, 25 June 2026) quotes stack and system bid prices, not installed costs. From the Mac, retrieve the GHR 2026 PDF chapter on electrolyser costs. If it confirms the 2025 installed-cost ranges, propose new rows with price date 2025-01-01 and reject the 2024 proposals as "superseded before approval". Until then the DOE row (USD 1,500/2,000/2,500 per kW, 2022$) is the only approved capex reference.
3. **Analyst role:** a platform-level role `reference_analyst`, propose-only. It may create `proposed` rows and attach sources; it may never approve or reject. Approval stays with PLATFORM_ADMIN, with the approver different from the proposer. Add the role to the ABAC policy model, and let it be held by GEX staff or contracted analysts, never by a tenant user.
4. **Items not executed:**
   - Keep the `setup_postgres_rls.sql` edit unexecuted until JML has read it, because it can reset role passwords. Prefer moving any needed grant into an Alembic revision.
   - Run the frontend type-check before merge.
   - Restart the backend in a planned window, then check `/api/v1/reference/parameters` against the approved seed.

### Notes for WP2

- **Four-eye adoption exception path:** a client company with only one executive needs a defined fallback, for example one executive plus GEX PLATFORM_ADMIN as second approver, logged as such. Decide before building.
- **Adoption is per field, not per project:** an adoption record names the field, old value, new value, reference row, the two approvers and the dates. Use the existing SoD module (`core/sod.py`) for the same-user check.
- **Order:** drop `fuel_defaults` in a separate migration after a test proves no code path reads it.
- **Push:** push the branch to the private remote, so the work exists outside the Mac.
