/**
 * CooperationHandoffFeed — live cross-functional knowledge transfer feed.
 * Shows insurance sign-offs, OFFTAKER EXECUTIVE decisions, HAZOP events,
 * commitment signings, and engineer-to-banker handoffs in chronological order.
 */
import { useEffect, useState } from 'react'
import {
  ShieldCheck, UserCheck, Zap, FileSignature, ArrowRightLeft,
  CheckCircle2, AlertTriangle, Clock, FileText,
} from 'lucide-react'
import { projectActivityAPI } from '@/api'
import { getProjectById } from '@/data/customerProjects'

// ─── Types ───────────────────────────────────────────────────────────────────

type HandoffType =
  | 'INSURANCE_SIGNOFF'
  | 'OFFTAKER_DECISION'
  | 'HAZOP_EVENT'
  | 'COMMITMENT_SIGNED'
  | 'ENGINEER_TO_BANKER'
  | 'WORKFLOW_ADVANCE'
  | 'EVIDENCE_UPDATE'

type HandoffStatus = 'COMPLETED' | 'PENDING' | 'BLOCKED'

interface HandoffEvent {
  id: string
  type: HandoffType
  status: HandoffStatus
  timestamp: string        // ISO
  title: string
  actor: string
  actorRole: string
  target?: string          // recipient / next owner
  targetRole?: string
  projectId?: string
  projectName: string
  details: string
  knowledgeLossRisk?: 'LOW' | 'MEDIUM' | 'HIGH'
}

interface ApiHandoffEvent {
  id: string
  type: HandoffType
  status: HandoffStatus
  timestamp: string
  title: string
  actor: string
  actor_role: string
  target?: string
  target_role?: string
  project_id: string
  project_name: string
  details: string
  knowledge_loss_risk?: 'LOW' | 'MEDIUM' | 'HIGH'
}

// ─── Static demo data ─────────────────────────────────────────────────────────

