# GEX Causal-Ways Map — GENERATED (do not hand-edit)

> Source of truth: `App.tsx` (routes+guards) · `data/evidenceCatalog.ts`
> (evidence ways + finance-guarded set) · `features/projects/ProjectsPage.tsx`
> (risk / next-action helpers) · engine `bankability_engine.py` (PERSONA_GATES).
> Regenerate: `node frontend/scripts/audit-causal-ways.mjs` · generated 2026-06-15.
>
> **Doctrine (Hidalgo/Sung):** every claim traces claim → consequence → a *way*
> to the screen where it is worked, and a way only targets a screen the viewer
> can enter. **Blue** = routed through `resolveActionRoute()` (the way is
> decided centrally, not by the screen). **Red** = finance-guarded, hit raw
> (not yet migrated). **Amber-dashed** = workflow GateLock. **Green** = open.
>
> Migration is strangler-pattern: each call-site delegates to the resolver one
> at a time; a red edge turning blue is the proof a migration landed.

```mermaid
flowchart TD
    M1[Projects menu] --> PP["/projects<br/>claims: next action · blockers · risk flags"]
    M2[Finance / Producer menu] --> PB["/producer-bankability<br/>persona-scoped gate evidence"]

    %% Deep-link funnel — engine persona decides which gates are visible
    PP -- "blocker deep-link<br/>persona=PRODUCER" --> PB
    PB -. "PRODUCER sees: G0 G1 G3 G5 G9 G11" .-> PBGPRODUCER([G0 G1 G3 G5 G9 G11])
    PP -- "blocker deep-link<br/>persona=FINANCE" --> PB
    PB -. "FINANCE sees: G4 G6 G7 G8 G10" .-> PBGFINANCE([G4 G6 G7 G8 G10])
    PP -- "blocker deep-link<br/>persona=REGULATOR" --> PB
    PB -. "REGULATOR sees: G2 G6 G9" .-> PBGREGULATOR([G2 G6 G9])
    PP -- "blocker deep-link<br/>persona=EXECUTIVE" --> PB
    PB -. "EXECUTIVE sees: all gates" .-> PBGEXECUTIVE([all gates])

    %% Evidence-item ways (generated from STATIC_EVIDENCE_CATALOG.route)
    PB --> RR{{"resolveActionRoute()<br/>allowed · fallback · forbidden"}}
    R_projects___edit["/projects/{project_id}/edit"]:::open
    RR -- "WORK IT" --> R_projects___edit
    R_finance_plant_builder["/finance-plant-builder"]:::open
    RR -- "WORK IT" --> R_finance_plant_builder
    R_dscr_sensitivity["/dscr-sensitivity"]:::resolved
    RR -- "WORK IT" --> R_dscr_sensitivity
    PB -- "Upload ✓ / Eye→docs ✓" --> DOC[("evidence_documents<br/>sha256 + append-only audit")]

    %% Risk-flag & next-action ways (scanned from ProjectsPage helpers)
    PP --> RR
    R_capital_stack["/capital-stack"]:::locked
    RR -- "risk flag" --> R_capital_stack
    R_bankability_scores["/bankability-scores"]:::open
    RR -- "risk flag" --> R_bankability_scores
    R_producer_bankability["/producer-bankability"]:::open
    RR -- "risk flag" --> R_producer_bankability
    R_stage_gates["/stage-gates"]:::open
    RR -- "risk flag" --> R_stage_gates
    R_offtake_quality["/offtake-quality"]:::locked
    RR -- "risk flag" --> R_offtake_quality
    R_finance_timeline["/finance-timeline"]:::open
    RR -- "risk flag" --> R_finance_timeline
    R_adversarial_review["/adversarial-review"]:::open
    RR -- "risk flag" --> R_adversarial_review
    R_cert_readiness["/cert-readiness"]:::open
    RR -- "risk flag" --> R_cert_readiness
    R_insurance["/insurance"]:::open
    RR -- "risk flag" --> R_insurance

    classDef guarded stroke:#e11d48,stroke-width:2px;
    classDef resolved stroke:#2563eb,stroke-width:2px;
    classDef locked stroke:#f59e0b,stroke-width:2px,stroke-dasharray:4 3;
    classDef open stroke:#10b981,stroke-width:1.5px;
```

## Lint result (0 blocking)

- ✅ resolver-handled  evidenceCatalog → /dscr-sensitivity  (resolveActionRoute → allowed | fallback | forbidden)
- ✅ resolver-handled  roleNextAction → /capital-stack  (owner-surface; resolver routes non-owners to fallback)
- ✅ resolver-handled  roleNextAction → /offtake-quality  (owner-surface; resolver routes non-owners to fallback)
- ✅ resolver-handled  riskFlagAction → /offtake-quality  (owner-surface; resolver routes non-owners to fallback)
- ✅ resolver-handled  riskFlagAction → /capital-stack  (owner-surface; resolver routes non-owners to fallback)
- ✅ resolver-handled  riskAlertAction → /offtake-quality  (owner-surface; resolver routes non-owners to fallback)
- ✅ resolver-handled  riskAlertAction → /capital-stack  (owner-surface; resolver routes non-owners to fallback)

## Persona deep-link funnel (engine PERSONA_GATES)

A blocker deep-link to `/producer-bankability?gate=Gx` resolves only if Gx is in
the viewer's persona view — otherwise the screen shows an explicit "not in your
persona" notice (no silent miss).

- **PRODUCER** → G0_SITE_RIGHTS, G1_GRID_WATER, G3_FEEDSTOCK_LOGISTICS, G5_EPC, G9_PERMITS, G11_COD
- **FINANCE** → G4_OFFTAKE, G6_IE_SIGNOFF, G7_INSURANCE, G8_MODEL_AUDIT, G10_FINANCIAL_CLOSE
- **REGULATOR** → G2_CERTIFICATION, G6_IE_SIGNOFF, G9_PERMITS
- **EXECUTIVE** → all gates
