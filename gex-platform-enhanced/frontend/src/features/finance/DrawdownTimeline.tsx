// Screen: Post-FID drawdown timeline (/finance/drawdown-timeline)
/**
 * DrawdownTimeline — quarterly Gantt-style timeline showing post-FID
 * drawdowns per tranche with status coloring and milestone markers.
 */
import { useState } from 'react'
import { Calendar, Milestone, ChevronDown, ChevronUp } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type DrawdownStatus = 'REQUESTED' | 'APPROVED' | 'DISBURSED' | 'RECONCILED'

interface DrawdownCell {
  status: DrawdownStatus
  amount: number  // €M
}

interface Tranche {
  id: string
  name: string
  totalCommitted: number  // €M
  cells: Record<string, DrawdownCell>  // key = quarter label e.g. "Q1-2029"
}

interface MilestoneMarker {
  quarter: string
  label: string
  icon: string
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const STATUS_STYLE: Record<DrawdownStatus, { bg: string; text: string; border: string; label: string }> = {
  REQUESTED:  { bg: 'bg-amber-100',   text: 'text-amber-700',  border: 'border-amber-300',  label: 'Requested'  },
  APPROVED:   { bg: 'bg-blue-100',    text: 'text-blue-700',   border: 'border-blue-300',   label: 'Approved'   },
  DISBURSED:  { bg: 'bg-teal-100',    text: 'text-teal-700',   border: 'border-teal-300',   label: 'Disbursed'  },
  RECONCILED: { bg: 'bg-green-100',   text: 'text-green-700',  border: 'border-green-300',  label: 'Reconciled' },
}

const QUARTERS = [
  'Q1-2029', 'Q2-2029', 'Q3-2029', 'Q4-2029',
  'Q1-2030', 'Q2-2030', 'Q3-2030', 'Q4-2030',
  'Q1-2031', 'Q2-2031', 'Q3-2031', 'Q4-2031',
]

// ═══════════════════════════════════════════════════════════════
// MOCK DATA — ETFuels Pecos I post-FID drawdowns
// ═══════════════════════════════════════════════════════════════

const MOCK_MILESTONES: MilestoneMarker[] = [
  { quarter: 'Q2-2029', label: 'EPC 25%',  icon: '25' },
  { quarter: 'Q4-2029', label: 'EPC 50%',  icon: '50' },
  { quarter: 'Q4-2031', label: 'COD',       icon: 'COD' },
]

const MOCK_TRANCHES: Record<string, Tranche[]> = {
  proj_etf_pecos1: [
    {
      id: 'senior',
      name: 'Senior Debt (Syndicate)',
      totalCommitted: 285,
      cells: {
        'Q1-2029': { status: 'DISBURSED',  amount: 28.5 },
        'Q2-2029': { status: 'DISBURSED',  amount: 42.8 },
        'Q3-2029': { status: 'DISBURSED',  amount: 42.8 },
        'Q4-2029': { status: 'RECONCILED', amount: 42.8 },
        'Q1-2030': { status: 'APPROVED',   amount: 42.8 },
        'Q2-2030': { status: 'APPROVED',   amount: 42.8 },
        'Q3-2030': { status: 'REQUESTED',  amount: 28.5 },
        'Q4-2030': { status: 'REQUESTED',  amount: 14.0 },
      },
    },
    {
      id: 'eib',
      name: 'EIB Concessional',
      totalCommitted: 120,
      cells: {
        'Q1-2029': { status: 'DISBURSED',  amount: 12.0 },
        'Q2-2029': { status: 'DISBURSED',  amount: 18.0 },
        'Q3-2029': { status: 'DISBURSED',  amount: 24.0 },
        'Q4-2029': { status: 'RECONCILED', amount: 24.0 },
        'Q1-2030': { status: 'APPROVED',   amount: 18.0 },
        'Q2-2030': { status: 'APPROVED',   amount: 12.0 },
        'Q3-2030': { status: 'REQUESTED',  amount: 12.0 },
      },
    },
    {
      id: 'eca',
      name: 'ECA (EXIM)',
      totalCommitted: 95,
      cells: {
        'Q2-2029': { status: 'DISBURSED',  amount: 14.2 },
        'Q3-2029': { status: 'DISBURSED',  amount: 19.0 },
        'Q4-2029': { status: 'RECONCILED', amount: 19.0 },
        'Q1-2030': { status: 'APPROVED',   amount: 19.0 },
        'Q2-2030': { status: 'REQUESTED',  amount: 14.2 },
        'Q3-2030': { status: 'REQUESTED',  amount: 9.6  },
      },
    },
    {
      id: 'equity',
      name: 'Sponsor Equity',
      totalCommitted: 112,
      cells: {
        'Q1-2029': { status: 'RECONCILED', amount: 22.4 },
        'Q2-2029': { status: 'RECONCILED', amount: 22.4 },
        'Q3-2029': { status: 'DISBURSED',  amount: 22.4 },
        'Q4-2029': { status: 'DISBURSED',  amount: 22.4 },
        'Q1-2030': { status: 'APPROVED',   amount: 11.2 },
        'Q2-2030': { status: 'APPROVED',   amount: 11.2 },
      },
    },
  ],
  default: [
    {
      id: 'senior',
      name: 'Senior Debt',
      totalCommitted: 200,
      cells: {
        'Q1-2029': { status: 'DISBURSED',  amount: 25.0 },
        'Q2-2029': { status: 'DISBURSED',  amount: 35.0 },
        'Q3-2029': { status: 'APPROVED',   amount: 35.0 },
        'Q4-2029': { status: 'APPROVED',   amount: 35.0 },
        'Q1-2030': { status: 'REQUESTED',  amount: 35.0 },
        'Q2-2030': { status: 'REQUESTED',  amount: 35.0 },
      },
    },
    {
      id: 'concessional',
      name: 'Concessional (DFI)',
      totalCommitted: 80,
      cells: {
        'Q1-2029': { status: 'DISBURSED', amount: 16.0 },
        'Q2-2029': { status: 'DISBURSED', amount: 16.0 },
        'Q3-2029': { status: 'APPROVED',  amount: 16.0 },
        'Q4-2029': { status: 'APPROVED',  amount: 16.0 },
        'Q1-2030': { status: 'REQUESTED', amount: 16.0 },
      },
    },
    {
      id: 'eca',
      name: 'ECA Guarantee',
      totalCommitted: 60,
      cells: {
        'Q2-2029': { status: 'DISBURSED', amount: 15.0 },
        'Q3-2029': { status: 'APPROVED',  amount: 15.0 },
        'Q4-2029': { status: 'REQUESTED', amount: 15.0 },
        'Q1-2030': { status: 'REQUESTED', amount: 15.0 },
      },
    },
    {
      id: 'equity',
      name: 'Sponsor Equity',
      totalCommitted: 90,
      cells: {
        'Q1-2029': { status: 'RECONCILED', amount: 18.0 },
        'Q2-2029': { status: 'RECONCILED', amount: 18.0 },
        'Q3-2029': { status: 'DISBURSED',  amount: 18.0 },
        'Q4-2029': { status: 'DISBURSED',  amount: 18.0 },
        'Q1-2030': { status: 'APPROVED',   amount: 18.0 },
      },
    },
  ],
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

function fmt(n: number): string {
  return n.toFixed(1)
}

function trancheDrawn(t: Tranche): number {
  return Object.values(t.cells).reduce((s, c) => s + c.amount, 0)
}

// ═══════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════

export function DrawdownTimeline() {
  const { selectedProjectId } = useSelectedProject()
  const [showSummary, setShowSummary] = useState(true)

  // No modelled drawdown schedule for this project (e.g. a project created via
  // the on-ramp, or one that hasn't reached financial close). Do NOT borrow the
  // 'default' demo schedule — a drawdown calendar implies committed debt and
  // signed facilities. Show an honest empty state instead.
  const tranches = MOCK_TRANCHES[selectedProjectId]
  if (!tranches) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 pb-8">
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden dark:border-[var(--border)] dark:bg-[var(--surface)]">
          <div className="flex items-center gap-2 px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Drawdown Timeline</span>
          </div>
        </div>
        <div className="flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          <Calendar className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            No drawdown schedule exists for this project yet. A quarterly drawdown calendar implies
            <strong> committed debt and signed facilities</strong> — it appears once the capital is committed at
            financial close (G10). Until then there is nothing to draw, and showing a schedule would be fiction.
          </span>
        </div>
      </div>
    )
  }

