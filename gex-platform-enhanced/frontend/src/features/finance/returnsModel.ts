// Screen: Shared model (no screen) — inputs, client and pre-FID spend for the returns screens
/**
 * What the Returns screen and the DEVEX brief share, kept in one place so the
 * two cannot describe the same project with different numbers.
 *
 * Vocabulary (the engine states the same definitions in every result):
 *   FCI    Fixed Capital Investment — the CAPEX committed at FID. In the
 *          screening case it falls in full at year 0; with a construction
 *          schedule it falls by construction year (the scheduled case).
 *   DEVEX  All pre-FID spend: packages in phases FEL 1, FEL 2 and FEED. It is
 *          paid before year 0 and by equity, grants or bridge only.
 *
 * The maths is the PF engine's (core/returns.py) through
 * POST /api/v1/finance-model/returns. Nothing here computes a return.
 */
import { useQuery } from '@tanstack/react-query'
import { getAuthHeader } from '@/lib/authToken'

export interface ReturnsInputs {
  fci_eur: number
  operating_years: number
  revenue_y1_eur: number
  revenue_growth: number
  opex_y1_eur: number
  opex_growth: number
  tax_rate: number
  depreciation_years: number
  residual_value_eur: number
  pre_fid_spend_eur: number[]      // by year, oldest first
  construction_schedule_eur: number[]   // CAPEX by year from FID; empty = screening case
  cod_months_after_fid: number | null   // null = the end of the last construction year
  ramp_up: number[]                // output share, first operating years
  opex_variable_share: number
  debt_eur: number
  interest_rate: number
  debt_tenor_years: number
  grant_eur: number
  risk_free_rate: number
  equity_beta: number
  equity_risk_premium: number
  country_risk_premium: number
  technology_risk_premium: number
  project_risk_premium: number
  valuation_boundary?: Boundary
  scenario?: string
}

export type Boundary = 'FULL_PROJECT' | 'FROM_FID'
export const BOUNDARY_LABEL: Record<Boundary, string> = {
  FULL_PROJECT: 'Full project — pre-FID spend before year 0',
  FROM_FID: 'From FID — pre-FID spend treated as sunk',
}

export interface DebtMetrics {
  dscr_by_year: { operating_year: number; cfads_eur: number; debt_service_eur: number; dscr: number }[]
  dscr_min: number | null; dscr_avg: number | null; llcr: number | null; llcr_status?: string; note?: string
}
export interface DownsideRow {
  id: string; label: string; error?: string
  unlevered_irr?: number | null; levered_irr?: number | null
  delta_unlevered_irr_bps?: number | null; delta_levered_irr_bps?: number | null
  npv_unlevered_eur?: number | null; npv_levered_eur?: number | null; dscr_min?: number | null; llcr?: number | null
}
export interface Downside { basis: string; shock_set_status: string; rows: DownsideRow[] }
export interface Provenance {
  calculation: { engine: string; module: string; model_version: string; computed_at: string }
  inputs_sha256: string; tea_case: Record<string, unknown>; assumptions: { name?: string; value?: unknown; source?: string; verification_status?: string }[]
  valuation_boundary: Boundary; scenario: string; timing: Record<string, unknown>
  validation_checks: { check: string; outcome: string; detail: string }[]; limitations: string[]; validity: string
}

export interface HurdleTest { hurdle: number; irr: number | null; spread_bps: number | null; clears: boolean | null }

export interface ReturnsFlows { first_period: number; unlevered: number[]; levered: number[] }

/** The headline figures of one case; a scheduled result carries the screening case in this shape. */
export interface CaseSummary {
  case: 'SCREENING_FCI_YEAR_0' | 'SCHEDULED'
  case_label: string
  first_operating_period: number
  unlevered_irr: number | null
  levered_irr: number | null
  npv_unlevered_eur: number
  npv_levered_eur: number | null
  payback_years: number | null
  equity_payback_years: number | null
  equity_invested_eur: number
  idc_eur: number
  flows: ReturnsFlows
}

