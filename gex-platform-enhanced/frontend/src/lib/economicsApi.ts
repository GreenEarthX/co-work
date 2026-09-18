// Screen: API client (no screen)
//
// TEA read model — the APPROVED economic picture for one project, from
// GET /api/v1/economics/snapshot/{projectId}.
//
// The refusals carry as much meaning as the data, so they are modelled as
// states rather than thrown away as errors: "not approved yet" is a thing the
// screen must say out loud, not an exception. The backend deliberately returns
// no figures with a 409 — nothing here invents them.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/economics'

export interface GhgClaim {
  claim_id: string
  state: string
  approved: boolean
  method: string | null
  approved_by: string | null
  /** Present only when the claim itself is approved. */
  value?: number
  unit?: string
}

export interface EconomicsSnapshot {
  project_id: string
  claim: {
    claim_id: string
    pathway_id: string | null
    state: string
    approved_by: string | null
    approval_decision_id: string | null
    valid_from: string
    created_at: string
    supersedes_claim_id: string | null
    run_evidence_id: string | null
  }
  basis: {
    engine: string | null
    cost_basis_hash: string
    nameplate_capacity: number | null
    nameplate_unit: string | null
  }
  economics: {
    capex_eur: number | null
    opex_eur_per_year: number | null
    lcop: number | null
    lcop_basis: string
  }
  lca: {
    g_co2e_per_mj?: GhgClaim | null
    ghg_saving?: GhgClaim | null
    method_note?: string
  }
  integrity: { ascertained: boolean; note: string }
  not_available: Record<string, string>
}

export type EconomicsSnapshotState =
  | { kind: 'approved'; data: EconomicsSnapshot }
  | { kind: 'not-approved'; claimId?: string; state?: string; message: string }
  | { kind: 'none' }
  | { kind: 'forbidden' }
  | { kind: 'error'; message: string }

export async function fetchEconomicsSnapshot(
  projectId: string,
  pathwayId?: string,
): Promise<EconomicsSnapshotState> {
  const token = getAuthToken()
  const q = pathwayId ? `?pathway_id=${encodeURIComponent(pathwayId)}` : ''
  let res: Response
  try {
    res = await fetch(`${API_PREFIX}/snapshot/${encodeURIComponent(projectId)}${q}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  } catch (e) {
    return { kind: 'error', message: e instanceof Error ? e.message : 'network error' }
  }

  if (res.ok) return { kind: 'approved', data: (await res.json()) as EconomicsSnapshot }
  if (res.status === 404) return { kind: 'none' }
  // 403 covers "not entitled" whether or not the project exists — the backend
  // answers alike on purpose, so the status cannot enumerate the portfolio.
  if (res.status === 403 || res.status === 401) return { kind: 'forbidden' }

  if (res.status === 409) {
    const body = await res.json().catch(() => null)
    const d = (body?.detail ?? {}) as Record<string, unknown>
    return {
      kind: 'not-approved',
      claimId: typeof d.claim_id === 'string' ? d.claim_id : undefined,
      state: typeof d.state === 'string' ? d.state : undefined,
      message: typeof d.message === 'string'
        ? d.message
        : 'The live base case has not been approved.',
    }
  }
  return { kind: 'error', message: `HTTP ${res.status}` }
}
