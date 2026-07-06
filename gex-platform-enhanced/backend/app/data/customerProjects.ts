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
  // Bankability snapshot (used as demo fallback when backend is unavailable)
  bankability: {
    overall_completion: number;
    gates: BankabilityGate[];
    capital_status: CapitalItem[];
    next_milestone: string;
    unlocked_capital: string[];
    risk_alerts: string[];
  };
  /** Molecule-specific regulatory and hazard gating — shown alongside standard bankability gates. */
  molecule_gating?: MoleculeGating;
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

export const CUSTOMER_PROJECTS: CustomerProject[] = [
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
    bankability: {
      overall_completion: 74,
      next_milestone: 'Finalise grid connection agreement (G1) to unlock Strategic Equity',
      unlocked_capital: ['GRANTS_TA', 'SEED_VC_ANGEL'],
      risk_alerts: ['Grid connection agreement still pending utility sign-off'],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',      completion_pct: 100, total_evidence: 4, verified_count: 4, is_complete: true,  blocking_items: [],                             description: 'Land title and environmental permits' },
        { id: 'G1_GRID_UTILITIES',       name: 'Grid Connection Secured',  completion_pct: 67,  total_evidence: 3, verified_count: 2, is_complete: false, blocking_items: ['grid_connection_agreement'],  description: 'Utility interconnection and capacity reservation' },
        { id: 'G5_EPC_RISK_PRICED',      name: 'EPC Risk Assessed',        completion_pct: 80,  total_evidence: 5, verified_count: 4, is_complete: false, blocking_items: ['performance_guarantees'],     description: 'Fixed-price EPC contract with performance guarantees' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€12M',  is_unlocked: true,  gating_gates: [],                                               progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€18M',  is_unlocked: true,  gating_gates: [],                                               progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€55M',  is_unlocked: false, gating_gates: ['G1_GRID_UTILITIES'],                            progress_pct: 67,  commitment_status: 'INDICATIVE' },
        { type: 'SENIOR_DEBT',          name: 'Senior Debt',              amount: '€135M', is_unlocked: false, gating_gates: ['G5_EPC_RISK_PRICED', 'G1_GRID_UTILITIES'],      progress_pct: 73,  commitment_status: 'NONE' },
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
        { type: 'DFI_GUARANTEES',       name: 'DFI Guarantees',           amount: '€45M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G4_OFFTAKE_BANKABLE'],                  progress_pct: 62,  commitment_status: 'INDICATIVE' },
        { type: 'SENIOR_DEBT',          name: 'Senior Debt',              amount: '€195M', is_unlocked: false, gating_gates: ['G8_AUDIT_GRADE_MODEL', 'G4_OFFTAKE_BANKABLE'],            progress_pct: 55,  commitment_status: 'NONE' },
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
      unlocked_capital: ['DFI_GUARANTEES'],
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
        { type: 'SENIOR_DEBT',         name: 'Senior Debt',       amount: '€98M',  is_unlocked: false, gating_gates: ['G8_AUDIT_GRADE_MODEL', 'G10_FINANCIAL_CLOSE_CP'],          progress_pct: 53,  commitment_status: 'INDICATIVE' },
        { type: 'DFI_GUARANTEES',      name: 'DFI Guarantees',    amount: '€25M',  is_unlocked: true,  gating_gates: ['G4_OFFTAKE_BANKABLE'],                                    progress_pct: 100, commitment_status: 'CREDIT_APPROVED' },
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
        { id: 'G3_TECH_VENDOR_LOCKED',  name: 'Technology Vendor Locked', completion_pct: 40,  total_evidence: 5, verified_count: 2, is_complete: false, blocking_items: ['technology_licence_agreement', 'licensor_performance_guarantee', 'technology_wrap_insurance'], description: 'Fischer-Tropsch technology licence and wrap' },
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured',completion_pct: 25,  total_evidence: 6, verified_count: 1, is_complete: false, blocking_items: ['signed_offtake_contract', 'credit_support_deed', 'offtake_15_year_term', 'price_floor_mechanism'], description: 'Airline take-or-pay agreement and credit support' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€8M',   is_unlocked: true,  gating_gates: [],                                                     progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€22M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS'],                                     progress_pct: 50,  commitment_status: 'NONE' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€90M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G3_TECH_VENDOR_LOCKED', 'G4_OFFTAKE_BANKABLE'], progress_pct: 38,  commitment_status: 'NONE' },
        { type: 'SENIOR_DEBT',          name: 'Senior Debt',              amount: '€170M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_TECH_VENDOR_LOCKED'],       progress_pct: 32,  commitment_status: 'NONE' },
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
      unlocked_capital: ['GRANTS_TA', 'SEED_VC_ANGEL', 'STRATEGIC_EQUITY', 'DFI_GUARANTEES', 'SENIOR_DEBT'],
      risk_alerts: [],
      gates: [
        { id: 'G0_SITE_RIGHTS',         name: 'Site Rights Secured',       completion_pct: 100, total_evidence: 4, verified_count: 4, is_complete: true,  blocking_items: [],                              description: 'Port concession and grid injection permits' },
        { id: 'G4_OFFTAKE_BANKABLE',    name: 'Bankable Off-take Secured', completion_pct: 100, total_evidence: 6, verified_count: 6, is_complete: true,  blocking_items: [],                              description: '20-year grid injection contract with Engie' },
        { id: 'G8_AUDIT_GRADE_MODEL',   name: 'Audit-Grade Financial Model',completion_pct: 100,total_evidence: 5, verified_count: 5, is_complete: true,  blocking_items: [],                              description: 'Big-4 certified model, Q4 2025' },
        { id: 'G11_GHG_VERIFIED',       name: 'GHG Certification Verified',completion_pct: 60, total_evidence: 5, verified_count: 3, is_complete: false, blocking_items: ['iso_14064_verification_report', 'third_party_ghg_audit'], description: 'ISO-14064 GHG verification and registry issuance' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',              amount: '€15M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / VC',                amount: '€20M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€60M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'DFI_GUARANTEES',       name: 'DFI Guarantees',           amount: '€30M',  is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
        { type: 'SENIOR_DEBT',          name: 'Senior Debt',              amount: '€120M', is_unlocked: true,  gating_gates: [],                 progress_pct: 100, commitment_status: 'DRAWN' },
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
        { id: 'G1_GRID_UTILITIES',       name: 'Grid Connection Secured',   completion_pct: 60,  total_evidence: 3, verified_count: 2, is_complete: false, blocking_items: ['grid_capacity_reservation'],       description: 'Grid capacity reservation for 150 MW electrolysis' },
        { id: 'G3_TECH_VENDOR_LOCKED',   name: 'Technology Vendor Locked',  completion_pct: 75,  total_evidence: 4, verified_count: 3, is_complete: false, blocking_items: ['epc_lump_sum_contract'],            description: 'e-MeOH reactor OEM selected; EPC contract in negotiation' },
        { id: 'G4_OFFTAKE_BANKABLE',     name: 'Bankable Offtake',          completion_pct: 30,  total_evidence: 5, verified_count: 1, is_complete: false, blocking_items: ['signed_offtake_agreement', 'volume_commitment_letter'], description: 'BremenThree AG target: 3,000 MT/month — term sheet stage' },
        { id: 'G7_INSURANCE_BOUND',      name: 'Insurance Bound',           completion_pct: 20,  total_evidence: 3, verified_count: 0, is_complete: false, blocking_items: ['car_ear_bound', 'dsu_quote'],      description: 'CAR/EAR/DSU to be placed on FEED completion' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA',          amount: '€8M',   is_unlocked: true,  gating_gates: [],                                                progress_pct: 100, commitment_status: 'DRAWN'           },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',     amount: '€45M',  is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE'],                           progress_pct: 30,  commitment_status: 'INDICATIVE'      },
        { type: 'DFI_GUARANTEES',       name: 'NordLB LC / DFI',      amount: '€30M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS', 'G4_OFFTAKE_BANKABLE'],         progress_pct: 45,  commitment_status: 'INDICATIVE'      },
        { type: 'SENIOR_DEBT',          name: 'Senior Debt',          amount: '€102M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],     progress_pct: 20,  commitment_status: 'NONE'            },
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
        { id: 'G1_GRID_UTILITIES',       name: 'Grid Connection Secured',   completion_pct: 40,  total_evidence: 3, verified_count: 1, is_complete: false, blocking_items: ['red_electrica_capacity', 'offgrid_ppa_signed'], description: 'Off-grid PPA preferred — Red Eléctrica capacity as backup' },
        { id: 'G3_TECH_VENDOR_LOCKED',   name: 'Technology Vendor Locked',  completion_pct: 50,  total_evidence: 4, verified_count: 2, is_complete: false, blocking_items: ['epc_selection', 'co2_source_contract'],  description: 'EngineSpain Spa shortlisted as EPC — MoU signed' },
        { id: 'G4_OFFTAKE_BANKABLE',     name: 'Bankable Offtake',          completion_pct: 15,  total_evidence: 5, verified_count: 1, is_complete: false, blocking_items: ['gabillon_pricing_agreed', 'offtake_term_sheet', 'spot_reference'], description: 'RotterdamOfftake4 AG: 10,000 MT/month. Pricing reference needed.' },
      ],
      capital_status: [
        { type: 'GRANTS_TA',            name: 'Grants & TA (CEF/IDAE)',   amount: '€15M',  is_unlocked: true,  gating_gates: [],                                                  progress_pct: 100, commitment_status: 'INDICATIVE'    },
        { type: 'SEED_VC_ANGEL',        name: 'Seed / Founders Capital',  amount: '€12M',  is_unlocked: false, gating_gates: ['G0_SITE_RIGHTS'],                                  progress_pct: 40,  commitment_status: 'NONE'          },
        { type: 'STRATEGIC_EQUITY',     name: 'Strategic Equity',         amount: '€65M',  is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G3_TECH_VENDOR_LOCKED'],   progress_pct: 15,  commitment_status: 'NONE'          },
        { type: 'SENIOR_DEBT',          name: 'ABN-AMRO Structured Debt', amount: '€168M', is_unlocked: false, gating_gates: ['G4_OFFTAKE_BANKABLE', 'G7_INSURANCE_BOUND'],       progress_pct: 10,  commitment_status: 'NONE'          },
      ],
    },
  },
];

export function getProjectById(id: string): CustomerProject | undefined {
  return CUSTOMER_PROJECTS.find(p => p.id === id);
}

export const DEFAULT_PROJECT_ID = CUSTOMER_PROJECTS[0].id;
