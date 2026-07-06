/**
 * Deal compute types — mirror gex_pf_engine/models/deal.py exactly.
 *
 * Convention: field names are snake_case to match the Supabase column names
 * AND the Python Pydantic model field names. Do NOT camelCase here, or the
 * round-trip JSON will not deserialise on either side.
 *
 * When the Python models change, update this file in lockstep. The golden
 * tests in gex_pf_engine/tests/test_compute.py and src/lib/finance/__tests__
 * are the contract between them.
 */

export type VerificationState = "UNVERIFIED" | "SUBMITTED" | "CONFIRMED" | "AUDITED";

export type TrancheType =
  | "senior_bank"
  | "senior_bond"
  | "mezzanine"
  | "shareholder_loan"
  | "equity_bridge"
  | "equity"
  | "contingent_equity";

export type DrawdownPhase = "construction" | "operations" | "both";

export type IDCTreatment =
  | "capitalised_from_drawings"
  | "capitalised_from_equity"
  | "capitalised_from_bridge"
  | "paid_current"
  | "not_applicable";

export type RepaymentProfile = "annuity" | "bullet" | "sculpted" | "custom" | "equity";

export type CovenantPhase = "construction" | "operations" | "at_cod_test";

export type PriceType =
  | "fixed"
  | "indexed"
  | "floor_collar"
  | "take_or_pay"
  | "cfd"
  | "spot";

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

export interface DealStructure {
  id: string;
  plant_id: string;
  user_id: string;
  name: string;
  version: number;
  status: string;
  construction_start_date: string;   // ISO date
  scheduled_cod_date: string;
  actual_cod_date: string | null;
  operating_period_years: number;
  discount_rate_pct: number;
  tax_rate_pct: number;
  depreciation_years: number;
  verification_state: VerificationState;
  deal_killer_flag: boolean;
}

export interface DebtTranche {
  id: string;
  deal_structure_id: string;
  seniority_rank: number;
  tranche_type: TrancheType;
  lender_class: string | null;
  lender_name: string | null;
  commitment_eur: number;
  currency: string;
  fx_hedge_pct: number;
  rate_type: "fixed" | "floating";
  base_rate_pct: number | null;
  spread_bps: number | null;
  fixed_rate_pct: number | null;
  upfront_fee_bps: number;
  commitment_fee_bps: number;
  tenor_years: number;
  grace_years: number;
  repayment_profile: RepaymentProfile;
  sculpted_schedule: Array<Record<string, unknown>> | null;
  drawdown_phase: DrawdownPhase;
  drawdown_schedule: Array<Record<string, unknown>> | null;
  conditions_precedent: Array<Record<string, unknown>> | null;
  idc_treatment: IDCTreatment | null;
  conversion_at_cod_terms: Record<string, unknown> | null;
  verification_state: VerificationState;
}

export interface OfftakeContract {
  id: string;
  plant_id: string;
  counterparty_name: string;
  counterparty_class: string | null;
  molecule: string;
  volume_per_year: number;
  volume_unit: string;
  price_type: PriceType;
  price_formula: Record<string, unknown>;
  currency: string;
  tenor_years: number;
  start_year_offset_months: number;
  ramp_up_profile: Array<Record<string, unknown>> | null;
  status: string;
  signed_date: string | null;
  verification_state: VerificationState;
  deal_killer_flag: boolean;
  allocation_pct: number;
}

export interface Covenant {
  id: string;
  deal_structure_id: string;
  phase: CovenantPhase;
  covenant_type: string;
  value: number | null;
  value_text: string | null;
  basis: string | null;
  test_frequency: string;
  applies_to_tranche_id: string | null;
}

export interface PreCODTest {
  id: string;
  deal_structure_id: string;
  test_type: string;
  threshold: number | null;
  threshold_text: string | null;
  comparison: string;
  test_frequency: string;
  breach_consequence: string;
}

export interface PlantSummary {
  id: string;
  capex_eur: number;
  opex_eur_per_year: number;
  nameplate_capacity: number | null;
  nameplate_unit: string | null;
  verification_state: VerificationState;
  deal_killer_flag: boolean;
  latest_engine_run_status: string | null;
}