const FALLBACK_EVENTS: HandoffEvent[] = [
  {
    id: 'H001',
    type: 'INSURANCE_SIGNOFF',
    status: 'COMPLETED',
    timestamp: '2026-03-25T14:22:00Z',
    title: 'Insurance Risk Engineer Sign-Off',
    actor: 'Dr. Claire Hoffmann',
    actorRole: 'Risk Engineer · Munich Re',
    target: 'GEX Finance Team',
    targetRole: 'Project Finance',
    projectName: 'Le Havre EMEOH',
    details: 'CAR/EAR policy bound. DSU conditional on 90-day waiting period. Workflow advanced to INSURANCE_REVIEWED.',
    knowledgeLossRisk: 'LOW',
  },
  {
    id: 'H002',
    type: 'OFFTAKER_DECISION',
    status: 'COMPLETED',
    timestamp: '2026-03-24T09:45:00Z',
    title: 'Offtaker Executive PPA Approval',
    actor: 'Jean-Pierre Moreau',
    actorRole: 'Executive VP · Engie Trading',
    target: 'Structuring Team',
    targetRole: 'Finance / Legal',
    projectName: 'Le Havre EMEOH',
    details: 'Board approval granted for 10-year PPA at €4.20/kg RED III certified H₂. Volume: 18,000 MTPA. Minimum floor: 75%.',
    knowledgeLossRisk: 'LOW',
  },
  {
    id: 'H003',
    type: 'HAZOP_EVENT',
    status: 'BLOCKED',
    timestamp: '2026-03-22T11:00:00Z',
    title: 'HAZOP Study — Session 3 Incomplete',
    actor: 'NovADes Engineering',
    actorRole: 'Lead HAZOP Facilitator',
    target: 'Project Engineer',
    targetRole: 'Engineering / CISO',
    projectName: 'Rotterdam NH₃',
    details: 'Node 4 (synthesis loop) review incomplete — P&ID revision R3 not available. Next session postponed 3 weeks.',
    knowledgeLossRisk: 'HIGH',
  },
  {
    id: 'H004',
    type: 'COMMITMENT_SIGNED',
    status: 'COMPLETED',
    timestamp: '2026-03-20T16:30:00Z',
    title: 'DFI Guarantee Commitment Signed',
    actor: 'Isabel Ferreira',
    actorRole: 'Investment Officer · EIB',
    target: 'CFO',
    targetRole: 'Executive / Finance',
    projectName: 'Helios e-Methanol',
    details: 'EKF Denmark indicative mandate signed. €55M ECA/DFI guarantee, 15-year tenor. Credit approval conditional on IFC E&S due diligence.',
    knowledgeLossRisk: 'LOW',
  },
  {
    id: 'H005',
    type: 'ENGINEER_TO_BANKER',
    status: 'COMPLETED',
    timestamp: '2026-03-18T10:00:00Z',
    title: 'Technical Due Diligence Package Transferred',
    actor: 'Dr. Ahmed Al-Rashidi',
    actorRole: 'Lead Process Engineer · GreenEarthX',
    target: 'ING / Rabobank Technical Adviser',
    targetRole: 'Technical Advisor · Lender',
    projectName: 'Rotterdam NH₃',
    details: 'FEED report, HAZOP Part 1, electrolyser stack OEM warranties, and CAPEX base estimate (±15%) shared via GEX Data Room.',
    knowledgeLossRisk: 'MEDIUM',
  },
  {
    id: 'H006',
    type: 'WORKFLOW_ADVANCE',
    status: 'COMPLETED',
    timestamp: '2026-03-15T08:00:00Z',
    title: 'Workflow Advanced: DRAFT → COMPUTED',
    actor: 'GEX Platform Engine',
    actorRole: 'Automated · GEX PF Engine',
    projectName: 'Celtic SAF',
    details: 'Bankability score engine ran: 7/10 gates green. Blocking: G7_INSURANCE_BOUND, G10_FINANCIAL_CLOSE_CP. Promotion to REVIEWED gated on 2 blockers.',
    knowledgeLossRisk: 'LOW',
  },
  {
    id: 'H007',
    type: 'OFFTAKER_DECISION',
    status: 'PENDING',
    timestamp: '2026-03-26T00:00:00Z',
    title: 'Offtaker Board Decision Pending',
    actor: 'Ryanair Procurement Committee',
    actorRole: 'Executive · OFFTAKER',
    target: 'GreenEarthX Origination',
    targetRole: 'Finance',
    projectName: 'Celtic SAF',
    details: 'SAF offtake term sheet under board review. Decision expected by 2026-04-10. Minimum volume 8,000 MTPA.',
    knowledgeLossRisk: 'MEDIUM',
  },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<HandoffType, { Icon: React.ElementType; color: string; bg: string }> = {
  INSURANCE_SIGNOFF:    { Icon: ShieldCheck,     color: 'text-sky-700',    bg: 'bg-sky-100'    },
  OFFTAKER_DECISION:    { Icon: UserCheck,        color: 'text-emerald-700',bg: 'bg-emerald-100'},
  HAZOP_EVENT:          { Icon: Zap,              color: 'text-orange-700', bg: 'bg-orange-100' },
  COMMITMENT_SIGNED:    { Icon: FileSignature,    color: 'text-violet-700', bg: 'bg-violet-100' },
  ENGINEER_TO_BANKER:   { Icon: ArrowRightLeft,   color: 'text-indigo-700', bg: 'bg-indigo-100' },
  WORKFLOW_ADVANCE:     { Icon: CheckCircle2,     color: 'text-green-700',  bg: 'bg-green-100'  },
  EVIDENCE_UPDATE:      { Icon: FileText,         color: 'text-slate-700',  bg: 'bg-slate-100'  },
}

const STATUS_CONFIG: Record<HandoffStatus, { Icon: React.ElementType; color: string; label: string }> = {
  COMPLETED: { Icon: CheckCircle2, color: 'text-green-600', label: 'Completed' },
  PENDING:   { Icon: Clock,        color: 'text-amber-600', label: 'Pending'   },
  BLOCKED:   { Icon: AlertTriangle,color: 'text-red-600',   label: 'Blocked'   },
}

const RISK_COLORS = { LOW: 'text-green-600', MEDIUM: 'text-amber-600', HIGH: 'text-red-600' }

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function normalizeEvent(event: ApiHandoffEvent): HandoffEvent {
  return {
    id: event.id,
    type: event.type,
    status: event.status,
    timestamp: event.timestamp,
    title: event.title,
    actor: event.actor,
    actorRole: event.actor_role,
    target: event.target,
    targetRole: event.target_role,
    projectId: event.project_id,
    projectName: event.project_name,
    details: event.details,
    knowledgeLossRisk: event.knowledge_loss_risk,
  }
}

// ─── Main component ───────────────────────────────────────────────────────────

interface CooperationHandoffFeedProps {
  compact?: boolean
  projectFilter?: string
  projectId?: string
  maxItems?: number
}

export function CooperationHandoffFeed({
  compact = false,
  projectFilter,
  projectId,
  maxItems = 20,
}: CooperationHandoffFeedProps) {
  const [typeFilter, setTypeFilter] = useState<HandoffType | 'ALL'>('ALL')
  const [events, setEvents] = useState<HandoffEvent[]>([])
  const [loading, setLoading] = useState(false)

  const resolvedProjectName = projectFilter ?? (projectId ? getProjectById(projectId)?.name : undefined)

  useEffect(() => {
    let cancelled = false

    if (!projectId) {
      setEvents(FALLBACK_EVENTS)
      return () => {
        cancelled = true
      }
    }

    setLoading(true)

    projectActivityAPI
      .listForProject(projectId, { limit: Math.max(maxItems * 3, 12) })
      .then((data: { events?: ApiHandoffEvent[] }) => {
        if (cancelled) return
        setEvents((data.events || []).map(normalizeEvent))
      })
      .catch(() => {
        if (cancelled) return
        const fallback = resolvedProjectName
          ? FALLBACK_EVENTS.filter((event) => event.projectName === resolvedProjectName)
          : FALLBACK_EVENTS
        setEvents(fallback)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [projectId, resolvedProjectName, maxItems])

  const displayed = events
    .filter(e => !resolvedProjectName || e.projectName === resolvedProjectName)
    .filter(e => typeFilter === 'ALL' || e.type === typeFilter)
    .slice(0, maxItems)

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      {!compact && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-gray-500">Filter:</span>
          {(['ALL', 'INSURANCE_SIGNOFF', 'OFFTAKER_DECISION', 'HAZOP_EVENT', 'COMMITMENT_SIGNED', 'ENGINEER_TO_BANKER', 'WORKFLOW_ADVANCE', 'EVIDENCE_UPDATE'] as const).map(t => {
            const cfg = t !== 'ALL' ? TYPE_CONFIG[t] : null
            return (
              <button
                key={t}
                type="button"
                onClick={() => setTypeFilter(t)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                  typeFilter === t
                    ? 'bg-gray-900 text-white border-gray-900'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-400'
                }`}
              >
                {cfg && <cfg.Icon className="w-3 h-3" />}
                {t === 'ALL' ? 'All Events' : t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </button>
            )
          })}
        </div>
      )}

      {/* Event timeline */}
      <div className="space-y-2">
        {loading && displayed.length === 0 && (
          <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-6 text-sm text-gray-500">
            Loading project activity…
          </div>
        )}

        {displayed.map(event => {
          const typeCfg = TYPE_CONFIG[event.type]
          const statusCfg = STATUS_CONFIG[event.status]
          const TypeIcon = typeCfg.Icon
          const StatusIcon = statusCfg.Icon

          return (
            <div
              key={event.id}
              className={`rounded-xl border p-4 ${
                event.status === 'BLOCKED'
                  ? 'border-red-200 bg-red-50'
                  : event.status === 'PENDING'
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Type icon */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${typeCfg.bg}`}>
                  <TypeIcon className={`w-4 h-4 ${typeCfg.color}`} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-bold text-gray-900">{event.title}</span>
                        <StatusIcon className={`w-3.5 h-3.5 ${statusCfg.color}`} />
                        <span className={`text-xs font-semibold ${statusCfg.color}`}>{statusCfg.label}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-gray-400">{formatTimestamp(event.timestamp)}</span>
                        <span className="text-gray-300">·</span>
                        <span className="text-xs font-medium text-gray-500">{event.projectName}</span>
                      </div>
                    </div>
                  </div>

                  {/* Actor → Target */}
                  <div className="flex items-center gap-1.5 mt-2 text-xs">
                    <span className="font-semibold text-gray-800">{event.actor}</span>
                    <span className="text-gray-400 text-xs">{event.actorRole}</span>
                    {event.target && (
                      <>
                        <ArrowRightLeft className="w-3 h-3 text-gray-300 mx-1" />
                        <span className="font-semibold text-gray-800">{event.target}</span>
                        {event.targetRole && <span className="text-gray-400">{event.targetRole}</span>}
                      </>
                    )}
                  </div>

                  {/* Details */}
                  {!compact && (
                    <p className="text-xs text-gray-600 mt-1.5 leading-relaxed">{event.details}</p>
                  )}

                  {/* Knowledge loss risk */}
                  {event.knowledgeLossRisk && event.knowledgeLossRisk !== 'LOW' && (
                    <div className={`mt-2 text-xs font-semibold flex items-center gap-1 ${RISK_COLORS[event.knowledgeLossRisk]}`}>
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Knowledge loss risk: {event.knowledgeLossRisk}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {!loading && displayed.length === 0 && (
        <div className="text-center py-8 text-gray-400 text-sm">No handoff events match the selected filter.</div>
      )}
    </div>
  )
}
