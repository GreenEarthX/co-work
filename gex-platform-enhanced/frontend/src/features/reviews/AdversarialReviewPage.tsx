import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  MessageSquareWarning,
  Plus,
  ShieldAlert,
  Siren,
  Workflow,
} from 'lucide-react'
import { CUSTOMER_PROJECTS, getProjectById } from '@/data/customerProjects'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { AdversarialReviewEntryCard } from '@/components/AdversarialReviewEntryCard'
import {
  adversarialReviewsAPI,
  type AdversarialReview,
  type AdversarialReviewSummary,
  type PromptPreset,
} from '@/lib/adversarialReviewsApi'

type ReviewStatus = 'OPEN' | 'ESCALATED' | 'RESOLVED' | 'WAIVED' | 'CLOSED'
type FinalStance = 'PROCEED' | 'PROCEED_WITH_CAUTION' | 'ESCALATE_INTERNALLY' | 'STOP'

interface ReviewCardProps {
  review: AdversarialReview
  onStatusChange: (reviewId: string, status: ReviewStatus, resolutionNote?: string) => Promise<void>
  onAddFinding: (reviewId: string, payload: Record<string, unknown>) => Promise<void>
  onAddHandoff: (reviewId: string, payload: Record<string, unknown>) => Promise<void>
}

function badgeClass(status: string): string {
  switch (status) {
    case 'ESCALATED':
      return 'bg-red-100 text-red-700 border-red-300'
    case 'RESOLVED':
      return 'bg-emerald-100 text-emerald-700 border-emerald-300'
    case 'WAIVED':
      return 'bg-amber-100 text-amber-700 border-amber-300'
    case 'CLOSED':
      return 'bg-gray-100 text-gray-700 border-gray-300'
    default:
      return 'bg-blue-100 text-blue-700 border-blue-300'
  }
}

function severityClass(severity: string): string {
  switch (severity) {
    case 'CRITICAL':
      return 'bg-red-100 text-red-700 border-red-300'
    case 'HIGH':
      return 'bg-orange-100 text-orange-700 border-orange-300'
    case 'MEDIUM':
      return 'bg-amber-100 text-amber-700 border-amber-300'
    default:
      return 'bg-slate-100 text-slate-700 border-slate-300'
  }
}

function stanceLabel(stance: string): string {
  return stance.replace(/_/g, ' ')
}

function FieldBlock({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">{label}</div>
      <p className="mt-1 text-sm leading-6 text-gray-700 whitespace-pre-wrap">{value}</p>
    </div>
  )
}

