// Screen: Project timeline screen (/finance-timeline, /finance/timeline)
/**
 * ProjectTimeline — Interactive project milestone timeline with drawdown schedule.
 * Three tabs: Timeline (phase swimlanes), Drawdown Schedule (S-curve), Milestones (table).
 */
import { useState, useMemo, useEffect } from 'react'
import { ChevronUp, ChevronDown, Euro, Calendar, User, Flag, CheckCircle, Clock, AlertCircle, Circle } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ─────────────────────────────── Types ───────────────────────────────────────

type MilestoneStatus = 'COMPLETED' | 'IN_PROGRESS' | 'PLANNED' | 'DELAYED' | 'BLOCKED'
type PhaseStatus = 'COMPLETED' | 'IN_PROGRESS' | 'PLANNED'
type PhaseName = 'ADVISORY' | 'BUILD' | 'FINANCIAL_CLOSE' | 'CONSTRUCTION' | 'OPERATIONS'

interface Milestone {
  name: string
  status: MilestoneStatus
  targetDate: string   // e.g. '2026-Q2'
  owner: string
  fundingTrigger: boolean
  drawdownAmount?: number
}

interface Phase {
  phase: PhaseName
  status: PhaseStatus
  milestones: Milestone[]
}

interface TimelineData {
  phases: Phase[]
}

type SortKey = 'name' | 'phase' | 'targetDate' | 'status' | 'owner' | 'drawdownAmount'
type SortDir = 'asc' | 'desc'

// ─────────────────────────── Non-sensitive demo data ─────────────────────────
//
// R1 (Ticket 1a): the frontend bundle ships ONLY non-sensitive project
// milestones (inception → development → permitting → FEED/EPC → construction →
// commissioning → COD → operations). It contains NO drawdownAmount, NO funding
// triggers, NO FINANCIAL_CLOSE phase, and NO term-sheet / lender / covenant /
// CP detail. That sensitive layer is served by the protected backend endpoint
// GET /api/v1/finance-model/drawdown-timeline/{project_id} (403 if unauthorized).

