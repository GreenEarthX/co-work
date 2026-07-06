# Gabillon Two-Factor Model — Audit Documentation

**Service:** `gex_pf_engine` · **Endpoint family:** `/api/v1/pricing/*` · **Core:** `backend/app/core/gabillon.py`, `backend/app/core/price_lineage.py`
**Status:** SEED-calibrated (expert priors, `n_observations = 0`) until market observations are loaded via `POST /api/v1/pricing/calibrate`.
**Last formula revision:** 2026-06-11 — corrected forward equation (see §8 Changelog).

---

## 0 · API surface — two Gabillon services, two scopes

The engine exposes **two distinct Gabillon services**. They were previously tagged almost identically ("Price Curve Engine — Gabillon" vs "… - Gabillon", em-dash vs hyphen) which made the docs unreadable; since 2026-06-11 they are:

| Tag | Routes | Scope unit | Purpose |
|---|---|---|---|
| **Gabillon — Market Curves (per molecule)** | `/api/v1/pricing/*` | one curve per **molecule** | Reference market view: implied spot, term structure, forwards, Monte-Carlo, seasonality, parameters, CFADS price deck, and the price decomposition (Information Lineage). One calibration per molecule, SEED until market quotes are loaded. This is what this document describes. |
| **Gabillon — Project Calibration & Offtake (per project)** | `/pf/*` | one curve per **project_id** | Deal pricing: calibrate against project fundamentals (LCOF anchor) with per-project audit memory, Q pricing curves, P forecast cones, offtake contract valuation, GreenMesh portfolio rollup. |

Rule of thumb: quoting the molecule market → Market Curves; pricing a specific deal → Project Calibration & Offtake.

---

## 1 · What the model is

The engine prices **forward curves for green fuels** (H₂, NH₃, e-methanol, SAF, e-NG, HVO, …) using a *modified Gabillon (1991) two-factor model*. The original model was built for oil futures; it describes a commodity price with two stochastic factors:

1. **Spot price `S(t)`** — mean-reverting in log space toward a long-run equilibrium level.
2. **Convenience yield `δ(t)`** — the implicit benefit of holding physical product (scarcity premium); itself mean-reverting.

Three green-fuel modifications are added on top:

| Extension | Why |
|---|---|
| **Seasonality** (Fourier terms) | Heating demand (H₂, e-NG peak Q1/Q4), aviation summer (SAF peaks Q2/Q3) |
| **CAPEX learning-curve floor** | Nascent markets can't trade durably below the levelised production cost; floor declines as installed capacity doubles |
| **Regulatory premium** | EU ETS carbon price + RFNBO/RED III mandate scarcity embeds a green premium over fossil parity |

These are *priors for a market with almost no liquid forward trading*. The model produces a defensible, explainable curve — not a market quote. Every output carries `calibration_status: SEED` until real observations replace the priors.

---

## 2 · The forward price equation

For tenor τ = (T − t) **in years**:

```
ln F(t,T) =  e^(−ατ) · ln S(t)                        ── spot influence, decaying
          + (1 − e^(−ατ)) · μ                          ── pull toward equilibrium level
          − ((1 − e^(−κτ))/κ) · (δ(t) − θ)             ── convenience-yield drag
          + (σ_S²/(4α)) · (1 − e^(−2ατ))               ── Jensen variance correction (OU)
          + (ρ·σ_S·σ_δ/(α−κ)) · (e^(−κτ) − e^(−ατ))    ── factor-correlation cross term
          + a₁·sin(2πT) + a₂·cos(2πT)                  ── seasonality at delivery date
          + 0.10·τ·(ln(floor) − ln S)  if S < floor    ── CAPEX-floor pull (else 0)
```

**Limiting behaviour (the audit checks):**

- **τ → 0:** every term vanishes → `F → S` (forward converges to spot). ✓
- **τ → ∞:** `ln F → μ + σ_S²/(4α) + …` → the forward converges to the long-run equilibrium `e^μ` plus a small convexity premium. ✓
- **Sanity bound:** no 12-month forward should exceed ~±20 % of equilibrium under seed parameters. The platform frontend additionally rejects any response with `forward/spot > 20×`.

