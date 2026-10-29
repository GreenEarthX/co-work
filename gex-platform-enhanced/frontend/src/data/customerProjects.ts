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
    | "H2"
    | "NH3"
    | "e-Methanol"
    | "SAF"
    | "e-NG"
    | "e-Methane"
    | "e-NH3"
    | "HVO"
    | "e-Gasoline"
    | "e-LG"
    | "e-Naphtha";
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
  capex_currency?: "EUR" | "USD" | "GBP" | "JPY" | "CHF" | "CAD" | "AUD";
  status: "development" | "construction" | "operating" | "commissioning";
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
  // Gates, state and capital eligibility — the ENGINE's evaluation, scoped to
  // the caller's persona (GET /projects/visible, app/core/engine_view.py).
  // Never typed by hand: the hand-written block this used to hold was removed
  // on 2026-10-28 (JML). `evaluated: false` means the engine has not judged
  // the project yet; show that, not a figure.
  bankability: {
    evaluated?: boolean;
    source?: "engine";
    state?: string | null;
    state_label?: string | null;
    next_state?: string | null;
    rules_version?: string | null;
    evaluated_at?: string | null;
    /** The overall figure covers every gate; a persona may see fewer. */
    scope?: { persona: string; visible_gates: number; total_gates: number; note?: string | null };
    unavailable?: string;
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
  /** SATISFIED | BLOCKED | UNRESOLVED | INCOMPLETE | WAIVED (engine 4.2.0). */
  determination?: string;
  blocked_reasons?: string[];
}

// ─── Structured risk flags ────────────────────────────────────────────────────
// Replaces flat risk_alerts strings. Design (Hidalgo/Sung): every flag is a
// causal unit — thought (claim) → consequence (severity/owner) → way (category,
// resolved to a role-aware route in the UI). `route` is deliberately NOT stored:
// routes are presentation, categories are domain.

/** Internal business function that owns WORKING the risk (task assignment —
 *  NOT visibility; visibility is governed by `classification`). */
export type BusinessFunctionOwner =
  | "EXECUTIVE"
  | "FINANCE_TREASURY"
  | "COMMERCIAL"
  | "ENGINEERING"
  | "OPERATIONS"
  | "COMPLIANCE_LEGAL";

/** Semantic domain of the risk — the UI derives the role-aware route from this. */
export type RiskCategory =
  | "capacity_claim" // disputed/overstated production figures → Challenge Review
  | "certification" // 45V / RFNBO / RED III / SAF cert chains → Cert Readiness
  | "offtake" // counterparty, related-party, volume risk → Offtake Quality
  | "financing" // grants vs project finance, tax credits  → Capital Stack
  | "site_permits" // land, water, grid, EIA                  → Gate Evidence
  | "insurance" // uninsured lines, PRI                    → Insurance Schedule
  | "supply_chain" // feedstock dependencies                  → Offtake Quality
  | "policy"; // pending legislation / mandates          → Cert Readiness

/** ABAC sensitivity — what the server-side filter polices. Ladder:
 *  PUBLIC < STAKEHOLDER (owner + associated companies) < CONFIDENTIAL (owner
 *  company) < RESTRICTED (owner EXEC/FINANCE only). Platform admin sees all. */
export type RiskClassification =
  | "PUBLIC"
  | "STAKEHOLDER"
  | "CONFIDENTIAL"
  | "RESTRICTED";

export interface RiskFlag {
  /** Stable id — audit trail, acknowledge/waive lifecycle, cross-references. */
  id: string;
  /** The thought: what is claimed to be wrong. */
  claim: string;
  /** Impact if true. */
  severity: "low" | "medium" | "high" | "critical";
  /** How certain the claim is (public-source doctrine: impact ≠ certainty). */
  confidence: "low" | "medium" | "high";
  category: RiskCategory;
  owner_function: BusinessFunctionOwner;
  classification: RiskClassification;
  /** Provenance — plural because conflicts ARE two sources disagreeing. */
  source_ids: string[];
  status: "OPEN" | "ACKNOWLEDGED" | "WAIVED" | "RESOLVED";
}

