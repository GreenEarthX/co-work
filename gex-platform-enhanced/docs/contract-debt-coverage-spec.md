# Contract–Debt Coverage — Build Spec (v1)

**Date:** 2026-08-11
**Status:** proposed
**One line:** compute whether contracted revenue survives as long as the senior debt, using
data the platform already holds, and return a verdict no data room can produce.

**Why this exists.** GEX's positioning claim is *reason, not print* — that the platform
computes things a document repository cannot. That claim is currently rhetorical. This spec
makes it demonstrable with the smallest possible change: one nullable field, one pure
function, one route, and the wiring of an engine that already exists and has never been called.

---

## 1. The claim, made falsifiable

> A project can hold a portfolio of offtake contracts that today scores **investment grade**
> on GEX's own contractual rating engine, while its contracted revenue expires years before
> the senior debt matures — and no engine in the platform notices.

This spec proves the claim by making the counter-computation exist. If the computation
returns `CONTRACT_COVERS_DEBT` for the fixture in §9.1, the claim is false and this spec
should be withdrawn.

---

## 2. The defect, verified

Six links, each measured against the working tree on 2026-08-11.

| # | Location | Finding |
|---|---|---|
| 1 | `backend/app/core/contractual_rating_engine.py:47` | `OfftakeContract` has `tenor_years` but **no start date**. Contracts cannot be placed on a timeline. |
| 2 | `backend/app/core/contractual_rating_engine.py:373` | `_compute_ocr` = `contracted_volume / nameplate` — a **timeless scalar**. A 3-year and a 20-year contract of equal volume are indistinguishable. |
| 3 | `backend/app/core/contractual_rating_engine.py:211` | `max_tenor = max(c.tenor_years …)`; `tenor_score = min(max_tenor / 10.0 * 60, 60)`. Uses **`max`**, so one long thin contract carries the tenor score for the whole portfolio. |
| 4 | `../gex_pf_engine/backend/app/core/cfads.py:130` | `calculate_with_offtake_contracts` is **single-period** (`period: str = "2027"`). Contract dicts carry `volume_mtpd` and `price_eur_kg` — no term, no start. |
| 5 | `../gex_pf_engine/backend/app/core/cfads.py:210` | `calculate_lifetime_cfads` applies **one scalar `offtake_price_eur_kg`** from `start_year` to `end_year`. It models production ramp-up. It never models contract **expiry**. |
| 6 | `backend/app/services/financial_model.py` | `dscr = cfads_pct / annual_debt_service_pct` — a **single scalar DSCR**, annuity over `blended_debt_tenor_years: int = 15`, implicitly assuming CFADS is constant for the full debt life. |

**And the engine that would have caught this already exists and is unreachable.**
`../gex_pf_engine/backend/app/core/debt/sculpting.py` (264 lines) defines `DebtSculptor.sculpt(cfads_profile: List[float])`,
returning `dscr_series`, `min_dscr`, `lock_up_years`, `is_compliant` and per-tranche payments.
Measured: **`sculpt()` has zero callers, nothing constructs a `cfads_profile`, and
`SculptingConstraints.tail_years` (line 20) is declared and never read.**

So the platform owns a period-level DSCR engine, computes DSCR as a scalar instead, and
feeds it a revenue stream it assumes is contracted forever, from contracts whose expiry it
does not record.

---

## 3. Scope

**In scope.** A pure, read-only computation returning a coverage curve, four headline
numbers, and a derived verdict. One nullable field added to the offtake contract shape. One
PF-engine route. One GEX backend proxy. One read-only panel.

**Explicitly out of scope.**
- No canonical offtake/commitment register. There are already five commitment-shaped
  objects (`instrument_registry`, `contractual_rating_engine.OfftakeContract`, `css`/
  `routes_commitments`, `contracts_sqlite`, `sovereign_instruments`). **Do not create a sixth.**
  Contracts arrive in the request payload, exactly as `ContractualRatingInput` already accepts them.
- **No new tables, in either repo.** This computation persists nothing.
- No merchant price forecasting. See §5.3 — the headline metric is deliberately
  assumption-free.
