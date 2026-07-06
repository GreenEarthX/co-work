// Screen: Static data (no screen)
/**
 * Canonical project registry for the GreenEarthX demo customer.
 * Single source of truth consumed by ProjectsPage, bankability views,
 * Dashboard, and any other feature that lists or selects projects.
 */

export interface CustomerProject {
  id: string;
  name: string;
  molecule:
    | 'H2'
    | 'NH3'
    | 'e-Methanol'
    | 'SAF'
    | 'e-NG'
    | 'e-Methane'
    | 'e-NH3'
    | 'HVO'
    | 'e-Gasoline'
    | 'e-LG'
    | 'e-Naphtha';
  location: string;
  country: string;
  lat: number;
  lng: number;
  capacity_mtpd: number;
  capex_eur: number;
  /**
   * Currency the CAPEX figure is denominated in. Decoupled from the field
   * name so users can keep the number and switch the unit without losing
   * the verification trail. Defaults to 'EUR' when absent.
   */
  capex_currency?: 'EUR' | 'USD' | 'GBP' | 'JPY' | 'CHF' | 'CAD' | 'AUD';
  status: 'development' | 'construction' | 'operating' | 'commissioning';
  phase: string;
  completion_date: string;
  description: string;
  /**
   * The producing company that owns this project.
   * Used for ABAC visibility: PRODUCER users only see projects
   * where owner_company === their company_name.
   */
  owner_company: string;
  /**
   * Third-party companies with read access (bankers, offtakers, insurers, engineers).
   * Used for ABAC visibility: THIRD_PARTY and OFFTAKER users see projects
   * where associated_companies includes their company_name.
   */
  associated_companies: string[];
  /** Absent = PROJECT_FINANCE (the legacy default). */
  financing_model?: FinancingModel;
  // Bankability snapshot (used as demo fallback when backend is unavailable)
  bankability: {
    overall_completion: number;
    gates: BankabilityGate[];
    capital_status: CapitalItem[];
    next_milestone: string;
    unlocked_capital: string[];
    /** @deprecated Legacy flat strings — use risk_flags where present. Kept in
     *  sync (risk_alerts[i] === risk_flags[i].claim) until all consumers migrate. */
    risk_alerts: string[];
    /**
     * Structured risk flags — the ABAC-governable replacement for risk_alerts.
     * Server-authoritative copy lives in backend risk_flags registry and is
     * filtered per requester (classification × stakeholding × clearance);
     * this static copy is the dev fallback only.
     */
    risk_flags?: RiskFlag[];
  };
  /** Molecule-specific regulatory and hazard gating — shown alongside standard bankability gates. */
  molecule_gating?: MoleculeGating;
  /** Structured offtake agreements — replaces unstructured description text for bankability analysis. */
  offtakes?: Offtake[];
  // ── Narrative source-of-truth fields (Option A) ────────────────────────────
  // The textarea on ProjectProfilePage is rendered from these by renderNarrative().
  // Editing the narrative is therefore disabled; the user edits these fields.
  /** Upstream renewable energy supplied to the project. */
  energy_input?: EnergyInput;
  /** Electrolyser stack — sized to convert energy_input into H₂. */
  electrolyser?: Electrolyser;
  /** Annual product output (computed from capacity_mtpd if absent). */
  capacity_kt_yr?: number;
  /** Regulatory certifications pursued or held. */
  certifications?: CertificationProgress[];
  /** Subsidies, grants, tax credits, concessional loans secured or pursued. */
  incentives?: Incentive[];
  /** Construction and production-start milestones. */
  timeline?: Timeline;
}

export interface BankabilityGate {
  id: string;
  name: string;
  completion_pct: number;
  total_evidence: number;
  verified_count: number;
  is_complete: boolean;
  blocking_items: string[];
  description: string;
}

// ─── Structured risk flags ────────────────────────────────────────────────────
// Replaces flat risk_alerts strings. Design (Hidalgo/Sung): every flag is a
// causal unit — thought (claim) → consequence (severity/owner) → way (category,
// resolved to a role-aware route in the UI). `route` is deliberately NOT stored:
// routes are presentation, categories are domain.

/** Internal business function that owns WORKING the risk (task assignment —
 *  NOT visibility; visibility is governed by `classification`). */
export type BusinessFunctionOwner =
  | 'EXECUTIVE'
  | 'FINANCE_TREASURY'
  | 'COMMERCIAL'
  | 'ENGINEERING'
  | 'OPERATIONS'
  | 'COMPLIANCE_LEGAL';

/** Semantic domain of the risk — the UI derives the role-aware route from this. */
export type RiskCategory =
  | 'capacity_claim'   // disputed/overstated production figures → Challenge Review
  | 'certification'    // 45V / RFNBO / RED III / SAF cert chains → Cert Readiness
  | 'offtake'          // counterparty, related-party, volume risk → Offtake Quality
  | 'financing'        // grants vs project finance, tax credits  → Capital Stack
  | 'site_permits'     // land, water, grid, EIA                  → Gate Evidence
  | 'insurance'        // uninsured lines, PRI                    → Insurance Schedule
  | 'supply_chain'     // feedstock dependencies                  → Offtake Quality
  | 'policy';          // pending legislation / mandates          → Cert Readiness

/** ABAC sensitivity — what the server-side filter polices. Ladder:
 *  PUBLIC < STAKEHOLDER (owner + associated companies) < CONFIDENTIAL (owner
 *  company) < RESTRICTED (owner EXEC/FINANCE only). Platform admin sees all. */
export type RiskClassification = 'PUBLIC' | 'STAKEHOLDER' | 'CONFIDENTIAL' | 'RESTRICTED';

export interface RiskFlag {
  /** Stable id — audit trail, acknowledge/waive lifecycle, cross-references. */
  id: string;
  /** The thought: what is claimed to be wrong. */
  claim: string;
  /** Impact if true. */
  severity: 'low' | 'medium' | 'high' | 'critical';
  /** How certain the claim is (public-source doctrine: impact ≠ certainty). */
  confidence: 'low' | 'medium' | 'high';
  category: RiskCategory;
  owner_function: BusinessFunctionOwner;
  classification: RiskClassification;
  /** Provenance — plural because conflicts ARE two sources disagreeing. */
  source_ids: string[];
  status: 'OPEN' | 'ACKNOWLEDGED' | 'WAIVED' | 'RESOLVED';
}

/** Commitment maturity for a capital item — distinct from evidence gate progress. */
export type CommitmentStatus =
  | 'NONE'          // No engagement yet
  | 'INDICATIVE'    // Indicative terms or LOI received
  | 'TERM_SHEET'    // Signed term sheet
  | 'CREDIT_APPROVED' // Internal credit committee approval granted
  | 'LEGAL_COMPLETE'  // Legal documentation signed
  | 'DRAWN';        // Capital drawn

export interface CapitalItem {
  type: string;
  name: string;
  amount: string;
  is_unlocked: boolean;
  gating_gates: string[];
  progress_pct: number;
  /** Lender/investor commitment maturity — NOT the same as gate evidence progress. */
  commitment_status: CommitmentStatus;
}

/**
 * Molecule-specific regulatory and hazard gating fields.
 * Surfaced on the Bankability Status page alongside standard gates.
 */
export interface MoleculeGating {
  /** NH3 only: HAZOP/HAZID study completed and signed off */
  hazop_completed?: boolean;
  /** NH3 only: Seveso III / COMAH tier declared and notified */
  seveso_tier?: 'LOWER' | 'UPPER' | 'PENDING' | null;
  /** NH3 only: Terminal operator interface agreement signed */
  terminal_interface_signed?: boolean;
  /** SAF only: Fischer-Tropsch / HEFA process hazard review completed */
  process_hazard_review?: boolean;
  /** SAF only: ASTM D7566 feedstock and blend certification status */
  astm_cert_status?: 'NONE' | 'IN_PROGRESS' | 'CERTIFIED';
  /** All: NH3/H2/SAF-specific insurance line (CAR/Marine/Liability) placed */
  molecule_insurance_placed?: boolean;
}

// ── Offtake Binding Status ──────────────────────────────────────────────────

export type OfftakeBindingStatus =
  | 'BINDING'       // Fully executed, legally binding contract
  | 'TERM_SHEET'    // Signed term sheet / heads of terms
  | 'LOI'           // Letter of intent
  | 'MOU'           // Memorandum of understanding
  | 'INDICATIVE';   // Indicative / non-binding expression of interest

export type OfftakeVerification =
  | 'UNVERIFIED'
  | 'SUBMITTED'
  | 'CONFIRMED'
  | 'CONTRADICTED';

