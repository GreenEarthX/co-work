// Screen: API client (no screen)
// Regime-forked certification gate — reads the project's PERSISTED claims from the
// ledger and evaluates the gate for the fuel's pathway_class (RFNBO vs advanced
// biofuel). Backed by backend GET /api/v1/tea/certification-gate/{projectId}.
const API_PREFIX = '/api/v1/tea'

function authToken(): string | null {
  try {
    const saved = localStorage.getItem('gex_auth_session')
    return saved ? (JSON.parse(saved).token ?? null) : null
  } catch {
    return null
  }
}

export interface CertificationGate {
  fuel_id: string
  pathway_class: string
  certification_scheme: string
  ghg_method?: string
  us_credit?: string
  required_cert_claims: string[]
  waived_cert_claims: string[]
  missing_claims: string[]
  gate_open: boolean
}

export interface CertificationGateResult {
  project_id: string
  claim_states_from_ledger: Record<string, string>
  gate: CertificationGate
}

export async function fetchCertificationGate(
  projectId: string,
  fuelId: string,
  pathwayId?: string,
): Promise<CertificationGateResult> {
  const token = authToken()
  const q = new URLSearchParams({ fuel_id: fuelId })
  if (pathwayId) q.set('pathway_id', pathwayId)
  const res = await fetch(`${API_PREFIX}/certification-gate/${encodeURIComponent(projectId)}?${q}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}