- No change to the existing rating engine's score. This computation sits *beside* it. Changing
  the letter rating is a separate, later decision.

---

## 4. Where it lives

The debt side (tranches, sculpting, CFADS) is entirely in the PF engine. The offtake side is
in the GEX backend. The computation belongs where the debt is.

```
GEX backend :8000
  routes_coverage.py  ──proxy, forwards bearer token──►  PF engine :8001
                                                          core/coverage/contract_coverage.py
                                                          core/debt/sculpting.py  (existing, wired at last)
```

> **Edit `files/gex_pf_engine/backend/app/` — the sibling repo.**
> `gex-platform-enhanced/gex_pf_engine/` is an in-repo copy and is **not** what serves `:8001`.
> Editing the copy produces no observable change and is the single most likely way to lose a day here.

---

## 5. The computation

Let `t = 1 … N` index operating years, `t = 1` being the COD year.

### 5.1 Coverage curve

For each contract `c`:

```
live(c, t)  =  1  if  start_year(c) ≤ t < start_year(c) + tenor_years(c)
               0  otherwise
```

```
V(t)    = Σ_c  volume_tpa(c) · live(c, t)          contracted volume in year t
P(t)    = Q · ramp(t)                              available production (Q = nameplate tpa)
OCR(t)  = min(V(t), P(t)) / P(t)                   time-varying coverage, ∈ [0,1]
```

`OCR(t)` is the object the current scalar `_compute_ocr` collapses. Everything else follows
from it.

### 5.2 Contracted-only CFADS

```
sold(t)    = min(V(t), P(t))                       pro-rata cap if oversold
R(t)       = Σ_c  volume_tpa(c) · live(c,t) · price_floor_eur_t(c) · cap_factor(t)
             where cap_factor(t) = sold(t) / V(t)  if V(t) > P(t), else 1
opex(t)    = opex_fixed + opex_var_per_t · sold(t)
CFADS_c(t) = R(t) + subsidies(t) − opex(t)
```

**Production basis: produce-to-contract.** Uncontracted capacity is assumed *not produced*,
so variable opex scales with `sold(t)` while fixed opex is incurred regardless. This is the
lender's downside convention and it requires no price forecast.

> **Engineering caveat to surface, not to model.** Many e-fuel plants cannot turn down below
> a minimum stable load. Where `OCR(t)` falls below that floor, produce-to-contract is
> physically unavailable and the plant must either sell merchant or idle. Return this as a
> flag (`below_min_turndown_years`), not as a modelled cost. Modelling it needs a merchant
> price and is out of scope.

### 5.3 Why the headline number needs no assumptions

`CFADS_c(t)` counts revenue **only** from contracts actually live in year `t`. It embeds no
merchant price, no forward curve, no escalation view. So:

> If `min DSCR_contracted(t) < 1.00` in any year with senior debt outstanding, the project
> **cannot service senior debt from contracted revenue alone** and is relying on merchant
> sales to do so.

That is a statement of fact about the contract portfolio, not a forecast. It is the reason
this metric is demonstrable rather than arguable, and it is why merchant modelling is
excluded rather than deferred.

### 5.4 Debt side — **revised 2026-08-11 after implementation**

The verdict is measured against **scheduled** debt service —
`Σ tranche.annual_debt_service(t)` — **not** against `DebtSculptor`'s sculpted service.

This reverses the original instruction to route the verdict through the sculptor, and the
reason is empirical. Sculpting *reduces* debt service to hit a target DSCR, so scoring the
verdict on it is circular: it flatters the exact number being measured. Measured on the
§9.1 fixture, year 5:

| | debt service | DSCR |
|---|---|---|
| scheduled | €19.27m | **0.078** |
| sculpted | €10.00m (floored at interest-only) | **0.15** |

Both fail, but the sculpted figure understates the shortfall by ~2×, and it does so by
assuming the lender accepts less — which is not "servicing the debt." Worse, §9.6
established that the sculptor **does not conserve principal**: a reduction in one year
never increases a later payment, so its profile does not repay the debt at all.