export interface Offtake {
  party: string;
  binding_status: OfftakeBindingStatus;
  is_related_party: boolean;
  volume_tpy: number | null;
  term_years: number | null;
  price_type: 'FIXED' | 'INDEX_LINKED' | 'UNDISCLOSED' | null;
  delivery_start: string | null;
  verification: OfftakeVerification;
  verification_source?: string;
  notes?: string;
}

// ── Narrative-feeding structured fields ─────────────────────────────────────
// Source of truth for the project narrative. The textarea on ProjectProfile
// is a derived view rendered from these fields — never a free-text input
// that diverges from the database (Hidalgo causal compression).

/**
 * Grid topology of the power supply — drives WHICH evidence G1 demands and
 * whether PPAs are structurally required:
 *  - OFF_GRID_BTM:    dedicated behind-the-meter generation, no grid import.
 *                     Evidence = grid-independence note + supply adequacy.
 *                     PPAs NOT required (generation is owned).
 *  - GRID_CONNECTED:  electrolyser draws from the grid. Evidence =
 *                     interconnection + ≥1 PPA, else electricity price risk
 *                     is unhedged (and RFNBO/45V additionality is at risk).
 *  - HYBRID:          BTM primary + grid import/export. PPA(s) required for
 *                     the grid-imported share.
 */
export type PowerModel = 'OFF_GRID_BTM' | 'GRID_CONNECTED' | 'HYBRID';

/**
 * Financing model. PROJECT_FINANCE = SPV with external debt — all 12 gates
 * apply. BALANCE_SHEET = corporate / prosumer funding from own balance sheet —
 * lender-protection gates (G4 offtake, G6 IE, G7 insurance, G8 model audit,
 * G10 financial close) are out of scope and waived by the engine.
 */
export type FinancingModel = 'PROJECT_FINANCE' | 'BALANCE_SHEET';

/** Power purchase agreement — the hedge that makes on-grid electricity bankable. */
export interface PPA {
  counterparty: string;
  /**
   * THIRD_PARTY = market PPA (default). INTERNAL_AFFILIATE = sleeved supply
   * from the owner's own generation portfolio — the prosumer structure.
   * Internal supply hedges price but demands transfer-pricing / sleeving
   * governance evidence instead of a market contract.
   */
  counterparty_type?: 'THIRD_PARTY' | 'INTERNAL_AFFILIATE';
  volume_mw: number;
  /** €/MWh — null when commercially confidential (existence still counts). */
  price_eur_mwh?: number | null;
  tenor_years: number;
  status: 'SIGNED' | 'TERM_SHEET' | 'LOI' | 'NEGOTIATION';
  type?: 'PHYSICAL' | 'VIRTUAL' | 'SLEEVED';
}

export interface EnergyInput {
  power_mw: number;                  // upstream renewable capacity
  source: 'wind' | 'solar' | 'hybrid' | 'hydro' | 'nuclear' | 'grid';
  /** On/off-grid topology. Absent = not yet declared (itself a data gap). */
  power_model?: PowerModel;
  /** Required (≥1) when power_model is GRID_CONNECTED or HYBRID. */
  ppas?: PPA[];
  /** HYBRID split: grid-imported share of load (MW). PPA coverage is judged
   *  against THIS, not total plant load — the BTM share needs no PPA. */
  grid_import_mw?: number;
  /** HYBRID split: owned BTM generation (MW). */
  btm_generation_mw?: number;
  curtailment_share_pct?: number;    // optional, for hybrids
}

export interface Electrolyser {
  capacity_mw: number;
  technology: 'PEM' | 'AEM' | 'SOEC' | 'alkaline';
  oem?: string;                       // e.g. "John Cockerill"
}

export type CertificationStatus =
  | 'ACTIVE'                          // certification granted and in force
  | 'UNDER_REVIEW'                    // application under regulatory review
  | 'PRE-ASSESSMENT'                  // gap analysis in progress
  | 'INTENDED'                        // declared target, not yet started
  | 'WITHDRAWN';

export interface CertificationProgress {
  scheme: '45V' | 'RFNBO' | 'GoO' | 'ISCC' | 'FuelEU_Maritime' | 'CORSIA' | 'ASTM_D7566' | 'RED_III';
  status: CertificationStatus;
  tier?: string;                      // e.g. "Tier 1", "Tier 2"
  note?: string;                      // e.g. "temporal correlation review"
}

export type IncentiveKind =
  | 'IRA_45V'                         // US production tax credit
  | 'IRA_45Q'                         // US carbon-capture credit
  | 'IRA_GRANT'                       // US Inflation Reduction Act grant
  | 'EU_INNOVATION_FUND'
  | 'EU_HYDROGEN_BANK'
  | 'BPIFRANCE'
  | 'KFW_GRANT'
  | 'DOE_LPO'                         // US Department of Energy Loan Programs Office
  | 'OTHER';

export interface Incentive {
  kind: IncentiveKind;
  amount_eur?: number | null;          // absolute amount, EUR
  amount_usd?: number | null;          // absolute amount, USD (one of the two)
  status: 'SECURED' | 'AWARDED' | 'APPLIED' | 'INTENDED' | 'DECLINED';
  note?: string;
}

export interface Timeline {
  construction_start_year?: number;    // FID-funded works begin
  production_start_year?: number;      // first product to spec
}