export interface ReturnsResult extends CaseSummary {
  fci_eur: number
  devex_eur: number
  total_investment_eur: number
  roi_avg_annual: number
  roi_cumulative: number
  roe_avg_annual: number | null
  hurdle: {
    cost_of_equity: number; cost_of_equity_basis: string
    equity_weight: number; debt_weight: number; cost_of_debt_after_tax: number
    wacc_after_tax: number; project_risk_premium: number
    project_hurdle: number; equity_hurdle: number
  }
  hurdle_test: { unlevered: HurdleTest; levered: HurdleTest }
  // The timing the figures rest on, stated by the engine with every result.
  timing: {
    cod_months_after_fid: number; cod_basis: string; first_operating_project_year: number
    first_year_operating_share: number; last_year_operating_share: number
    operating_life_years: number; assumptions: string[]
  }
  screening_case?: CaseSummary
  difference?: {
    first_operating_period: { screening: number; scheduled: number }
    project_undiscounted_total_eur: { screening: number; scheduled: number }
    equity_undiscounted_total_eur: { screening: number; scheduled: number }
    idc_eur: number
    ramp_up_applied: boolean
  }
  definitions: Record<string, string>
  limitations: string[]
  valuation_boundary?: Boundary
  valuation_boundary_label?: string
  scenario?: string
  debt_metrics?: DebtMetrics
  downside?: Downside
  provenance?: Provenance
}

export interface Governance { model: string; basis: string; note: string; input_sha: string; computed_at: string }
export interface ReturnsAnswer { returns: ReturnsResult; governance: Governance | null }

/**
 * Starting values for a project with nothing agreed yet. They are ILLUSTRATIVE:
 * revenue and OPEX use the same ratios to CAPEX as the debt cashflow screen,
 * gearing is the reference registry's 0.65, and the hurdle build-up is a
 * placeholder for the sponsor's own. The form exists so they get replaced.
 */
export function illustrativeInputs(fciEur: number, preFidSpendEur: number[]): ReturnsInputs {
  const revenue = fciEur * 0.22
  return {
    fci_eur: fciEur, operating_years: 20,
    revenue_y1_eur: revenue, revenue_growth: 0.02,
    opex_y1_eur: revenue * 0.40, opex_growth: 0.02,
    tax_rate: 0.25, depreciation_years: 20, residual_value_eur: 0,
    pre_fid_spend_eur: preFidSpendEur,
    construction_schedule_eur: [], cod_months_after_fid: null, ramp_up: [], opex_variable_share: 0,
    debt_eur: fciEur * 0.65, interest_rate: 0.055, debt_tenor_years: 15, grant_eur: 0,
    risk_free_rate: 0.03, equity_beta: 1.2, equity_risk_premium: 0.055,
    country_risk_premium: 0, technology_risk_premium: 0.03, project_risk_premium: 0.01,
  }
}