`DebtSculptor` is still run and its output returned as `sculpted` context — `lock_up_years`,
per-tranche detail, grace handling are all genuinely useful. It is simply not the verdict.
The headline claim therefore does not depend on the correctness of a module that had never
executed.

`outstanding_principal(tranche, year)` is derived in the coverage module (interest-only
through grace, annuity thereafter) because `Tranche` exposes debt service but no balance.

### 5.5 Headline outputs

| Metric | Definition |
|---|---|
| `coverage_cliff_year` | first `t` where `OCR(t) < θ` (θ default **0.80**, matching the rating engine's existing `ocr / 0.8` full-credit line) |
| `tenor_gap_years` | `debt_maturity_year − coverage_cliff_year`. **Positive = merchant tail under live debt.** Negative = contracts outlive debt. |
| `naive_tenor_gap_years` | `debt_maturity_year − max(start + tenor − 1)` — the comparison figure the current engine implies. Reported **only** to expose the divergence from `tenor_gap_years`. |
| `merchant_exposed_debt_eur` / `_pct` | senior principal still outstanding at `coverage_cliff_year` |
| `uncovered_debt_years` | count of `t` where debt outstanding **and** `OCR(t) < θ` |
| `min_dscr_contracted` / `_year` | from the sculptor, on the contracted-only profile |

### 5.6 Verdict — derived, never authored

| Verdict | Condition |
|---|---|
| `CONTRACT_COVERS_DEBT` | `OCR(t) ≥ θ` for every year debt is outstanding |
| `MERCHANT_TAIL` | cliff precedes debt maturity, but `min_dscr_contracted ≥ 1.00` throughout — debt has amortised enough that contracted revenue still covers it |
| `MERCHANT_DEPENDENT` | `min_dscr_contracted < 1.00` while debt outstanding |
| `INSUFFICIENT_DATA` | debt tenor, COD, or every contract start absent |

`INSUFFICIENT_DATA` is a first-class result, per v4 §2.2 and §10.1. It is **never** substituted
with `0`, a default tenor, or a fabricated date.

---

## 6. The one schema addition

```python
@dataclass
class OfftakeContract:
    ...
    start_year: int | None = None   # absolute operating year; defaults to COD year when None
```

Nullable and defaulted, so every existing caller and every existing rating result is
unchanged. When `None` for **all** contracts and COD is unknown → `INSUFFICIENT_DATA`.

Expressing start as an absolute year (not an offset from COD) matches how real contracts are
written. When COD is revised through `project_baseline_revisions` (v4 §2.3, metric
`TARGET_COD`), the coverage curve shifts and the verdict may flip — which is correct, is
computed, and is exactly the behaviour v4 §11.3 asks the project history to show.

---

## 7. API

**PF engine (`:8001`) — new**

```
POST /api/model/coverage/contract-debt
```

Request: contracts (with `start_year`), nameplate + ramp, opex split, subsidies by year,
financing structure, COD year, `theta` (optional, default 0.80).
Response: `coverage_curve[]`, the six headline metrics, `verdict`, `dscr_series`,
`lock_up_years`, `below_min_turndown_years`, and an `inputs_echo` with every default applied
named explicitly.

**GEX backend (`:8000`) — new proxy**

```
GET /api/v1/coverage/contract-debt?project_id=…
```

Forwards the caller's bearer token via `GEX_ENGINE_URL`, per handoff §4. Register the router
in `main.py` and map the prefix to a business domain in `app/core/domain_authorization.py`.
Read-only: **no POST, PATCH or PUT writes any output of this computation.**

---

## 8. Doctrine compliance

| Rule | How this complies |
|---|---|
| Readiness emergent, never authored (v4 law 7) | Every output is computed; §9.4 asserts no write path exists |
| One canonical object per concept (v4 law 1) | Zero new tables; contracts arrive in the payload; no sixth commitment register |
| Unknown is legitimate (v4 law 6) | `INSUFFICIENT_DATA` verdict; nullable `start_year` |
| SQLite ratchet (handoff §3, baseline 97 → 68, may only decrease) | No persistence, therefore **no new `sqlite3.connect` sites** |
| Tenant context fails closed (handoff §7) | Proxy route carries the caller's identity; no `PLATFORM_ADMIN` default |
| PF engine is the finance engine (memory: PF topology) | Computation lives at `:8001`, in the **sibling** repo |
| Separate state axes (v4 §4) | `verdict` is a new derived axis; it does not touch `workflow_state`, `lifecycle_status`, or `BankabilityState` |

---

## 9. Tests

### 9.1 The fixture that proves the claim — **BUILT AND MEASURED 2026-08-11**

Nameplate 100 kt/yr. Senior €200m @ 5% over 15 years, no grace. COD 2030.
Opex €5m fixed + €300/t variable. LCOF €700/t.

| Contract | Volume | Price floor | Start | Tenor | Counterparty |
|---|---|---|---|---|---|
| A | 80 kt/yr | €900/t | COD | **4** | A− (take-or-pay, corporate floor) |
| B | 10 kt/yr | €950/t | COD | **15** | A |

**What the rating engine returns today — measured, not estimated:**

> **score 85.3 · letter AA · investment_grade True · committee_ready True · OCR 0.90**

And it returns **exactly 85.3 whether contract A runs for 1 year, 4 years, or 14 years.**
`tenor_score` reads `max(c.tenor_years)`, so contract B's 15 years always wins the max and
the duration of 80% of the volume never reaches the score at all.

**What the coverage computation returns — measured:**

| | |
|---|---|
| `verdict` | **`MERCHANT_DEPENDENT`** |
| `coverage_cliff_year` | 5 |
| `tenor_gap_years` | **+10** |
| `naive_tenor_gap_years` | **0** ← what `max(tenor)` implies |
| `uncovered_debt_years` | 11 |
| `min_dscr_contracted` | **0.078** (year 5) |
| `merchant_exposed_debt_pct` | **80.0%** (€160.05m of €200m) |

DSCR is 2.569 in years 1–4 and 0.078 in years 5–15. Same inputs, opposite conclusion.

The two halves live where their engines live and mirror the fixture constants verbatim,
each naming the other:
- `../gex_pf_engine/backend/tests/test_contract_debt_coverage.py` — 22 tests
- `backend/tests/test_rating_engine_expiry_blindness.py` — 5 tests

### 9.2 Positive control

Single contract, 90 kt/yr, tenor 18, 15-year debt → `CONTRACT_COVERS_DEBT`,
`tenor_gap_years` negative, `min_dscr_contracted` ≥ target.

### 9.3 Insufficient data — negative verification

Debt tenor absent → assert the response `verdict == "INSUFFICIENT_DATA"` **and** that
`min_dscr_contracted`, `tenor_gap_years` and `merchant_exposed_debt_eur` are `None`.
Assert explicitly that no numeric value is returned — the failure mode this guards is a
fabricated `0`, which reads as "fully covered."

### 9.4 No write path — AST

Walk the route modules and assert no handler accepts or persists `verdict`,
`min_dscr_contracted`, or any coverage output. Mirrors the pattern in
`tests/test_tenant_context_default.py` and satisfies v4 test 12. Match definition lines, not
prose — per handoff §7, guardrails in this repo have repeatedly matched their own explanatory
comments.

### 9.5 Edge cases

Oversold (`ΣV > Q`) → pro-rata cap, `OCR(t) ≤ 1.0`, never >100%. Contract expiring before COD
→ contributes nothing, no crash. Zero contracts → `OCR(t) = 0` for all `t`, verdict
`MERCHANT_DEPENDENT` (not `INSUFFICIENT_DATA` — no contracts is a known fact, not a missing one).
Determinism: no wall-clock read inside the computation; the valuation date is an input.

### 9.6 Characterize the sculptor first — **BUILT 2026-08-11, 13 tests**

`../gex_pf_engine/backend/tests/test_debt_sculptor_characterization.py`. `sculpt()` runs and
its grace/reduction/acceleration paths behave as documented. Four defects were found and are
pinned as characterization, labelled `DEFECT` — do not "fix" the assertions, fix the code
deliberately:

1. **Sculpting does not conserve principal.** `Tranche.annual_debt_service(year)` recomputes
   the annuity from the full original amount every year and has no knowledge of what was
   paid. A reduction never increases a later payment; an acceleration never shortens the
   tenor; `cumulative_shortfall` is recorded and never repaid. **The sculpted profile does
   not repay the debt** — it is a DSCR diagnostic, never a repayment schedule. This is why
   §5.4 was reversed.
2. **DSCR is `float('inf')` after maturity**, which poisons `avg_dscr` and `max_dscr` and
   makes the summary invalid strict JSON. Callers must clamp the horizon to the debt life.
3. **The interest floor ignores FX.** `_reduce_commercial_first` floors at
   `t.amount * t.rate` while `annual_debt_service` amortises `t.amount_in_base` — wrong
   currency for any tranche with `fx_rate_to_base != 1.0`.
4. **`tail_years` is dead config**, asserted over the AST (a text grep matches the test's own
   docstring — a failure mode this repo has hit repeatedly). Negative-verified: injecting a
   read makes it fail.

---

## 10. The demonstration

```
FEED-stage e-methanol project, 15-year senior debt
→ two offtake contracts, 90% volume coverage
→ GEX contractual rating: investment grade
→ Contract–Debt Coverage: coverage cliff year 5
→ merchant-exposed debt: 70% of senior outstanding
→ verdict: MERCHANT_DEPENDENT
→ revise TARGET_COD by 18 months via project_baseline_revisions
→ curve shifts, prior baseline preserved, verdict recomputed
```

No document produces this. Both numbers were already in the data room; only their
*difference* is the finding, and the difference is a computation.

---

## 11. What this deliberately does not do

- Does not change the contractual rating score. The divergence in §9.1 is the product; closing
  it is a separate decision requiring Jim.
- Does not model merchant revenue, price curves, or refinancing. A refinancing assumption
  would dissolve the finding, which is precisely why it is excluded here and must be an
  explicit, labelled scenario if ever added.
- Does not build the demand-side commitment register. When that exists, it becomes the source
  of contracts and this route's payload shrinks to a `project_id`.
- Does not touch `contracts_sqlite.py` or the live 500 on `/api/v1/contracts/summary`
  (handoff §8.1). Unrelated object, unrelated defect.

---

## 12. Sequence

1. ~~Characterization tests over `DebtSculptor` (§9.6).~~ **DONE 2026-08-11** — 13 tests, 4 defects pinned.
2. ~~`core/coverage/contract_coverage.py` in the **sibling** PF engine.~~ **DONE** — pure functions, no I/O, no persistence.
3. ~~Fixture test §9.1.~~ **DONE** — 22 coverage tests + 5 rating-engine tests. The argument is now a passing test.
4. **`start_year` on `OfftakeContract`, nullable.** Not yet done — the coverage module carries
   its own `CoverageContract` so the fixture could be built without touching the shared
   dataclass. Adding it is what lets the two engines share one contract object, and
   `test_offtake_contract_cannot_express_when_a_contract_starts` fails the day it lands, by
   design. Delete that test in the same commit.
5. PF route, then GEX proxy, then the read-only panel.

Steps 1–3 are the argument, and they are done. Steps 4–5 are the product.

**Suite state at time of writing.** PF engine: 94 passed (`test_gabillon.py` and
`test_offtake.py` do not collect — the `micro_service` venv is missing `httpx`, pre-existing
and unrelated; the new tests import no FastAPI). GEX backend: **230 passed, 105 skipped, 0
failed**, against a 225-passed baseline — exactly +5, no new skips.

Negative-verified in three directions, each failing correctly and restoring clean: injecting
a `tail_years` read, fabricating `0` instead of `None` on `INSUFFICIENT_DATA`, and removing
contract expiry from `_is_live` (which collapses 8 of the 22 coverage tests).
