const API_PREFIX = '/api/v1/adversarial-reviews'

async function fetchAdversarial<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export interface PromptPreset {
  id: string
  prompt_card_id: string
  agent_id: string
  employee_name: string
  actor_type: string
  category: string
  subtype: string
  sophistication: number
  tone: string
  trust_trigger: string
  cooperation_priority: string
  description: string
}

export interface AdversarialFinding {
  id: string
  review_id: string
  kind: string
  classification: string
  severity: string
  title: string
  detail: string
  owner_role?: string | null
  blocking: boolean
  evidence_refs: string[]
  created_by: string
  created_at: string
}

export interface AdversarialHandoff {
  id: string
  review_id: string
  from_role?: string | null
  to_role: string
  plain_language: string
  status: string
  due_at?: string | null
  created_by: string
  created_at: string
}

export interface AdversarialReview {
  id: string
  project_id: string
  actor_type: string
  target_type?: string | null
  target_id?: string | null
  target_route?: string | null
  screen_title?: string | null
  prompt_preset_id?: string | null
  prompt_card_id?: string | null
  agent_id?: string | null
  employee_name?: string | null
  category?: string | null
  subtype?: string | null
  sophistication?: number | null
  summary?: string | null
  what_it_seems_to_do?: string | null
  what_it_gets_wrong?: string | null
  what_is_missing?: string | null
  what_feels_dangerous?: string | null
  cooperation_risk?: string | null
  trust_increase_needed?: string | null
  clean_handoff_note?: string | null
  final_stance: string
  trust_delta: number
  status: string
  created_by: string
  resolution_note?: string | null
  resolved_by?: string | null
  correlation_id: string
  created_at: string
  updated_at: string
  resolved_at?: string | null
  blocking_findings: number
  critical_findings: number
  findings: AdversarialFinding[]
  handoffs: AdversarialHandoff[]
}

export interface AdversarialReviewSummary {
  project_id: string
  actor_type?: string | null
  total_reviews: number
  open_reviews: number
  escalated_reviews: number
  resolved_reviews: number
  blocking_findings: number
  critical_findings: number
  net_trust_delta: number
  owner_roles: string[]
  stance_counts: Record<string, number>
  recent_reviews: Array<{
    id: string
    actor_type: string
    agent_id?: string | null
    screen_title?: string | null
    target_route?: string | null
    status: string
    final_stance: string
    blocking_findings: number
    critical_findings: number
    created_at: string
  }>
  recommended_presets: PromptPreset[]
}

export const adversarialReviewsAPI = {
  health: () => fetchAdversarial<{ status: string }>('/health'),

  getPromptPresets: (actorType?: string) =>
    fetchAdversarial<PromptPreset[]>(`/prompt-presets${actorType ? `?actor_type=${encodeURIComponent(actorType)}` : ''}`),

  getProjectSummary: (projectId: string, actorType?: string) =>
    fetchAdversarial<AdversarialReviewSummary>(
      `/project/${encodeURIComponent(projectId)}/summary${actorType ? `?actor_type=${encodeURIComponent(actorType)}` : ''}`
    ),

  listProjectReviews: (projectId: string, actorType?: string) =>
    fetchAdversarial<AdversarialReview[]>(
      `/project/${encodeURIComponent(projectId)}${actorType ? `?actor_type=${encodeURIComponent(actorType)}` : ''}`
    ),

  createReview: (payload: Record<string, unknown>) =>
    fetchAdversarial<AdversarialReview>('/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  addFinding: (reviewId: string, payload: Record<string, unknown>) =>
    fetchAdversarial<AdversarialFinding>(`/${encodeURIComponent(reviewId)}/findings`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  addHandoff: (reviewId: string, payload: Record<string, unknown>) =>
    fetchAdversarial<AdversarialHandoff>(`/${encodeURIComponent(reviewId)}/handoffs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateStatus: (reviewId: string, payload: Record<string, unknown>) =>
    fetchAdversarial<AdversarialReview>(`/${encodeURIComponent(reviewId)}/status`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
