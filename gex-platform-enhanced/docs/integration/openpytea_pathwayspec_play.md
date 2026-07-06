# OpenPyTEA + pathway-spec → GEX integration play

**Status:** design draft · 2026-06-29
**Thesis:** GEX does not revolutionise the market — it integrates producers,
financiers, insurers, certifiers, logistics, traders and regulators around one
project so each party's presence compounds the value of the others' evidence,
compressing time-to-FID into measurable NPV. Two external repos help, in
different roles:

| Repo | Role in GEX | Verdict |
|---|---|---|
| [OpenPyTEA](https://github.com/pbtamarona/OpenPyTEA) | **Compute / engine layer** — equipment specs → CAPEX/OPEX/LCOP, sensitivity, Monte-Carlo | Adopt now. Fills the Economics/Modelling gap, plugs **upstream** of the PF engine. |
| [pathway-spec](https://github.com/insightquantix/pathway-spec) | **Contract / interface layer** — one machine-readable pathway object every party reads | Mine the idea, don't depend on the repo (v0.5, 1 star). Absorb its hierarchy into a *GEX-owned* canonical pathway schema. |

The decisive finding from reading our own code: **GEX already owns the
integration spine.** We do not invent a state machine, an evidence model, or a
layering — `efuel_truth_stack` already defines them. These two repos slot into
seams that already exist.

---

## Pillar mapping — where each repo lands

| GEX pillar | Operationalised by (existing) | What the repo adds |
|---|---|---|
| **Evidence Integrity** | `efuel_truth_stack` — `CanonicalLedgerEntry`, `Claim`, `EvidenceLink`, 9-state `ClaimState` | pathway-spec gives the *structural* object that the claims hang off (feedstock → stream → process-unit → TEA → LCA) |
| **Decision-Grade Trust** | 12-gate evidence framework + ABAC workspaces (11 actors) | OpenPyTEA makes the economics *reproducible & auditable* (FAIR, JSON I/O, peer-reviewed) instead of a black-box spreadsheet — a cost number becomes a defensible claim |
| **Bankable Outcomes** | `gex_pf_engine` (port 8001) — CFADS, DSCR, Gabillon, bankability scoring | OpenPyTEA supplies the CAPEX/OPEX/LCOP basis the PF engine currently *assumes as input* |

---

## Play #1 — OpenPyTEA as the TEA compute service (upstream of the PF engine)

### The seam already exists

The PF engine consumes plant economics through one Pydantic model
([`gex_pf_engine/models/deal.py`](../../gex_pf_engine/models/deal.py)):

```python
class PlantSummary(BaseModel):           # "Subset of plant data the engine needs"
    id:                  str
    capex_eur:           float = Field(ge=0)
    opex_eur_per_year:   float = Field(ge=0)
    nameplate_capacity:  Optional[float] = None
    nameplate_unit:      Optional[str]   = None
    verification_state:  VerificationState = VerificationState.UNVERIFIED
    deal_killer_flag:    bool = False
```

Today `capex_eur` / `opex_eur_per_year` arrive as hand-entered numbers (from the
`public.plants` table / `_docs/Breizh_SAF_Project_Workbook`). That is precisely
the spreadsheet-as-black-box problem GEX exists to kill. **OpenPyTEA's three-tier
output is exactly these three fields** — equipment costing → plant CAPEX
(ISBL/OSBL/engineering/contingency) → OPEX → LCOP. So the integration is not a
rebuild; it is *populating an existing input with a transparent engine*.

### Topology

```
                       ┌─────────────────────────────────────────────┐
                       │  GEX pathway object  (Play #2 schema)        │
                       │  engineering layer:  process_units[], streams│
                       └──────────────────┬──────────────────────────┘
                                          │  (equipment specs, utilities)
                                          ▼
   NEW         ┌──────────────────────────────────────────┐
   service     │  tea_engine  (OpenPyTEA wrapped, :8002)   │
   :8002       │  POST /tea/compute  → CAPEX/OPEX/LCOP      │
               │  POST /tea/sensitivity → tornado/MC        │
               └──────────────────┬───────────────────────┘
                                  │  capex_eur, opex_eur_per_year, lcop
                                  │  + cost-basis hash (→ Evidence Ledger Claim)
                                  ▼
   EXISTING    ┌──────────────────────────────────────────┐
   :8001       │  gex_pf_engine  (port 8001)               │
               │  PlantSummary ← TEA output                 │
               │  compute_deal(DealInputs) → CFADS/DSCR/NPV │
               │  Gabillon price curves                     │
               └──────────────────────────────────────────┘
```

Two clean reasons to keep TEA as its **own** service (`:8002`) rather than
folding it into `:8001`:

1. **Separation of certainty dimensions.** The PF engine's bankability score is
   weighted across *Cost · Revenue · Certification · Execution · Counterparty*.
   OpenPyTEA owns **Cost certainty**; the PF engine owns the rest. Keeping them
   as separate services keeps that boundary honest and independently versionable.
2. **Different cadence.** Cost correlations / CEPCI update on an engineering
   cadence; the deal structure iterates per financing round. Coupling them would
   force redeploys across concerns.

The PF engine already anticipates the sensitivity call it will delegate —
`routes/deals.py` reserves `POST /deals/{id}/sensitivity` for Sprint 3. That
endpoint should **fan out to `:8002/tea/sensitivity`** for the cost axis rather
than re-implementing tornado/Monte-Carlo (OpenPyTEA already ships both).

### Adapter contract

The only glue code is a thin adapter that (a) turns the pathway object's
`engineering` layer into OpenPyTEA `Equipment` objects, and (b) maps OpenPyTEA's
result back onto `PlantSummary`. A reference stub lives at
[`gex_pf_engine/compute/tea_adapter.py`](../../gex_pf_engine/compute/tea_adapter.py)
(import-guarded — it does not require OpenPyTEA to be installed to import the
rest of the engine).

### Evidence-integrity hook (this is what makes it GEX, not just a calculator)

OpenPyTEA writes JSON result files. **Every TEA run emits a
`CanonicalLedgerEntry`** of `kind=derived`, `entry_type=projection_snapshot`,
with the input-config hash in `payload` and the cost-basis hash returned to the
caller. The resulting `capex_eur` becomes a **`Claim`** (`claim_type="capex_eur"`,
`value_type=numeric`, `subject_node=<plant engineering node>`) whose `state`
walks the existing 9-state machine:

```
asserted ─submit─▶ submitted ─verify(IE)─▶ verified ─▶ satisfied
```

`PlantSummary.verification_state` then reflects whether the cost basis is
`UNVERIFIED` (raw OpenPyTEA run) or `CONFIRMED`/`AUDITED` (independent engineer
signed the run). **That is the difference between a number and decision-grade
trust** — and it is why OpenPyTEA is adopted *behind* the truth stack, not beside it.

### Build order

1. **`tea_engine` service — BUILT, REAL OpenPyTEA wired & verified** (`tea_engine/`,
   port 8002). Wraps OpenPyTEA behind the copied Supabase-JWT bridge. `POST
   /tea/compute` takes the pathway `engineering` layer → returns a **provisional**
   `PlantSummary` extract (`verification_state=UNVERIFIED`,
   `model_claim_state=submitted`) + a `projection_snapshot` evidence proposal;
   `POST /tea/sensitivity` → tornado. `openpytea==2.1.0` is pinned and installs
   cleanly (numpy/scipy/pandas/matplotlib wheels on py3.14). The real runner builds
   `openpytea.Equipment` per process unit and an `openpytea.Plant`, runs
   `calculate_all()`, and extracts `capital_costs.fixed_capital` (CAPEX),
   `variable_opex.total+fixed_opex.total` (OPEX), `metrics.levelized_cost` (LCOP).
   `TEA_STUB=1` still gives deterministic output for CI/demo (the only thing the
   `engine` field flips between: `openpytea` | `stub`). Verified end-to-end in REAL
   mode: e-methanol-shaped plant → CAPEX €66M / OPEX €20.6M·yr⁻¹ / LCOP €0.675·kg⁻¹,
   tornado with hydrogen price dominating; provisional contract preserved. Note:
   OpenPyTEA validates `material`/`category`/`type` against its cost-correlation
   CSV — callers must use its taxonomy (or pass `cost_func`). Wired into
   docker-compose (`TEA_ENGINE_URL`, `TEA_STUB=0`).
2. **Backend bridge — BUILT & verified** (`backend/app/api/v1/routes_tea.py`,
   mounted at `/api/v1/tea`). `POST /compute/{project_id}` proxies to `:8002`,
   appends the run to the hash-chained `evidence_ledger` (category=COST,
   `UNVERIFIED`), and creates a `model_base_case` claim in state `submitted`,
   superseding any prior live base case. `POST /base-case/{id}/approve` is the
   IE/CFO `approval_decision` that folds `submitted → verified` (rejects
   `tea_engine` self-approval and illegal state hops). `GET /base-case/{project}`
   returns the live claim with `is_release_ready`. Verified end-to-end (real
   tea_engine compute): submitted→supersede→approve→verified, evidence chain
   intact, self-verify 403, illegal transition 409.
3. **Release-gate enforced — BUILT & verified** (`routes_finance_model.py`). The
   B7 rule now bites at the PF call site: the release-gated endpoints (`/lifetime`,
   `/covenants`, `/waterfall`, `/waterfall-structured`, `/metrics`,
   `/cfads-with-financing`) take an optional `project_id`; when supplied,
   `_require_release_ready()` refuses (409) unless the project's live
   `model_base_case` is terminal-valid, and stamps governance basis
   `RELEASE_READY_BASE_CASE` when it is. No project_id → ungated legacy path
   (still stamped not-for-credit). Verified: provisional→409, verified→200,
   ungated→200, unknown-project→409.
4. **Sprint-3 sensitivity** — point `:8001 /deals/{id}/sensitivity`'s cost axis at
   `:8002 /tea/sensitivity`.
5. **docker-compose** — add `tea_engine` alongside `pf_engine`, inject
   `TEA_ENGINE_URL: http://tea_engine:8002` into `backend` (mirrors the existing
   `PF_ENGINE_URL` pattern).

---

## Play #1b — per-molecule PROCESS FUNCTION registry (the molecule spine's root)

`tea_engine/process_functions.py` ascertains, **per molecule**, *how the molecule
is actually made* — reaction, feedstock stoichiometry, and a real equipment train —
so the TEA describes that molecule's plant, not a generic one. Without it,
CAPEX/OPEX/LCOP (and the `model_base_case` claim, and the release gate) describe a
fiction.

- **E_METHANOL** is fully defined (CO₂ + 3H₂ → CH₃OH, 12-unit train, 0.90 yield).
  `POST /tea/compute` with only `fuel_id` (no equipment) derives the train and
  returns real OpenPyTEA economics: ~€186M CAPEX, ~€55M·yr⁻¹ OPEX, LCOP dominated
  by hydrogen price (verified). Feedstock consumption is stoichiometric (per-day,
  matching OpenPyTEA's `consumption·price·365·utilization`).
- **E_METHANE / GREEN_H2 / E_AMMONIA** are scaffolds (reaction + stoichiometry
  present, equipment train not yet costed). Computing them returns **422 — GEX
  refuses to emit fictional economics** for a molecule whose process function
  isn't defined. Same for unknown molecules.
- Every equipment entry uses an OpenPyTEA correlation that actually computes
  (valid taxonomy, CEPCI-covered year). Caught a pathological correlation on the
  way: `Heat exchangers/Kettle reboiler` (2001) explodes on extrapolation (€134M
  at 300 m²) — swapped for `Thermosiphon reboiler`. **Not every OpenPyTEA
  correlation is usable; the registry curates the valid ones.**
- `ascertained=False` on every template: the process function is itself a
  claim-in-waiting — a canonical first-pass (sizing coefficients tuned at 50 kt/yr)
  that an **independent engineer must verify** before `ascertained=True`, exactly
  like `model_base_case` is `submitted` until approved. Result + run-evidence carry
  the `process_function` id/version/ascertained so a TEA run records *which*
  process basis it used. Supplying explicit `process_units` overrides the registry.

## Play #2 — GEX canonical pathway schema (pathway-spec hierarchy, GEX vocabulary)

See [`schemas/gex_pathway.schema.yaml`](../../schemas/gex_pathway.schema.yaml) and the
worked e-methanol example
[`schemas/examples/breizh_emethanol.pathway.yaml`](../../schemas/examples/breizh_emethanol.pathway.yaml).

Design rules:

- **Borrow pathway-spec's process hierarchy** (metadata · feedstocks · products ·
  streams · process_units · balances · TEA · LCA). It is good, and it is the
  reproducibility win.
- **Reject pathway-spec's flat TEA/LCA-only framing.** GEX pathways must carry the
  full molecule→capital arc, so the top-level layers mirror the truth stack's
  `Layer` enum exactly: `molecule · certification · engineering · commercial ·
  financial · accounts · capital · public_controls`.
- **Every leaf value is a claim, not a constant.** Each numeric/categorical field
  references a `claim_id`; the claim carries `state` (9-state machine), `unit`,
  `evidence_refs`, `authority_rule`. This is how the pathway object becomes
  *decision-grade* rather than a config file.
- **Gates are first-class.** The 12-gate framework is expressed as `gates[]`, each
  binding a set of required claims + an `ApprovalRequirement` (actor, threshold,
  veto/drawstop rights) — reusing `ApprovalRequirement` from truth-stack `models.py`.
- **Units come from the fuel catalog**, not free text — `gex_fuel_catalog.json`
  already defines `trading_unit`, `price_unit`, `emissions_unit` per fuel
  (`E_METHANOL`: t / EUR/t / kgCO2e/kg).

### Validation (contract track — built & green)

[`schemas/validate_pathway.py`](../../schemas/validate_pathway.py) validates a
`.pathway.yaml` and **round-trips it into the truth stack** (13/13 checks green on
the worked example; deps: PyYAML + `efuel_truth_stack`, run via `backend/venv`):

- **Level-1 structural** — sections present, claim refs resolve, node DAG acyclic,
  gate validation_level within the ladder.
- **Round-trip** — every claim → `models.Claim`; the TEA run → a
  `CanonicalLedgerEntry` appended to a `Ledger` (auto-hash + append-only proven);
  nodes → `models.Node`; gates → `ApprovalRequirement`; claims folded through the
  real `rollup_nodes` projector.

**Key finding from running it (this is why we validated before building the
service):** binding to the truth-stack *types* is necessary but not sufficient.
`rollup_nodes` is hardwired to the spec's **canonical node registry**
(`efuel_truth_stack.projectors.NODES` — 41 nodes: `electrolyser`, `synthesis`,
`product`, `financial_model`, `ghg_lca`, `goo_pos`, `offtake_matrix`, `epc_signed`,
`fel_class`, …) with a fixed claim_type vocabulary per node (`product_t`,
`conversion_yield`, `g_co2e_per_mj`, `rfnbo_issued`, `epc_price`,
`model_base_case`, `volume`/`tenor`/`price_index`/`buyer_credit`, …). A pathway
that invents its own ids (`NODE-PLANT`, `capex_eur`) binds to the types but
**silently never folds**. So the canonical pathway schema constrains node ids and
claim_types to that registry (validator checks B5/B6) — the same discipline that
killed the `capital_taxonomy` entropy.

**Consequence for the OpenPyTEA seam (refined — evidence vs claim).** There is no
canonical `capex_eur` claim, and the OpenPyTEA run does **not** auto-become the
base case. The run is *evidence* (an immutable ledger entry, producer
`tea_engine`); `model_base_case` is a *claim* on the `financial_model` node that
is **promoted against** that evidence — `submitted → verified` only via an
`APPROVAL_DECISION` (IE/CFO), never self-verified. The literal CAPEX/OPEX/LCOP
numbers are a hash-derived *projection* of that evidence, carried in the `tea:`
block to populate `PlantSummary`. `model_base_case` also carries
`supersedes_claim` (each re-run supersedes the prior accepted case — full lineage)
and `reconciliation_group_id` (ex-ante assumptions ↔ ex-post metered facts,
ladder Level 6). **`aace_class` is a separate claim on the `fel_class` node,
produced by the IE/cost estimator — never by OpenPyTEA** (an AACE class certifies
engineering-definition maturity, which a TEA calculator cannot see).

**Compute-authorization rule (now enforced).** While `model_base_case` is not
terminal-valid, the PF engine may run *provisional* compute only; **no
release-gated gate may open on a provisional cost basis**. The validator's B7
check enforces this and reports the compute mode (`PROVISIONAL` /
`RELEASE-READY`). The GEX 0–100% progression bar must be **derived from gate/claim
states** (`node_is_green`), not hand-set — so it can never be mistaken for an
AACE class.

`schemas/validate_pathway.py` now runs **17 checks** (structural + evidence-ref
resolution + truth-stack round-trip + supersession lineage + release-gate guard),
all green on the worked example; teeth confirmed by negative + scenario tests.

**[SPEC-REVIEW — resolved by Jim]** `model_base_case` is the right home, but the
OpenPyTEA run is its *evidence*, promoted to base case only on approval;
`aace_class` is IE-assigned, not computed. Both encoded above.

### Why not just adopt pathway-spec's YAML directly?

Because it would re-introduce the entropy GEX is removing. pathway-spec is a
TEA/LCA artifact owned by an outside project with 6 commits; if GEX depended on
it, the canonical object would drift with someone else's roadmap and would lack
the certification/commercial/capital layers and the claim/gate machinery that
make it bankable. We take the *shape* and bind it to types we already own and test.

---

## One-line verdict per repo, in GEX terms

- **OpenPyTEA — adopt.** It is the transparent cost-certainty engine that turns
  the PF engine's assumed CAPEX/OPEX into a verifiable claim. Upstream of `:8001`,
  its own service at `:8002`.
- **pathway-spec — absorb, don't adopt.** Its hierarchy is the right blueprint for
  the canonical pathway object; its repo is too immature to be a dependency. We
  own the schema, bound to `efuel_truth_stack` vocabulary.