> **Critical convention:** `μ` (`mu_base`) is a **log price level** — e.g. `ln(800) = 6.68` for e-methanol — *not* an annual drift rate. It enters through the blend weight `(1 − e^(−ατ))`, never multiplied by τ. (Violating this was the 2026-06-11 bug: `τ·μ` in the exponent produced forwards 700–4,700× spot.)

---

## 3 · Model parameters (`GabillonParams`)

Seed values per molecule live in `SEED_PARAMS` (`backend/app/core/gabillon.py`). Sources: BNEF H2 LCOH Tracker 2025, ICIS SAF assessments NWE 2024–25, Argus eMeOH NWE 2025, OIES ET52 (2026).

| Parameter | Symbol | Unit | Meaning | Effect on the curve | Audit question to ask |
|---|---|---|---|---|---|
| `alpha` | α | yr⁻¹ | Spot mean-reversion speed | Higher α → spot shocks die out faster; half-life = ln 2/α (e.g. α=1.0 → 8.3 months) | Is the half-life consistent with how fast this market re-anchors after a shock? |
| `mu_base` | μ | ln(€/t) | Long-run equilibrium **log price level** | `e^μ` is where the curve flattens at long tenors (H₂: ln 5500, e-MeOH: ln 800) | Does `e^μ` match the consensus long-run price? Who set it, on what source? |
| `sigma_s` | σ_S | %/√yr | Annualised spot volatility | Sets the Jensen convexity premium and Monte-Carlo cone width | Is vol consistent with observed price series / proxy market (TTF, jet fuel)? |
| `kappa` | κ | yr⁻¹ | Convenience-yield mean-reversion speed | How fast scarcity premiums normalise | Plausible vs. storage/logistics cycle of the molecule? |
| `theta_0` | θ₀ | dimensionless | Long-run convenience yield level | δ > θ → backwardation (scarcity); δ < θ → contango | Is the market structurally short (positive θ) or oversupplied? |
| `sigma_delta` | σ_δ | %/√yr | Convenience-yield volatility | Second-factor uncertainty; widens long-tenor risk | — |
| `rho` | ρ | [−1, 1] | Correlation between spot and convenience-yield shocks | Negative ρ (all seeds) dampens long-tenor variance | Sign justified? (scarcity ↑ when price ↑ → typically negative for storables) |
| `season_a1`, `season_a2` | a₁, a₂ | log points | Fourier sin/cos coefficients (annual cycle) | Amplitude = √(a₁²+a₂²); e.g. H₂ ±9.4 % peak-to-trough, Q1 peak | Does the seasonal phase match physical demand (heating vs aviation)? |
| `learning_rate` | — | per doubling | CAPEX cost decline per doubling of installed capacity | Lowers the future floor as capacity grows | Wright's-law rate defensible for this technology? |
| `reference_capacity_gw` | — | GW | Cumulative installed capacity at calibration | Anchors the learning curve | — |
| `capex_floor_eur_t` | — | €/t | Levelised production cost floor (LCOH/LCOF from Plant Builder) | If spot < floor, an upward pull of `0.10·τ·ln(floor/S)` applies | Floor sourced from an actual Plant Builder run, or a placeholder? |
| `regulatory_premium_base` | RP | €/t | Green premium from EU ETS + RFNBO/RED III mandates | Added to the cost stack (not inside the market forward) | Which carbon price / mandate year does it reflect? |
| `calibration_error_pct` | — | % | Mean abs. deviation of model vs observations | Quality metric; 0 for seed | — |
| `n_observations` | — | count | Observations used in last calibration | **0 = SEED priors, not market data** | Has anyone loaded real quotes yet? |
| `last_calibrated` | — | date | Calibration timestamp | Shown as "Calibration" date in the UI | Stale? |

**Current seed snapshot (per molecule):**

