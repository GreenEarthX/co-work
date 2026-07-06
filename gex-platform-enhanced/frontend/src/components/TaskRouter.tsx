// Screen: Shared component — Finance dashboard, CISO dashboard screens
/**
 * TaskRouter — R6 (Architectural Reform v6.0)
 *
 * Replaces the landing page of each workspace.
 * Shows: Objective → Overall Status → Step Cards → Next Action
 *
 * Step card states:
 *   ✓ DONE         — green, completed
 *   ⚡ IN_PROGRESS  — blue, active
 *   🔒 BLOCKED      — red, with blockers listed
 *   ○ NOT_STARTED  — gray
 *
 * The full sidebar is still accessible via "Show full navigation ▾" toggle.
 * The DealKillerBanner renders above this component when killers are active.
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { DealKillerBanner, useActiveKillers } from './DealKillerBanner'
import { AdversarialReviewEntryCard } from './AdversarialReviewEntryCard'

// ─── Types ────────────────────────────────────────────────────────────────────

type StepStatus = 'DONE' | 'IN_PROGRESS' | 'BLOCKED' | 'NOT_STARTED'

interface FlowStep {
  number:       number
  title:        string
  description:  string
  page:         string
  status:       StepStatus
  status_detail: string
  blocked_by:   string[]
}

interface ActorFlow {
  actor_type:           string
  project_id:           string
  objective:            string
  overall_status:       string
  steps:                FlowStep[]
  fatal_killers_active: number
  next_action:          string
  next_action_page:     string
}

interface TaskRouterProps {
  actorType:  string      // COMMERCIAL_BANKER | OFFTAKER | CREDIT_COMMITTEE_CHAIR | PRODUCER
  projectId:  string
  projectName?: string
  /** Render the sidebar toggle at the bottom */
  onShowSidebar?: () => void
}

// ─── Step style — slate body, color reserved for a 2-px left band only ──

