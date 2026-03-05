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
