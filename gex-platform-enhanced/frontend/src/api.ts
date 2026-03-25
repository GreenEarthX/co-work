// API Client for GreenEarthX Platform
const API_BASE_URL = 'http://localhost:8000/api/v1'

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE_URL}${endpoint}`

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// ═══════════════════════════════════════════════════════════════
// Capacities API — prefix: /api/v1/capacities
// ═══════════════════════════════════════════════════════════════
export const capacitiesAPI = {
  create: (data: any) => fetchAPI('/capacities/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: () => fetchAPI('/capacities/'),
  get: (id: string) => fetchAPI(`/capacities/${id}`),
  delete: (id: string) => fetchAPI(`/capacities/${id}`, { method: 'DELETE' }),
}

// ═══════════════════════════════════════════════════════════════
// Offers API — prefix: /api/v1/marketplace
// ═══════════════════════════════════════════════════════════════
export const offersAPI = {
  create: (data: any) => fetchAPI('/marketplace/offers', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/marketplace/offers${query ? `?${query}` : ''}`)
  },
  get: (id: string) => fetchAPI(`/marketplace/offers/${id}`),
  updateStatus: (id: string, status: string) =>
    fetchAPI(`/marketplace/offers/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  delete: (id: string) => fetchAPI(`/marketplace/offers/${id}`, { method: 'DELETE' }),
}

// ═══════════════════════════════════════════════════════════════
// RFQs API — prefix: /api/v1/matching
// ═══════════════════════════════════════════════════════════════
export const rfqsAPI = {
  create: (data: any) => fetchAPI('/matching/rfqs', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/matching/rfqs${query ? `?${query}` : ''}`)
  },
  get: (id: string) => fetchAPI(`/matching/rfqs/${id}`),
}

// ═══════════════════════════════════════════════════════════════
// Matching API — prefix: /api/v1/matching
// ═══════════════════════════════════════════════════════════════
export const matchingAPI = {
  run: (data?: any) => fetchAPI('/matching/run', {
    method: 'POST',
    body: data ? JSON.stringify(data) : '{}',
  }),
  list: (params?: { molecule?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/matching/${query ? `?${query}` : ''}`)
  },
  get: (id: string) => fetchAPI(`/matching/${id}`),
  accept: (id: string) => fetchAPI(`/matching/${id}/accept`, { method: 'POST' }),
}

// ═══════════════════════════════════════════════════════════════
// Contracts API — prefix: /api/v1/contracts
// ═══════════════════════════════════════════════════════════════
export const contractsAPI = {
  create: (data: any) => fetchAPI('/contracts/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: (params?: { status?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/contracts/${query ? `?${query}` : ''}`)
  },
  get: (id: string) => fetchAPI(`/contracts/${id}`),
  updateStatus: (id: string, status: string) =>
    fetchAPI(`/contracts/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  getAcceptedMatches: () => fetchAPI('/contracts/accepted-matches/available'),
}

// ═══════════════════════════════════════════════════════════════
// Tokens API — prefix: /api/v1/tokens
// ═══════════════════════════════════════════════════════════════
export const tokensAPI = {
  create: (data: any) => fetchAPI('/tokens/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: (params?: { capacity_id?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/tokens/${query ? `?${query}` : ''}`)
  },
  get: (id: string) => fetchAPI(`/tokens/${id}`),
  updateCompliance: (id: string, data: any) =>
    fetchAPI(`/tokens/${id}/compliance`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  delete: (id: string) => fetchAPI(`/tokens/${id}`, { method: 'DELETE' }),
}

// ═══════════════════════════════════════════════════════════════
// Finance API — prefix: /api/v1/finance
// ═══════════════════════════════════════════════════════════════
export const financeAPI = {
  getStageGates: () => fetchAPI('/finance/stage-gates'),
  getCovenants: () => fetchAPI('/finance/covenants'),
  getInsurance: () => fetchAPI('/finance/insurance'),
  getGuarantees: () => fetchAPI('/finance/guarantees'),
  getContracts: () => fetchAPI('/finance/contracts'),
  getRisks: () => fetchAPI('/finance/risks'),
}

// ═══════════════════════════════════════════════════════════════
// Bankability API — prefix: /api/v1/bankability
// Live engine integration (platform proxies to gex_pf_engine)
// ═══════════════════════════════════════════════════════════════
export const bankabilityAPI = {
  evaluate: (projectId: string = 'default') =>
    fetchAPI(`/bankability/evaluate?project_id=${projectId}`),

  evaluateForPersona: (persona: string, projectId: string = 'default') =>
    fetchAPI(`/bankability/evaluate/persona?persona=${persona}&project_id=${projectId}`),

  getGates: () => fetchAPI('/bankability/gates'),

  getRules: () => fetchAPI('/bankability/rules'),

  updateEvidence: (data: {
    project_id?: string
    evidence_key: string
    new_status: string
    submitted_by?: string
    notes?: string
  }) => fetchAPI('/bankability/evidence', {
    method: 'POST',
    body: JSON.stringify({ project_id: 'default', ...data }),
  }),

  listEvidence: (projectId: string = 'default') =>
    fetchAPI(`/bankability/evidence?project_id=${projectId}`),

  seedDemo: (projectId: string = 'default') =>
    fetchAPI(`/bankability/evidence/seed?project_id=${projectId}`, { method: 'POST' }),

  checkRegression: (projectId: string = 'default') =>
    fetchAPI(`/bankability/regression/check?project_id=${projectId}`),

  health: () => fetchAPI('/bankability/health'),
}

