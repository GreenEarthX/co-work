// Screen: API client (no screen) — finance entitlement checks (Ticket 1a)
//
// The backend is the authoritative boundary (it 403s the data regardless).
// This client powers the FRONTEND ROUTE GUARD, whose only job is UX: show an
// Access-Denied / Project-Required state instead of a broken page.

export interface EntitlementCheck {
  allowed: boolean
  basis: 'role' | 'project_entitlement' | 'dev_global' | 'none'
  reason: string
  project_id: string | null
}

/**
 * Ask the backend whether the current caller may access project-finance content
 * for `projectId`. Identity travels via the global fetch auth-bridge headers
 * (x-demo-* and Authorization), so no args beyond the project are needed.
 */
export async function checkFinanceEntitlement(projectId: string | null): Promise<EntitlementCheck> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  const res = await fetch(`/api/v1/entitlements/check${qs}`)
  if (!res.ok) throw new Error(`entitlement check failed: ${res.status}`)
  return res.json()
}

export interface Entitlement {
  entitlement_id: string
  user_id: string
  project_id: string
  capability: string
  granted_by: string
  granted_at: string
  reason: string | null
  expires_at: string | null
  revoked_at: string | null
  revoked_by: string | null
  status: 'active' | 'expired' | 'revoked'
}

export const entitlementsAPI = {
  list: (params?: { user_id?: string; project_id?: string }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString()
    return fetch(`/api/v1/entitlements${q ? `?${q}` : ''}`).then(r => r.json())
  },
  grant: (body: { user_id: string; project_id: string; capability?: string; reason?: string; expires_at?: string }) =>
    fetch('/api/v1/entitlements', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
  revoke: (entitlementId: string) =>
    fetch(`/api/v1/entitlements/${entitlementId}`, { method: 'DELETE' }).then(r => r.json()),
}