export async function fetchReturns(inputs: ReturnsInputs): Promise<ReturnsAnswer> {
  const res = await fetch('/api/v1/finance-model/returns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
    body: JSON.stringify(inputs),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw Object.assign(new Error(typeof body?.detail === 'string' ? body.detail : `The server answered ${res.status}.`), { status: res.status })
  return { returns: body.returns as ReturnsResult, governance: (body.governance as Governance) ?? null }
}

export const fmtEur = (n: number | null | undefined) => {
  if (n == null || !isFinite(n)) return '—'
  const a = Math.abs(n)
  return `${n < 0 ? '−' : ''}${a >= 1e6 ? `€${(a / 1e6).toFixed(1)}M` : `€${(a / 1e3).toFixed(0)}k`}`
}

export const fmtPct = (n: number | null | undefined, digits = 1) =>
  n == null || !isFinite(n) ? '—' : `${(n * 100).toFixed(digits)}%`

/** One line: the hurdle, the spread to it, and whether the IRR clears it. */
export function hurdleLine(t: HurdleTest): string {
  if (t.irr == null || t.spread_bps == null) return `hurdle ${fmtPct(t.hurdle)} · IRR not defined`
  const sign = t.spread_bps >= 0 ? '+' : ''
  return `hurdle ${fmtPct(t.hurdle)} · ${sign}${t.spread_bps.toFixed(0)} bps · ${t.clears ? 'clears' : 'below hurdle'}`
}

// ── The DEVEX brief ──────────────────────────────────────────────────────────
// Assembled by the backend (GET /api/v1/devex-brief/{id}), which sends only the
// sections the caller may read: everything to the owner's finance and
// executives, the shared sections to anyone the owner shared them with, a 403
// to anyone else, and a 503 when the records cannot be read. Both screens read
// pre-FID spend through it, so Returns access never shows DEVEX that has not
// been shared. It is refetched on every visit, so a revoked share closes here
// as soon as the screen is opened again.

export interface PackageRow {
  package_id: string
  package_name: string
  package_type: string
  phase_required: string
  cost_amount: number
  cost_p10?: number | null
  cost_p90?: number | null
  estimate_class: string
  risk_removed: string[]
  capital_eligible: string[]
  unlock_condition?: string[] | null
  workflow_state: string
  gex_gate?: string | null
}

export interface DevexBriefData {
  project_id: string
  project_name: string
  basis: 'owner' | 'platform_admin' | 'share'
  read_only: boolean
  can_manage_shares: boolean
  as_of: string
  sections: string[]
  pre_fid_phases: string[]
  section_labels: Record<string, string>
  summary?: {
    pre_fid_spend_eur: number; package_count: number; drawn_eur: number; to_draw_eur: number
    evidenced_share: number | null; fid_grade_share: number | null
  }
  breakdown?: {
    rows: { package_type: string; by_phase: Record<string, number>; total_eur: number }[]
    phase_totals: Record<string, number>
    total_eur: number
  }
  funding?: {
    years: { year: number; layers: Record<string, number> }[]     // EUR
    layers: string[]
    layer_totals_eur: Record<string, number>
    total_eur: number
    verification_state: string | null
    drawn_before_fid: string[]
    register_gap_eur?: number
  } | null
  packages?: PackageRow[]
}

export interface DevexBrief {
  loading: boolean
  data: DevexBriefData | null
  denied: string | null      // the server's reason when the brief is not open to this caller
  error: string | null
}

type BriefAnswer = { data: DevexBriefData } | { denied: string }

export function useDevexBrief(projectId: string | null | undefined): DevexBrief {
  const valid = !!projectId && projectId !== 'all'
  const query = useQuery<BriefAnswer>({
    queryKey: ['devex-brief', projectId],
    enabled: valid,
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    queryFn: async () => {
      const res = await fetch(`/api/v1/devex-brief/${encodeURIComponent(projectId as string)}`, { headers: getAuthHeader() })
      const body = await res.json().catch(() => ({}))
      if (res.status === 403) return { denied: body?.detail?.reason ?? 'The DEVEX brief of this project is not open to you.' }
      if (!res.ok) {
        const failure = new Error(typeof body?.detail === 'string' ? body.detail : body?.detail?.message ?? `The server answered ${res.status}.`) as Error & { status?: number }
        failure.status = res.status
        throw failure
      }
      return { data: body as DevexBriefData }
    },
  })
  const answer = query.data
  return {
    loading: valid && query.isLoading,
    data: answer && 'data' in answer ? answer.data : null,
    denied: answer && 'denied' in answer ? answer.denied : null,
    error: query.isError ? (query.error as Error).message : null,
  }
}

/** Pre-FID spend by year for the returns calculation: the spend wave when it is
 *  in the brief, else the register total in one year, else nothing. */
export function preFidByYear(brief: DevexBriefData | null): { eur: number[]; basis: 'SPEND_WAVE' | 'PACKAGES' | 'NONE' } {
  const funding = brief?.funding
  if (funding && funding.total_eur > 0) {
    const eur = funding.years.map(y => Object.values(y.layers).reduce((s, v) => s + v, 0)).filter(v => v > 0)
    return { eur, basis: 'SPEND_WAVE' }
  }
  const total = brief?.summary?.pre_fid_spend_eur ?? 0
  return total > 0 ? { eur: [total], basis: 'PACKAGES' } : { eur: [], basis: 'NONE' }
}
