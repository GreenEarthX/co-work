/**
 * Test data shaped like the gate engine's readout (rules 4.1.0) for a
 * grid-connected, project-financed plant with no verified evidence: the state
 * the engine reported for HamburgOne on 2026-09-30. Gate names, capital labels
 * and gating gates are the engine's.
 */
import { vi } from 'vitest'
import type { EngineGate, EngineReadout } from '@/lib/engineReadout'

const GATES: Array<[string, string, number]> = [
  ['G0_SITE_RIGHTS', 'Site Rights & Social License', 4],
  ['G1_GRID_UTILITIES_REALITY', 'Power, Utilities & Technology Basis', 15],
  ['G2_CERTIFICATION_PATH_LOCKED', 'Green Certification Pathway', 6],
  ['G3_INPUTS_SECURED', 'Feedstock & Logistics Terms', 4],
  ['G4_OFFTAKE_BANKABLE', 'Binding Offtake', 10],
  ['G5_EPC_RISK_PRICED', 'EPC Risk Priced', 12],
  ['G6_IE_SIGNOFF', 'Independent Engineer Sign-off', 5],
  ['G7_INSURANCE_BOUND', 'Insurability Confirmed', 5],
  ['G8_AUDIT_GRADE_MODEL', 'Audit-Grade Financial Model', 7],
  ['G9_PERMITS_SAFE', 'Permits Granted & Appeal Risk Managed', 6],
  ['G10_FINANCIAL_CLOSE_CP', 'Financial Close', 8],
  ['G11_COD_STABILIZATION', 'COD & Stabilization', 7],
]

const DEAL_KILLERS: Record<string, Array<[string, string]>> = {
  G0_SITE_RIGHTS: [['land_option_or_lease_executed', 'Land Option or Lease Executed']],
  G1_GRID_UTILITIES_REALITY: [['grid_interconnection_study', 'Grid Interconnection Study']],
}

function gate([gate_id, gate_name, total]: [string, string, number]): EngineGate {
  const killers = DEAL_KILLERS[gate_id] ?? []
  return {
    gate_id, gate_name, determination: 'BLOCKED', is_complete: false,
    verified_count: 0, total_evidence: total, completion_pct: 0,
    blocking_items: killers.map(([k]) => k),
    blocked_reasons: [],
    deal_killers_blocked: killers.map(([k]) => k),
    evidence_detail: killers.map(([key, label]) => ({ key, label, status: 'NOT_STARTED', severity: 'deal_killer' })),
    financing_applicable: true,
  }
}

const CAPITAL: Array<[string, string, string]> = [
  ['GRANTS_TA', 'Grants & TA', 'G0_SITE_RIGHTS'],
  ['SEED_VC_ANGEL', 'Seed / VC / Angel', 'G1_GRID_UTILITIES_REALITY'],
  ['STRATEGIC_EQUITY', 'Strategic Equity', 'G3_INPUTS_SECURED'],
  ['PROJECT_EQUITY', 'Project Equity', 'G4_OFFTAKE_BANKABLE'],
  ['DFI_MEZZ_GUARANTEES', 'DFI / Mezz / Guarantees', 'G6_IE_SIGNOFF'],
  ['SENIOR_DEBT_COMMITMENT', 'Senior Debt Credit Approval (conditional)', 'G8_AUDIT_GRADE_MODEL'],
  ['DEBT_DRAWDOWN', 'Debt Drawdown', 'G10_FINANCIAL_CLOSE_CP'],
  ['REFINANCE_BONDS_INFRA', 'Refinance / Bonds / Infra', 'G11_COD_STABILIZATION'],
]

export function speculativeReadout(overrides: Partial<EngineReadout> = {}): EngineReadout {
  return {
    project_id: 'proj_hamburgone_emethanol',
    rules_version: '4.1.0',
    project_phase: 'development',
    current_state: 'SPECULATIVE',
    state_label: 'Idea stage — nothing can be committed yet',
    next_state: 'TECHNICALLY_PLAUSIBLE',
    next_state_label: 'Site and technology basis confirmed',
    gates_blocking_next_state: ['G0_SITE_RIGHTS', 'G1_GRID_UTILITIES_REALITY'],
    commitments_blocking_next_state: [],
    gate_evaluations: GATES.map(gate),
    capital_unlocks: CAPITAL.map(([capital_type, label, g]) => ({
      capital_type, label, decision_eligible: false, is_unlocked: false,
      financing_applicable: true, gating_gates: [g],
    })),
    total_verified: 0,
    total_evidence: 89,
    offtake: { level: 'O0', reasons: ['No verified offtake document with a declared maturity.'] },
    epc: { level: 'E0', reasons: ['No contracting strategy and no verified EPC document.'] },
    regression: null,
    ...overrides,
  }
}

export const ENGINE_RULES = {
  rules_version: '4.1.0',
  capital_semantics:
    "A satisfied gate makes a project eligible for the named capital provider's decision. " +
    'GEX does not commit, release or draw capital.',
  persona_gates: {
    FINANCE: ['G4_OFFTAKE_BANKABLE', 'G6_IE_SIGNOFF', 'G7_INSURANCE_BOUND', 'G8_AUDIT_GRADE_MODEL', 'G10_FINANCIAL_CLOSE_CP'],
  },
}

export const VOCABULARY: Record<string, { terms: Array<{ canonical: string; label: string }> }> = {
  readiness: {
    terms: [
      { canonical: 'SPECULATIVE', label: 'Speculative' },
      { canonical: 'TECHNICALLY_PLAUSIBLE', label: 'Technically plausible' },
    ],
  },
  project_phase: { terms: [{ canonical: 'development', label: 'Development' }] },
}

type Reply = { status: number; body: unknown }

/**
 * Stub `fetch` with a router: the first matching URL fragment answers. Returns
 * the mock so a test can assert which URLs were (or were not) requested.
 */
export function stubFetch(routes: Array<[string, Reply | (() => Reply)]>) {
  const mock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const hit = routes.find(([fragment]) => url.includes(fragment))
    const reply = hit ? (typeof hit[1] === 'function' ? hit[1]() : hit[1]) : { status: 404, body: { detail: 'not stubbed' } }
    return {
      ok: reply.status >= 200 && reply.status < 300,
      status: reply.status,
      json: async () => reply.body,
    } as Response
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

export function engineRoutes(readouts: Record<string, EngineReadout | Reply>): Array<[string, Reply]> {
  return [
    ...Object.entries(readouts).map(([projectId, r]): [string, Reply] => [
      `/bankability/projects/${projectId}/bankability/EXECUTIVE`,
      'status' in r && 'body' in r ? (r as Reply) : { status: 200, body: r },
    ]),
    ['/bankability/rules', { status: 200, body: ENGINE_RULES }],
    ['/vocabulary/readiness', { status: 200, body: VOCABULARY.readiness }],
    ['/vocabulary/project_phase', { status: 200, body: VOCABULARY.project_phase }],
  ]
}
