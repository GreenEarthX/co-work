/**
 * GEX Platform Help Text — Centralised Constants
 * File: src/config/helpText.ts
 *
 * Every tooltip and tab description in one place.
 * Enables: centralised maintenance, future i18n, consistency.
 *
 * Usage:
 *   import { HELP } from '@/config/helpText';
 *   <InfoTooltip text={HELP.DSCR_P50} />
 *   <p className="text-sm text-gray-500">{TAB_DESCRIPTIONS.GAP_ANALYSIS}</p>
 */

// ═══════════════════════════════════════════
// TAB DESCRIPTIONS (shown under page title)
// ═══════════════════════════════════════════

export const TAB_DESCRIPTIONS = {
  // ── MONITOR ZONE ──
  DASHBOARD:
    'Portfolio overview — all active projects with key metrics at a glance. Click any project to drill into its bankability state.',
  BANKABILITY_SCORES:
    "Deep-dive into the project's Bankability Score (0–100) and Credibility Score (0–100) with platform benchmark histogram.",
  STAGE_GATES:
    "The 12 gates (G0–G11) that govern the project's progression from site rights through to commercial operations.",
  DSCR_SENSITIVITY:
    "How sensitive is the project's DSCR to changes in 7 key variables? The heatmap shows which risks are most dangerous.",
  COVENANTS:
    'Active financial covenants and their current compliance status. Breach triggers remediation or acceleration.',

  // ── STRUCTURE ZONE ──
  GAP_ANALYSIS:
    "What's blocking FID? Identifies every gap between the project's current state and the next bankability threshold. Gaps ranked: BLOCKING (red), DEGRADING (amber), ADVISORY (blue).",
  INSTRUMENT_CATALOG:
    'All de-risking instruments this project is eligible for, based on jurisdiction, molecule, development stage, and size. Select instruments to build a stacked package.',
  PACKAGE_BUILDER:
    'The core workbench. Stacks selected instruments and computes cumulative effect on WACC, DSCR, and bankability state. Shows before/after comparison and stackability warnings.',
  RISK_ALLOCATION_MATRIX:
    'For each project risk: who bears it, what mitigates it, what remains, what it costs. This is the table a credit committee requires before approving a facility.',
  STRUCTURING_TIMELINE:
    'When to apply for each instrument, in what order, with what dependencies. DFI applications must precede commercial instruments.',
  DEMAND_PIPELINE:
    'Track offtake demand signals from EOI through LOI to binding term sheet. Compute coverage metrics and identify aggregation opportunities.',
  PLANT_BUILDER:
    'Configure a greenfield plant from the equipment catalog. Computes CAPEX, OPEX, levelised cost per tonne, competitive gap (subsidy needed), and certification distance from RFNBO/RED III/45V.',
  CAPITAL_STACK:
    'Multi-tranche capital structure with three tabs: Stack (sources + green bond comparison), CAPEX Layers (per-layer WACC + ETV), De-Risking (instruments from registry).',
  OFFTAKE_QUALITY:
    'Five-test bankability scorecard for offtake contracts: Tenor, Credit, Volume Firmness, Pricing/Indexation, Curtailment/Shape Risk.',
  CERT_READINESS:
    'Pre-certification scorecard: how close is the project to achieving RFNBO, RED III, 45V, CORSIA, CertifHy certification?',
  TERM_SHEET_TRACKER:
    '19 commercial terms in 5 groups. Track convergence between project company and counterparties. AGREED / PENDING / DISPUTED.',

  // ── EXPORT ZONE ──
  BANKER_SNAPSHOT:
    'Auto-generated 1-page lender decision summary. Includes the recommended de-risking package and before/after metrics. Print to PDF for credit committee.',
  IC_PACK_BUILDER:
    'Investment Committee pack — 9 sections assembled from governed platform data. All sections must be APPROVED before the pack is exportable.',
  DATA_ROOM:
    'Virtual data room with 11 document categories per Playbook Annex E. Each document carries a SHA-256 integrity hash.',
  INSURANCE_SCHEDULE:
    '8-line insurance programme: CAR, DSU, Performance Bond, Marine, TPL, Pollution, BI, Lender Loss Payee. Tracks placement status for G7 gate.',
  TRANSFER_READINESS:
    'Secondary market exit index (TRI, 0–100). Measures how easily project ownership can be transferred to a new sponsor.',

  // ── DEAL ROOM ZONE ──
  APPROVAL_QUEUE:
    'Pending WAE (Workflow Authorization Engine) approvals. Approve or reject with quorum progress tracking.',
  COMMITMENT_SIGNING:
    'CSS (Commitment Signature Service) signing ceremony. Creates an immutable, SHA-256 hash-chain record of binding commercial acts.',
  COMMITMENT_VERIFIER:
    'Verify the integrity of any signed commitment by checking its hash against the append-only ledger.',
  PROJECT_TIMELINE:
    'Three views: phase swimlanes (5 phases × milestones), S-curve drawdown chart, milestone table with 23 items.',
} as const;


