import { useState, useEffect } from 'react'
import { Printer, AlertTriangle, CheckSquare, Square, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

interface PortfolioRow {
  id: string
  name: string
  state: string
  trustScore: number
  dscrP50: number
  nextGate: string
}

interface KPICard {
  label: string
  value: string
  delta: string
  trend: 'up' | 'down' | 'neutral'
  sentiment: 'green' | 'amber' | 'red'
  note?: string
}

interface RiskItem {
  rank: number
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  title: string
  detail: string
}

interface DecisionItem {
  id: string
  text: string
  deadline: string
}

interface GanttRow {
  project: string
  tasks: { label: string; start: number; end: number; color: string }[]
}

// ═══════════════════════════════════════════════════════════════
// DEMO DATA
// ═══════════════════════════════════════════════════════════════

const PORTFOLIO_ROWS: PortfolioRow[] = [
  { id: 'proj_le_havre_eng',    name: 'Le Havre H₂',     state: 'BANKABLE',   trustScore: 94, dscrP50: 1.58, nextGate: 'G10 FID' },
  { id: 'proj_bremen_h2',       name: 'Bremen H₂',       state: 'BUILDABLE',  trustScore: 72, dscrP50: 1.34, nextGate: 'G5 EPC' },
  { id: 'proj_helios_emethanol',name: 'Helios e-MeOH',   state: 'FUNDABLE',   trustScore: 51, dscrP50: 1.22, nextGate: 'G3 Offtake' },
  { id: 'proj_rotterdam_nh3',   name: 'Rotterdam NH₃',   state: 'EARLY_DEV',  trustScore: 40, dscrP50: 1.05, nextGate: 'G1 Grid' },
  { id: 'proj_wales_saf',       name: 'Wales SAF',        state: 'EARLY_DEV',  trustScore: 30, dscrP50: 0.98, nextGate: 'G1 Offtake' },
]

const KPI_CARDS: KPICard[] = [
  { label: 'Portfolio avg WACC',       value: '10.78%',    delta: '+0.3% vs LM', trend: 'up',      sentiment: 'red',   note: 'Rate environment pressure' },
  { label: 'Portfolio DSCR range',     value: '0.98–1.58', delta: 'improving',   trend: 'up',      sentiment: 'green', note: 'Le Havre leading' },
  { label: 'Contracted revenue (avg)', value: '57%',       delta: 'target 80%',  trend: 'neutral', sentiment: 'amber', note: '3 projects below threshold' },
  { label: 'Cert readiness avg',       value: '53/100',    delta: '+5 vs LM',    trend: 'up',      sentiment: 'green', note: 'Le Havre & Bremen progressing' },
  { label: 'Projects BANKABLE',        value: '1/5',       delta: 'target 3/5',  trend: 'neutral', sentiment: 'amber', note: 'EOY target at risk' },
  { label: 'Projects at FID risk',     value: '2',         delta: 'Wales, Rott.', trend: 'down',   sentiment: 'red',   note: 'Action required this quarter' },
]

const RISKS: RiskItem[] = [
  {
    rank: 1,
    severity: 'HIGH',
    title: 'Grid connection delays',
    detail: 'Bremen G1 pending utility sign-off. Rotterdam grid application not yet started. Both projects at risk of 12–18 month slippage.',
  },
  {
    rank: 2,
    severity: 'HIGH',
    title: 'Offtake coverage insufficient',
    detail: 'Wales 20%, Rotterdam 35% contracted — both below the 70% senior lender threshold. Financial close unreachable under current structure.',
  },
  {
    rank: 3,
    severity: 'MEDIUM',
    title: 'EPC performance guarantee gap',
    detail: 'Bremen G5 performance guarantees not yet finalised. EPC contractor has not confirmed liquidated damages schedule. Blocking FID.',
  },
]

const DECISIONS: DecisionItem[] = [
  {
    id: 'd1',
    text: 'Approve BP engagement as second offtaker for Rotterdam NH₃',
    deadline: 'Deadline: Q2-2026',
  },
  {
    id: 'd2',
    text: 'Authorize KfW pre-mandate engagement for Bremen H₂ (budget: €85K advisory fee)',
    deadline: 'Deadline: April 2026',
  },
  {
    id: 'd3',
    text: 'Confirm EPC shortlist for Wales SAF pre-FEED (3 bidders, board approval needed)',
    deadline: 'Deadline: Q3-2026',
  },
]

const GANTT_ROWS: GanttRow[] = [
  {
    project: 'Le Havre',
    tasks: [
      { label: 'IE sign-off',      start: 1,  end: 4,  color: '#22c55e' },
      { label: 'BPI term sheet',   start: 5,  end: 8,  color: '#3b82f6' },
      { label: 'FID prep',         start: 9,  end: 12, color: '#8b5cf6' },
    ],
  },
  {
    project: 'Bremen',
    tasks: [
      { label: 'Grid utility mtg', start: 1,  end: 2,  color: '#f59e0b' },
      { label: 'EPC wrap',         start: 3,  end: 8,  color: '#3b82f6' },
      { label: 'EIB engagement',   start: 9,  end: 12, color: '#22c55e' },
    ],
  },
  {
    project: 'Helios',
    tasks: [
      { label: 'CO₂ supply agmt',  start: 1,  end: 6,  color: '#f59e0b' },
      { label: 'EPC pre-FEED',     start: 7,  end: 12, color: '#3b82f6' },
    ],
  },
]

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

function trafficLight(dscr: number, trust: number): 'green' | 'amber' | 'red' {
  if (dscr >= 1.30 && trust >= 70) return 'green'
  if (dscr < 1.10 || trust < 35) return 'red'
  return 'amber'
}

const TRAFFIC_COLOR: Record<string, string> = {
  green: '#22c55e',
  amber: '#f59e0b',
  red:   '#ef4444',
}

const STATE_BG: Record<string, string> = {
  BANKABLE:  'bg-green-100 text-green-800',
  BUILDABLE: 'bg-blue-100 text-blue-800',
  FUNDABLE:  'bg-purple-100 text-purple-800',
  EARLY_DEV: 'bg-gray-100 text-gray-600',
}

const SEVERITY_BG: Record<string, string> = {
  HIGH:   'bg-red-100 text-red-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  LOW:    'bg-green-100 text-green-700',
}

const SENTIMENT_COLOR: Record<string, string> = {
  green: 'text-green-600',
  amber: 'text-amber-600',
  red:   'text-red-600',
}

// Small trust-score arc (SVG, 60px)
function TrustArc({ score }: { score: number }) {
  const r = 22
  const cx = 30
  const cy = 30
  const circumference = Math.PI * r  // half-circle arc length
  const fill = (score / 100) * circumference
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444'
  return (
    <svg width={60} height={36} viewBox="0 0 60 36" className="inline-block">
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#e5e7eb" strokeWidth={5}
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke={color} strokeWidth={5}
        strokeDasharray={`${fill} ${circumference}`}
      />
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize={10} fontWeight="bold" fill={color}>{score}</text>
    </svg>
  )
}

// Gantt chart section (CSS-grid based)
function GanttChart() {
  const WEEKS = Array.from({ length: 12 }, (_, i) => i + 1)
  return (
    <div className="text-xs">
      {/* Header */}
      <div className="grid mb-1" style={{ gridTemplateColumns: '90px repeat(12, 1fr)' }}>
        <div />
        {WEEKS.map(w => (
          <div key={w} className="text-center font-medium" style={{ color: 'var(--text-muted, #6b7280)' }}>W{w}</div>
        ))}
      </div>
      {GANTT_ROWS.map(row => (
        <div key={row.project} className="grid items-center mb-2" style={{ gridTemplateColumns: '90px repeat(12, 1fr)', minHeight: 28 }}>
          <div className="font-semibold pr-2 truncate" style={{ color: 'var(--text, #111)' }}>{row.project}</div>
          {WEEKS.map(w => {
            const task = row.tasks.find(t => t.start <= w && t.end >= w)
            const isStart = task && task.start === w
            const isEnd   = task && task.end === w
            return (
              <div
                key={w}
                title={task?.label}
                style={{
                  backgroundColor: task ? task.color : 'transparent',
                  opacity: task ? 0.85 : 1,
                  borderRadius: isStart ? '4px 0 0 4px' : isEnd ? '0 4px 4px 0' : '0',
                  height: 20,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {isStart && task && (
                  <span className="text-white font-medium truncate px-1" style={{ fontSize: 9 }}>
                    {task.label}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function CFOReport() {
  const [generatedAt] = useState(() => new Date().toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }))

  // Section 1: Portfolio status rows
  const portfolioRows = PORTFOLIO_ROWS

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: 'var(--surface, #f8fafc)', color: 'var(--text, #0f172a)' }}>

      {/* ── Top bar ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6 print:hidden">
        <div className="flex items-center gap-3">
          <span className="px-3 py-1 text-xs font-bold rounded-full bg-red-100 text-red-700 uppercase tracking-widest border border-red-300">
            Internal — Strictly Confidential
          </span>
          <span className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>
            Generated: {generatedAt}
          </span>
        </div>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-opacity hover:opacity-90"
          style={{ backgroundColor: 'var(--brand, #0ea5e9)' }}
        >
          <Printer size={16} />
          Generate Report
        </button>
      </div>

      {/* ── Report header ───────────────────────────────────── */}
      <div className="mb-6 pb-4" style={{ borderBottom: '2px solid var(--border, #e2e8f0)' }}>
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: 'var(--brand, #0ea5e9)' }}>
          GreenEarthX — Executive Report
        </p>
        <h1 className="text-2xl font-bold mb-0.5">CFO → CEO Portfolio Report</h1>
        <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>
          Reporting period: March 2026 · Prepared by: Finance &amp; Strategy · {generatedAt}
        </p>
      </div>

      {/* ══════════════════════════════════════════════════════
          SECTION 1 — PORTFOLIO STATUS
      ══════════════════════════════════════════════════════ */}
      <section className="mb-8">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          1 · Portfolio Status
        </h2>
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border, #e2e8f0)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ backgroundColor: 'var(--surface-raised, #f1f5f9)' }}>
                {['Project', 'State', 'Trust Score', 'DSCR P50', 'Next Gate', 'Signal'].map(h => (
                  <th key={h} className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wide"
                    style={{ color: 'var(--text-muted, #64748b)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {portfolioRows.map((row, i) => {
                const light = trafficLight(row.dscrP50, row.trustScore)
                return (
                  <tr key={row.id} style={{ borderTop: i > 0 ? '1px solid var(--border, #e2e8f0)' : undefined }}>
                    <td className="px-4 py-3 font-medium">{row.name}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATE_BG[row.state] ?? 'bg-gray-100 text-gray-600'}`}>
                        {row.state}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <TrustArc score={row.trustScore} />
                    </td>
                    <td className="px-4 py-3 font-mono font-semibold">
                      {row.dscrP50.toFixed(2)}x
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-muted, #64748b)' }}>
                      {row.nextGate}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="inline-flex items-center justify-center w-5 h-5 rounded-full"
                        style={{ backgroundColor: TRAFFIC_COLOR[light] }}
                        title={light.toUpperCase()}
                      />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          SECTION 2 — FUNDING PIPELINE
      ══════════════════════════════════════════════════════ */}
      <section className="mb-8">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          2 · Funding Pipeline
        </h2>
        <div className="rounded-xl p-5" style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}>
          {/* Stacked bar */}
          <p className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: 'var(--text-muted, #64748b)' }}>
            Total portfolio capital stack
          </p>
          <div className="flex rounded-lg overflow-hidden h-8 mb-2">
            {/* Committed: €210M of €763M total ≈ 27.5% */}
            <div
              className="flex items-center justify-center text-white text-xs font-bold"
              style={{ width: '27.5%', backgroundColor: '#22c55e' }}
              title="Committed: €210M"
            >
              €210M
            </div>
            {/* DFI in progress: assume €150M ≈ 19.7% */}
            <div
              className="flex items-center justify-center text-white text-xs font-bold"
              style={{ width: '19.7%', backgroundColor: '#f59e0b' }}
              title="DFI in progress"
            >
              DFI
            </div>
            {/* Not secured: remainder */}
            <div
              className="flex items-center justify-center text-white text-xs font-bold flex-1"
              style={{ backgroundColor: '#94a3b8' }}
              title="Not secured: €403M"
            >
              €403M unsecured
            </div>
          </div>
          <div className="flex gap-4 text-xs mb-4">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-green-500 inline-block" /> Committed</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-amber-500 inline-block" /> DFI in progress</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-slate-400 inline-block" /> Not secured</span>
          </div>

          {/* Key item */}
          <div className="text-sm mb-4 p-3 rounded-lg bg-blue-50 border border-blue-200">
            <span className="font-semibold text-blue-800">Le Havre:</span>
            <span className="text-blue-700"> BPI mandate letter + EIB co-finance → Q2-2026 term sheet</span>
          </div>

          {/* Gap callout */}
          <div className="p-3 rounded-lg border border-red-300 bg-red-50 flex items-start gap-2">
            <AlertTriangle size={16} className="text-red-600 mt-0.5 shrink-0" />
            <p className="text-sm font-semibold text-red-700">
              €553M senior debt across portfolio requires immediate banker engagement. 4 of 5 projects have no committed financing.
            </p>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          SECTION 3 — KEY METRICS vs LAST MONTH
      ══════════════════════════════════════════════════════ */}
      <section className="mb-8">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          3 · Key Metrics vs Last Month
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {KPI_CARDS.map(kpi => (
            <div
              key={kpi.label}
              className="rounded-xl p-4"
              style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
            >
              <p className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: 'var(--text-muted, #64748b)' }}>
                {kpi.label}
              </p>
              <p className={`text-xl font-bold mb-1 ${SENTIMENT_COLOR[kpi.sentiment]}`}>
                {kpi.value}
              </p>
              <div className="flex items-center gap-1">
                {kpi.trend === 'up' && <TrendingUp size={12} className={SENTIMENT_COLOR[kpi.sentiment]} />}
                {kpi.trend === 'down' && <TrendingDown size={12} className={SENTIMENT_COLOR[kpi.sentiment]} />}
                {kpi.trend === 'neutral' && <Minus size={12} className={SENTIMENT_COLOR[kpi.sentiment]} />}
                <span className={`text-xs font-medium ${SENTIMENT_COLOR[kpi.sentiment]}`}>{kpi.delta}</span>
              </div>
              {kpi.note && (
                <p className="text-xs mt-1" style={{ color: 'var(--text-muted, #64748b)' }}>{kpi.note}</p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          SECTION 4 — RISK REGISTER
      ══════════════════════════════════════════════════════ */}
      <section className="mb-8">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          4 · Risk Register — Top Risks
        </h2>
        <div className="flex flex-col gap-3">
          {RISKS.map(risk => (
            <div
              key={risk.rank}
              className="rounded-xl p-4 flex gap-4 items-start"
              style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
            >
              <div className="shrink-0 flex flex-col items-center gap-1">
                <span className="text-xs font-bold" style={{ color: 'var(--text-muted, #64748b)' }}>#{risk.rank}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${SEVERITY_BG[risk.severity]}`}>
                  {risk.severity}
                </span>
              </div>
              <div>
                <p className="font-semibold text-sm mb-1">{risk.title}</p>
                <p className="text-sm" style={{ color: 'var(--text-muted, #64748b)' }}>{risk.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          SECTION 5 — DECISIONS REQUIRED
      ══════════════════════════════════════════════════════ */}
      <section className="mb-8">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          5 · Decisions Required
        </h2>
        <div
          className="rounded-xl p-5"
          style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
        >
          <div className="flex flex-col gap-4">
            {DECISIONS.map(d => (
              <div key={d.id} className="flex items-start gap-3">
                <Square size={18} className="mt-0.5 shrink-0" style={{ color: 'var(--brand, #0ea5e9)' }} />
                <div>
                  <p className="text-sm font-medium">{d.text}</p>
                  <p className="text-xs mt-0.5 font-semibold" style={{ color: 'var(--text-muted, #64748b)' }}>{d.deadline}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          SECTION 6 — 90-DAY OUTLOOK
      ══════════════════════════════════════════════════════ */}
      <section className="mb-4">
        <h2 className="text-base font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--brand, #0ea5e9)' }}>
          6 · 90-Day Outlook (12-Week Plan)
        </h2>
        <div
          className="rounded-xl p-5"
          style={{ border: '1px solid var(--border, #e2e8f0)', backgroundColor: 'var(--surface-raised, #f8fafc)' }}
        >
          <GanttChart />
          <div className="flex flex-wrap gap-3 mt-4 text-xs">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-green-500" /> Milestone / sign-off</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-blue-500" /> Commercial / finance</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-purple-500" /> FID preparation</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block bg-amber-500" /> Regulatory / utility</span>
          </div>
        </div>
      </section>

      {/* Print footer */}
      <div className="mt-8 pt-4 text-xs text-center hidden print:block" style={{ borderTop: '1px solid var(--border, #e2e8f0)', color: 'var(--text-muted, #64748b)' }}>
        INTERNAL — STRICTLY CONFIDENTIAL · GreenEarthX · {generatedAt}
      </div>
    </div>
  )
}
