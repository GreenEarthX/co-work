# Menu Cleanup — Follow-up Tickets

> Spun off after the v6.1 navigation consolidation + two-layer prototype
> (see `menu-architecture-map.md`). The consolidation is merged; these are the
> open product/security decisions it surfaced. Audit reproducer:
> `cd frontend && node scripts/audit-menu.mjs`.

---

## Ticket 1 — Sensitive finance route review

**Problem.** Three routes are `visible_to: [ALL]` (full *access* for every role).
The two-layer prototype reduced their *nav prominence* for Finance/Bank, but
**access is still ALL** — i.e. logistics, certifier, engineer, and every
offtaker can still open them by URL or from their own nav. "Already visible"
≠ "strategically correct." Each needs a conscious classification.

Taxonomy for the decision: **`ALL-visible` · `role-filtered` · `screen-internal
redaction` · `split into public/private views`**.

| Route | Component | Verified content | Current | **Recommendation** |
|---|---|---|---|---|
| `/finance-timeline` | `ProjectTimeline.tsx` | **53 drawdown refs + Financial Close milestones** (not a generic timeline) | ALL | **Split** — `Project Timeline` (ALL: construction/COD milestones) vs `Drawdown & CP Timeline` (Finance / Bank / Legal / Executive: drawdown logic, CP sequencing, lender status). Interim: **screen-internal redaction** of drawdown/CP rows for non-finance roles until the split ships. |
| `/dscr-sensitivity` | `DSCRHeatmap.tsx` | Projected/scenario DSCR — a **first-class pre-COD** bankability instrument (restricted because sensitive, NOT post-COD-only) | ✅ **DONE — function-level entitlement** | `visible_to: [PROD(FINANCE_TREASURY), PROD(EXECUTIVE), OFT(FINANCE_TREASURY), OFT(EXECUTIVE), TP(BANK), TP(INSURER)]`. By role/function, not generic company type. Prosumer finance/exec covered via capability expansion. **Follow-ups:** add `TP('DFI')` when DFI is a ServiceType; allow Engineer/Ops with a finance-review permission (no such flag yet). **Caveat → Sub-item 1a.** |
| `/pricing-lineage` | `MoleculeLineage.tsx` | Full Gabillon decomposition: forward curve, risk premium, volatility, basis, seasonality, margin — commercially sensitive | ALL | **Split into two modes** — `Price Explanation` (Commercial / Offtaker / Producer: business-facing, no model internals) vs `Price Decomposition (Gabillon)` (Finance / Executive / Bank: full model). Interim: role-filter the decomposition to Finance/Exec/Bank. |

**Acceptance criteria**
- Each route has an explicit, documented classification (one of the four).
- `audit-menu.mjs` shows the narrowed `visible_to` per route; no role outside
  the agreed set has access.
- Where "split" is chosen, two distinct routes/labels exist (no commingled
  screen serving both audiences).
- Where "screen-internal redaction" is the interim, the sensitive rows are
  hidden by role inside the component, not merely de-emphasised.

**Effort:** S for role-filter (`/dscr-sensitivity`); M for redaction; L for the
two splits (new routes + components). Ship role-filter first (fastest risk
reduction), splits as a follow-on.
**Risk if not done:** commercial/financial-fragility data exposed to logistics,
certifier, and offtaker roles.

### Sub-item 1a — Route/data-level enforcement (security hardening, OPEN)
**Finding (verified 2026-05-30):** `visible_to` controls **menu visibility only**.
`/dscr-sensitivity` is a plain `<Route>` with no role guard — `GatedRoute` is
gate-prerequisite (workflow), not role. So the role-filter hides the screen from
9 personas' menus but a determined user could still reach it by **direct URL**.
This is the platform-wide model, not a regression introduced here — but for a
genuinely sensitive screen, menu-hiding is necessary, not sufficient.
**True enforcement requires one of:**
- a `RoleGuard` route wrapper (mirrors `GatedRoute`, checks `isVisible`), and/or
- **backend authz** on the data the screen fetches (`/finance-model/dscr-heatmap/*`
  should reject roles outside the allowed set) — the real control, since the
  data is the asset, not the page.
Applies equally to `/pricing-lineage` and the `/finance-timeline` drawdown layer
once those land. Recommend a single hardening pass covering all three.