function generateTimelineData(projectId: string): TimelineData {
  if (projectId === 'proj_le_havre_eng') {
    return {
      phases: [
        { phase: 'ADVISORY', status: 'COMPLETED', milestones: [
          { name: 'LCA Protocol Locked', status: 'COMPLETED', targetDate: '2025-Q1', owner: 'DNV', fundingTrigger: false },
          { name: 'Offtake 92% Signed', status: 'COMPLETED', targetDate: '2025-Q4', owner: 'Commercial', fundingTrigger: false },
        ]},
        { phase: 'BUILD', status: 'COMPLETED', milestones: [
          { name: 'EPC Contract Executed', status: 'COMPLETED', targetDate: '2025-Q2', owner: 'PM', fundingTrigger: false },
          { name: 'Insurance CAR/DSU Placed', status: 'COMPLETED', targetDate: '2025-Q3', owner: 'Risk', fundingTrigger: false },
        ]},
        { phase: 'CONSTRUCTION', status: 'PLANNED', milestones: [
          { name: 'NTP Issued', status: 'PLANNED', targetDate: '2026-Q3', owner: 'PM', fundingTrigger: false },
          { name: 'Electrolyser Delivery', status: 'PLANNED', targetDate: '2027-Q1', owner: 'PM', fundingTrigger: false },
          { name: 'Methanation Unit FAT', status: 'PLANNED', targetDate: '2027-Q4', owner: 'PM', fundingTrigger: false },
          { name: 'COD Commissioning', status: 'PLANNED', targetDate: '2028-Q2', owner: 'PM', fundingTrigger: false },
        ]},
        { phase: 'OPERATIONS', status: 'PLANNED', milestones: [
          { name: 'Commercial Operations', status: 'PLANNED', targetDate: '2028-Q2', owner: 'Operations', fundingTrigger: false },
          { name: 'First GoO Issuance', status: 'PLANNED', targetDate: '2028-Q3', owner: 'Certification', fundingTrigger: false },
        ]},
      ],
    }
  }

  if (projectId === 'proj_bremen_h2') {
    return {
      phases: [
        { phase: 'ADVISORY', status: 'COMPLETED', milestones: [
          { name: 'Feasibility Study', status: 'COMPLETED', targetDate: '2024-Q2', owner: 'Engineering', fundingTrigger: false },
          { name: 'Stakeholder MoU', status: 'COMPLETED', targetDate: '2024-Q4', owner: 'BD', fundingTrigger: false },
        ]},
        { phase: 'BUILD', status: 'IN_PROGRESS', milestones: [
          { name: 'EPC Tender Award', status: 'COMPLETED', targetDate: '2025-Q2', owner: 'PM', fundingTrigger: false },
          { name: 'Grid Connection Agreement', status: 'IN_PROGRESS', targetDate: '2026-Q1', owner: 'Grid Ops', fundingTrigger: false },
        ]},
        { phase: 'CONSTRUCTION', status: 'PLANNED', milestones: [
          { name: 'NTP Issued', status: 'PLANNED', targetDate: '2027-Q1', owner: 'PM', fundingTrigger: false },
          { name: 'COD Commissioning', status: 'PLANNED', targetDate: '2028-Q4', owner: 'PM', fundingTrigger: false },
        ]},
        { phase: 'OPERATIONS', status: 'PLANNED', milestones: [
          { name: 'Commercial Operations', status: 'PLANNED', targetDate: '2029-Q1', owner: 'Operations', fundingTrigger: false },
        ]},
      ],
    }
  }

  if (projectId === 'proj_helios_solar' || projectId === 'proj_rotterdam_nh3') {
    return {
      phases: [
        { phase: 'ADVISORY', status: 'IN_PROGRESS', milestones: [
          { name: 'Pre-Feasibility Study', status: 'COMPLETED', targetDate: '2025-Q3', owner: 'Engineering', fundingTrigger: false },
          { name: 'Site Selection', status: 'IN_PROGRESS', targetDate: '2026-Q2', owner: 'BD', fundingTrigger: false },
          { name: 'Environmental Assessment', status: 'PLANNED', targetDate: '2026-Q3', owner: 'ESG', fundingTrigger: false },
        ]},
        { phase: 'BUILD', status: 'PLANNED', milestones: [
          { name: 'EPC Tender', status: 'PLANNED', targetDate: '2027-Q1', owner: 'PM', fundingTrigger: false },
        ]},
        { phase: 'CONSTRUCTION', status: 'PLANNED', milestones: [
          { name: 'NTP Issued', status: 'PLANNED', targetDate: '2028-Q1', owner: 'PM', fundingTrigger: false },
        ]},
        { phase: 'OPERATIONS', status: 'PLANNED', milestones: [
          { name: 'Commercial Operations', status: 'PLANNED', targetDate: '2029-Q4', owner: 'Operations', fundingTrigger: false },
        ]},
      ],
    }
  }

  // Wales / default (PRE_ADVISORY)
  return {
    phases: [
      { phase: 'ADVISORY', status: 'PLANNED', milestones: [
        { name: 'Initial Screening', status: 'PLANNED', targetDate: '2026-Q3', owner: 'BD', fundingTrigger: false },
        { name: 'Concept Note', status: 'PLANNED', targetDate: '2026-Q4', owner: 'Engineering', fundingTrigger: false },
      ]},
      { phase: 'BUILD', status: 'PLANNED', milestones: [
        { name: 'EPC Tender', status: 'PLANNED', targetDate: '2028-Q1', owner: 'PM', fundingTrigger: false },
      ]},
      { phase: 'CONSTRUCTION', status: 'PLANNED', milestones: [
        { name: 'NTP Issued', status: 'PLANNED', targetDate: '2029-Q1', owner: 'PM', fundingTrigger: false },
      ]},
      { phase: 'OPERATIONS', status: 'PLANNED', milestones: [
        { name: 'Commercial Operations', status: 'PLANNED', targetDate: '2030-Q3', owner: 'Operations', fundingTrigger: false },
      ]},
    ],
  }
}

