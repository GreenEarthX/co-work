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
import {
  CheckCircle, Circle, Lock, Zap, ArrowRight, ChevronDown, ChevronUp,
  Target,
} from 'lucide-react'
import { DealKillerBanner, useActiveKillers } from './DealKillerBanner'

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

// ─── Step icon & styles ───────────────────────────────────────────────────────

const STEP_CONFIG: Record<StepStatus, {
  Icon: React.ElementType
  containerClass: string
  titleClass: string
  iconClass: string
  badge: string
}> = {
  DONE: {
    Icon: CheckCircle,
    containerClass: 'border-green-200 bg-green-50',
    titleClass:     'text-green-800',
    iconClass:      'text-green-600',
    badge:          'bg-green-100 text-green-700',
  },
  IN_PROGRESS: {
    Icon: Zap,
    containerClass: 'border-blue-300 bg-blue-50 ring-1 ring-blue-200',
    titleClass:     'text-blue-800',
    iconClass:      'text-blue-600',
    badge:          'bg-blue-100 text-blue-700',
  },
  BLOCKED: {
    Icon: Lock,
    containerClass: 'border-red-200 bg-red-50',
    titleClass:     'text-red-800',
    iconClass:      'text-red-500',
    badge:          'bg-red-100 text-red-700',
  },
  NOT_STARTED: {
    Icon: Circle,
    containerClass: 'border-gray-200 bg-white',
    titleClass:     'text-gray-700',
    iconClass:      'text-gray-300',
    badge:          'bg-gray-100 text-gray-500',
  },
}

const STATUS_LABELS: Record<StepStatus, string> = {
  DONE:        '✓ Done',
  IN_PROGRESS: '⚡ In progress',
  BLOCKED:     '🔒 Blocked',
  NOT_STARTED: '○ Not started',
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

  const currentStep = flow.steps.find(s => s.status === 'IN_PROGRESS')
    ?? flow.steps.find(s => s.status === 'NOT_STARTED')

  return (
    <div className="space-y-4 max-w-2xl">
      {/* Deal-Killer Banner — always first */}
      <DealKillerBanner killers={killers} projectName={projectName} />

      {/* Objective header */}
      <div className="flex items-start gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3">
        <Target className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
        <div>
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-0.5">Objective</p>
          <p className="text-sm font-semibold text-gray-800">{flow.objective}</p>
          {projectName && <p className="text-xs text-gray-400 mt-0.5">{projectName}</p>}
        </div>
        <OverallBadge status={flow.overall_status} />
      </div>

      {/* Step cards */}
      <div className="space-y-2">
        {flow.steps.map(step => {
          const cfg = STEP_CONFIG[step.status]
          return (
            <div
              key={step.number}
              className={`rounded-lg border px-4 py-3 transition-all ${cfg.containerClass}`}
            >
              <div className="flex items-start gap-3">
                {/* Step number + icon */}
                <div className="flex flex-col items-center gap-1 flex-shrink-0">
                  <cfg.Icon className={`w-4 h-4 ${cfg.iconClass}`} />
                  <span className="text-[10px] text-gray-400 font-mono">{step.number}</span>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={`text-sm font-semibold ${cfg.titleClass}`}>{step.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.badge}`}>
                      {STATUS_LABELS[step.status]}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500">{step.description}</p>

                  {step.status_detail && (
                    <p className={`text-xs mt-1 font-medium ${cfg.titleClass}`}>
                      {step.status_detail}
                    </p>
                  )}

                  {step.blocked_by.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {step.blocked_by.map((b, i) => (
                        <li key={i} className="text-xs text-red-600 flex items-start gap-1">
                          <span className="flex-shrink-0">•</span> {b}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Navigate CTA (only for IN_PROGRESS) */}
                {step.status === 'IN_PROGRESS' && (
                  <button
                    onClick={() => navigate(step.page)}
                    className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-blue-700 hover:text-blue-900 underline underline-offset-2"
                  >
                    Go <ArrowRight className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Next action button */}
      {flow.next_action && (
        <button
          onClick={() => navigate(flow.next_action_page)}
          className="w-full flex items-center justify-between px-4 py-3 rounded-lg bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 transition-colors"
        >
          <span>{flow.next_action}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      )}

      {/* Sidebar toggle */}
      {onShowSidebar && (
        <button
          onClick={onShowSidebar}
          className="w-full text-xs text-gray-400 hover:text-gray-600 flex items-center justify-center gap-1 py-1"
        >
          Show full navigation <ChevronDown className="w-3 h-3" />
        </button>
      )}
    </div>
  )
}

// ─── Overall status badge ─────────────────────────────────────────────────────

function OverallBadge({ status }: { status: string }) {
  const cfg =
    status === 'READY'       ? 'bg-green-100 text-green-700 border-green-300' :
    status === 'CONDITIONAL' ? 'bg-amber-100 text-amber-700 border-amber-300' :
                               'bg-red-100 text-red-700 border-red-300'
  return (
    <span className={`ml-auto flex-shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border ${cfg}`}>
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