// ═══════════════════════════════════════════════════════════════
// Finance Model API — prefix: /api/v1/finance-model
// Proxied to gex_pf_engine (port 8001)
// ═══════════════════════════════════════════════════════════════
export const financeModelAPI = {
  health: () => fetchAPI('/finance-model/health'),

  calculateCfads: (params: {
    production_mtpd: number
    offtake_price_eur_kg: number
    opex_eur_kg: number
    subsidies?: Record<string, number>
    maintenance_capex?: number
    period_days?: number
  }) => fetchAPI('/finance-model/cfads', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  modelLifetime: (params: {
    capacity_mtpd: number
    price_eur_kg: number
    opex_eur_kg: number
    total_capex: number
    senior_debt_amount: number
    interest_rate: number
    tenor_years: number
    operations_start_year?: number
  }) => fetchAPI('/finance-model/lifetime', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  checkCovenants: (params: {
    dscr: number
    dsra_funded: boolean
    completion_guarantee: boolean
    covenant_requirements: Record<string, any>
  }) => fetchAPI('/finance-model/covenants', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  executeWaterfall: (params: {
    cfads: number
    senior_debt_service: number
    junior_debt_service?: number
    mezzanine_service?: number
    dsra_required?: number
    maintenance_reserve?: number
  }) => fetchAPI('/finance-model/waterfall', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  calculateMetrics: (params: {
    revenue: number
    opex: number
    capex: number
    debt_service: number
    period: string
  }) => fetchAPI('/finance-model/metrics', {
    method: 'POST',
    body: JSON.stringify(params),
  }),
}

// ═══════════════════════════════════════════════════════════════
// WAE Approvals API — prefix: /api/v1/approvals
// Workflow Authorization Engine — countersignature + quorum
// ═══════════════════════════════════════════════════════════════
export const approvalsAPI = {
  health: () => fetchAPI('/approvals/health'),

  evaluate: (params: {
    initiator_user_id: string
    action_type: string
    resource_id?: string
    project_id?: string
    payload?: Record<string, any>
    amount?: number
    volume?: number
  }) => fetchAPI('/approvals/evaluate', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  getPending: (params?: { company_id?: string; project_id?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/approvals/pending${query ? `?${query}` : ''}`)
  },

  getRequest: (requestId: string) => fetchAPI(`/approvals/${requestId}`),

  decide: (requestId: string, params: {
    approver_user_id: string
    decision: 'APPROVE' | 'REJECT'
    reason_text?: string
  }) => fetchAPI(`/approvals/${requestId}/decide`, {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  getAuditTrail: (resourceId: string) =>
    fetchAPI(`/approvals/audit-trail/${resourceId}`),

  listPolicies: () => fetchAPI('/approvals/policies/list'),

  getSodPairs: () => fetchAPI('/approvals/sod/pairs'),
}

// ═══════════════════════════════════════════════════════════════
// Commitments API — prefix: /api/v1/commitments
// CSS — Commitment Signature Service (non-repudiation)
// ═══════════════════════════════════════════════════════════════
export const commitmentsAPI = {
  health: () => fetchAPI('/commitments/health'),

  sign: (params: {
    initiator_user_id: string
    initiator_company_id: string
    action_type: string
    project_id: string
    payload: Record<string, any>
    approval_request_id?: string
    approver_snapshots?: Record<string, any>[]
  }) => fetchAPI('/commitments/sign', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  countersign: (commitmentId: string, params: {
    counterparty_user_id: string
    counterparty_company_id: string
  }) => fetchAPI(`/commitments/${commitmentId}/countersign`, {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  verify: (commitmentId: string) =>
    fetchAPI(`/commitments/${commitmentId}/verify`),

  listForProject: (projectId: string) =>
    fetchAPI(`/commitments/project/${projectId}`),

  get: (commitmentId: string) =>
    fetchAPI(`/commitments/${commitmentId}`),
}

// ═══════════════════════════════════════════════════════════════
// Plant Data API — prefix: /api/v1/plant-data
// OT/IT Boundary — inbound telemetry from registered gateways
// ═══════════════════════════════════════════════════════════════
export const plantDataAPI = {
  health: () => fetchAPI('/plant-data/health'),

  getForProject: (projectId: string, params?: { data_type?: string; limit?: number }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/plant-data/data/${projectId}${query ? `?${query}` : ''}`)
  },

  getDemoData: (projectId: string) =>
    fetchAPI(`/plant-data/demo/${projectId}`),

  listGateways: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : ''
    return fetchAPI(`/plant-data/gateways${query}`)
  },

  getGateway: (gatewayId: string) =>
    fetchAPI(`/plant-data/gateways/${gatewayId}`),
}

// ═══════════════════════════════════════════════════════════════
// CISO Security Extension API — prefix: /api/v1/ciso
// Barriers, Residency, Gateways (Domains 3, 4, 5)
// ═══════════════════════════════════════════════════════════════
export const cisoSecurityAPI = {
  listBarriers: () => fetchAPI('/ciso/barriers'),
  getBarrier: (barrierId: string) => fetchAPI(`/ciso/barriers/${barrierId}`),
  createBarrier: (params: {
    side_a: string
    side_b: string
    barrier_type?: string
    applies_to_data?: string[]
    description?: string
  }) => fetchAPI('/ciso/barriers', {
    method: 'POST',
    body: JSON.stringify(params),
  }),

  listResidencyPolicies: () => fetchAPI('/ciso/residency/policies'),
  upsertResidencyPolicy: (params: {
    data_category: string
    required_jurisdiction: string
    storage_zone: string
    note?: string
  }) => fetchAPI('/ciso/residency/policies', {
    method: 'POST',
    body: JSON.stringify(params),
  }),
  getResidencyAudit: () => fetchAPI('/ciso/residency/audit'),

  listGateways: (projectId?: string) => {
    const query = projectId ? `?project_id=${projectId}` : ''
    return fetchAPI(`/ciso/gateways${query}`)
  },
}
