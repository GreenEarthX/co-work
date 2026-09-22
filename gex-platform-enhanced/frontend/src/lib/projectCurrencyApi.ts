// Screen: API client (no screen)
//
// The project's working base currency (GET/PUT /api/v1/tea/project/{id}/currency).
// OpenPyTEA costs in USD; GEX converts every new TEA run to this currency at a
// fixed dated rate. The server records who set it from the bearer token — the
// client names no owner.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/tea/project'

// Must match the backend SUPPORTED_CURRENCIES (tea_engine.integrity.USD_TO_BASE).
export const SUPPORTED_CURRENCIES = ['EUR', 'USD'] as const
export type Currency = (typeof SUPPORTED_CURRENCIES)[number]

export interface ProjectCurrency {
  project_id: string
  base_currency: string
  is_default: boolean
  set_by?: string | null
  set_at?: string | null
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAuthToken()
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* keep the status */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export function getProjectCurrency(projectId: string): Promise<ProjectCurrency> {
  return call<ProjectCurrency>(`/${encodeURIComponent(projectId)}/currency`)
}

export function setProjectCurrency(
  projectId: string,
  baseCurrency: Currency,
): Promise<ProjectCurrency> {
  return call<ProjectCurrency>(`/${encodeURIComponent(projectId)}/currency`, {
    method: 'PUT',
    body: JSON.stringify({ base_currency: baseCurrency }),
  })
}