  const milestones = MOCK_MILESTONES

  const totalCommitted = tranches.reduce((s, t) => s + t.totalCommitted, 0)
  const totalDrawn = tranches.reduce((s, t) => s + trancheDrawn(t), 0)

  // Count statuses across all cells
  const statusCounts: Record<DrawdownStatus, number> = { REQUESTED: 0, APPROVED: 0, DISBURSED: 0, RECONCILED: 0 }
  for (const t of tranches) {
    for (const c of Object.values(t.cells)) {
      statusCounts[c.status]++
    }
  }

  return (
    <div className="space-y-4 max-w-7xl mx-auto pb-8">

      {/* Header */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Calendar className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Drawdown Timeline</span>
            </div>
            <h1 className="text-2xl font-black text-white">Post-FID Quarterly Drawdowns</h1>
            <p className="text-sm text-gray-400 mt-0.5">{QUARTERS[0]} through {QUARTERS[QUARTERS.length - 1]}</p>
          </div>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">{fmt(totalCommitted)}M</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Total Committed</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-teal-600">{fmt(totalDrawn)}M</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Total Scheduled</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-gray-900">{tranches.length}</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Tranches</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm text-center">
          <div className="text-2xl font-black tabular-nums text-green-600">{statusCounts.RECONCILED}</div>
          <div className="text-xs font-semibold text-gray-500 mt-1">Reconciled Draws</div>
        </div>
      </div>

      {/* Status legend */}
      <div className="flex flex-wrap gap-3 px-1">
        {(Object.keys(STATUS_STYLE) as DrawdownStatus[]).map(status => {
          const s = STATUS_STYLE[status]
          return (
            <div key={status} className="flex items-center gap-1.5">
              <div className={`w-3 h-3 rounded-sm ${s.bg} border ${s.border}`} />
              <span className={`text-xs font-semibold ${s.text}`}>{s.label}</span>
              <span className="text-xs tabular-nums text-gray-500">({statusCounts[status]})</span>
            </div>
          )
        })}
      </div>

      {/* Gantt timeline */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
            Quarterly Drawdown Schedule
          </h3>
          <InfoTooltip text="Each row is a capital tranche. Filled cells show drawdowns with their status. Milestone markers indicate EPC progress and COD." />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="sticky left-0 z-10 bg-gray-50 text-left px-4 py-2.5 font-semibold text-gray-500 uppercase tracking-wide min-w-[180px] border-r border-gray-100">
                  Tranche
                </th>
                {QUARTERS.map(q => {
                  const milestone = milestones.find(m => m.quarter === q)
                  return (
                    <th key={q} className="text-center px-1.5 py-2.5 font-semibold text-gray-500 uppercase tracking-wide min-w-[72px] relative">
                      <div>{q}</div>
                      {milestone && (
                        <div className="flex items-center justify-center mt-1">
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 text-[9px] font-bold">
                            <Milestone className="w-2.5 h-2.5" />
                            {milestone.label}
                          </span>
                        </div>
                      )}
                    </th>
                  )
                })}
                <th className="text-right px-3 py-2.5 font-semibold text-gray-500 uppercase tracking-wide min-w-[80px] border-l border-gray-100">
                  Drawn / Total
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {tranches.map(tranche => {
                const drawn = trancheDrawn(tranche)
                const pct = tranche.totalCommitted > 0 ? (drawn / tranche.totalCommitted * 100) : 0
                return (
                  <tr key={tranche.id} className="hover:bg-gray-50/60">
                    <td className="sticky left-0 z-10 bg-white px-4 py-3 border-r border-gray-100">
                      <div className="font-semibold text-gray-800">{tranche.name}</div>
                      <div className="text-gray-400 text-[10px] mt-0.5">{fmt(tranche.totalCommitted)}M committed</div>
                    </td>
                    {QUARTERS.map(q => {
                      const cell = tranche.cells[q]
                      if (!cell) {
                        return <td key={q} className="text-center px-1.5 py-3"><div className="w-full h-7" /></td>
                      }
                      const s = STATUS_STYLE[cell.status]
                      return (
                        <td key={q} className="text-center px-1.5 py-3">
                          <div
                            className={`${s.bg} ${s.text} border ${s.border} rounded-md px-1 py-1.5 font-bold tabular-nums`}
                            title={`${s.label}: ${fmt(cell.amount)}M`}
                          >
                            {fmt(cell.amount)}
                          </div>
                        </td>
                      )
                    })}
                    <td className="text-right px-3 py-3 border-l border-gray-100">
                      <div className="font-bold tabular-nums text-gray-900">{fmt(drawn)}M</div>
                      <div className="text-gray-400 text-[10px]">{pct.toFixed(0)}% of {fmt(tranche.totalCommitted)}M</div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Summary table (collapsible) */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setShowSummary(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
        >
          <span className="text-xs font-black uppercase tracking-widest text-gray-600">
            Tranche Utilisation Summary
          </span>
          {showSummary ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </button>
        {showSummary && (
          <div className="px-4 py-3">
            <div className="space-y-2">
              {tranches.map(tranche => {
                const drawn = trancheDrawn(tranche)
                const pct = tranche.totalCommitted > 0 ? (drawn / tranche.totalCommitted * 100) : 0
                return (
                  <div key={tranche.id}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-gray-700">{tranche.name}</span>
                      <span className="text-xs tabular-nums font-bold text-gray-900">
                        {fmt(drawn)}M / {fmt(tranche.totalCommitted)}M ({pct.toFixed(0)}%)
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-teal-500 transition-all"
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
