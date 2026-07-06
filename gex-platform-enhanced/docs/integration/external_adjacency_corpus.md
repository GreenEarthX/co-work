# External Adjacency Corpus — Skeleton (review item #5) — BUILT EMPTY

**Status:** machine built & verified 2026-07-02; **corpus deliberately empty**
— ingestion is a drop-in after licensing sign-off. Fabricating a seed would be
worse than N=1; the codebase's own `FALLBACK_COHORTS` (fabricated demo DSCRs)
is now loudly labeled and superseded on import.

## Two-layer design (the trap, resolved)

External databases contain **attributes**, never GEX **evidence profiles** —
so no dataset can seed the §3.5 evidence-conditional proximity. Hence:

- **Layer A — attribute adjacency** (this build): fuel × technology ×
  jurisdiction × pathway_class over observed external projects. Heuristic
  weights (.40/.25/.20/.15), documented as uncalibrated.
- **Layer B — evidence-profile adjacency**: platform-native, unlocks at N≥5.
  Every density response names its layer and provenance split.

**Revealed outcomes are the real Hidalgo analog:** version-over-version status
diffs (announced→FID→operational/cancelled) are captured as
`corpus_status_transitions` — the diffs ARE the dataset.

## Epistemic policy (ruled, enforced)

Everything the corpus emits is **`EXTERNAL_PRIOR`** — benchmark/nudge context
only. It never enters gate evaluation or bankability scoring. Enforced by a
**leak-guard test** (import boundary on `bankability_engine`,
`gex_project_rating_engine`, `routes_verification`, `routes_finance_model`,
`tea_engine/regimes`). **DSCR is not observable in any external corpus and is
never emitted** (`base_rates.dscr = None`; adjacency suppresses DSCR to 0.0
under an EXTERNAL_PRIOR basis rather than fabricate).

## What was built

| Piece | Where |
|---|---|
| Store: `corpus_versions` (hash-anchored, license+attribution REQUIRED), `external_projects`, `corpus_taxonomy_map` (census-then-sign), `corpus_status_transitions` | `backend/app/core/external_corpus.py` |
| Import (quarantines unmapped labels — never guesses), mapping sign-off, density (provenance split), base-rates (counts + revealed transitions only) | same |
| Routes: `/api/v1/corpus/{summary, import, taxonomy/sign, density, base-rates}` | `backend/app/api/v1/corpus_routes.py` |
| Adjacency benchmark: corpus-first sourcing + mandatory `basis` label (`EXTERNAL_PRIOR` / `PLATFORM_CACHE` / `FABRICATED_DEMO_FALLBACK`) | `backend/app/api/v1/adjacency.py` |
| NBA `cohort_context` (nudge-side, never enters ranking) | `backend/app/api/v1/next_best_action.py` |
| 7-test suite incl. leak guard, quarantine lifecycle, transition diffs | `backend/tests/test_external_corpus.py` |

Verified: empty → benchmarks say `FABRICATED_DEMO_FALLBACK`; after a signed
synthetic import → `EXTERNAL_PRIOR` density over observed projects, DSCR
suppressed; NBA carries the context; leak guard green.

## What remains before real data (the sign-offs)

1. **Dataset ruling** — recommendation: **IEA Hydrogen Production &
   Infrastructure Projects Database** as the v1 spine (**CC BY 4.0, verified
   2026-07-02** — commercial use with attribution; annual updates; H₂ +
   ammonia/methanol/synfuel derivatives). Supplements pending terms review:
   ICAO SAF facilities tracker (SAF), EU IPCEI/Innovation Fund award lists,
   US DOE announcements. Commercial trackers (BNEF/WoodMac) only if gaps survive.
2. **Legal sign-off** of the attribution line + whether serving *derived cohort
   statistics* to platform users satisfies each license (CC BY: yes, with
   attribution).
3. **First import + taxonomy census**: import the snapshot (labels quarantine),
   review `/corpus/summary` unmapped labels, sign the observed mapping
   (`/corpus/taxonomy/sign`), re-import — same census-then-sign discipline as
   everywhere else.
4. Schedule the refresh (annual IEA release) — each import auto-yields the
   transition dataset.