| Molecule | α | e^μ (€/t) | σ_S | θ₀ | Seasonal peak | CAPEX floor | Reg. premium |
|---|---|---|---|---|---|---|---|
| H2 | 1.00 | 5,500 | 42 % | 0.15 | Q1 (heating) | 3,500 | 200 |
| SAF | 0.55 | 1,500 | 25 % | 0.08 | Q2–Q3 (aviation) | 1,200 | 350 |
| E_METHANOL | 0.65 | 800 | 30 % | 0.05 | mild, shipping | 600 | 150 |
| NH3 | 0.50 | 700 | 22 % | 0.06 | mild | 450 | 80 |
| E_NG | 0.80 | 120 (€/MWh) | 45 % | 0.10 | Q4/Q1 (heating) | 95 | 25 |
| HVO | 0.45 | 1,800 | 28 % | 0.07 | feedstock Q1–Q2 | 1,400 | 200 |

---

## 4 · `POST /api/v1/pricing/decomposition` — request fields

Everything beyond `molecule`/`tenor_months` is **optional context** that adds cost-stack components on top of the market forward.

| Field | Type / default | Meaning |
|---|---|---|
| `molecule` | string, required | Engine key (`H2`, `NH3`, `E_METHANOL`, `SAF`, `E_NG`, `HVO`, …). Free-form names like `e-Methanol` are normalised server-side. |
| `tenor_months` | int, 12 | Delivery tenor. Converted to years internally (τ = months/12). |
| `spot_override` | float, null | Scenario spot price. Default = implied spot from calibration (`e^μ` at seed). |
| `tranches[]` | list, [] | Debt structure; enables the financing components. Per tranche: |
| · `name` | string | Label for the audit trail. |
| · `tranche_type` | `"senior"` | `senior`, `mezzanine`, `concessional` — concessional tranches drive the DFI absorption credit. |
| · `amount` | € ≥ 0 | Tranche principal. |
| · `rate` | 0–1 | All-in interest rate (e.g. `0.041` = 4.1 %). |
| · `tenor` | years 1–50 | Tranche maturity — used in the capital-recovery factor. |
| · `grace_period_years` | int, 0 | Interest-only years; feeds the Grace Period Benefit. |
| · `dfi_provider` | string, null | `EIB`, `KFW`, … — listed in the lineage and WACC card. |
| · `is_first_loss` | bool, false | Marks catalytic first-loss capital (used in catalytic ratio). |
| `equity_amount` | € , 0 | Equity in the capital stack (WACC weighting). |
| `equity_cost` | 0–1, **0.12** | Required return on equity used in blended WACC. |
| `grants_amount` | €, 0 | Non-repayable capital; reduces the financed base. |
| `subsidies` | dict, {} | **€/kg** of product — the engine multiplies ×1000 to €/t. `{"45V": 3.0}` = $3/kg hydrogen PTC = €3,000/t. ⚠️ Scale to the molecule: a 45V pass-through embedded in 1 t of e-methanol is ~€0.5/kg, not 3.0. |
| `insurance_annual_eur` | €/yr, 0 | Annual premium; allocated per tonne via `annual_production_tonnes`. |
| `insurance_provider` | string | Shown as the lineage source for the insurance row. |
| `annual_production_tonnes` | t/yr, 18,250 | Plant output used to convert annual costs to €/t. |
| `certifications` | list | Display context (e.g. `RED_III`, `RFNBO`, `45V`) — listed in the subsidy card. |
| `correlation_id` | string | Caller-supplied trace ID propagated into every component for audit joins. |

---

## 5 · Decomposition output — the reconciliation identity

The waterfall is split into **market terms** (priced by Gabillon) and **cost-stack pass-throughs** (deterministic arithmetic), with one bridge line:

```
MARKET (Gabillon):     spot_basis + convenience_yield + mean_reversion
                       + seasonality + capex_floor + residual  =  market forward
COST STACK (added):    + regulatory_premium + financing_spread
                       + concessional_absorption + grace_period_benefit
                       + insurance_premium
                       ─────────────────────────────────────────
                       =  forward_price_eur_t   (the contract forward)
BRIDGE:                + Σ subsidies (negative)
                       =  effective offtaker cost
```

