// Screen: API client (no screen)
//
// KYC/KYB, from /api/v1/kyc. Replaces the `localStorage` persistence in
// kycState.ts, which held ~45 profile fields plus the KYB record — legal name,
// registration number, VAT id, registered address and BENEFICIAL OWNERS — in a
// single browser profile.
//
// THE POINT OF THIS FILE: no function here takes a user id or a company id.
// The server reads both from the bearer token, and migration 051's policies
// enforce the same thing one layer down: a user reaches their own KYC profile,
// GEX staff reach any (vetting is what KYC is for), and a colleague at the same
// company reaches none.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/kyc'

/** Where a stored value came from. VERIFIED is never writable from here. */
export type Provenance = 'SEED' | 'EXTERNAL_PRIOR' | 'CLIENT_ASSERTED' | 'VERIFIED'

export interface RemoteKycState {
  kycCompleted: boolean
  kycRole: string | null
  kycProfile: Record<string, unknown> | null
  company: string | null
  kybStatus: 'none' | 'pending_colleague' | 'completed'
  kybData: Record<string, unknown> | null
  provenance?: { kyc?: Provenance | null; kyb?: Provenance | null }
  verified?: { kyc_by?: string | null; kyc_at?: string | null }
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
      detail = body?.detail ?? detail
    } catch { /* keep the status */ }
    throw new Error(detail)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const fetchKycState = () => call<RemoteKycState>('/state')

export const putProfile = (body: {
  profile: Record<string, unknown>
  kyc_role?: string | null
  completed?: boolean
  provenance?: Exclude<Provenance, 'VERIFIED'>
  source_ref?: string | null
}) => call('/profile', { method: 'PUT', body: JSON.stringify(body) })

export const putKyb = (body: Record<string, unknown>) =>
  call('/kyb', { method: 'PUT', body: JSON.stringify(body) })

export const listInvitations = () =>
  call<Array<Record<string, unknown>>>('/kyb/invitations')

export const createInvitation = (body: {
  email: string; company_name: string; company_domain?: string | null
}) => call('/kyb/invitations', { method: 'POST', body: JSON.stringify(body) })

export const acceptInvitation = (email: string) =>
  call('/kyb/invitations/accept', { method: 'POST', body: JSON.stringify({ email }) })

/** One-time move of whatever this browser still holds. Written as
 *  CLIENT_ASSERTED: the user did type it, but nobody has checked it. */
export const importLocal = (state: unknown) =>
  call<{ imported: { profile: boolean; kyb: boolean } }>(
    '/import-local', { method: 'POST', body: JSON.stringify(state) })