function ReviewCard({ review, onStatusChange, onAddFinding, onAddHandoff }: ReviewCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [showFindingForm, setShowFindingForm] = useState(false)
  const [showHandoffForm, setShowHandoffForm] = useState(false)
  const [resolutionNote, setResolutionNote] = useState('')
  const [findingDraft, setFindingDraft] = useState({
    kind: 'TRUST_PROBLEM',
    classification: 'MISSING',
    severity: 'MEDIUM',
    title: '',
    detail: '',
    owner_role: '',
    evidence_refs: '',
    created_by: review.created_by,
    blocking: true,
  })
  const [handoffDraft, setHandoffDraft] = useState({
    from_role: review.actor_type,
    to_role: '',
    plain_language: '',
    status: 'OPEN',
    due_at: '',
    created_by: review.created_by,
  })

  const active = !['RESOLVED', 'WAIVED', 'CLOSED'].includes(review.status)

  async function submitFinding() {
    if (!findingDraft.title.trim() || !findingDraft.detail.trim()) return
    await onAddFinding(review.id, {
      ...findingDraft,
      owner_role: findingDraft.owner_role || null,
      evidence_refs: findingDraft.evidence_refs
        .split(',')
        .map(item => item.trim())
        .filter(Boolean),
    })
    setFindingDraft({
      ...findingDraft,
      title: '',
      detail: '',
      owner_role: '',
      evidence_refs: '',
    })
    setShowFindingForm(false)
    setExpanded(true)
  }

  async function submitHandoff() {
    if (!handoffDraft.to_role.trim() || !handoffDraft.plain_language.trim()) return
    await onAddHandoff(review.id, {
      ...handoffDraft,
      from_role: handoffDraft.from_role || null,
      due_at: handoffDraft.due_at || null,
    })
    setHandoffDraft({
      ...handoffDraft,
      to_role: '',
      plain_language: '',
      due_at: '',
    })
    setShowHandoffForm(false)
    setExpanded(true)
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-gray-900">
              {review.screen_title || review.target_route || 'Adversarial review'}
            </span>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${badgeClass(review.status)}`}>
              {review.status}
            </span>
            <span className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[10px] font-bold text-gray-600">
              {stanceLabel(review.final_stance)}
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-500">
            {review.agent_id || review.prompt_card_id || review.actor_type}
            {review.employee_name ? ` · ${review.employee_name}` : ''}
            {review.target_route ? ` · ${review.target_route}` : ''}
          </div>
          {review.summary && (
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-700">{review.summary}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => onStatusChange(review.id, 'ESCALATED')}
            disabled={!active}
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 disabled:opacity-50"
          >
            Escalate
          </button>
          <button
            onClick={() => onStatusChange(review.id, 'RESOLVED', resolutionNote || undefined)}
            disabled={!active}
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 disabled:opacity-50"
          >
            Resolve
          </button>
          <button
            onClick={() => onStatusChange(review.id, 'WAIVED', resolutionNote || undefined)}
            disabled={!active}
            className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 disabled:opacity-50"
          >
            Waive
          </button>
          <button
            onClick={() => setExpanded(value => !value)}
            className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700"
          >
            {expanded ? 'Hide detail' : 'Show detail'}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div className="border-t border-gray-100 px-5 py-3">
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Trust delta</div>
            <div className="mt-1 text-xl font-black text-slate-900">
              {review.trust_delta >= 0 ? '+' : ''}
              {review.trust_delta}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Blocking findings</div>
            <div className="mt-1 text-xl font-black text-slate-900">{review.blocking_findings}</div>
          </div>
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Critical findings</div>
            <div className="mt-1 text-xl font-black text-slate-900">{review.critical_findings}</div>
          </div>
          <div className="rounded-xl bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Created</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">
              {new Date(review.created_at).toLocaleString('en-GB')}
            </div>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100 px-5 py-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <FieldBlock label="What This Seems To Be Doing" value={review.what_it_seems_to_do} />
            <FieldBlock label="What It Gets Wrong" value={review.what_it_gets_wrong} />
            <FieldBlock label="What Is Missing" value={review.what_is_missing} />
            <FieldBlock label="What Feels Dangerous" value={review.what_feels_dangerous} />
            <FieldBlock label="Cooperation Risk" value={review.cooperation_risk} />
            <FieldBlock label="Trust Increase Needed" value={review.trust_increase_needed} />
          </div>

          <FieldBlock label="Clean Handoff Note" value={review.clean_handoff_note} />

          <div className="mt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-sm font-bold text-gray-900">Findings</h4>
              <button
                onClick={() => setShowFindingForm(value => !value)}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700"
              >
                <Plus className="h-3.5 w-3.5" />
                Add finding
              </button>
            </div>
            <div className="mt-3 space-y-3">
              {review.findings.length === 0 && (
                <p className="text-sm text-gray-500">No structured findings captured yet.</p>
              )}
              {review.findings.map(finding => (
                <div key={finding.id} className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${severityClass(finding.severity)}`}>
                      {finding.severity}
                    </span>
                    <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-bold text-gray-600">
                      {finding.classification.replace(/_/g, ' ')}
                    </span>
                    <span className="text-sm font-semibold text-gray-900">{finding.title}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-gray-700">{finding.detail}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
                    <span>{finding.kind.replace(/_/g, ' ')}</span>
                    {finding.owner_role && <span>Owner: {finding.owner_role}</span>}
                    {finding.blocking && <span>Blocking</span>}
                    {finding.evidence_refs.length > 0 && <span>Evidence: {finding.evidence_refs.join(', ')}</span>}
                  </div>
                </div>
              ))}
            </div>

            {showFindingForm && (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <input
                    value={findingDraft.title}
                    onChange={event => setFindingDraft(current => ({ ...current, title: event.target.value }))}
                    placeholder="Finding title"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                  <input
                    value={findingDraft.owner_role}
                    onChange={event => setFindingDraft(current => ({ ...current, owner_role: event.target.value }))}
                    placeholder="Owner role"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                  <select
                    value={findingDraft.kind}
                    onChange={event => setFindingDraft(current => ({ ...current, kind: event.target.value }))}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    {['FALSE_PREMISE', 'KNOWLEDGE_GAP', 'MISUNDERSTOOD_TASK', 'UX_WEAKNESS', 'SEQUENCING_ERROR', 'LOGIC_FLAW', 'TRUST_PROBLEM', 'COOPERATION_BREAKDOWN', 'HANDOFF_FAILURE'].map(item => (
                      <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                  <select
                    value={findingDraft.classification}
                    onChange={event => setFindingDraft(current => ({ ...current, classification: event.target.value }))}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    {['UNCLEAR', 'MISSING', 'MISLEADING', 'STRUCTURALLY_WRONG'].map(item => (
                      <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                  <select
                    value={findingDraft.severity}
                    onChange={event => setFindingDraft(current => ({ ...current, severity: event.target.value }))}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(item => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                  <input
                    value={findingDraft.evidence_refs}
                    onChange={event => setFindingDraft(current => ({ ...current, evidence_refs: event.target.value }))}
                    placeholder="Evidence refs (comma separated)"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <textarea
                  value={findingDraft.detail}
                  onChange={event => setFindingDraft(current => ({ ...current, detail: event.target.value }))}
                  placeholder="Explain the finding in plain language"
                  className="mt-3 min-h-[110px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
                <label className="mt-3 flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={findingDraft.blocking}
                    onChange={event => setFindingDraft(current => ({ ...current, blocking: event.target.checked }))}
                  />
                  This finding blocks progress until addressed
                </label>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={submitFinding}
                    className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white"
                  >
                    Save finding
                  </button>
                  <button
                    onClick={() => setShowFindingForm(false)}
                    className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="mt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-sm font-bold text-gray-900">Handoffs</h4>
              <button
                onClick={() => setShowHandoffForm(value => !value)}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs font-semibold text-gray-700"
              >
                <Workflow className="h-3.5 w-3.5" />
                Add handoff
              </button>
            </div>
            <div className="mt-3 space-y-3">
              {review.handoffs.length === 0 && (
                <p className="text-sm text-gray-500">No explicit handoffs captured yet.</p>
              )}
              {review.handoffs.map(handoff => (
                <div key={handoff.id} className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-bold text-gray-600">
                      {handoff.status}
                    </span>
                    <span className="text-sm font-semibold text-gray-900">
                      {handoff.from_role || 'Current reviewer'} → {handoff.to_role}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-gray-700">{handoff.plain_language}</p>
                </div>
              ))}
            </div>

            {showHandoffForm && (
              <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50/50 p-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <input
                    value={handoffDraft.from_role}
                    onChange={event => setHandoffDraft(current => ({ ...current, from_role: event.target.value }))}
                    placeholder="From role"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                  <input
                    value={handoffDraft.to_role}
                    onChange={event => setHandoffDraft(current => ({ ...current, to_role: event.target.value }))}
                    placeholder="To role"
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                  <select
                    value={handoffDraft.status}
                    onChange={event => setHandoffDraft(current => ({ ...current, status: event.target.value }))}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    {['OPEN', 'SENT', 'ACKNOWLEDGED', 'CLOSED'].map(item => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                  <input
                    type="datetime-local"
                    value={handoffDraft.due_at}
                    onChange={event => setHandoffDraft(current => ({ ...current, due_at: event.target.value }))}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
                <textarea
                  value={handoffDraft.plain_language}
                  onChange={event => setHandoffDraft(current => ({ ...current, plain_language: event.target.value }))}
                  placeholder="Describe exactly who needs to know what next, in plain language"
                  className="mt-3 min-h-[100px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={submitHandoff}
                    className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white"
                  >
                    Save handoff
                  </button>
                  <button
                    onClick={() => setShowHandoffForm(false)}
                    className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="mt-6">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Resolution note</div>
            <textarea
              value={resolutionNote}
              onChange={event => setResolutionNote(event.target.value)}
              placeholder="Optional note when resolving or waiving the review"
              className="mt-2 min-h-[90px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function AdversarialReviewPage() {
  const { selectedProjectId, setSelectedProjectId } = useSelectedProject()
  const [searchParams, setSearchParams] = useSearchParams()
  const searchProject = searchParams.get('project')
  const searchActor = searchParams.get('actor')
  const projectId = searchProject || selectedProjectId
  const initialActorType = searchActor || 'COMMERCIAL_BANKER'

  const [actorType, setActorType] = useState(initialActorType)
  const [summary, setSummary] = useState<AdversarialReviewSummary | null>(null)
  const [reviews, setReviews] = useState<AdversarialReview[]>([])
  const [presets, setPresets] = useState<PromptPreset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createExpanded, setCreateExpanded] = useState(true)
  const [draft, setDraft] = useState({
    actor_type: initialActorType,
    prompt_preset_id: '',
    target_route: '',
    screen_title: '',
    summary: '',
    what_it_seems_to_do: '',
    what_it_gets_wrong: '',
    what_is_missing: '',
    what_feels_dangerous: '',
    cooperation_risk: '',
    trust_increase_needed: '',
    clean_handoff_note: '',
    final_stance: 'ESCALATE_INTERNALLY' as FinalStance,
    trust_delta: -1,
    created_by: 'gex_operator',
  })
  const [initialFinding, setInitialFinding] = useState({
    enabled: false,
    kind: 'TRUST_PROBLEM',
    classification: 'MISSING',
    severity: 'MEDIUM',
    title: '',
    detail: '',
    owner_role: '',
    evidence_refs: '',
  })
  const [initialHandoff, setInitialHandoff] = useState({
    enabled: false,
    from_role: initialActorType,
    to_role: '',
    plain_language: '',
    status: 'OPEN',
    due_at: '',
  })

  useEffect(() => {
    setSelectedProjectId(projectId)
  }, [projectId, setSelectedProjectId])

  useEffect(() => {
    setActorType(initialActorType)
    setDraft(current => ({ ...current, actor_type: initialActorType }))
    setInitialHandoff(current => ({ ...current, from_role: initialActorType }))
  }, [initialActorType])

  useEffect(() => {
    adversarialReviewsAPI.getPromptPresets()
      .then(setPresets)
      .catch(() => setPresets([]))
  }, [])

  useEffect(() => {
    if (!presets.length) return
    const recommended = presets.find(preset => preset.actor_type === draft.actor_type)
    if (recommended && !draft.prompt_preset_id) {
      setDraft(current => ({ ...current, prompt_preset_id: recommended.id }))
    }
  }, [draft.actor_type, draft.prompt_preset_id, presets])

  useEffect(() => {
    loadProjectState()
  }, [projectId, actorType])

  async function loadProjectState() {
    setLoading(true)
    try {
      const [nextSummary, nextReviews] = await Promise.all([
        adversarialReviewsAPI.getProjectSummary(projectId, actorType),
        adversarialReviewsAPI.listProjectReviews(projectId, actorType),
      ])
      setSummary(nextSummary)
      setReviews(nextReviews)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load adversarial review state')
    } finally {
      setLoading(false)
    }
  }

  async function submitReview() {
    if (!draft.summary.trim()) return
    const payload: Record<string, unknown> = {
      project_id: projectId,
      actor_type: draft.actor_type,
      prompt_preset_id: draft.prompt_preset_id || null,
      target_route: draft.target_route || null,
      screen_title: draft.screen_title || null,
      summary: draft.summary,
      what_it_seems_to_do: draft.what_it_seems_to_do || null,
      what_it_gets_wrong: draft.what_it_gets_wrong || null,
      what_is_missing: draft.what_is_missing || null,
      what_feels_dangerous: draft.what_feels_dangerous || null,
      cooperation_risk: draft.cooperation_risk || null,
      trust_increase_needed: draft.trust_increase_needed || null,
      clean_handoff_note: draft.clean_handoff_note || null,
      final_stance: draft.final_stance,
      trust_delta: Number(draft.trust_delta),
      created_by: draft.created_by,
      findings: initialFinding.enabled && initialFinding.title.trim() && initialFinding.detail.trim()
        ? [{
            kind: initialFinding.kind,
            classification: initialFinding.classification,
            severity: initialFinding.severity,
            title: initialFinding.title,
            detail: initialFinding.detail,
            owner_role: initialFinding.owner_role || null,
            blocking: true,
            evidence_refs: initialFinding.evidence_refs
              .split(',')
              .map(item => item.trim())
              .filter(Boolean),
            created_by: draft.created_by,
          }]
        : [],
      handoffs: initialHandoff.enabled && initialHandoff.to_role.trim() && initialHandoff.plain_language.trim()
        ? [{
            from_role: initialHandoff.from_role || null,
            to_role: initialHandoff.to_role,
            plain_language: initialHandoff.plain_language,
            status: initialHandoff.status,
            due_at: initialHandoff.due_at || null,
            created_by: draft.created_by,
          }]
        : [],
    }

    await adversarialReviewsAPI.createReview(payload)
    setDraft(current => ({
      ...current,
      target_route: '',
      screen_title: '',
      summary: '',
      what_it_seems_to_do: '',
      what_it_gets_wrong: '',
      what_is_missing: '',
      what_feels_dangerous: '',
      cooperation_risk: '',
      trust_increase_needed: '',
      clean_handoff_note: '',
      trust_delta: -1,
    }))
    setInitialFinding({
      enabled: false,
      kind: 'TRUST_PROBLEM',
      classification: 'MISSING',
      severity: 'MEDIUM',
      title: '',
      detail: '',
      owner_role: '',
      evidence_refs: '',
    })
    setInitialHandoff({
      enabled: false,
      from_role: draft.actor_type,
      to_role: '',
      plain_language: '',
      status: 'OPEN',
      due_at: '',
    })
    await loadProjectState()
  }

  async function handleStatusChange(reviewId: string, status: ReviewStatus, resolutionNote?: string) {
    await adversarialReviewsAPI.updateStatus(reviewId, {
      status,
      resolution_note: resolutionNote || null,
      resolved_by: draft.created_by,
    })
    await loadProjectState()
  }

  async function handleAddFinding(reviewId: string, payload: Record<string, unknown>) {
    await adversarialReviewsAPI.addFinding(reviewId, payload)
    await loadProjectState()
  }

  async function handleAddHandoff(reviewId: string, payload: Record<string, unknown>) {
    await adversarialReviewsAPI.addHandoff(reviewId, payload)
    await loadProjectState()
  }

  const project = getProjectById(projectId) ?? CUSTOMER_PROJECTS[0]
  const actorPresets = presets.filter(preset => preset.actor_type === draft.actor_type)

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-amber-700">
            <ShieldAlert className="h-4 w-4" />
            Adversarial Review Workspace
          </div>
          <h1 className="mt-1 text-2xl font-black text-gray-900">Pressure-test what the orchestrator is assuming</h1>
          <p className="mt-1 max-w-3xl text-sm text-gray-600">
            Capture skeptical role-based reviews, preserve handoff memory, and escalate blocking findings without touching the existing finance-engine microservice boundary.
          </p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-700 shadow-sm">
          <div className="font-semibold text-gray-900">{project.name}</div>
          <div className="text-xs text-gray-500">{project.location} · {project.molecule}</div>
        </div>
      </div>

      <AdversarialReviewEntryCard projectId={projectId} actorType={actorType} title="Project challenge summary" />

      <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 lg:grid-cols-[220px_220px_1fr]">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Project</div>
            <select
              value={projectId}
              onChange={event => setSearchParams({ project: event.target.value, actor: actorType })}
              className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            >
              {CUSTOMER_PROJECTS.map(item => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Actor lens</div>
            <select
              value={actorType}
              onChange={event => {
                setActorType(event.target.value)
                setSearchParams({ project: projectId, actor: event.target.value })
                setDraft(current => ({ ...current, actor_type: event.target.value, prompt_preset_id: '' }))
              }}
              className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
            >
              {['COMMERCIAL_BANKER', 'OFFTAKER', 'PRODUCER'].map(item => (
                <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Open</div>
              <div className="mt-1 text-2xl font-black text-slate-900">{summary?.open_reviews ?? '—'}</div>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Blocking</div>
              <div className="mt-1 text-2xl font-black text-slate-900">{summary?.blocking_findings ?? '—'}</div>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Escalated</div>
              <div className="mt-1 text-2xl font-black text-slate-900">{summary?.escalated_reviews ?? '—'}</div>
            </div>
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Trust delta</div>
              <div className="mt-1 text-2xl font-black text-slate-900">
                {summary ? `${summary.net_trust_delta >= 0 ? '+' : ''}${summary.net_trust_delta}` : '—'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
        <button
          onClick={() => setCreateExpanded(value => !value)}
          className="flex w-full items-center justify-between px-5 py-4 text-left"
        >
          <div>
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">New review</div>
            <div className="mt-1 text-lg font-bold text-gray-900">Create a structured adversarial challenge</div>
          </div>
          {createExpanded ? <ChevronUp className="h-5 w-5 text-gray-500" /> : <ChevronDown className="h-5 w-5 text-gray-500" />}
        </button>

        {createExpanded && (
          <div className="border-t border-gray-100 px-5 py-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Prompt preset</div>
                <select
                  value={draft.prompt_preset_id}
                  onChange={event => setDraft(current => ({ ...current, prompt_preset_id: event.target.value }))}
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                >
                  <option value="">No preset</option>
                  {actorPresets.map(preset => (
                    <option key={preset.id} value={preset.id}>
                      {preset.prompt_card_id} · {preset.employee_name}
                    </option>
                  ))}
                </select>
                {draft.prompt_preset_id && (
                  <div className="mt-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
                    {actorPresets.find(preset => preset.id === draft.prompt_preset_id)?.description}
                  </div>
                )}
              </div>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Created by</div>
                <input
                  value={draft.created_by}
                  onChange={event => setDraft(current => ({ ...current, created_by: event.target.value }))}
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Target route</div>
                <input
                  value={draft.target_route}
                  onChange={event => setDraft(current => ({ ...current, target_route: event.target.value }))}
                  placeholder="/finance/bankers-snapshot"
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Screen title</div>
                <input
                  value={draft.screen_title}
                  onChange={event => setDraft(current => ({ ...current, screen_title: event.target.value }))}
                  placeholder="Banker's Snapshot"
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </div>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Final stance</div>
                <select
                  value={draft.final_stance}
                  onChange={event => setDraft(current => ({ ...current, final_stance: event.target.value as FinalStance }))}
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                >
                  {['PROCEED', 'PROCEED_WITH_CAUTION', 'ESCALATE_INTERNALLY', 'STOP'].map(item => (
                    <option key={item} value={item}>{item.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Trust delta</div>
                <input
                  type="number"
                  value={draft.trust_delta}
                  onChange={event => setDraft(current => ({ ...current, trust_delta: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="mt-4">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Summary</div>
              <textarea
                value={draft.summary}
                onChange={event => setDraft(current => ({ ...current, summary: event.target.value }))}
                placeholder="State in one paragraph what the current setup is trying to do and why the challenge matters."
                className="mt-2 min-h-[110px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {[
                ['What this seems to be doing', 'what_it_seems_to_do'],
                ['What it gets wrong', 'what_it_gets_wrong'],
                ['What is missing', 'what_is_missing'],
                ['What feels dangerous', 'what_feels_dangerous'],
                ['Cooperation risk', 'cooperation_risk'],
                ['What would increase trust', 'trust_increase_needed'],
              ].map(([label, key]) => (
                <div key={key}>
                  <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">{label}</div>
                  <textarea
                    value={draft[key as keyof typeof draft] as string}
                    onChange={event => setDraft(current => ({ ...current, [key]: event.target.value }))}
                    className="mt-2 min-h-[100px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  />
                </div>
              ))}
            </div>

            <div className="mt-4">
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Clean handoff note</div>
              <textarea
                value={draft.clean_handoff_note}
                onChange={event => setDraft(current => ({ ...current, clean_handoff_note: event.target.value }))}
                placeholder="Who needs to know what next, and in what plain language?"
                className="mt-2 min-h-[100px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              />
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                <label className="flex items-center gap-2 text-sm font-semibold text-gray-800">
                  <input
                    type="checkbox"
                    checked={initialFinding.enabled}
                    onChange={event => setInitialFinding(current => ({ ...current, enabled: event.target.checked }))}
                  />
                  Include first finding now
                </label>
                {initialFinding.enabled && (
                  <div className="mt-3 space-y-3">
                    <input
                      value={initialFinding.title}
                      onChange={event => setInitialFinding(current => ({ ...current, title: event.target.value }))}
                      placeholder="Finding title"
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                    <textarea
                      value={initialFinding.detail}
                      onChange={event => setInitialFinding(current => ({ ...current, detail: event.target.value }))}
                      placeholder="Finding detail"
                      className="min-h-[100px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
                <label className="flex items-center gap-2 text-sm font-semibold text-gray-800">
                  <input
                    type="checkbox"
                    checked={initialHandoff.enabled}
                    onChange={event => setInitialHandoff(current => ({ ...current, enabled: event.target.checked }))}
                  />
                  Include first handoff now
                </label>
                {initialHandoff.enabled && (
                  <div className="mt-3 space-y-3">
                    <input
                      value={initialHandoff.to_role}
                      onChange={event => setInitialHandoff(current => ({ ...current, to_role: event.target.value }))}
                      placeholder="To role"
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                    <textarea
                      value={initialHandoff.plain_language}
                      onChange={event => setInitialHandoff(current => ({ ...current, plain_language: event.target.value }))}
                      placeholder="Plain-language handoff"
                      className="min-h-[100px] w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                onClick={submitReview}
                className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white"
              >
                <Plus className="h-4 w-4" />
                Create review
              </button>
              <button
                onClick={() => setCreateExpanded(false)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700"
              >
                Collapse
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Recorded reviews</h2>
            <p className="text-sm text-gray-500">
              {loading ? 'Loading…' : `${reviews.length} review${reviews.length === 1 ? '' : 's'} for ${project.name}`}
            </p>
          </div>
          {summary?.owner_roles && summary.owner_roles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {summary.owner_roles.map(role => (
                <span key={role} className="rounded-full border border-gray-200 bg-white px-2 py-1 text-[11px] font-semibold text-gray-600">
                  {role}
                </span>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {!loading && reviews.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
            <ShieldAlert className="mx-auto h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm font-semibold text-gray-700">No adversarial reviews recorded for this actor lens yet.</p>
            <p className="mt-1 text-sm text-gray-500">Start with one challenge review to capture what the workflow is assuming and where trust can break.</p>
          </div>
        )}

        {reviews.map(review => (
          <ReviewCard
            key={review.id}
            review={review}
            onStatusChange={handleStatusChange}
            onAddFinding={handleAddFinding}
            onAddHandoff={handleAddHandoff}
          />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
            <MessageSquareWarning className="h-4 w-4 text-amber-600" />
            What this module does
          </div>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            It gives prompt agents a first-class place to record challenges, not just narrate them in chat.
          </p>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
            <Siren className="h-4 w-4 text-red-600" />
            What it should catch
          </div>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            False premises, weak sequencing, hidden evidence gaps, and cross-functional handoff failures before they become committee surprises.
          </p>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-bold text-gray-900">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            Why it is safe
          </div>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            Everything stays in the platform backend and SQLite store. No `gex_pf_engine` contract or port wiring was changed.
          </p>
        </div>
      </div>
    </div>
  )
}
