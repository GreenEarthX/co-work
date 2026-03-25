// API Client for GreenEarthX Platform
const API_BASE_URL = 'http://localhost:8000/api/v1'

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_BASE_URL}${endpoint}`
  
  console.log(`[API] ${options.method || 'GET'} ${endpoint}`)
  if (options.body) {
    console.log('[API] Request body:', JSON.parse(options.body as string))
  }
  
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })
  
  console.log(`[API] Response status: ${response.status}`)
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    console.error('[API] Error:', error)
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  
  const data = await response.json()
  console.log('[API] Response data:', data)
  
  return data
}

// Capacities API
export const capacitiesAPI = {
  create: (data: any) => fetchAPI('/capacities/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  list: () => fetchAPI('/capacities/'),
  get: (id: string) => fetchAPI(`/capacities/${id}`),
  delete: (id: string) => fetchAPI(`/capacities/${id}`, { method: 'DELETE' }),
}

// Offers API
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

// RFQs API
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

// Matching API
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

// Contracts API
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

// Tokens API
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

// ============================================
// FINANCE API - NEW
// ============================================

export const financeAPI = {
  // Stage Gates
  getStageGates: () => fetchAPI('/finance/stage-gates'),
  
  // Covenants
  getCovenants: () => fetchAPI('/finance/covenants'),
  
  // Insurance
  getInsurance: () => fetchAPI('/finance/insurance'),
  
  // Guarantees
  getGuarantees: () => fetchAPI('/finance/guarantees'),
  
  // Contracts (Revenue/Offtake)
  getContracts: () => fetchAPI('/finance/contracts'),
  
  // Risks
  getRisks: () => fetchAPI('/finance/risks'),
}
