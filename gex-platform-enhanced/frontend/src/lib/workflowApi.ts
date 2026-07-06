// Screen: API client (no screen)
export type WorkflowStateValue =
  | 'DRAFT'
  | 'COMPUTED'
  | 'REVIEWED'
  | 'INSURANCE_REVIEWED'  // Insurance risk engineer sign-off captured before APPROVED
  | 'APPROVED'
  | 'EXPORTED'
  | 'SHARED_EXTERNAL'

export interface WorkflowPromotionBlocker {
  review_id: string
  finding_id: string
  severity: string
  title: string
  owner_role?: string | null
  actor_type: string
  screen_title?: string | null
  target_route?: string | null
  review_status: string
  created_at: string
}

export interface WorkflowPromotionGate {
  project_id?: string | null
  blocked: boolean
  blocking_findings: number
  blocking_reviews: number
  critical_findings: number
  summary?: string | null
  blocking_titles: string[]
  blockers: WorkflowPromotionBlocker[]
}

export interface InsuranceReviewRecord {
  /** Risk engineer full name */
  reviewer_name: string
  /** Firm / institution of the risk engineer */
  reviewer_firm: string
  /** Professional qualification (e.g. CERA, CEng, IRM) */
  reviewer_qualification?: string | null
  /** Documents reviewed (e.g. HAZOP report ref, process design basis) */
  documents_reviewed: string[]
  /** HAZOP/HAZID study reference linked to this review */
  hazop_reference?: string | null
  /** ISO timestamp of sign-off */
  signed_at: string
}

export interface WorkflowStateResponse {
  object_type: string
  object_id: string
  project_id?: string | null
  state: WorkflowStateValue
  computed_at?: string | null
  reviewed_by?: string | null
  /** Populated when state reaches INSURANCE_REVIEWED */
  insurance_review?: InsuranceReviewRecord | null
  approved_by?: string | null
  export_hash?: string | null
  is_stale: boolean
  promotion_blocked: boolean
  blocking_findings: number
  blocking_reviews: number
  critical_findings: number
  promotion_gate_summary?: string | null
  blocking_titles: string[]
  blockers: WorkflowPromotionBlocker[]
}

export class WorkflowApiError extends Error {
  status: number
  code?: string
  promotionGate?: WorkflowPromotionGate

  constructor(message: string, status: number, data?: { code?: string; promotion_gate?: WorkflowPromotionGate }) {
    super(message)
    this.name = 'WorkflowApiError'
    this.status = status
    this.code = data?.code
    this.promotionGate = data?.promotion_gate
  }
}

async function fetchWorkflow<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/workflow${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: `HTTP ${response.status}` }))

    throw new WorkflowApiError(
      error.detail || `HTTP ${response.status}`,
      response.status,
      error,
    )
  }

  return response.json()
}

export const workflowAPI = {
  getState: (objectType: string, objectId: string, projectId?: string) => {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
    return fetchWorkflow<WorkflowStateResponse>(
      `/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}/state${query}`
    )
  },
}