Audit invariants enforced by the engine:

1. **Σ(non-subsidy components) = `forward_price_eur_t`** exactly.
2. **`residual`** reconciles *only* the market terms (Jensen + cross-term non-linearity). It must stay small — a large residual means the linearised components no longer explain the model forward. It can never absorb financing or subsidies.
3. **Subsidies never change the contract forward** — they only bridge to effective offtaker cost.

Component-level formulas (in `price_lineage.py`):

| Component | Formula (€/t) |
|---|---|
| Spot Basis | `S` |
| Convenience Yield | `S·(e^(−((1−e^(−κτ))/κ)(δ−θ)) − 1)` — 0 at seed since δ = θ |
| Mean Reversion | `S·(e^((1−e^(−ατ))(μ − ln S)) − 1)` — 0 when spot is at equilibrium |
| Seasonality | `S·(a₁ sin 2πT + a₂ cos 2πT)` |
| CAPEX Floor | `S·0.10·τ·ln(floor/S)` if S < floor, else 0 |
| Regulatory Premium | `regulatory_premium_base` (constant €/t) |
| Financing Spread | `0.65·floor·(CRF(WACC,15y) − CRF(3%,15y))` — cost of capital above risk-free via capital-recovery factors |
| Concessional Absorption | −(0.65·floor · rate-saving · concessional-share · 0.08) |
| Grace Period Benefit | −(floor · 0.02 · max grace years) |
| Subsidy *X* | −(€/kg value × 1000) |
| Insurance Premium | `insurance_annual_eur / annual_production_tonnes` |

---

## 6 · Calibration path (SEED → market-calibrated)

`POST /api/v1/pricing/calibrate` with `observations[]` (`date`, `price_eur`, `tenor_months`, `source`, `volume_tonnes`):

1. Volume-weighted average per tenor bucket.
2. Spot bootstrapped from the shortest tenor.
3. Term-structure slope → `theta_0` (clamped ±0.3).
4. Geometric mean of ≥24-month observations → `mu_base` (or 70/30 blend with seed).
5. Residual fit error stored as `calibration_error_pct`; `n_observations` updated.

Until this is run with real quotes, every output is **prior-based**. Treat SEED curves as *structured expert judgment*, suitable for screening — not for marking a book.

---

## 7 · Access control

The platform proxies this endpoint at `gex-platform-enhanced` → `/api/v1/pricing/decomposition` with two gates:

1. **ABAC middleware** — any `/api/` call without a Bearer JWT → 401.
2. **`require_finance_entitlement("price_decomposition")`** — requires a finance role (Finance/Exec/Bank/DFI/Insurer) or a project-scoped `FINANCE_REVIEW` grant → otherwise 403, decision audited.

The frontend deliberately ships **no seed decomposition** in the JS bundle; an unauthorized or engine-down state renders an explanatory empty state instead of fake numbers.

---

## 8 · Changelog

**2026-06-11 — forward equation corrected** (`gabillon.py::forward_price`)

- *Bug:* `drift_term = τ·(μ − σ²/2 + ρσσ_δ/κ)` treated the equilibrium **log level** μ as an annual **drift rate** → `e^(μτ)` explosions (12M forwards 98×–4,676× spot across all molecules). A GBM-style drift had been pasted into a mean-reverting model.
- *Fix:* level blend `(1 − e^(−ατ))(μ − ln S)`; convenience-yield drag corrected to decay at κ with a negative (backwardation) sign; GBM drift removed (the OU Jensen term `σ²/(4α)(1−e^(−2ατ))` already supplies the convexity correction).
- `price_lineage.py` components updated to the same formulas, and the residual now reconciles market terms only (it previously absorbed the whole cost stack, e.g. +€2,884 on an €800 e-MeOH decomposition).
- Post-fix 12M forwards: H₂ 0.975×, NH₃ 0.993×, e-MeOH 0.988×, SAF 1.110×, e-NG 0.949×, HVO 1.084× spot.