---

## Ticket 2 — Make one real Reports view live

**Problem.** The Reports & Evidence hub is 100% `PLANNED` (honest, but it reads
as a roadmap, not an operating surface). Ship **one** genuinely live, low-risk
report so the hub is operational.

**Chosen report: Gate Status / Evidence Index.** Lowest-risk because the data
already exists — `project.bankability.gates[]` (frontend seed) and the live
`GET /api/v1/bankability/projects/{id}/bankability/FINANCE` endpoint already
return per-gate completion, verified/total evidence counts, and blocking items.
No new backend.

**Scope**
- Add (or repurpose the `evidence-upload` view as) a **"Gate Status & Evidence
  Index"** view in `ReportsPage.tsx`, state `LIVE`.
- Render real per-gate rows for the selected project: gate name · completion % ·
  `verified/total` · blocking items · state chip.
- Header count auto-updates (derivation already in place → "1/N live").
- Optional: CSV / print export (defer if it adds risk).

**Acceptance criteria**
- ReportsPage header shows **≥1 live** report; the Gate Status view renders real
  data for the active project (not placeholder text).
- Switching the selected project updates the report.
- No fabricated numbers — every value traces to `bankability.gates`.

**Effort:** S–M (frontend only, reuses existing bankability data).
**Risk if not done:** users open "Reports & Evidence" and see only a roadmap.

---

## Ticket 3 — Producer menu weight reduction (portfolio vs project)

**Problem (with real numbers).** The headline "Producer = 50" is the **org-union**
across all six producer business-functions — not a single user. Per-user
(post-prototype) the only heavy producer persona is **Finance-Treasury at 30**
(already cut from 39 by the two-layer prototype); the rest are 15–22. So this
ticket is narrow, not a wholesale producer redesign.

| Producer persona | Top-nav (now) |
|---|---:|
| Engineering | 15 |
| Operations | 16 |
| Compliance-Legal | 15 |
| Executive | 21 |
| Commercial | 22 |
| **Finance-Treasury** | **30** ← target |

**Two levers to go below 30:**
1. **Extend the two-layer `consult_for` tagging** to the remaining roles that
   carry analytics they only read (Executive, Insurer, Legal, Offtaker-Finance).
   Cheap; reuses the shipped mechanism.
2. **Portfolio-vs-project split (the bigger lever).** Several *operate* screens
   are themselves single-project scoped (Capital Stack, Gap Analysis, Package
   Builder, IC Pack, Drawdown Timeline). Move these from the global top-nav to
   the **Project profile** ("operate this project" surface), leaving the top-nav
   for portfolio-level actions + a project switcher.
   - Goal: **Producer primary menu = operate the project; Project profile =
     inspect the full project truth.**

**Acceptance criteria**
- Agree a per-user nav ceiling (proposal: **≤ 20** top-nav items per persona).
- `audit-menu.mjs` shows every persona at or below the ceiling, with **access
  unchanged** (access-preservation check stays green).
- Project-scoped operate screens are reachable from the Project profile with
  `?project=` context (the `DetailLinkRow` pattern already shipped).
- No destination removed; only relocated.

**Effort:** S for lever 1; L for lever 2 (touches routing model + project
profile). Recommend lever 1 first, measure, then decide on lever 2.
**Dependency:** the Project profile must be the canonical "everything about this
project" surface before lever 2 (else discoverability regresses).

---

## Ticket 4 — R2: PF/pricing engine (:8001) must not be browser-reachable (PRODUCTION BLOCKER)

**Problem.** Backend authorization (`require_finance_entitlement`) lives on the
platform proxy (`:8000`). The PF/pricing engine on `:8001` computes the sensitive
Gabillon decomposition and CFADS. If the engine is reachable from the browser in
production, a user can bypass the proxy guard entirely and hit `:8001` directly.

**Required before production:**
- The engine must be on a private network, reachable **only** from the platform
  backend — never exposed to the browser / public internet.
- No frontend code may call `:8001` directly. Enforced now by the CI **bundle
  hygiene** stage: `grep fetch\(...:8001` over `frontend/src` must be empty
  (`scripts/ci-check.sh` stage 4/4 — currently green).
- Add a deploy-time assertion (ingress/network policy) that `:8001` has no public
  route. (Infra task — not codeable in this repo.)