export const CUSTOMER_PROJECTS: CustomerProject[] = [
  // ── 0 · e-Methanol · West Texas (ETFuels Rattlesnake Gap — demo anchor) ──
  // Verification report 2026-05-21: corrected Status, capacity, COD, added RFOcean offtake
  {
    id: 'proj_etf_pecos1',
    name: 'ETFuels Rattlesnake Gap',
    molecule: 'e-Methanol',
    location: 'West Texas',
    country: 'US',
    lat: 31.42,
    lng: -103.49,
    capacity_mtpd: 329,
    capex_eur: 562000000,
    capex_currency: 'USD',
    status: 'development',
    phase: 'FEED Class 3 — Structurally Bankable',
    completion_date: '2030-06-30',
    description:
      '340 MW wind → 150 MW PEM electrolysis → 120,000 t/yr e-methanol. ' +
      'Primary offtake: RFOcean (binding 10-year fixed-price from 2030, bankable contract). ' +
      'Secondary: ETFuels SA (5-year ToP, 70,000 t/yr, CIF Rotterdam — related-party, unverified). ' +
      'Indicative: Lufthansa Cargo SAF pool (30,000 t/yr — non-binding). ' +
      'Certification: 45V active (Tier 1 pathway), RFNBO under temporal correlation review. ' +
      'IRA incentives: ~$1.5B secured. Construction start 2027, production 2030.',
    owner_company: 'ETFuels SA',
    associated_companies: ['ING Capital', 'BNP Paribas CIB', 'RFOcean', 'Maersk Decarbonization'],
    offtakes: [
      {
        party: 'RFOcean',
        binding_status: 'BINDING',
        is_related_party: false,
        volume_tpy: null,
        term_years: 10,
        price_type: 'FIXED',
        delivery_start: '2030-01-01',
        verification: 'CONFIRMED',
        verification_source: '10 public sources (Feb–Mar 2026), CEO quotes',
        notes: 'Binding 10-year fixed-price. Structured to support project finance. Volume undisclosed but material. 8 methanol-ready tankers on order.',
      },
      {
        party: 'ETFuels SA',
        binding_status: 'MOU',
        is_related_party: true,
        volume_tpy: 70000,
        term_years: 5,
        price_type: 'UNDISCLOSED',
        delivery_start: '2030-01-01',
        verification: 'UNVERIFIED',
        notes: 'Related-party (owner = offtaker). 5-year ToP, CIF Rotterdam. Not in public sources — may be aspirational or for a different facility.',
      },
      {
        party: 'Lufthansa Cargo SAF Pool',
        binding_status: 'INDICATIVE',
        is_related_party: false,
        volume_tpy: 30000,
        term_years: null,
        price_type: 'UNDISCLOSED',
        delivery_start: null,
        verification: 'UNVERIFIED',
        notes: 'Indicative / non-binding expression of interest. Not in public sources.',
      },
    ],
    // Narrative-feeding structured fields (Option A — Hidalgo causal compression)
    // Off-grid behind-the-meter per public sources (500 MW wind+solar, grid-
    // independent design) — no PPAs required: generation is owned, not bought.
    energy_input: { power_mw: 340, source: 'wind', power_model: 'OFF_GRID_BTM', ppas: [] },
    electrolyser: { capacity_mw: 150, technology: 'PEM' },
    capacity_kt_yr: 120,
    certifications: [
      { scheme: '45V',   status: 'ACTIVE',       tier: 'Tier 1' },
      { scheme: 'RFNBO', status: 'UNDER_REVIEW', note: 'temporal correlation review' },
    ],
    incentives: [
      { kind: 'IRA_45V', amount_usd: 1_500_000_000, status: 'SECURED', note: 'IRA-aggregate' },
    ],
    timeline: { construction_start_year: 2027, production_start_year: 2030 },
    bankability: {
      overall_completion: 58,
      next_milestone: 'Resolve capacity discrepancy (GEX 165k vs public 120k t/yr) → then complete G4 credit support',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'Capacity discrepancy: GEX showed 165k t/yr, public sources confirm 120k t/yr (27% overstatement corrected)',
        '45V temporal matching rule: IRS guidance still pending — annual vs hourly conflict with RFNBO',
        'ETFuels SA offtake (70k t/yr) is related-party — lenders may discount or exclude from bankability',
      ],
      risk_flags: [
        {
          id: 'rf_etf_pecos1_capacity_overstatement',
          claim: 'Capacity discrepancy: GEX showed 165k t/yr, public sources confirm 120k t/yr (27% overstatement corrected)',
          severity: 'high',
          confidence: 'high',
          category: 'capacity_claim',
          owner_function: 'COMMERCIAL',
          classification: 'STAKEHOLDER',
          source_ids: ['SRC_ETFUELS_OUR_SOLUTION_2026', 'SRC_ARGUS_RFOCEAN_2026_02_24', 'SRC_CARBONSTORAGE_RATTLESNAKE'],
          status: 'ACKNOWLEDGED',
        },
        {
          id: 'rf_etf_pecos1_45v_temporal',
          claim: '45V temporal matching rule: IRS guidance still pending — annual vs hourly conflict with RFNBO',
          severity: 'high',
          confidence: 'medium',
          category: 'certification',
          owner_function: 'COMPLIANCE_LEGAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_RATTLESNAKE_FEED_2025_10_27'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_pecos1_related_party_offtake',
          claim: 'ETFuels SA offtake (70k t/yr) is related-party — lenders may discount or exclude from bankability',
          severity: 'critical',
          confidence: 'high',
          category: 'offtake',
          owner_function: 'FINANCE_TREASURY',
          classification: 'STAKEHOLDER',
          source_ids: ['SRC_GEX_INTERNAL_OFFTAKE_REVIEW'],
          status: 'OPEN',
        },
      ],
      gates: [
        {
          id: 'G0_SITE_RIGHTS',
          name: 'Site Rights & Land Access',
          completion_pct: 100,
          total_evidence: 4,
          verified_count: 4,
          is_complete: true,
          blocking_items: [],
          description: 'Surface rights, mineral rights waiver, access road easements',
        },
        {
          id: 'G1_GRID_UTILITIES_REALITY',
          name: 'Power, Water & Critical Utility Access',
          // Off-grid BTM: 8 applicable items (BTM generation + curtailment/
          // dispatch + water). Grid-access and PPA items are N/A by power
          // model — NO ERCOT generation interconnect unless surplus export
          // is pursued (legacy grid-connected premise corrected 2026-06-11).
          completion_pct: 75,
          total_evidence: 8,
          verified_count: 6,
          is_complete: false,
          blocking_items: ['grid_independence_note', 'backup_construction_power_plan'],
          description:
            'OFF_GRID_BTM · 500 MW wind+solar — generation asset ✓, P90 yield study ✓, water ✓. ' +
            'Blocking: grid-independence design note, backup/construction power plan.',
        },
        {
          id: 'G3_INPUTS_SECURED',
          name: 'Technology Vendor Locked',
          completion_pct: 75,
          total_evidence: 4,
          verified_count: 3,
          is_complete: false,
          blocking_items: ['EPC_LUMP_SUM_SIGNED'],
          description: 'PEM electrolyser OEM selection, EPC contract, technology wrap',
        },
        {
          id: 'G4_OFFTAKE_BANKABLE',
          name: 'Bankable Offtake Agreement',
          completion_pct: 78,
          total_evidence: 8,
          verified_count: 6,
          is_complete: false,
          blocking_items: ['CREDIT_SUPPORT_POSTED'],
          description:
            'RFOcean: binding 10-year fixed-price (CONFIRMED, bankable contract from 2030). ' +
            'ETFuels SA: 70k t/yr 5-year ToP (related-party, UNVERIFIED). ' +
            'Lufthansa Cargo: 30k t/yr indicative (non-binding).',
        },
        {
          id: 'G7_INSURANCE_BOUND',
          name: 'Insurance Programme Bound',
          completion_pct: 40,
          total_evidence: 5,
          verified_count: 2,
          is_complete: false,
          blocking_items: ['CAR_EAR_POLICY_BOUND', 'DSU_POLICY_BOUND'],
          description: 'CAR/EAR, DSU, BI, and marine cargo insurance lines',
        },
        {
          id: 'G8_AUDIT_GRADE_MODEL',
          name: 'Audit-Grade Financial Model',
          completion_pct: 45,
          total_evidence: 4,
          verified_count: 2,
          is_complete: false,
          blocking_items: ['INDEPENDENT_MODEL_AUDIT', 'LENDER_TECHNICAL_ADVISOR_SIGN_OFF'],
          description: 'IEA-compliant CFADS model, DSCR stress test, audited by Deloitte PF',
        },
        {
          id: 'G10_FINANCIAL_CLOSE_CP',
          name: 'Financial Close Conditions Precedent',
          completion_pct: 20,
          total_evidence: 8,
          verified_count: 2,
          is_complete: false,
          blocking_items: ['SENIOR_DEBT_COMMITMENT_LETTER', 'EQUITY_FUNDING_CONFIRMATION'],
          description: 'All CPs for financial close — requires G4, G7, G8 complete',
        },
        {
          id: 'G11_COD_STABILIZATION',
          name: 'GHG Pathway Verified',
          completion_pct: 72,
          total_evidence: 5,
          verified_count: 4,
          is_complete: false,
          blocking_items: ['RFNBO_TEMPORAL_CORRELATION_DECLARATION'],
          description:
            '45V Tier 1 LCA (0.42 kgCO₂e/MJ H₂) — DNV pre-audit complete. RFNBO hourly matching review pending.',
        },
      ],
      capital_status: [
        {
          type: 'GRANTS_TA',
          name: 'DOE H2Hubs Grant (TA component)',
          amount: '$18M',
          is_unlocked: true,
          gating_gates: [],
          progress_pct: 100,
          commitment_status: 'DRAWN',
        },
        {
          type: 'SEED_VC_ANGEL',
          name: 'Development Equity',
          amount: '$32M',
          is_unlocked: true,
          gating_gates: [],
          progress_pct: 100,
          commitment_status: 'DRAWN',
        },
        {
          type: 'STRATEGIC_EQUITY',
          name: 'Strategic Equity (ING / BNP)',
          amount: '$130M',
          is_unlocked: false,
          gating_gates: ['G4_OFFTAKE_BANKABLE'],
          progress_pct: 55,
          commitment_status: 'INDICATIVE',
        },
        {
          type: 'SENIOR_DEBT_COMMITMENT',
          name: 'Senior Debt — MLA Club',
          amount: '$420M',
          is_unlocked: false,
          gating_gates: ['G6_IE_SIGNOFF', 'G7_INSURANCE_BOUND', 'G8_AUDIT_GRADE_MODEL'],
          progress_pct: 33,
          commitment_status: 'NONE',
        },
        {
          type: 'ECA',
          name: 'US EXIM / OPIC Coverage',
          amount: '$120M',
          is_unlocked: false,
          gating_gates: ['G5_EPC_RISK_PRICED', 'G6_IE_SIGNOFF'],
          progress_pct: 20,
          commitment_status: 'NONE',
        },
      ],
    },
  },
  // ── 0b · e-Methanol · West Texas (ETFuels — Rattlesnake Gap) ─────────────
  {
    id: 'etfuels_us_tx_rattlesnake_gap',
    name: 'Rattlesnake Gap',
    molecule: 'e-Methanol',
    location: 'West Texas (Christoval / Schleicher County)',
    country: 'US',
    lat: 31.20,
    lng: -100.50,
    capacity_mtpd: 342,
    capex_eur: 0,
    status: 'development',
    phase: 'FEED underway — FID target end-2026',
    completion_date: '2030-03-31',
    description:
      '500 MW behind-the-meter wind+solar → John Cockerill electrolyser → Johnson Matthey eMERALD → ' +
      '125,000 t/yr e-methanol (conflict: 120,000 t/yr in older sources). ' +
      'FEED engineer: S&B Engineers and Constructors. ' +
      'Offtake: RFOcean binding long-term fixed-price from 2030 (FuelEU Maritime driver; volume not public). ' +
      'CAPEX not publicly disclosed. Public-source seed — not bankable evidence.',
    owner_company: 'ETFuels SA',
    associated_companies: [],
    // Import pack: power_model "behind_the_meter_off_grid_or_grid_independent",
    // 500 MW wind+solar — owned generation, no PPAs required.
    energy_input: { power_mw: 500, source: 'hybrid', power_model: 'OFF_GRID_BTM', ppas: [] },
    bankability: {
      overall_completion: 35,
      next_milestone: 'Complete FEED package and secure FID (target end-2026)',
      unlocked_capital: [],
      risk_alerts: [
        'Capacity conflict: 125 kt (company current) vs 120 kt (trade press / third-party DB)',
        'Electrolyser MW conflict: 220 MW (Argus 2024) vs 500 MW (CarbonStorage DB)',
        '45V qualification not automatic — IRS guidance pending',
        'Offtake volume with RFOcean not publicly disclosed',
      ],
      risk_flags: [
        {
          id: 'rf_etf_rsg_capacity_conflict',
          claim: 'Capacity conflict: 125 kt (company current) vs 120 kt (trade press / third-party DB)',
          severity: 'medium',
          confidence: 'high',
          category: 'capacity_claim',
          owner_function: 'FINANCE_TREASURY',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_OUR_SOLUTION_2026', 'SRC_ARGUS_RFOCEAN_2026_02_24', 'SRC_CARBONSTORAGE_RATTLESNAKE'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_rsg_electrolyser_mw_conflict',
          claim: 'Electrolyser MW conflict: 220 MW (Argus 2024) vs 500 MW (CarbonStorage DB)',
          severity: 'high',
          confidence: 'medium',
          category: 'site_permits',
          owner_function: 'ENGINEERING',
          classification: 'PUBLIC',
          source_ids: ['SRC_ARGUS_2024_PIPELINE', 'SRC_CARBONSTORAGE_RATTLESNAKE'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_rsg_45v_qualification',
          claim: '45V qualification not automatic — IRS guidance pending',
          severity: 'high',
          confidence: 'medium',
          category: 'certification',
          owner_function: 'COMPLIANCE_LEGAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_RATTLESNAKE_FEED_2025_10_27', 'SRC_ARGUS_RFOCEAN_2026_02_24'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_rsg_offtake_volume_private',
          claim: 'Offtake volume with RFOcean not publicly disclosed',
          severity: 'medium',
          confidence: 'high',
          category: 'offtake',
          owner_function: 'COMMERCIAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_RFOCEAN_2026_02_24', 'SRC_ARGUS_RFOCEAN_2026_02_24'],
          status: 'OPEN',
        },
      ],
      gates: [
        {
          id: 'G0_SITE_RIGHTS',
          name: 'Site Rights & Land Access',
          completion_pct: 30,
          total_evidence: 4,
          verified_count: 1,
          is_complete: false,
          blocking_items: ['LAND_CONTROL_EVIDENCE', 'WATER_RIGHTS'],
          description: 'West Texas site — land control and water rights evidence required',
        },
        {
          id: 'G1_GRID_UTILITIES_REALITY',
          name: 'Power, Water & Critical Utility Access',
          // Off-grid BTM: 8 applicable items — grid/PPA tracks N/A by power model.
          completion_pct: 25,
          total_evidence: 8,
          verified_count: 2,
          is_complete: false,
          blocking_items: ['btm_generation_asset_evidence', 'generation_yield_study', 'grid_independence_note', 'water_permit_pathway_memo'],
          description: 'OFF_GRID_BTM — BTM generation asset spec, P90 yield study, grid-independence note and water permit pathway outstanding',
        },
        {
          id: 'G3_INPUTS_SECURED',
          name: 'Technology Vendor Locked',
          completion_pct: 60,
          total_evidence: 5,
          verified_count: 3,
          is_complete: false,
          blocking_items: ['ELECTROLYSER_SUPPLY_AGREEMENT', 'METHANOL_TECH_LICENCE'],
          description: 'John Cockerill electrolyser + JM eMERALD selected; S&B FEED engineer; supply agreements pending',
        },
        {
          id: 'G4_OFFTAKE_BANKABLE',
          name: 'Bankable Offtake Agreement',
          completion_pct: 45,
          total_evidence: 5,
          verified_count: 2,
          is_complete: false,
          blocking_items: ['OFFTAKE_REDACTED_TERMS', 'VOLUME_COMMITMENT'],
          description: 'RFOcean binding fixed-price from 2030 — volume and redacted terms not yet filed',
        },
        {
          id: 'G11_COD_STABILIZATION',
          name: 'GHG Pathway Verified',
          completion_pct: 20,
          total_evidence: 4,
          verified_count: 1,
          is_complete: false,
          blocking_items: ['45V_RFNBO_PRE_ASSESSMENT', 'FUELEU_COMPLIANCE_NOTE'],
          description: '45V + RFNBO + FuelEU Maritime certification targets — pre-assessment required',
        },
      ],
      capital_status: [
        {
          type: 'GRANTS_TA',
          name: 'IRA / 45V Stack (potential)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G0_SITE_RIGHTS'],
          progress_pct: 20,
          commitment_status: 'NONE',
        },
        {
          type: 'SEED_VC_ANGEL',
          name: 'Development Equity',
          amount: 'Undisclosed',
          is_unlocked: true,
          gating_gates: [],
          progress_pct: 100,
          commitment_status: 'DRAWN',
        },
        {
          type: 'SENIOR_DEBT_COMMITMENT',
          name: 'Senior Debt (not yet structured)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G6_IE_SIGNOFF', 'G7_INSURANCE_BOUND', 'G8_AUDIT_GRADE_MODEL'],
          progress_pct: 10,
          commitment_status: 'NONE',
        },
      ],
    },
  },

  // ── 0c · e-Methanol · Ranua, Finland (ETFuels — Näätäaapa) ─────────────
  {
    id: 'etfuels_fi_ranua_naataaapa',
    name: 'Ranua Näätäaapa e-Methanol',
    molecule: 'e-Methanol',
    location: 'Ranua, Lapland',
    country: 'FI',
    lat: 65.93,
    lng: 26.13,
    capacity_mtpd: 301,
    capex_eur: 800_000_000,
    status: 'development',
    phase: 'Pre-FEED — tax credit awarded',
    completion_date: '2031-12-31',
    description:
      '300 MW wind → renewable H₂ → e-methanol. ' +
      '110,000 t/yr (conflict: 100,000 t/yr in legacy sources). ' +
      'Biogenic CO₂ from Finnish industrial/forestry value chain (counterparty not public). ' +
      '€118.6M Business Finland Clean Transition Tax Credit awarded (20% cap on eligible CAPEX). ' +
      'Legacy total investment reported €800M (low confidence). Public-source seed — not bankable evidence.',
    owner_company: 'ETFuels SA',
    associated_companies: [],
    energy_input: { power_mw: 300, source: 'wind', power_model: 'OFF_GRID_BTM', ppas: [] },
    bankability: {
      overall_completion: 22,
      next_milestone: 'Secure land control and wind power evidence; begin RFNBO pre-assessment',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'Capacity conflict: 110 kt (tax credit release) vs 100 kt (legacy page)',
        'Tax credit is NOT a cash grant — depends on tax eligibility and utilisation',
        'Offtake not publicly disclosed',
        'CO₂ counterparty not public — certification risk',
      ],
      risk_flags: [
        {
          id: 'rf_etf_ranua_capacity_conflict',
          claim: 'Capacity conflict: 110 kt (tax credit release) vs 100 kt (legacy page)',
          severity: 'medium',
          confidence: 'high',
          category: 'capacity_claim',
          owner_function: 'FINANCE_TREASURY',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23', 'SRC_ETFUELS_OLD_PROJECTS'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_ranua_tax_credit_not_cash',
          claim: 'Tax credit is NOT a cash grant — depends on tax eligibility and utilisation',
          severity: 'high',
          confidence: 'high',
          category: 'financing',
          owner_function: 'FINANCE_TREASURY',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_ranua_offtake_private',
          claim: 'Offtake not publicly disclosed',
          severity: 'medium',
          confidence: 'high',
          category: 'offtake',
          owner_function: 'COMMERCIAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_ranua_co2_counterparty',
          claim: 'CO₂ counterparty not public — certification risk',
          severity: 'medium',
          confidence: 'medium',
          category: 'certification',
          owner_function: 'COMPLIANCE_LEGAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_FINLAND_TAX_CREDIT_2026_02_23', 'SRC_ETFUELS_OLD_PROJECTS'],
          status: 'OPEN',
        },
      ],
      gates: [
        {
          id: 'G0_SITE_RIGHTS',
          name: 'Site Rights & Land Access',
          completion_pct: 25,
          total_evidence: 4,
          verified_count: 1,
          is_complete: false,
          blocking_items: ['LAND_CONTROL', 'PERMITTING_STATUS'],
          description: 'Ranua / Näätäaapa site — land control and Finnish permitting required',
        },
        {
          id: 'G1_GRID_UTILITIES_REALITY',
          name: 'Power, Water & Critical Utility Access',
          // Off-grid BTM: 8 applicable items — grid/PPA tracks N/A by power model.
          completion_pct: 13,
          total_evidence: 8,
          verified_count: 1,
          is_complete: false,
          blocking_items: ['btm_generation_asset_evidence', 'generation_yield_study', 'backup_construction_power_plan', 'water_source_plan'],
          description: 'OFF_GRID_BTM — 300 MW wind BTM: generation asset evidence, yield study, backup power and water source plan outstanding',
        },
        {
          id: 'G3_INPUTS_SECURED',
          name: 'Technology Vendor Locked',
          completion_pct: 15,
          total_evidence: 4,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['ELECTROLYSER_SELECTION', 'CO2_SUPPLY_CONTRACT'],
          description: 'Renewable-hydrogen-based e-methanol — technology details sparse in public domain',
        },
        {
          id: 'G4_OFFTAKE_BANKABLE',
          name: 'Bankable Offtake Agreement',
          completion_pct: 0,
          total_evidence: 5,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['OFFTAKE_NOT_PUBLIC'],
          description: 'Target: European maritime + industrial — no offtake publicly disclosed',
        },
        {
          id: 'G11_COD_STABILIZATION',
          name: 'GHG Pathway Verified',
          completion_pct: 10,
          total_evidence: 4,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['RFNBO_PRE_ASSESSMENT', 'RED_III_COMPLIANCE'],
          description: 'EU RFNBO + RED III + FuelEU Maritime + Finnish clean transition targets',
        },
      ],
      capital_status: [
        {
          type: 'GRANTS_TA',
          name: 'Business Finland Tax Credit',
          amount: '€118.6M (max)',
          is_unlocked: true,
          gating_gates: [],
          progress_pct: 100,
          commitment_status: 'CREDIT_APPROVED',
        },
        {
          type: 'STRATEGIC_EQUITY',
          name: 'Strategic Equity (not yet structured)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G4_OFFTAKE_BANKABLE'],
          progress_pct: 0,
          commitment_status: 'NONE',
        },
        {
          type: 'SENIOR_DEBT_COMMITMENT',
          name: 'Senior Debt (not yet structured)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G6_IE_SIGNOFF', 'G7_INSURANCE_BOUND', 'G8_AUDIT_GRADE_MODEL'],
          progress_pct: 0,
          commitment_status: 'NONE',
        },
      ],
    },
  },

  // ── 0d · SAF · Redcar, UK (ETFuels — SkyFuel Teesside) ─────────────────
  {
    id: 'etfuels_uk_skyfuel_teesside',
    name: 'Project SkyFuel Teesside',
    molecule: 'SAF',
    location: 'Redcar, Teesside',
    country: 'GB',
    lat: 54.62,
    lng: -1.07,
    capacity_mtpd: 90,
    capex_eur: 0,
    status: 'development',
    phase: 'AFF-supported development — FEED progressing',
    completion_date: '2032-12-31',
    description:
      'e-SAF via Methanol-to-Jet pathway. 33,000 t/yr e-SAF. ' +
      'Technology partners: Johnson Matthey + Protium (green H₂). ' +
      'Biogenic CO₂ feedstock. £5M UK Advanced Fuels Fund grant awarded. ' +
      'Feedstock linked to ETFuels global e-methanol pipeline. ' +
      'CAPEX not publicly disclosed. Public-source seed — not bankable evidence.',
    owner_company: 'ETFuels SA',
    associated_companies: [],
    // Green H₂ via Protium partnership; ETFuels off-grid BTM model assumed
    // for the power premise (public-source seed).
    energy_input: { power_mw: 0, source: 'wind', power_model: 'OFF_GRID_BTM', ppas: [] },
    bankability: {
      overall_completion: 18,
      next_milestone: 'Secure Teesside land control and green H₂ partnership contract',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'AFF grant is development support only — not full project finance',
        'UK Revenue Certainty Mechanism details still developing (legislation May 2026)',
        'Feedstock dependency on external e-methanol pipeline (TX/FI)',
        'SAF testing/certification/distribution chain required',
      ],
      risk_flags: [
        {
          id: 'rf_etf_skyfuel_aff_dev_support',
          claim: 'AFF grant is development support only — not full project finance',
          severity: 'high',
          confidence: 'high',
          category: 'financing',
          owner_function: 'FINANCE_TREASURY',
          classification: 'PUBLIC',
          source_ids: ['SRC_GOVUK_AFF_WINNERS_2025_07_22', 'SRC_RICARDO_AFF'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_skyfuel_rcm_developing',
          claim: 'UK Revenue Certainty Mechanism details still developing (legislation May 2026)',
          severity: 'high',
          confidence: 'medium',
          category: 'policy',
          owner_function: 'COMPLIANCE_LEGAL',
          classification: 'PUBLIC',
          source_ids: ['SRC_UK_SAF_TASK_FINISH_2026_04_27'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_skyfuel_feedstock_dependency',
          claim: 'Feedstock dependency on external e-methanol pipeline (TX/FI)',
          severity: 'medium',
          confidence: 'high',
          category: 'supply_chain',
          owner_function: 'OPERATIONS',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_OUR_SOLUTION_2026', 'SRC_ETFUELS_OLD_PROJECTS'],
          status: 'OPEN',
        },
        {
          id: 'rf_etf_skyfuel_saf_cert_chain',
          claim: 'SAF testing/certification/distribution chain required',
          severity: 'medium',
          confidence: 'high',
          category: 'certification',
          owner_function: 'OPERATIONS',
          classification: 'PUBLIC',
          source_ids: ['SRC_ETFUELS_SKYFUEL_GRANT_2025_07_23'],
          status: 'OPEN',
        },
      ],
      gates: [
        {
          id: 'G0_SITE_RIGHTS',
          name: 'Site Rights & Land Access',
          completion_pct: 20,
          total_evidence: 4,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['TEESSIDE_LAND_CONTROL'],
          description: 'Redcar site — land control evidence required',
        },
        {
          id: 'G3_INPUTS_SECURED',
          name: 'Technology Vendor Locked',
          completion_pct: 35,
          total_evidence: 5,
          verified_count: 1,
          is_complete: false,
          blocking_items: ['MtJ_TECHNOLOGY_LICENCE', 'GREEN_H2_PARTNERSHIP_CONTRACT', 'CO2_CONTRACT'],
          description: 'Johnson Matthey MtJ + Protium H₂ — partnership contracts pending',
        },
        {
          id: 'G4_OFFTAKE_BANKABLE',
          name: 'Bankable Offtake Agreement',
          completion_pct: 0,
          total_evidence: 5,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['OFFTAKE_NOT_PUBLIC', 'BLENDING_ROUTE'],
          description: 'Target: UK + EU aviation — no offtake publicly disclosed',
        },
        {
          id: 'G11_COD_STABILIZATION',
          name: 'GHG / SAF Certification',
          completion_pct: 15,
          total_evidence: 5,
          verified_count: 0,
          is_complete: false,
          blocking_items: ['SAF_CERTIFICATION_PATHWAY', 'ASTM_BLENDING', 'RCM_ELIGIBILITY'],
          description: 'UK SAF Mandate + Revenue Certainty Mechanism + CORSIA + ASTM approval chain',
        },
      ],
      capital_status: [
        {
          type: 'GRANTS_TA',
          name: 'UK Advanced Fuels Fund',
          amount: '£5M',
          is_unlocked: true,
          gating_gates: [],
          progress_pct: 100,
          commitment_status: 'DRAWN',
        },
        {
          type: 'STRATEGIC_EQUITY',
          name: 'Strategic Equity (not yet structured)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_INPUTS_SECURED'],
          progress_pct: 0,
          commitment_status: 'NONE',
        },
        {
          type: 'SENIOR_DEBT_COMMITMENT',
          name: 'Senior Debt (not yet structured)',
          amount: 'TBD',
          is_unlocked: false,
          gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_INPUTS_SECURED'],
          progress_pct: 0,
          commitment_status: 'NONE',
        },
      ],
    },
    molecule_gating: {
      process_hazard_review: false,
      astm_cert_status: 'NONE',
      molecule_insurance_placed: false,
    },
  },

  // ── 1 · H2 · Bremen, Germany ─────────────────────────────────────────────
  {
    id: 'proj_bremen_h2',
    name: 'Bremen Green Hydrogen Plant',
    molecule: 'H2',
    location: 'Bremen, Germany',
    country: 'DE',
    lat: 53.0793,
    lng: 8.8017,
    capacity_mtpd: 85,
    capex_eur: 220_000_000,
    status: 'construction',
    phase: 'Pre-COD / late construction',
    completion_date: '2026-09-30',
    description: 'PEM electrolysis plant fed by North Sea offshore wind PPAs. Primary offtake: industrial H2 for port decarbonisation and heavy transport.',
    owner_company: 'HeliosNord GmbH',
    associated_companies: ['Allianz', 'Siemens Energy'],
    // Grid-connected: electricity bought via PPA (the description's "fed by
    // North Sea offshore wind PPAs") — on-grid REQUIRES ≥1 PPA to be bankable.
    energy_input: {
      power_mw: 200,
      source: 'wind',
      power_model: 'GRID_CONNECTED',
      ppas: [
        { counterparty: 'North Sea OWF Consortium', volume_mw: 200, price_eur_mwh: null, tenor_years: 15, status: 'SIGNED', type: 'PHYSICAL' },
      ],
    },
    bankability: {
      overall_completion: 74,
      next_milestone: 'Finalise grid connection agreement (G1) to unlock Strategic Equity',
      unlocked_capital: ['GRANTS_TA', 'SEED_VC_ANGEL'],
      risk_alerts: ['Grid connection agreement still pending utility sign-off'],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',      completion_pct: 100, total_evidence: 4, verified_count: 4, is_complete: true,  blocking_items: [],                             description: 'Land title and environmental permits' },
        { id: 'G1_GRID_UTILITIES_REALITY',       name: 'Power, Water & Critical Utility Access', completion_pct: 58,  total_evidence: 12, verified_count: 7, is_complete: false, blocking_items: ['grid_connection_cost_estimate', 'connection_date_cod_compatibility_memo', 'ppa_volume_load_coverage_analysis', 'ppa_tenor_debt_comparison', 'dispatch_load_factor_production_impact'], description: 'Grid-connected: PPA signed ✓ · interconnection study ✓ · queue position ✓ · curtailment assessed. Blocking: connection cost, COD compatibility, PPA coverage analysis' },
        { id: 'G5_EPC_RISK_PRICED',      name: 'EPC Risk Assessed',        completion_pct: 80,  total_evidence: 5, verified_count: 4, is_complete: false, blocking_items: ['performance_guarantees'],     description: 'Fixed-price EPC contract with performance guarantees' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€12M',  is_unlocked: true,  gating_gates: [],                                               progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€18M',  is_unlocked: true,  gating_gates: [],                                               progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€55M',  is_unlocked: false, gating_gates: ['G1_GRID_UTILITIES_REALITY'],                            progress_pct: 67,  commitment_status: 'INDICATIVE' },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'Senior Debt',              amount: '€135M', is_unlocked: false, gating_gates: ['G5_EPC_RISK_PRICED', 'G1_GRID_UTILITIES_REALITY'],      progress_pct: 73,  commitment_status: 'NONE' },
      ],
    },
  },

  // ── 2 · NH3 · Rotterdam, Netherlands ─────────────────────────────────────
  {
    id: 'proj_rotterdam_nh3',
    name: 'Rotterdam Green Ammonia Terminal',
    molecule: 'NH3',
    location: 'Rotterdam, Netherlands',
    country: 'NL',
    lat: 51.9244,
    lng: 4.4777,
    capacity_mtpd: 160,
    capex_eur: 380_000_000,
    status: 'development',
    phase: 'Early development / FID preparation',
    completion_date: '2028-06-30',
    description: 'Green ammonia production integrated with Maasvlakte port logistics. Offtake committed to fertiliser manufacturers and export traders.',
    owner_company: 'RotterdamGreenFuels BV',
    associated_companies: ['Allianz', 'Zürich Versicherung AG'],
    bankability: {
      overall_completion: 52,
      next_milestone: 'Secure bankable off-take agreement (G4) to unlock €120M Strategic Equity',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'Off-take term sheet received but 15-year tenor not yet confirmed',
        'Environmental impact assessment delayed by 2 months',
      ],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',      completion_pct: 75,  total_evidence: 4, verified_count: 3, is_complete: false, blocking_items: ['environmental_impact_assessment'], description: 'Land lease and port authority permits' },
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured',completion_pct: 50,  total_evidence: 6, verified_count: 3, is_complete: false, blocking_items: ['offtake_15_year_term', 'credit_support_deed'], description: 'Long-term take-or-pay with investment-grade counterparty' },
        { id: 'G8_AUDIT_GRADE_MODEL',   name: 'Audit-Grade Financial Model',completion_pct: 60, total_evidence: 5, verified_count: 3, is_complete: false, blocking_items: ['stress_test_certification', 'independent_engineer_sign_off'], description: 'Third-party verified model with stress tests' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€20M',  is_unlocked: true,  gating_gates: [],                                                          progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€120M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE'],                                     progress_pct: 50,  commitment_status: 'NONE' },
        { type: 'DFI_MEZZ_GUARANTEES',       name: 'DFI Guarantees',           amount: '€45M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G4_OFFTAKE_BANKABLE'],                  progress_pct: 62,  commitment_status: 'INDICATIVE' },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'Senior Debt',              amount: '€195M', is_unlocked: false, gating_gates: ['G8_AUDIT_GRADE_MODEL', 'G4_OFFTAKE_BANKABLE'],            progress_pct: 55,  commitment_status: 'NONE' },
      ],
    },
    molecule_gating: {
      hazop_completed: false,
      seveso_tier: 'PENDING',
      terminal_interface_signed: false,
      molecule_insurance_placed: false,
    },
  },

  // ── 3 · e-Methanol · San Sebastián, Spain ────────────────────────────────
  {
    id: 'proj_sansebastian_emethanol',
    name: 'Project Helios e-Methanol',
    molecule: 'e-Methanol',
    location: 'San Sebastián, Spain',
    country: 'ES',
    lat: 43.3183,
    lng: -1.9812,
    capacity_mtpd: 42,
    capex_eur: 165_000_000,
    status: 'construction',
    phase: 'Pre-COD / late construction',
    completion_date: '2027-03-31',
    description: 'e-Methanol synthesis combining green H2 and biogenic CO2 captured from a nearby pulp mill. Primary offtake: Maersk and CMA CGM marine fuel blending.',
    owner_company: 'Helios Energía SL',
    associated_companies: ['Allianz'],
    bankability: {
      overall_completion: 66,
      next_milestone: 'Complete G4 + G7 for €42M Project Equity unlock',
      unlocked_capital: ['DFI_MEZZ_GUARANTEES'],
      risk_alerts: [
        'Take-or-pay contract needs 10-year term extension',
        'Political risk insurance pending government approval',
      ],
      gates: [
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured',  completion_pct: 83, total_evidence: 6, verified_count: 5, is_complete: false, blocking_items: ['offtake_contract_10_year_term'],          description: 'Long-term take-or-pay with investment-grade counterparties' },
        { id: 'G7_INSURANCE_BOUND',     name: 'Insurance Coverage Bound',   completion_pct: 75, total_evidence: 4, verified_count: 3, is_complete: false, blocking_items: ['political_risk_insurance'],               description: 'Comprehensive construction & operational insurance' },
        { id: 'G8_AUDIT_GRADE_MODEL',   name: 'Audit-Grade Financial Model',completion_pct: 80, total_evidence: 5, verified_count: 4, is_complete: false, blocking_items: ['stress_test_certification'],             description: 'Third-party verified model with stress testing' },
        { id: 'G10_FINANCIAL_CLOSE_CP', name: 'Financial Close Ready',      completion_pct: 25, total_evidence: 8, verified_count: 2, is_complete: false, blocking_items: ['senior_debt_commitment', 'equity_funding_confirmed'], description: 'All funding commitments and legal docs ready' },
      ],
      capital_status: [
        { type: 'PROJECT_EQUITY',       name: 'Project Equity',   amount: '€42M',  is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],              progress_pct: 79,  commitment_status: 'TERM_SHEET' },
        { type: 'SENIOR_DEBT_COMMITMENT',         name: 'Senior Debt',       amount: '€98M',  is_unlocked: false, gating_gates: ['G8_AUDIT_GRADE_MODEL', 'G10_FINANCIAL_CLOSE_CP'],          progress_pct: 53,  commitment_status: 'INDICATIVE' },
        { type: 'DFI_MEZZ_GUARANTEES',      name: 'DFI Guarantees',    amount: '€25M',  is_unlocked: true,  gating_gates: ['G4_OFFTAKE_BANKABLE'],                                    progress_pct: 100, commitment_status: 'CREDIT_APPROVED' },
        { type: 'DEBT_DRAWDOWN',       name: 'Debt Drawdown',     amount: '€98M',  is_unlocked: false, gating_gates: ['G10_FINANCIAL_CLOSE_CP'],                                 progress_pct: 25,  commitment_status: 'NONE' },
      ],
    },
  },

  // ── 4 · SAF · Wales, UK ──────────────────────────────────────────────────
  {
    id: 'proj_wales_saf',
    name: 'Celtic Green SAF Complex',
    molecule: 'SAF',
    location: 'Neath Port Talbot, Wales',
    country: 'GB',
    lat: 51.6614,
    lng: -3.8019,
    capacity_mtpd: 28,
    capex_eur: 290_000_000,
    status: 'development',
    phase: 'Project development / pre-FID',
    completion_date: '2029-01-31',
    description: 'Power-to-liquid SAF via Fischer-Tropsch synthesis, co-located with former steelworks site. Offtake discussions with British Airways and easyJet.',
    owner_company: 'Celtic Green Fuels Ltd',
    associated_companies: ['Zürich Versicherung AG'],
    bankability: {
      overall_completion: 38,
      next_milestone: 'Advance permitting (G0) and technology wrap (G5) to attract institutional equity',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'UK SAF mandate trajectory still subject to parliamentary review',
        'Power purchase agreement with National Grid not yet executed',
      ],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',      completion_pct: 50,  total_evidence: 4, verified_count: 2, is_complete: false, blocking_items: ['full_planning_permission', 'environmental_impact_assessment'], description: 'Brownfield site permitting and title transfer' },
        { id: 'G3_INPUTS_SECURED',  name: 'Technology Vendor Locked', completion_pct: 40,  total_evidence: 5, verified_count: 2, is_complete: false, blocking_items: ['technology_licence_agreement', 'licensor_performance_guarantee', 'technology_wrap_insurance'], description: 'Fischer-Tropsch technology licence and wrap' },
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured',completion_pct: 25,  total_evidence: 6, verified_count: 1, is_complete: false, blocking_items: ['signed_offtake_contract', 'credit_support_deed', 'offtake_15_year_term', 'price_floor_mechanism'], description: 'Airline take-or-pay agreement and credit support' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€8M',   is_unlocked: true,  gating_gates: [],                                                     progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€22M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS'],                                     progress_pct: 50,  commitment_status: 'NONE' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€90M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G3_INPUTS_SECURED', 'G4_OFFTAKE_BANKABLE'], progress_pct: 38,  commitment_status: 'NONE' },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'Senior Debt',              amount: '€170M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_INPUTS_SECURED'],       progress_pct: 32,  commitment_status: 'NONE' },
      ],
    },
    molecule_gating: {
      process_hazard_review: false,
      astm_cert_status: 'IN_PROGRESS',
      molecule_insurance_placed: false,
    },
  },

  // ── 5 · e-NG · Le Havre, France ──────────────────────────────────────────
  {
    id: 'proj_lehavre_eng',
    name: 'Le Havre e-Gas Hub',
    molecule: 'e-NG',
    location: 'Le Havre, France',
    country: 'FR',
    lat: 49.4944,
    lng: 0.1079,
    capacity_mtpd: 55,
    capex_eur: 195_000_000,
    status: 'operating',
    phase: 'COD / early operations',
    completion_date: '2025-11-30',
    description: 'Synthetic methane (e-NG) via Sabatier methanation from green H2 and offshore-sourced biogenic CO2. Grid injection under the French green gas tariff scheme.',
    owner_company: 'Normandie Hydrogène SA',
    associated_companies: ['Allianz', 'Zürich Versicherung AG'],
    bankability: {
      overall_completion: 91,
      next_milestone: 'Certify ISO-14064 verification report (G11) to close DSRA escrow',
      unlocked_capital: ['GRANTS_TA', 'SEED_VC_ANGEL', 'STRATEGIC_EQUITY', 'DFI_MEZZ_GUARANTEES', 'SENIOR_DEBT_COMMITMENT'],
      risk_alerts: [],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',       completion_pct: 100, total_evidence: 4, verified_count: 4, is_complete: true,  blocking_items: [],                              description: 'Port concession and grid injection permits' },
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured', completion_pct: 100, total_evidence: 6, verified_count: 6, is_complete: true,  blocking_items: [],                              description: '20-year grid injection contract with Engie' },
        { id: 'G8_AUDIT_GRADE_MODEL',   name: 'Audit-Grade Financial Model',completion_pct: 100,total_evidence: 5, verified_count: 5, is_complete: true,  blocking_items: [],                              description: 'Big-4 certified model, Q4 2025' },
        { id: 'G11_COD_STABILIZATION',       name: 'GHG Certification Verified',completion_pct: 60, total_evidence: 5, verified_count: 3, is_complete: false, blocking_items: ['iso_14064_verification_report', 'third_party_ghg_audit'], description: 'ISO-14064 GHG verification and registry issuance' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€15M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€20M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€60M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'DFI_MEZZ_GUARANTEES',       name: 'DFI Guarantees',           amount: '€30M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'Senior Debt',              amount: '€120M', is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
      ],
    },
  },

  // ── 6 · e-Methanol · Hamburg, Germany — HamburgOne ───────────────────────
  {
    id: 'proj_hamburgone_emethanol',
    name: 'HamburgOne e-Methanol Plant',
    molecule: 'e-Methanol',
    location: 'Hamburg, Germany',
    country: 'DE',
    lat: 53.5753,
    lng: 9.9950,
    capacity_mtpd: 28,
    capex_eur: 185_000_000,
    status: 'development',
    phase: 'FEED / Financial Structuring',
    completion_date: '2028-02-01',
    description: 'Green e-methanol plant co-located with Hamburg port industrial zone. Primary offtake target: BremenThree AG (3,000 MT/month). Certifier: DNV. Team: Lisa Friedrich (CEO/CFO), Mark Puntz (Chief Engineer), Lucie Mertz (CCO). Structured lending via NordLB (Henrik Vost).',
    owner_company: 'HamburgOne.com',
    associated_companies: ['NordLB', 'BremenThree AG', 'Allianz', 'Siemens Energy'],
    // Grid-connected (150 MW grid capacity reservation in G1) with NO PPA yet —
    // deliberately triggers the on-grid-without-PPA contradiction on the edit
    // screen: electricity price unhedged + RFNBO additionality at risk.
    energy_input: { power_mw: 150, source: 'grid', power_model: 'GRID_CONNECTED', ppas: [] },
    bankability: {
      overall_completion: 52,
      next_milestone: 'Complete FEED and secure DNV interim certification milestone',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'CO₂ feedstock supply agreement not yet signed',
        'Investor-ready documentation package still in preparation',
        'BremenThree AG offtake LOI received — term sheet pending',
      ],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',       completion_pct: 100, total_evidence: 4, verified_count: 4, is_complete: true,  blocking_items: [],                                  description: 'Hamburg port zone land lease signed' },
        { id: 'G1_GRID_UTILITIES_REALITY',       name: 'Power, Water & Critical Utility Access', completion_pct: 17,  total_evidence: 12, verified_count: 2, is_complete: false, blocking_items: ['ppa_register', 'ppa_signed_or_term_sheet_evidence', 'ppa_volume_load_coverage_analysis', 'ppa_tenor_debt_comparison', 'grid_connection_cost_estimate', 'connection_date_cod_compatibility_memo', 'curtailment_assessment', 'dispatch_load_factor_production_impact', 'water_permit_pathway_memo'], description: 'GRID_CONNECTED · No PPA recorded — DEAL KILLER: electricity price unhedged, RFNBO/45V additionality cannot be evidenced. Grid interconnection study submitted.' },
        { id: 'G3_INPUTS_SECURED',   name: 'Technology Vendor Locked',  completion_pct: 75,  total_evidence: 4, verified_count: 3, is_complete: false, blocking_items: ['epc_lump_sum_contract'],            description: 'e-MeOH reactor OEM selected; EPC contract in negotiation' },
        { id: 'G4_OFFTAKE_BANKABLE',     name: 'Bankable Offtake',          completion_pct: 30,  total_evidence: 5, verified_count: 1, is_complete: false, blocking_items: ['signed_offtake_agreement', 'volume_commitment_letter'], description: 'BremenThree AG target: 3,000 MT/month — term sheet stage' },
        { id: 'G7_INSURANCE_BOUND',      name: 'Insurance Bound',           completion_pct: 20,  total_evidence: 3, verified_count: 0, is_complete: false, blocking_items: ['car_ear_bound', 'dsu_quote'],      description: 'CAR/EAR/DSU to be placed on FEED completion' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',          amount: '€8M',   is_unlocked: true,  gating_gates: [],                                                progress_pct: 100, commitment_status: 'DRAWN'           },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',     amount: '€45M',  is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE'],                           progress_pct: 30,  commitment_status: 'INDICATIVE'      },
        { type: 'DFI_MEZZ_GUARANTEES',       name: 'NordLB LC / DFI',      amount: '€30M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G4_OFFTAKE_BANKABLE'],         progress_pct: 45,  commitment_status: 'INDICATIVE'      },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'Senior Debt',          amount: '€102M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],     progress_pct: 20,  commitment_status: 'NONE'            },
      ],
    },
  },

  // ── 7 · e-Methanol · San Sebastián, Spain — Madrid2 ──────────────────────
  {
    id: 'proj_madrid2_sansebastian',
    name: 'Madrid2 San-Sebastián e-Methanol',
    molecule: 'e-Methanol',
    location: 'San Sebastián, Spain',
    country: 'ES',
    lat: 43.3183,
    lng: -1.9812,
    capacity_mtpd: 42,
    capex_eur: 260_000_000,
    status: 'development',
    phase: 'Pre-FEED / Feasibility',
    completion_date: '2029-06-30',
    description: 'Integrated e-methanol hub with three sub-projects: green H₂ (Basque offshore wind), Green Carbon capture from industrial emitters, off-grid PPA from Iberdrola. Engineering: EngineSpain Spa (external). CEO: Diego Martinez; CCO: Claudia Nunez. Primary offtaker: RotterdamOfftake4 AG (10,000 MT/month SAF+eMeOH combined; Luc Marchand CFO). Requires Gabillon forward pricing and spot reference. Structured lending: ABN-AMRO (Sander de Vries).',
    owner_company: 'Madrid2.com',
    associated_companies: ['ABN-AMRO', 'RotterdamOfftake4 AG', 'Zürich Versicherung AG'],
    bankability: {
      overall_completion: 28,
      next_milestone: 'Execute CO₂ supply MOU with ArcelorMittal Gijón and complete Pre-FEED',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [
        'CO₂ feedstock source (Green Carbon sub-project) not contractualised',
        'Off-grid PPA with Iberdrola in early commercial stage',
        'RotterdamOfftake4 AG requires Gabillon pricing reference before LOI',
        'ABN-AMRO structured lending conditional on bankable offtake',
      ],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',       completion_pct: 80,  total_evidence: 4, verified_count: 3, is_complete: false, blocking_items: ['environmental_impact_assessment'], description: 'Basque Country industrial zone — EIA in progress' },
        { id: 'G1_GRID_UTILITIES_REALITY',       name: 'Grid Connection Secured',   completion_pct: 40,  total_evidence: 3, verified_count: 1, is_complete: false, blocking_items: ['red_electrica_capacity', 'offgrid_ppa_signed'], description: 'Off-grid PPA preferred — Red Eléctrica capacity as backup' },
        { id: 'G3_INPUTS_SECURED',   name: 'Technology Vendor Locked',  completion_pct: 50,  total_evidence: 4, verified_count: 2, is_complete: false, blocking_items: ['epc_selection', 'co2_source_contract'],  description: 'EngineSpain Spa shortlisted as EPC — MoU signed' },
        { id: 'G4_OFFTAKE_BANKABLE',     name: 'Bankable Offtake',          completion_pct: 15,  total_evidence: 5, verified_count: 1, is_complete: false, blocking_items: ['gabillon_pricing_agreed', 'offtake_term_sheet', 'spot_reference'], description: 'RotterdamOfftake4 AG: 10,000 MT/month. Pricing reference needed.' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA (CEF/IDAE)',   amount: '€15M',  is_unlocked: true,  gating_gates: [],                                                  progress_pct: 100, commitment_status: 'INDICATIVE'    },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / Founders Capital',  amount: '€12M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS'],                                  progress_pct: 40,  commitment_status: 'NONE'          },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€65M',  is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_INPUTS_SECURED'],   progress_pct: 15,  commitment_status: 'NONE'          },
        { type: 'SENIOR_DEBT_COMMITMENT',          name: 'ABN-AMRO Structured Debt', amount: '€168M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],       progress_pct: 10,  commitment_status: 'NONE'          },
      ],
    },
  },

  // ── 9 · H2 · Duisburg, DE (RheinWerk — PROSUMER demo) ──────────────────
  // Demonstrates the balance-sheet / prosumer mode: HYBRID power (own wind
  // BTM + grid import sleeved from the owner's portfolio), BALANCE_SHEET
  // financing (lender gates waived by the engine), internal self-offtake.
  {
    id: 'proj_rheinwerk_prosumer',
    name: 'RheinWerk Duisburg H₂ (Prosumer)',
    molecule: 'H2',
    location: 'Duisburg, NRW',
    country: 'DE',
    lat: 51.43,
    lng: 6.76,
    capacity_mtpd: 55,
    capex_eur: 210_000_000,
    status: 'development',
    phase: 'Corporate FID preparation — balance-sheet funded',
    completion_date: '2028-06-30',
    description:
      'Industrial prosumer: 120 MW electrolysis for own steel-finishing decarbonisation. ' +
      'HYBRID power — 80 MW owned BTM wind + 60 MW grid import sleeved from the RheinWerk ' +
      'generation portfolio (internal affiliate PPA). Self-offtake: 100% of H₂ consumed on site. ' +
      'No external project debt — funded from group balance sheet.',
    owner_company: 'RheinWerk Industries AG',
    associated_companies: [],
    financing_model: 'BALANCE_SHEET',
    energy_input: {
      power_mw: 140,
      source: 'hybrid',
      power_model: 'HYBRID',
      grid_import_mw: 60,
      btm_generation_mw: 80,
      ppas: [
        {
          counterparty: 'RheinWerk Energie GmbH (group portfolio)',
          counterparty_type: 'INTERNAL_AFFILIATE',
          volume_mw: 60,
          price_eur_mwh: null,
          tenor_years: 12,
          status: 'SIGNED',
          type: 'SLEEVED',
        },
      ],
    },
    bankability: {
      overall_completion: 46,
      next_milestone: 'Complete BTM yield study and water permit pathway for corporate FID',
      unlocked_capital: ['GRANTS_TA'],
      risk_alerts: [],
      gates: [
        { id: 'G0_SITE_RIGHTS', name: 'Site Rights Secured', completion_pct: 100, total_evidence: 3, verified_count: 3, is_complete: true, blocking_items: [], description: 'Owned industrial land — site control inherent' },
        { id: 'G1_GRID_UTILITIES_REALITY', name: 'Power, Water & Critical Utility Access', completion_pct: 50, total_evidence: 16, verified_count: 8, is_complete: false, blocking_items: ['generation_yield_study', 'water_permit_pathway_memo', 'ppa_volume_load_coverage_analysis'], description: 'HYBRID — both grid and BTM tracks apply. Internal sleeved PPA signed; yield study and water permits outstanding' },
        { id: 'G3_INPUTS_SECURED', name: 'Key Inputs Secured', completion_pct: 70, total_evidence: 3, verified_count: 2, is_complete: false, blocking_items: ['logistics_concept_note'], description: 'On-site consumption — minimal logistics' },
      ],
      capital_status: [
        { type: 'GRANTS_TA', name: 'IPCEI / NRW Grants', amount: '€28M', is_unlocked: true, gating_gates: [], progress_pct: 100, commitment_status: 'DRAWN' },
        // No external debt tranches — balance-sheet funded. Lender capital
        // types are intentionally absent, not "locked".
      ],
    },
  },
];

export function getProjectById(id: string): CustomerProject | undefined {
  return CUSTOMER_PROJECTS.find(p => p.id === id);
}

export const DEFAULT_PROJECT_ID = CUSTOMER_PROJECTS[0].id;