export interface DealInputs {
  deal: DealStructure;
  plant: PlantSummary;
  tranches: DebtTranche[];
  offtakes: OfftakeContract[];
  covenants: Covenant[];
  precod: PreCODTest[];
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

export interface PeriodRow {
  period_index: number;
  period_start_date: string;
  phase: "construction" | "operations";
  revenue_eur: number;
  revenue_by_offtake: Record<string, number>;
  opex_eur: number;
  capex_invested_eur: number;
  ebitda_eur: number;
  depreciation_eur: number;
  ebit_eur: number;
  interest_expense_eur: number;
  tax_eur: number;
  net_income_eur: number;
  drawn_by_tranche: Record<string, number>;
  debt_service_by_tranche: Record<string, number>;
  outstanding_by_tranche: Record<string, number>;
  idc_capitalised_eur: number;
  cfads_eur: number | null;
  total_debt_service_eur: number;
  dsra_balance_eur: number;
  cash_swept_eur: number;
  lockup_active: boolean;
  free_cash_flow_eur: number;
  distributions_eur: number;
  dscr: number | null;
  icr: number | null;
}

export interface PreCODRatioPoint {
  period_index: number;
  period_start_date: string;
  cost_to_complete_coverage: number | null;
  equity_drawn_ratio: number | null;
  pari_passu_ratio: number | null;
  physical_progress_pct: number | null;
  sponsor_support_headroom_eur: number | null;
  breaches: string[];
}

export interface PreCODSummary {
  period_rows: PreCODRatioPoint[];
  total_idc_capitalised_eur: number;
  final_construction_loan_eur: number;
  worst_cost_to_complete_coverage: number | null;
  worst_breach: string | null;
}

export interface CODTestSummary {
  capacity_demonstration_pct: number | null;
  permits_in_force: boolean | null;
  offtake_unconditional: boolean | null;
  dsra_funded: boolean | null;
  lookforward_dscr_p90: number | null;
  lookforward_llcr_p90: number | null;
  lookforward_dscr_threshold: number | null;
  projected_passed: boolean | null;
  blocking_conditions: string[];
}

export interface TaghizadehHesaryAssessment {
  current_bank_pct: number;
  current_bond_pct: number;
  optimal_bank_pct: number;
  optimal_bond_pct: number;
  deviation_bps: number;
  interpretation: string;
}

export interface ComputeWarning {
  code: string;
  message: string;
  severity: "info" | "warning" | "error";
}

export interface ComputeOutput {
  deal_structure_id: string;
  inputs_hash: string;
  engine_version: string;
  cashflow_schedule: PeriodRow[];
  precod_summary: PreCODSummary | null;
  cod_test_summary: CODTestSummary | null;
  project_irr: number | null;
  equity_irr: number | null;
  npv_eur: number | null;
  min_dscr_operations: number | null;
  avg_dscr_operations: number | null;
  llcr: number | null;
  rating_band: string | null;
  binding_constraint: string | null;
  covenant_breach_periods: number[];
  warnings: ComputeWarning[];
  errors: ComputeWarning[];
  taghizadeh_hesary_assessment: TaghizadehHesaryAssessment | null;
}

// ---------------------------------------------------------------------------
// Equation engine runs — for the src/engine/ elevation
// ---------------------------------------------------------------------------

export type EngineRunStatus = "clean" | "warnings" | "violations" | "engine_error";

export interface EngineViolation {
  rule_id: string;
  gate?: string;
  equipment_id?: string;
  severity: "info" | "warning" | "error" | "deal_killer";
  message: string;
  suggested_fix?: string;
}

export interface EquationEngineRun {
  id: string;
  plant_id: string;
  engine_version: string;
  inputs_hash: string;
  ran_at: string;
  triggered_by_user: string | null;
  status: EngineRunStatus;
  formula_dag_resolved: boolean;
  mass_balance_closed: boolean;
  energy_balance_closed: boolean;
  unit_check_passed: boolean;
  rule_check_passed: boolean;
  violations: EngineViolation[];
  warnings: EngineViolation[];
  metrics: Record<string, unknown>;
  has_deal_killer: boolean;
  verification_state: VerificationState;
}

export interface LatestEngineRun {
  plant_id: string;
  run_id: string;
  ran_at: string;
  status: EngineRunStatus;
  formula_dag_resolved: boolean;
  mass_balance_closed: boolean;
  energy_balance_closed: boolean;
  unit_check_passed: boolean;
  rule_check_passed: boolean;
  has_deal_killer: boolean;
  violation_count: number;
  warning_count: number;
  verification_state: VerificationState;
}