**Status:** frontend no longer calls `:8001` (verified, CI-enforced). Network
isolation is an infra/deploy control — tracked here as a production blocker.

---

### Cross-cutting rule (recorded from review)
> Cross-surface aliases (one screen, two menu surfaces) are allowed **only**
> where the user mental model is genuinely different AND the role boundary is
> hard. Current sole case: `/ciso-gateways` (Ops monitoring vs CISO admin).
> Not a licence to reintroduce duplicate names in the main tabs.

---

## Ticket 5 — Canonical route registry + aliases (clears route-name drift)

**Problem.** `audit-menu.mjs` §9 reports **16 route-name drifts** — URLs whose
leaf shares no word with the door label (`Sales → /finance-demand`,
`RFQ Management → /trader-dashboard`, `Commercial Overview → /marketplace`, …).
The screens were relabelled to honest vocabulary, but the URLs still speak the
old (often finance-origin) names. Renaming URLs directly breaks deep links,
bookmarks, the resolver's `OWNER_SURFACES`/`FINANCE_GUARDED_ROUTES` sets, and
any external references.

**Proposal.** Introduce a canonical-route registry with aliases + deprecation
dates, so names can be cleaned without breaking links:
```
/commercial/sales         ← canonical
/finance-demand           → 301-style redirect (alias), deprecate 2026-Q4
```
Steps: (1) registry mapping canonical → [aliases, deprecate_on]; (2) router
redirects aliases → canonical; (3) menu + resolver reference canonical only;
(4) `audit-menu.mjs` treats an alias-backed path as coherent (drift clears as
each canonical name lands). **Do NOT** rename URLs without this — it is the
deferred half of the §9 coherence fix.

**Owner.** Frontend + product. **Priority.** Medium (debt, not user-facing).

---

## Ticket 6 — CTRM posture decision (confirm the §9 dispositions)

**Problem.** §9 reports 6/6 CTRM risk/position functions absent, each tagged
with a *proposed* disposition (v1 / later / integrate) in `CTRM` inside
`audit-menu.mjs`. The proposed posture is **"GEX is an offtake/bankability OS,
not a merchant trading desk → integrate with an external CTRM"** for position
book, MTM/P&L and VaR; **v1** for credit/exposure; **later** for blotter &
confirmations. This is a **strategic product + investor-narrative choice** and
needs an explicit owner sign-off, not a developer default.

**Action.** Product to confirm or edit the `CTRM` disposition map; the §9 table
and investor narrative regenerate from it. **Owner.** Product/exec.

---

## Ticket 7 — Finance compute fragmentation + pre-COD data plumbing (Step-0 finding)

Surfaced while implementing the pre-COD governance scaffold (§10).

**7a — Three finance compute surfaces.** GEX now has THREE engines that compute
overlapping finance numbers: `gex_pf_engine` (CFADS/waterfall/DSCR/sculpting),
`backend/app/api/v1/pre_cod_metrics.py` (CEC/FRI/RMR/CBM/LLCR/SUC), and
`backend/app/services/financial_model.py` (FinancialModelEngine: its own
`DSCRResult`, `FundingStack`, IDC, annuity, stress test). Before building the
itemized Sources & Uses statement (Step 2d), DECIDE the single home — do not let
financial_model.py become a fourth DSCR/funding truth source. Audit which of its
outputs are real inputs vs seed vs derived.

**7b — pre-COD endpoint can't see packages.** `POST /api/v1/pre-cod-metrics/{id}`
reads `development_packages` from its own SQLite path; `POST /api/v1/packages`
writes to a different DB file. So the endpoint returns "create packages first"
even after a package is created, and FinanceBankabilityView falls back to
client-side PROXY mode (honestly stamped, but ungoverned). Unify the DB path so
the governed backend pre-COD report is reachable.

**7c — per-screen stamping.** §10 marks a metric "governed" if surfaced on ≥1
stamped screen. The standalone **DSCR Sensitivity (DSCRHeatmap)** and
**Covenants** screens are NOT stamped — a banker viewing them directly sees a
naked number. Stamp them, then flip §10's `governed?` gate from WARN to FAIL.

**Owner.** Backend + finance. **Priority.** 7b/7c medium (credibility), 7a before Step 2d.