/** Commitment maturity for a capital item — distinct from evidence gate progress. */
export type CommitmentStatus =
  | "NONE" // No engagement yet
  | "INDICATIVE" // Indicative terms or LOI received
  | "TERM_SHEET" // Signed term sheet
  | "CREDIT_APPROVED" // Internal credit committee approval granted
  | "LEGAL_COMPLETE" // Legal documentation signed
  | "DRAWN" // Capital drawn
  // What the engine reports (2026-10-28): GEX establishes whether the evidence
  // makes a capital DECISION eligible; it never records money as committed.
  | "DECISION_ELIGIBLE"
  | "NOT_YET_ELIGIBLE";

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
  seveso_tier?: "LOWER" | "UPPER" | "PENDING" | null;
  /** NH3 only: Terminal operator interface agreement signed */
  terminal_interface_signed?: boolean;
  /** SAF only: Fischer-Tropsch / HEFA process hazard review completed */
  process_hazard_review?: boolean;
  /** SAF only: ASTM D7566 feedstock and blend certification status */
  astm_cert_status?: "NONE" | "IN_PROGRESS" | "CERTIFIED";
  /** All: NH3/H2/SAF-specific insurance line (CAR/Marine/Liability) placed */
  molecule_insurance_placed?: boolean;
}

// ── Offtake Binding Status ──────────────────────────────────────────────────

export type OfftakeBindingStatus =
  | "BINDING" // Fully executed, legally binding contract
  | "TERM_SHEET" // Signed term sheet / heads of terms
  | "LOI" // Letter of intent
  | "MOU" // Memorandum of understanding
  | "INDICATIVE"; // Indicative / non-binding expression of interest

export type OfftakeVerification =
  | "UNVERIFIED"
  | "SUBMITTED"
  | "CONFIRMED"
  | "CONTRADICTED";