// ═══════════════════════════════════════════
// METRIC TOOLTIPS (ⓘ next to metric labels)
// ═══════════════════════════════════════════

export const HELP = {
  // ── Financial metrics ──
  DSCR_P50:
    'Debt Service Coverage Ratio (P50 scenario) = Cash Flow Available for Debt Service ÷ annual debt service. Lenders require P50 ≥ 1.30x.',
  DSCR_P90:
    'DSCR under the P90 downside scenario. Must exceed 1.20x. If breached, the project fails the lender stress test.',
  LLCR:
    'Loan Life Coverage Ratio = NPV of remaining CFADS ÷ outstanding debt balance. Must exceed 1.40x at all times.',
  WACC:
    'Weighted Average Cost of Capital — blended cost of all capital tranches. Lower = cheaper financing = higher equity IRR.',
  WACC_SAVING:
    'Basis-point reduction in WACC from layer-optimised financing vs traditional flat-WACC approach.',
  CFADS:
    'Cash Flow Available for Debt Service = EBITDA − tax − working capital change − maintenance capex. The cash available to pay lenders.',
  DSRA:
    'Debt Service Reserve Account — must hold 6 months of debt service as a liquidity buffer. Underfunding triggers a distribution lock-up.',
  ETV:
    'Enterprise Technology Value — optionality not on the balance sheet: product switching (H₂→NH₃→SAF→eMeOH), carbon premium escalation, GoO appreciation, learning curve, refinancing option at COD.',

  // ── Bankability metrics ──
  TRUST_SCORE:
    'Composite 0–100: gate completion (40pts), state bracket (30pts), capital unlock count (20pts), risk-free indicators (10pts). Updated on every gate change.',
  BANKABILITY_SCORE:
    'Composite 0–100: gate completion (40pts) + state bracket (30pts) + capital unlock (20pts) + risk-free (10pts). Score ≥75 = investor-ready.',
  CREDIBILITY_SCORE:
    'Composite 0–100: evidence verification (35pts) + gate depth (25pts) + CAPEX efficiency (15pts) + risk profile (15pts) + maturity (10pts). ≥80 = credit committee grade.',
  BANKABILITY_STATE:
    'The 9-state ladder: SPECULATIVE → TECHNICALLY_PLAUSIBLE → COMMERCIALLY_PLAUSIBLE → BUILDABLE → STRUCTURALLY_BANKABLE → CREDIT_APPROVED → FINANCEABLE → OPERATIONAL → REFINANCING_ELIGIBLE.',
  GATE_SCORE:
    'Weighted sum of sub-criteria for this gate. Each gate has CISO-configurable weights and analyst-scored variables. Score ≥ threshold = gate passed.',

  // ── Offtake metrics ──
  OFFTAKE_COVERAGE:
    'Firm contracted volume ÷ total production capacity. Must reach 70% for bankable threshold. Firm = binding term sheet or executed contract (not LOI).',
  ANCHOR_BUYER:
    "The highest-volume, highest-credit firm offtaker. Lenders assess the anchor's credit quality as the offtake security floor.",
  TENOR_TEST:
    'Offtake contract tenor ≥ debt tenor. If the offtake expires before the debt, the project has refinancing risk.',
  CREDIT_TEST:
    'Offtaker credit rating ≥ BBB- (or credit-wrapped by an investment-grade guarantor). Below IG requires credit enhancement.',
  VOLUME_FIRMNESS:
    'Percentage of contracted volume that is firm (binding, not subject to curtailment). Must be ≥70% for bankable.',
  CURTAILMENT_TEST:
    'Offtaker right to reduce take volume. >10% annual curtailment right degrades bankability significantly.',

  // ── Sensitivity & risk ──
  INTEREST_RATE_SENSITIVITY:
    'Per Taghizadeh-Hesary (2022): at ≥60% debt ratio, ±75bps ≈ ±0.08 DSCR. Interest rate is the dominant sensitivity for H₂/SAF projects.',
  BREAKEVEN:
    'Maximum adverse move in a single variable before DSCR hits the 1.20x covenant floor. Tighter margin = more fragile project.',
  REGULATORY_RISK_PREMIUM:
    'Basis-point spread added to cost of capital for jurisdictional political/regulatory risk. FR: +10bps (low), EG: +120bps (high).',
  RISK_PROBABILITY:
    'Likelihood of this risk materialising: HIGH, MEDIUM, LOW. Based on project stage, technology maturity, and jurisdiction.',
  RISK_IMPACT:
    'Severity if risk materialises: HIGH = threatens debt service, MEDIUM = reduces equity returns, LOW = manageable within contingency.',
  RESIDUAL_RISK:
    'What remains after the mitigating instrument is applied. NEGLIGIBLE = fully covered. LOW/MEDIUM = partially covered. The sponsor carries residual.',

  // ── Structuring & instruments ──
  BLOCKING_GAP:
    'This gap prevents the project from advancing to the next bankability state. Must be resolved before FID.',
  DEGRADING_GAP:
    'This gap weakens the credit case but does not block progression. Resolving it improves WACC, DSCR, and investor confidence.',
  ADVISORY_GAP:
    'Worth noting but not materially impacting bankability. May become degrading if conditions deteriorate.',
  INSTRUMENT_TYPE:
    'Instrument category: CfD, GCGC, partial credit guarantee, PRI, ECA, grant, concessional loan, green bond, performance guarantee, interest rate swap, etc.',
  RATE_REDUCTION_BPS:
    'How many basis points this instrument reduces the effective senior debt rate. Higher = more impactful on WACC and DSCR.',
  INSTRUMENT_COST_BPS:
    'Annual guarantee fee or insurance premium in basis points. This is the price of the de-risking. Net benefit = rate_reduction − cost.',
  INSTRUMENT_COVERAGE:
    'Maximum percentage of senior debt or CAPEX that this instrument covers. Total coverage across all instruments should not exceed 100%.',
  STACKABILITY_WARNING:
    'Conflict or concern when combining instruments. E.g., 45V + 45Y cannot both be claimed; total coverage >100% = over-insurance.',
  TAX_STACKING_RISK:
    '45V (US) + RFNBO (EU): risk of double-claim on renewable energy attributes. If claiming 45V on RE used for H₂, EU may deny RFNBO if same EACs are counted twice.',

  // ── Plant Builder ──
  INSTALLATION_MULTIPLIER:
    'Total installed cost = equipment price × multiplier. Covers civil works, piping, electrical, commissioning, first fills. Typical range: 1.2–1.6×.',
  LEVELISED_COST:
    'Levelised Cost = (Annualised CAPEX + annual OPEX) ÷ annual output. The minimum price per tonne at which the plant breaks even. Uses Capital Recovery Factor with configurable WACC and project life.',
  COMPETITIVE_GAP:
    'Levelised cost − market reference price. Positive = subsidy or premium needed to be competitive. Negative = project is competitive on its own.',
  CERT_READINESS_SCORE:
    'Score 0–100 per certification regime. Factors: power source additionality, temporal correlation, GHG pathway, geographic correlation, equipment certifications, audit trail completeness.',
  CAPEX_LAYER:
    'Which CAPEX decomposition layer (L1–L5) this equipment belongs to. Each layer has its own risk profile, useful life, and optimal cost of capital.',

  // ── GreenMesh ──
  CERTIFICATION_PREMIUM:
    'Revenue uplift from certification, per molecule, per regime. E.g., RFNBO H₂: +€400/t, SAF RFNBO: +€350/t. This is earned revenue from compliance effort, not subsidy.',
  GOO_VALUE:
    'Guarantee of Origin value = certification premium × volume. A separate revenue stream from the physical commodity, tradeable independently.',
  MASS_BALANCE:
    'Chain-of-custody tracking: verifies the green attribute follows the physical molecule from production through logistics to delivery. Required for GoO validity.',
  NETTING_EFFICIENCY:
    'FlowFusion™ result: (gross bilateral flows − net multilateral flows) ÷ gross flows. Higher = fewer physical transfers needed.',

  // ── Gabillon / Pricing ──
  SPOT_PRICE:
    "Implied current spot price, derived from observed forward prices via Gabillon two-factor model inversion. Not a market quote — it's a calibrated estimate.",
  FORWARD_CURVE:
    'Term structure of forward prices from 1M to 60M. Contango (upward slope) = storage/carry cost dominates. Backwardation (downward slope) = scarcity/convenience yield dominates.',
  MEAN_REVERSION:
    'Rate at which the spot price reverts to the long-term equilibrium (production cost floor). Higher α = faster reversion = less sustained deviation from fundamentals.',
  SEASONALITY:
    'Quarterly price pattern: H₂ peaks Q1 (heating), SAF peaks Q2–Q3 (aviation), MeOH moderate. Extracted via Fourier decomposition from calibrated residuals.',
  CAPEX_FLOOR:
    'The spot price cannot stay below levelised cost of production indefinitely. If market < LCOH, the Gabillon model prices in upward mean reversion.',
  MONTE_CARLO_VAR:
    'Value-at-Risk from 10,000 simulated price paths using calibrated Gabillon parameters with Cholesky-correlated Brownian motions. Shows downside risk at 5th/10th percentile.',

  // ── Workflow & governance ──
  WORKFLOW_STATE:
    'Every bankability artefact carries a state: DRAFT → COMPUTED → REVIEWED → APPROVED → EXPORTED → SHARED_EXTERNAL. No document leaves the platform without APPROVED.',
  STALE_WARNING:
    'This artefact was last computed >7 days ago. Underlying data may have changed. Recompute before sharing externally.',
  WAE_QUORUM:
    'Number of required approvers who have voted. Once quorum is met, the action is authorised. E.g., SAF_FORWARD_SALE >€500K requires Trader + Risk + Treasury.',
  CSS_HASH:
    'SHA-256 hash of the commitment content. Part of the append-only ledger. Once signed, cannot be altered without detection.',
  COUNTERSIGN:
    'The counterparty must countersign to complete the commitment. Until countersigned, the record is a unilateral declaration.',
  EXPORT_BLOCKED:
    'Export returns HTTP 409 if workflow state < APPROVED. This prevents sending incomplete or ungoverned documents to lenders.',
  SHA256_INTEGRITY:
    'SHA-256 cryptographic hash of document contents. Any modification after upload is detectable by comparing hashes.',

  // ── Covenants ──
  DSCR_COVENANT:
    'Minimum DSCR the project must maintain. Typical: 1.20x–1.30x. Breach triggers cash sweep (excess cash repays debt) or distribution lock-up (no dividends to equity).',
  DSRA_COVENANT:
    'DSRA must hold ≥6 months of forward debt service. Underfunding triggers a distribution lock-up until the reserve is replenished.',

  // ── Capital Stack ──
  GREEN_BOND_COMPARISON:
    'Taghizadeh-Hesary (2022): optimal debt mix is 56% bank loans / 44% green bonds. Green bonds price 20–30bps below bank loans for ICMA-certified frameworks.',
  BLENDED_WACC:
    'Weighted average of all capital sources: Σ(tranche_weight × tranche_cost). Target: <8% for investment-grade green fuel project.',
  LAYER_WACC:
    'Each CAPEX layer (site, electrolyser, FT, infrastructure) has its own risk spread and optimal financing. Layer-stratified approach saves 80–150bps vs flat WACC.',
} as const;