const STEP_CONFIG: Record<StepStatus, {
  bandClass: string         // left-edge tone (the only color in the row)
  chipToneClass: string     // small status chip inside the row
  label: string             // short uppercase status label
}> = {
  DONE:        { bandClass: 'border-l-emerald-600', chipToneClass: 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300', label: 'DONE' },
  IN_PROGRESS: { bandClass: 'border-l-sky-600',     chipToneClass: 'border-l-sky-600     text-sky-800     dark:text-sky-300',     label: 'IN PROGRESS' },
  BLOCKED:     { bandClass: 'border-l-red-700',     chipToneClass: 'border-l-red-700     text-red-800     dark:text-red-300',     label: 'BLOCKED' },
  NOT_STARTED: { bandClass: 'border-l-slate-400',   chipToneClass: 'border-l-slate-400   text-slate-500   dark:text-slate-400',   label: 'NOT STARTED' },
}

// ─── Main component ───────────────────────────────────────────────────────────

export function TaskRouter({ actorType, projectId, projectName, onShowSidebar }: TaskRouterProps) {
  const navigate = useNavigate()
  const [flow, setFlow]       = useState<ActorFlow | null>(null)
  const [loading, setLoading] = useState(true)
  const { killers }           = useActiveKillers(projectId)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/v1/task-flow/${actorType}/${projectId}`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(setFlow)
      .catch(() => setFlow(getDemoFlow(actorType, projectId)))
      .finally(() => setLoading(false))
  }, [actorType, projectId])

  if (loading || !flow) {
    return <div className="h-48 flex items-center justify-center text-gray-400 text-sm">Loading…</div>
  }

  return (
    <div className="space-y-2 max-w-2xl">
      {/* Deal-Killer Banner — always first */}
      <DealKillerBanner killers={killers} projectName={projectName} />

      <AdversarialReviewEntryCard
        projectId={projectId}
        actorType={actorType}
        title="Challenge Review"
        compact
      />

      {/* Objective header */}
      <section className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
        <header className="border-b border-slate-200 dark:border-slate-800 px-2 py-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">Objective</span>
        </header>
        <div className="grid grid-cols-[minmax(0,1fr)_120px] items-center gap-2 px-2 py-1.5">
          <div className="min-w-0">
            <p className="font-mono text-[12px] font-semibold text-slate-900 dark:text-slate-100 leading-snug truncate">
              {flow.objective}
            </p>
            {projectName && (
              <p className="font-mono text-[10px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">{projectName}</p>
            )}
          </div>
          <OverallChip status={flow.overall_status} />
        </div>
      </section>

      {/* Step rows */}
      <section className="border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
        <header className="border-b border-slate-200 dark:border-slate-800 px-2 py-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">Steps</span>
        </header>
        <ol className="divide-y divide-slate-100 dark:divide-slate-900">
          {flow.steps.map(step => {
            const cfg = STEP_CONFIG[step.status]
            return (
              <li
                key={step.number}
                className={`border-l-2 grid grid-cols-[32px_minmax(0,1fr)_110px_64px] items-center gap-2 px-2 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-900 ${cfg.bandClass}`}
              >
                <span className="font-mono text-[10px] tabular-nums text-slate-500 dark:text-slate-400">
                  {String(step.number).padStart(2, '0')}
                </span>

                <div className="min-w-0">
                  <div className="font-mono text-[11px] font-semibold text-slate-900 dark:text-slate-100 truncate">
                    {step.title}
                  </div>
                  <div className="font-mono text-[10px] text-slate-500 dark:text-slate-400 leading-snug truncate">
                    {step.description}
                  </div>
                  {step.status_detail && (
                    <div className="font-mono text-[10px] text-slate-700 dark:text-slate-300 truncate">
                      {step.status_detail}
                    </div>
                  )}
                  {step.blocked_by.length > 0 && (
                    <ul className="mt-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300 leading-snug">
                      {step.blocked_by.map((b, i) => (
                        <li key={i}>· {b}</li>
                      ))}
                    </ul>
                  )}
                </div>

                <span
                  className={`justify-self-start inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${cfg.chipToneClass}`}
                >
                  {cfg.label}
                </span>

                {step.status === 'IN_PROGRESS' ? (
                  <button
                    onClick={() => navigate(step.page)}
                    className="justify-self-end font-mono text-[10px] uppercase tracking-[0.08em] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:underline whitespace-nowrap"
                  >
                    open →
                  </button>
                ) : <span />}
              </li>
            )
          })}
        </ol>
      </section>

      {/* Next action — slate bar, no rounding */}
      {flow.next_action && (
        <button
          onClick={() => navigate(flow.next_action_page)}
          className="w-full flex items-center justify-between border border-slate-900 dark:border-slate-100 bg-slate-900 dark:bg-slate-100 text-slate-50 dark:text-slate-900 px-2 py-1.5 font-mono text-[11px] uppercase tracking-[0.08em] hover:bg-slate-800 dark:hover:bg-slate-200"
        >
          <span>{flow.next_action}</span>
          <span>→</span>
        </button>
      )}

      {/* Sidebar toggle — mono link */}
      {onShowSidebar && (
        <button
          onClick={onShowSidebar}
          className="w-full font-mono text-[10px] uppercase tracking-[0.08em] text-slate-500 hover:text-slate-900 dark:hover:text-slate-100 py-0.5"
        >
          show full navigation ▾
        </button>
      )}
    </div>
  )
}

// ─── Overall status chip — same chip pattern as the dashboard rows ────────

function OverallChip({ status }: { status: string }) {
  const tone =
    status === 'READY'       ? 'border-l-emerald-600 text-emerald-800 dark:text-emerald-300' :
    status === 'CONDITIONAL' ? 'border-l-amber-600   text-amber-800   dark:text-amber-300' :
                               'border-l-red-700     text-red-800     dark:text-red-300'
  return (
    <span
      className={`justify-self-end inline-flex h-[15px] items-center justify-center border border-l-2 border-slate-300 bg-white dark:bg-slate-950 px-1 font-mono text-[8px] font-bold uppercase tracking-[0.08em] leading-none whitespace-nowrap ${tone}`}
    >
      {status}
    </span>
  )
}

// ─── Demo fallback ────────────────────────────────────────────────────────────

function getDemoFlow(actorType: string, projectId: string): ActorFlow {
  return {
    actor_type: actorType,
    project_id: projectId,
    objective: 'Assess this project for credit committee submission',
    overall_status: 'NOT_READY',
    fatal_killers_active: 2,
    next_action: 'Resolve FATAL deal-killers',
    next_action_page: '/finance/bankability',
    steps: [
      { number: 1, title: "Review Banker's Snapshot", description: "Get a one-page summary.", page: '/finance/bankers-snapshot', status: 'DONE', status_detail: 'Viewed', blocked_by: [] },
      { number: 2, title: 'Check Gates and Deal-Killers', description: 'Identify FATAL issues.', page: '/finance/bankability', status: 'IN_PROGRESS', status_detail: '2 FATAL deal-killers active', blocked_by: [] },
      { number: 3, title: 'Review Evidence Verification', description: 'Check evidence states.', page: '/finance/stage-gates', status: 'NOT_STARTED', status_detail: '42% at CONFIRMED+', blocked_by: [] },
      { number: 4, title: 'Confirm Commitment Firmness', description: 'Verify capital stack.', page: '/finance/capital-stack', status: 'NOT_STARTED', status_detail: '', blocked_by: [] },
      { number: 5, title: 'Generate IC Pack', description: 'Export when clear.', page: '/finance/ic-pack', status: 'BLOCKED', status_detail: '', blocked_by: ['2 FATAL deal-killers active', 'G8 not AUDIT_GRADE'] },
    ],
  }
}