// Sensitive layer fetched from the protected backend endpoint.
interface DrawdownLayer {
  financial_close: Phase
  drawdowns: Array<{ phase: string; name: string; targetDate: string; drawdownAmount: number }>
}

/** Merge the protected sensitive layer into the broad timeline (entitled users). */
function mergeSensitiveLayer(broad: TimelineData, layer: DrawdownLayer): TimelineData {
  const amountByName = new Map(layer.drawdowns.map(d => [d.name, d.drawdownAmount]))
  const phases = broad.phases.map(p => ({
    ...p,
    milestones: p.milestones.map(m =>
      amountByName.has(m.name) ? { ...m, drawdownAmount: amountByName.get(m.name), fundingTrigger: true } : m
    ),
  }))
  // Insert the FINANCIAL_CLOSE phase after BUILD (before CONSTRUCTION).
  const out: Phase[] = []
  let inserted = false
  for (const p of phases) {
    if (p.phase === 'CONSTRUCTION' && !inserted) {
      out.push(layer.financial_close as Phase); inserted = true
    }
    out.push(p)
  }
  if (!inserted) out.push(layer.financial_close as Phase)
  return { phases: out }
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

const PHASE_CONFIG: Record<PhaseName | string, { label: string; color: string; bg: string; border: string; barBg: string }> = {
  ADVISORY:        { label: 'Phase 0 · Advisory',        color: 'text-amber-700',   bg: 'bg-amber-50',   border: 'border-amber-300',  barBg: 'bg-amber-400' },
  BUILD:           { label: 'Phase 1 · Build',            color: 'text-blue-700',    bg: 'bg-blue-50',    border: 'border-blue-300',   barBg: 'bg-blue-400' },
  FINANCIAL_CLOSE: { label: 'Phase 2 · Financial Close',  color: 'text-purple-700',  bg: 'bg-purple-50',  border: 'border-purple-300', barBg: 'bg-purple-400' },
  CONSTRUCTION:    { label: 'Phase 3 · Construction',     color: 'text-green-700',   bg: 'bg-green-50',   border: 'border-green-300',  barBg: 'bg-green-500' },
  OPERATIONS:      { label: 'Phase 4 · Operations',       color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-300', barBg: 'bg-emerald-500' },
}

const STATUS_CONFIG: Record<MilestoneStatus | PhaseStatus, { label: string; bg: string; text: string; icon: React.ReactNode }> = {
  COMPLETED:  { label: 'Completed',   bg: 'bg-green-100',  text: 'text-green-700',  icon: <CheckCircle size={12} /> },
  IN_PROGRESS:{ label: 'In Progress', bg: 'bg-blue-100',   text: 'text-blue-700',   icon: <Clock size={12} /> },
  PLANNED:    { label: 'Planned',     bg: 'bg-gray-100',   text: 'text-gray-600',   icon: <Circle size={12} /> },
  DELAYED:    { label: 'Delayed',     bg: 'bg-amber-100',  text: 'text-amber-700',  icon: <AlertCircle size={12} /> },
  BLOCKED:    { label: 'Blocked',     bg: 'bg-red-100',    text: 'text-red-700',    icon: <AlertCircle size={12} /> },
}

function fmtEur(amount: number): string {
  if (amount >= 1_000_000) return `€${(amount / 1_000_000).toFixed(0)}M`
  if (amount >= 1_000) return `€${(amount / 1_000).toFixed(0)}K`
  return `€${amount}`
}

function quarterToIndex(q: string): number {
  // e.g. '2026-Q2' → numeric index from 2025-Q1 = 0
  const [year, qPart] = q.split('-Q')
  return (parseInt(year) - 2025) * 4 + (parseInt(qPart) - 1)
}

// ─────────────────────────────── Sub-components ──────────────────────────────

function StatusBadge({ status }: { status: MilestoneStatus | PhaseStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG['PLANNED']
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  )
}

function PhaseBadge({ phase }: { phase: PhaseName | string }) {
  const cfg = PHASE_CONFIG[phase] ?? PHASE_CONFIG['ADVISORY']
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cfg.bg} ${cfg.color}`}>
      {cfg.label}
    </span>
  )
}

// ─────────────────────────────── Timeline Tab ────────────────────────────────

function TimelineTab({ data }: { data: TimelineData }) {
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null)

  // Collect all quarters present in data to build x-axis
  const allQuarters = useMemo(() => {
    const set = new Set<string>()
    data.phases.forEach(p => p.milestones.forEach(m => set.add(m.targetDate)))
    return Array.from(set).sort((a, b) => quarterToIndex(a) - quarterToIndex(b))
  }, [data])

  const minIdx = allQuarters.length > 0 ? quarterToIndex(allQuarters[0]) : 0
  const maxIdx = allQuarters.length > 0 ? quarterToIndex(allQuarters[allQuarters.length - 1]) : 1
  const span = Math.max(maxIdx - minIdx, 1)

  function pct(q: string) {
    return ((quarterToIndex(q) - minIdx) / span) * 90 // leave 5% padding each side
  }

  return (
    <div className="space-y-4">
      {/* Quarter ruler */}
      <div className="relative h-6 ml-40 mr-4 border-b border-gray-200">
        {allQuarters.map(q => (
          <div
            key={q}
            className="absolute text-xs text-gray-400 -translate-x-1/2"
            style={{ left: `calc(5% + ${pct(q)}%)` }}
          >
            {q}
          </div>
        ))}
      </div>

      {/* Phase swimlanes */}
      {data.phases.map(phase => {
        const cfg = PHASE_CONFIG[phase.phase] ?? PHASE_CONFIG['ADVISORY']
        const isOpen = expandedPhase === phase.phase

        return (
          <div key={phase.phase} className={`rounded-lg border ${cfg.border} overflow-hidden`}>
            {/* Phase header */}
            <div
              className={`flex items-center gap-3 px-4 py-2 cursor-pointer select-none ${cfg.bg}`}
              onClick={() => setExpandedPhase(isOpen ? null : phase.phase)}
            >
              <span className={`text-sm font-semibold ${cfg.color} w-36 shrink-0`}>
                {cfg.label}
              </span>
              <StatusBadge status={phase.status} />
              <span className="text-xs text-gray-400 ml-2">
                {phase.milestones.length} milestone{phase.milestones.length !== 1 ? 's' : ''}
              </span>
              <div className="ml-auto text-gray-400">
                {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </div>
            </div>

            {/* Swimlane with milestone bars */}
            <div className="relative bg-white px-4 py-3 min-h-[56px]">
              {/* Grid lines */}
              {allQuarters.map(q => (
                <div
                  key={q}
                  className="absolute top-0 bottom-0 border-l border-gray-100"
                  style={{ left: `calc(160px + (100% - 176px) * ${(5 + pct(q)) / 100})` }}
                />
              ))}

              {/* Milestone dots / diamonds */}
              <div className="relative ml-40">
                {phase.milestones.map((m, i) => {
                  const leftPct = 5 + pct(m.targetDate)
                  return (
                    <div
                      key={m.name}
                      className="absolute flex flex-col items-center group"
                      style={{ left: `${leftPct}%`, top: `${i * 28}px` }}
                    >
                      {/* Diamond shape */}
                      <div
                        className={`w-3 h-3 rotate-45 shrink-0 ${
                          m.status === 'COMPLETED' ? 'bg-green-500' :
                          m.status === 'IN_PROGRESS' ? 'bg-blue-500' :
                          m.status === 'DELAYED' ? 'bg-amber-400' :
                          m.status === 'BLOCKED' ? 'bg-red-500' :
                          'bg-gray-300'
                        } ${m.fundingTrigger ? 'ring-2 ring-offset-1 ring-yellow-400' : ''}`}
                      />
                      {/* Tooltip */}
                      <div className="absolute bottom-full mb-1 -translate-x-1/2 hidden group-hover:block z-10 bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap">
                        <div className="font-medium">{m.name}</div>
                        <div className="text-gray-300">{m.targetDate} · {m.owner}</div>
                        {m.fundingTrigger && m.drawdownAmount && (
                          <div className="text-yellow-300">Drawdown: {fmtEur(m.drawdownAmount)}</div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Height spacer based on milestone count */}
              <div style={{ height: `${phase.milestones.length * 28 + 8}px` }} />
            </div>

            {/* Expanded detail list */}
            {isOpen && (
              <div className={`border-t ${cfg.border} divide-y divide-gray-100`}>
                {phase.milestones.map(m => (
                  <div key={m.name} className="flex items-center gap-3 px-4 py-2 bg-white text-sm">
                    <StatusBadge status={m.status} />
                    <span className="font-medium text-gray-800 flex-1">{m.name}</span>
                    <span className="text-xs text-gray-500 flex items-center gap-1">
                      <Calendar size={11} /> {m.targetDate}
                    </span>
                    <span className="text-xs text-gray-500 flex items-center gap-1 w-36">
                      <User size={11} /> {m.owner}
                    </span>
                    {m.fundingTrigger && m.drawdownAmount ? (
                      <span className="text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 px-2 py-0.5 rounded flex items-center gap-1">
                        <Euro size={10} /> {fmtEur(m.drawdownAmount)}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-300 w-16 text-right">—</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      <div className="flex items-center gap-4 text-xs text-gray-400 pt-2">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rotate-45 inline-block bg-green-500" /> Completed
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rotate-45 inline-block bg-blue-500" /> In Progress
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rotate-45 inline-block bg-gray-300" /> Planned
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rotate-45 inline-block bg-green-500 ring-2 ring-yellow-400" /> Funding Trigger
        </span>
      </div>
    </div>
  )
}

// ─────────────────────────────── Drawdown Tab ────────────────────────────────

function DrawdownTab({ data }: { data: TimelineData }) {
  const drawdownMilestones = useMemo(() => {
    const result: Array<Milestone & { phase: PhaseName }> = []
    data.phases.forEach(p => {
      p.milestones.filter(m => m.fundingTrigger && m.drawdownAmount).forEach(m => {
        result.push({ ...m, phase: p.phase })
      })
    })
    return result.sort((a, b) => quarterToIndex(a.targetDate) - quarterToIndex(b.targetDate))
  }, [data])

  const totalAsk = drawdownMilestones.reduce((s, m) => s + (m.drawdownAmount ?? 0), 0)

  if (drawdownMilestones.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        No drawdown triggers defined for this project yet.
      </div>
    )
  }

  // Build S-curve points
  const SVG_W = 700
  const SVG_H = 220
  const PAD_LEFT = 60
  const PAD_RIGHT = 20
  const PAD_TOP = 20
  const PAD_BOTTOM = 40
  const chartW = SVG_W - PAD_LEFT - PAD_RIGHT
  const chartH = SVG_H - PAD_TOP - PAD_BOTTOM

  const quarters: string[] = []
  if (drawdownMilestones.length > 0) {
    const first = quarterToIndex(drawdownMilestones[0].targetDate)
    const last = quarterToIndex(drawdownMilestones[drawdownMilestones.length - 1].targetDate) + 2
    for (let i = first; i <= last; i++) {
      const yr = 2025 + Math.floor(i / 4)
      const q = (i % 4) + 1
      quarters.push(`${yr}-Q${q}`)
    }
  }
  if (quarters.length < 2) quarters.push('2030-Q1')

  const qSpan = quarters.length - 1

  function xForQ(q: string) {
    const idx = quarters.indexOf(q)
    if (idx < 0) {
      // extrapolate
      const first = quarterToIndex(quarters[0])
      const rel = quarterToIndex(q) - first
      return PAD_LEFT + (rel / qSpan) * chartW
    }
    return PAD_LEFT + (idx / qSpan) * chartW
  }

  // Cumulative points
  const cumulativePoints: Array<{ x: number; y: number; label: string }> = [
    { x: PAD_LEFT, y: PAD_TOP + chartH, label: quarters[0] },
  ]
  let runningSum = 0
  drawdownMilestones.forEach(m => {
    runningSum += m.drawdownAmount ?? 0
    const x = xForQ(m.targetDate)
    const y = PAD_TOP + chartH - (runningSum / totalAsk) * chartH
    cumulativePoints.push({ x, y, label: m.targetDate })
  })
  // Extend flat line to end
  cumulativePoints.push({ x: PAD_LEFT + chartW, y: cumulativePoints[cumulativePoints.length - 1].y, label: '' })

  const committedPoints = cumulativePoints
    .filter((_, i) => {
      if (i === 0) return true
      const milestone = drawdownMilestones[i - 1]
      return milestone && (milestone.status === 'COMPLETED' || milestone.status === 'IN_PROGRESS')
    })
    .slice(0, drawdownMilestones.filter(m => m.status === 'COMPLETED' || m.status === 'IN_PROGRESS').length + 1)

  const toPolyline = (pts: Array<{ x: number; y: number }>) =>
    pts.map(p => `${p.x},${p.y}`).join(' ')

  // Y axis labels
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0]

  return (
    <div className="space-y-6">
      {/* S-curve SVG */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="text-sm font-semibold text-gray-700 mb-3">Cumulative Drawdown S-Curve</div>
        <svg width={SVG_W} height={SVG_H} className="w-full" viewBox={`0 0 ${SVG_W} ${SVG_H}`}>
          {/* Grid */}
          {yTicks.map(t => {
            const y = PAD_TOP + chartH - t * chartH
            return (
              <g key={t}>
                <line x1={PAD_LEFT} y1={y} x2={PAD_LEFT + chartW} y2={y} stroke="#f0f0f0" strokeWidth="1" />
                <text x={PAD_LEFT - 8} y={y + 4} textAnchor="end" fontSize="10" fill="#9ca3af">
                  €{(t * totalAsk / 1_000_000).toFixed(0)}M
                </text>
              </g>
            )
          })}
          {/* X axis quarter labels */}
          {quarters.filter((_, i) => i % 2 === 0).map(q => (
            <text key={q} x={xForQ(q)} y={SVG_H - 6} textAnchor="middle" fontSize="10" fill="#9ca3af">
              {q}
            </text>
          ))}
          {/* Axes */}
          <line x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={PAD_TOP + chartH} stroke="#d1d5db" strokeWidth="1" />
          <line x1={PAD_LEFT} y1={PAD_TOP + chartH} x2={PAD_LEFT + chartW} y2={PAD_TOP + chartH} stroke="#d1d5db" strokeWidth="1" />

          {/* Planned (all) — blue dashed */}
          <polyline
            points={toPolyline(cumulativePoints)}
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2"
            strokeDasharray="6 3"
          />
          {/* Committed — green solid */}
          {committedPoints.length > 1 && (
            <polyline
              points={toPolyline(committedPoints)}
              fill="none"
              stroke="#22c55e"
              strokeWidth="2.5"
            />
          )}

          {/* Milestone dots on planned line */}
          {cumulativePoints.slice(1, -1).map((pt, i) => (
            <circle key={i} cx={pt.x} cy={pt.y} r="4" fill="#3b82f6" />
          ))}

          {/* Legend */}
          <g transform={`translate(${PAD_LEFT + 10}, ${PAD_TOP + 10})`}>
            <line x1="0" y1="6" x2="20" y2="6" stroke="#22c55e" strokeWidth="2.5" />
            <text x="24" y="10" fontSize="11" fill="#4b5563">Committed</text>
            <line x1="70" y1="6" x2="90" y2="6" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5 3" />
            <text x="94" y="10" fontSize="11" fill="#4b5563">Planned</text>
          </g>
        </svg>
      </div>

      {/* Per-milestone bar chart */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <div className="text-sm font-semibold text-gray-700 mb-3">Per-Milestone Drawdown Amounts</div>
        <div className="space-y-2">
          {drawdownMilestones.map(m => {
            const cfg = PHASE_CONFIG[m.phase] ?? PHASE_CONFIG['ADVISORY']
            const barPct = ((m.drawdownAmount ?? 0) / totalAsk) * 100
            return (
              <div key={m.name} className="flex items-center gap-3 text-sm">
                <span className="w-48 shrink-0 text-gray-700 truncate">{m.name}</span>
                <div className="flex-1 bg-gray-100 rounded h-5 overflow-hidden">
                  <div
                    className={`h-full ${cfg.barBg} rounded`}
                    style={{ width: `${barPct}%` }}
                  />
                </div>
                <span className="w-16 text-right text-gray-600 font-medium shrink-0">
                  {fmtEur(m.drawdownAmount ?? 0)}
                </span>
                <span className="w-16 text-right text-gray-400 shrink-0 text-xs">{m.targetDate}</span>
              </div>
            )
          })}
          <div className="flex items-center gap-3 text-sm border-t pt-2 mt-2">
            <span className="w-48 shrink-0 font-semibold text-gray-800">Total Ask</span>
            <div className="flex-1" />
            <span className="w-16 text-right font-bold text-gray-900">{fmtEur(totalAsk)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────── Milestones Tab ──────────────────────────────

function MilestonesTab({ data }: { data: TimelineData }) {
  const [sortKey, setSortKey] = useState<SortKey>('targetDate')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [phaseFilter, setPhaseFilter] = useState<string>('ALL')

  const allMilestones = useMemo(() => {
    const flat: Array<Milestone & { phase: PhaseName }> = []
    data.phases.forEach(p => p.milestones.forEach(m => flat.push({ ...m, phase: p.phase })))
    return flat
  }, [data])

  const filtered = useMemo(() => {
    return allMilestones.filter(m => phaseFilter === 'ALL' || m.phase === phaseFilter)
  }, [allMilestones, phaseFilter])

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let av: any, bv: any
      if (sortKey === 'targetDate') {
        av = quarterToIndex(a.targetDate)
        bv = quarterToIndex(b.targetDate)
      } else if (sortKey === 'drawdownAmount') {
        av = a.drawdownAmount ?? 0
        bv = b.drawdownAmount ?? 0
      } else {
        av = (a as any)[sortKey] ?? ''
        bv = (b as any)[sortKey] ?? ''
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [filtered, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronDown size={12} className="text-gray-300" />
    return sortDir === 'asc' ? <ChevronUp size={12} className="text-gray-500" /> : <ChevronDown size={12} className="text-gray-500" />
  }

  const phases = data.phases.map(p => p.phase)

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-500">Phase:</label>
        <select
          value={phaseFilter}
          onChange={e => setPhaseFilter(e.target.value)}
          className="text-sm border border-gray-200 rounded px-3 py-1.5 bg-white text-gray-700"
        >
          <option value="ALL">All Phases</option>
          {phases.map(p => (
            <option key={p} value={p}>{PHASE_CONFIG[p]?.label ?? p}</option>
          ))}
        </select>
        <span className="text-xs text-gray-400">{sorted.length} milestone{sorted.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {([
                ['name', 'Milestone'],
                ['phase', 'Phase'],
                ['targetDate', 'Target Date'],
                ['status', 'Status'],
                ['owner', 'Owner'],
                ['drawdownAmount', 'Funding Trigger'],
              ] as [SortKey, string][]).map(([key, label]) => (
                <th
                  key={key}
                  className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                  onClick={() => toggleSort(key)}
                >
                  <span className="flex items-center gap-1">
                    {label}
                    <SortIcon k={key} />
                  </span>
                </th>
              ))}
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Variance
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((m, i) => {
              const rowBg =
                m.status === 'DELAYED' ? 'bg-amber-50' :
                m.status === 'BLOCKED' ? 'bg-red-50' :
                i % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
              return (
                <tr key={`${m.phase}-${m.name}`} className={rowBg}>
                  <td className="px-4 py-2.5 font-medium text-gray-800">
                    <div className="flex items-center gap-1.5">
                      {m.fundingTrigger && <Flag size={12} className="text-yellow-500 shrink-0" />}
                      {m.name}
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <PhaseBadge phase={m.phase} />
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">{m.targetDate}</td>
                  <td className="px-4 py-2.5">
                    <StatusBadge status={m.status} />
                  </td>
                  <td className="px-4 py-2.5 text-gray-600">{m.owner}</td>
                  <td className="px-4 py-2.5">
                    {m.fundingTrigger && m.drawdownAmount ? (
                      <span className="text-yellow-700 font-medium">{fmtEur(m.drawdownAmount)}</span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {m.status === 'DELAYED' ? (
                      <span className="text-amber-600 text-xs">+1Q est.</span>
                    ) : m.status === 'BLOCKED' ? (
                      <span className="text-red-600 text-xs">TBD</span>
                    ) : m.status === 'COMPLETED' ? (
                      <span className="text-green-600 text-xs">On time</span>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─────────────────────────────── Main component ──────────────────────────────

type Tab = 'timeline' | 'drawdown' | 'milestones'

export function ProjectTimeline() {
  const { selectedProjectId } = useSelectedProject()
  const [activeTab, setActiveTab] = useState<Tab>('timeline')

  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  const rawData = generateTimelineData(selectedProjectId ?? '')

  // Fetch the PROTECTED sensitive layer. The endpoint 403s unauthorized callers;
  // success === authorized for this project. The sensitive data is never in the
  // bundle — it only exists here if the backend authorised and returned it.
  const [layer, setLayer] = useState<DrawdownLayer | null>(null)
  useEffect(() => {
    let cancelled = false
    setLayer(null) // fail closed by default
    if (!selectedProjectId) return
    fetch(`/api/v1/finance-model/drawdown-timeline/${encodeURIComponent(selectedProjectId)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(j => { if (!cancelled && j && j.financial_close) setLayer(j as DrawdownLayer) })
      .catch(() => { /* fail closed — no sensitive layer */ })
    return () => { cancelled = true }
  }, [selectedProjectId])

  const financeEntitled = layer !== null
  const data = financeEntitled ? mergeSensitiveLayer(rawData, layer) : rawData

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'timeline',   label: 'Timeline' },
    // Drawdown Schedule (S-curve of drawdown amounts) is finance-only.
    ...(financeEntitled ? [{ id: 'drawdown' as Tab, label: 'Drawdown Schedule' }] : []),
    { id: 'milestones', label: 'Milestones' },
  ]
  // If a non-entitled user is somehow on the drawdown tab, send them to timeline.
  const safeTab: Tab = (activeTab === 'drawdown' && !financeEntitled) ? 'timeline' : activeTab

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Project Timeline</h1>
        <p className="text-sm text-gray-500 mt-1">
          {project?.name ?? selectedProjectId ?? 'Select a project'} — Milestone{financeEntitled ? ' & Drawdown' : ''} Schedule
        </p>
        {!financeEntitled && (
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.08em] text-amber-700">
            Drawdown / Financial Close detail redacted — requires finance entitlement
          </p>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              safeTab === tab.id
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/40'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {safeTab === 'timeline'   && <TimelineTab data={data} />}
      {safeTab === 'drawdown'   && financeEntitled && <DrawdownTab data={data} />}
      {safeTab === 'milestones' && <MilestonesTab data={data} />}
    </div>
  )
}