export interface Offtake {
  party: string;
  binding_status: OfftakeBindingStatus;
  is_related_party: boolean;
  volume_tpy: number | null;
  term_years: number | null;
  price_type: "FIXED" | "INDEX_LINKED" | "UNDISCLOSED" | null;
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
 * Grid topology of the power supply — drives WHICH evidence G1 demands.
 *
 * It does NOT decide whether power evidence is owed: every model owes it. Off-
 * grid changes the instrument, not the obligation (see PowerAttribution).
 *  - OFF_GRID_BTM:    dedicated behind-the-meter generation, no grid import.
 *                     Evidence = direct-line route: additionality, temporal and
 *                     geographic correlation, zero-grid-import metering, and
 *                     retired attribute certificates. A PPA is still required
 *                     whenever the generator is a separate legal entity —
 *                     RED III defines a renewables PPA contractually, not
 *                     topologically.
 *  - GRID_CONNECTED:  electrolyser draws from the grid. Evidence =
 *                     interconnection + ≥1 PPA, else electricity price risk
 *                     is unhedged (and RFNBO/45V additionality is at risk).
 *  - HYBRID:          BTM primary + grid import/export. PPA(s) required for
 *                     the grid-imported share.
 */
export type PowerModel = "OFF_GRID_BTM" | "GRID_CONNECTED" | "HYBRID";

/**
 * Evidence that the electricity behind the molecule actually qualifies it.
 *
 * Off-grid behind-the-meter is not an exemption — it is a different, and in
 * places stricter, evidence burden:
 *  - RFNBO DA (EU) 2023/1184 Art. 3 — the direct-line route still owes
 *    additionality, temporal and geographic correlation, AND adds a
 *    zero-grid-import metering condition the PPA route does not carry. Any
 *    grid import voids the route outright.
 *  - RFNBO DA Art. 5 — a generator that received operating or investment aid
 *    is disqualified for additionality unless the aid was fully repaid.
 *  - US 45V final regulations (Jan 2025) — EACs are required for captive,
 *    co-located behind-the-meter power, not only for purchased power, because
 *    BTM power can create induced emissions if it previously served the grid
 *    or another load. Incrementality, temporal matching and deliverability all
 *    apply to a dedicated on-site wind farm.
 *  - RED III Art. 2 — a "renewables power purchase agreement" is a contract to
 *    purchase renewable electricity DIRECTLY FROM an electricity producer. A
 *    direct line between two legal entities is therefore a PPA; only single-
 *    entity ownership of both assets escapes the contract, and it still owes
 *    certificate attribution.
 */
export interface PowerAttribution {
  /** Ownership of the generating asset relative to the fuel producer.
   *  SAME_ENTITY is the only case with no supply contract — and it still owes
   *  certificate attribution under 45V. */
  generator_ownership?: "SAME_ENTITY" | "AFFILIATE" | "THIRD_PARTY";
  /** Commissioning year of the generating asset. Additionality tests this
   *  against production start: the generator must have come into operation no
   *  more than 36 months before the fuel plant starts producing. */
  generator_cod_year?: number;
  /** Generator received operating or investment aid — disqualifying for RFNBO
   *  additionality unless fully repaid (DA Art. 5). */
  generator_received_aid?: boolean;
  /** Smart metering evidencing zero grid import on the direct-line route
   *  (DA Art. 3(b)). VERIFIED = metered and attested, not merely fitted. */
  grid_import_metering?: "NONE" | "INSTALLED" | "VERIFIED";
  /** Granularity at which attribute certificates (EACs / GOs) are retired
   *  against production. 45V requires hourly matching from 2028; RFNBO from
   *  2030. Annual matching is not sufficient for either beyond those dates. */
  certificate_matching?: "NONE" | "ANNUAL" | "MONTHLY" | "HOURLY";
}

/**
 * Financing model. PROJECT_FINANCE = SPV with external debt — all 12 gates
 * apply. BALANCE_SHEET = corporate / prosumer funding from own balance sheet —
 * lender-protection gates (G4 offtake, G6 IE, G7 insurance, G8 model audit,
 * G10 financial close) are out of scope and waived by the engine.
 */
export type FinancingModel = "PROJECT_FINANCE" | "BALANCE_SHEET";

/** Power purchase agreement — the hedge that makes on-grid electricity bankable. */
export interface PPA {
  counterparty: string;
  /**
   * THIRD_PARTY = market PPA (default). INTERNAL_AFFILIATE = sleeved supply
   * from the owner's own generation portfolio — the prosumer structure.
   * Internal supply hedges price but demands transfer-pricing / sleeving
   * governance evidence instead of a market contract.
   */
  counterparty_type?: "THIRD_PARTY" | "INTERNAL_AFFILIATE";
  volume_mw: number;
  /** €/MWh — null when commercially confidential (existence still counts). */
  price_eur_mwh?: number | null;
  tenor_years: number;
  status: "SIGNED" | "TERM_SHEET" | "LOI" | "NEGOTIATION";
  type?: "PHYSICAL" | "VIRTUAL" | "SLEEVED";
}

export interface EnergyInput {
  power_mw: number; // upstream renewable capacity
  source: "wind" | "solar" | "hybrid" | "hydro" | "nuclear" | "grid";
  /** On/off-grid topology. Absent = not yet declared (itself a data gap). */
  power_model?: PowerModel;
  /** Required (≥1) when power_model is GRID_CONNECTED or HYBRID, and whenever
   *  the generator is a separate legal entity on any topology. */
  ppas?: PPA[];
  /** Evidence qualifying the electricity. Owed on every power_model — off-grid
   *  swaps the instrument, not the obligation. Absent = undeclared, itself a gap. */
  power_attribution?: PowerAttribution;
  /** HYBRID split: grid-imported share of load (MW). PPA coverage is judged
   *  against THIS, not total plant load — the BTM share needs no PPA. */
  grid_import_mw?: number;
  /** HYBRID split: owned BTM generation (MW). */
  btm_generation_mw?: number;
  curtailment_share_pct?: number; // optional, for hybrids
}

export interface Electrolyser {
  capacity_mw: number;
  technology: "PEM" | "AEM" | "SOEC" | "alkaline";
  oem?: string; // e.g. "John Cockerill"
}

export type CertificationStatus =
  | "ACTIVE" // certification granted and in force
  | "UNDER_REVIEW" // application under regulatory review
  | "PRE-ASSESSMENT" // gap analysis in progress
  | "INTENDED" // declared target, not yet started
  | "WITHDRAWN";

export interface CertificationProgress {
  scheme:
    | "45V"
    | "RFNBO"
    | "GoO"
    | "ISCC"
    | "FuelEU_Maritime"
    | "CORSIA"
    | "ASTM_D7566"
    | "RED_III";
  status: CertificationStatus;
  tier?: string; // e.g. "Tier 1", "Tier 2"
  note?: string; // e.g. "temporal correlation review"
}

export type IncentiveKind =
  | "IRA_45V" // US production tax credit
  | "IRA_45Q" // US carbon-capture credit
  | "IRA_GRANT" // US Inflation Reduction Act grant
  | "EU_INNOVATION_FUND"
  | "EU_HYDROGEN_BANK"
  | "BPIFRANCE"
  | "KFW_GRANT"
  | "DOE_LPO" // US Department of Energy Loan Programs Office
  | "OTHER";

export interface Incentive {
  kind: IncentiveKind;
  amount_eur?: number | null; // absolute amount, EUR
  amount_usd?: number | null; // absolute amount, USD (one of the two)
  status: "SECURED" | "AWARDED" | "APPLIED" | "INTENDED" | "DECLINED";
  note?: string;
}

export interface Timeline {
  construction_start_year?: number; // FID-funded works begin
  production_start_year?: number; // first product to spec
}

// The project RECORDS are not here. They live in PostgreSQL — `projects` for the
// headline fields, `project_profile` for the rest (alembic 068), delivered by
// GET /api/v1/projects/visible through useVisibleProjects(). The array that
// stood here was moved there on 2026-10-25 (JML) and this file keeps only the
// types. Tests use src/test/fixtures/customerProjects.ts.
