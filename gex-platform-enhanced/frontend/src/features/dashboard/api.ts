const API_BASE_URL = 'http://localhost:8000/api/v1'

// Generic fetch wrapper
async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }
  
  return response.json()
}

// Capacities API
export const capacitiesAPI = {
  create: (data: any) => fetchAPI('/capacities/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  list: () => fetchAPI('/capacities/'),
  
  get: (id: string) => fetchAPI(`/capacities/${id}`),
  
  delete: (id: string) => fetchAPI(`/capacities/${id}`, {
    method: 'DELETE',
  }),
}

// Offers API
export const offersAPI = {
  create: (data: any) => fetchAPI('/offers/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/offers/?${query}`)
  },
  
  get: (id: string) => fetchAPI(`/offers/${id}`),
  
  updateStatus: (id: string, status: string) => 
    fetchAPI(`/offers/${id}/status?status=${status}`, {
      method: 'PATCH',
    }),
  
  delete: (id: string) => fetchAPI(`/offers/${id}`, {
    method: 'DELETE',
  }),
}

// RFQs API
export const rfqsAPI = {
  create: (data: any) => fetchAPI('/rfqs/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  list: (params?: { molecule?: string; status?: string }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/rfqs/?${query}`)
  },
  
  get: (id: string) => fetchAPI(`/rfqs/${id}`),
}

// Matching API
export const matchingAPI = {
  run: (data: any) => fetchAPI('/matching/run', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  list: (params?: { molecule?: string; min_score?: number }) => {
    const query = new URLSearchParams(params as any).toString()
    return fetchAPI(`/matching/?${query}`)
  },
  
  get: (id: string) => fetchAPI(`/matching/${id}`),
  
  accept: (id: string) => fetchAPI(`/matching/${id}/accept`, {
    method: 'POST',
  }),
}

// Tokenisation API
export const tokensAPI = {
  create: (data: any) => fetchAPI('/tokens/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  
  list: (capacityId?: string) => {
    const query = capacityId ? `?capacity_id=${capacityId}` : ''
    return fetchAPI(`/tokens/${query}`)
  },
  
  get: (id: string) => fetchAPI(`/tokens/${id}`),
  
  updateCompliance: (id: string, data: any) => 
    fetchAPI(`/tokens/${id}/compliance`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
}