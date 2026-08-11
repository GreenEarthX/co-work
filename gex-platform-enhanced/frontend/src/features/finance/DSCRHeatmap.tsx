// Screen: DSCR sensitivity heatmap screen (/dscr-sensitivity, /finance/dscr-sensitivity)
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, TrendingDown, Shield, Info, RefreshCw, Database, CalendarDays } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import type { CustomerProject } from '@/data/customerProjects'
import { financeModelAPI } from '@/lib/api'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type SensitivityFactor = 'power_price' | 'efficiency' | 'capex' | 'cod_delay' | 'curtailment' | 'logistics_cost' | 'interest_rate'

interface SensitivityRow {
  factor: SensitivityFactor
  label: string
  unit: string
  deltas: number[]
  deltaLabels: string[]
  values: number[]
}

interface HeatmapCell {
  powerDelta: number
  effDelta: number
  dscr: number
}

interface BreakevenMetric {
  label: string
  value: string
  description: string
  breached: boolean
}

interface MonthlyDSCR {
  month: number
  dscr: number
}

interface SensitivityDataset {
  baseDSCR: number
  sensitivityRows: SensitivityRow[]
  heatmapCells: HeatmapCell[]
  breakevenMetrics: BreakevenMetric[]
  monthlySeries: MonthlyDSCR[]
  isLive?: boolean
  debtServiceSource?: string
  hasEstimates?: boolean
}

// ═══════════════════════════════════════════════════════════════
// NO CLIENT-SIDE FALLBACK — BY DESIGN
// ═══════════════════════════════════════════════════════════════
// This screen used to synthesise a sensitivity dataset locally when the API
// was unavailable: a hardcoded base-DSCR lookup, seven hand-tuned elasticity
// arrays, and an ADDITIVE 5x5 grid (base + pd*-0.07 + ed*0.06). Two defects
// followed and both reached a lender's screen:
//
//   1. the single-factor table showed a power-price RISE improving DSCR while
//      the grid showed the opposite — on the same page;
//   2. an additive grid understates the worst corner, the one direction a
//      credit committee cannot tolerate.
//
// A sensitivity surface a lender cannot distinguish from engine output is
// worse than an empty state, so there is deliberately nothing to fall back to.
// The model now lives once, server-side, in services/dscr_sensitivity.py.

// ═══════════════════════════════════════════════════════════════
// API RESPONSE → SensitivityDataset adapter
// ═══════════════════════════════════════════════════════════════

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function adaptApiResponse(data: any): SensitivityDataset {
  const base: number = data.baseDSCR ?? 1.20

  const sensitivityRows: SensitivityRow[] = (data.sensitivityRows ?? []).map(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (r: any) => ({
      factor: r.factor as SensitivityFactor,
      label: r.label,
      unit: r.unit,
      deltas: [-20, -10, 0, 10, 20],
      deltaLabels: r.deltaLabels ?? [],
      values: r.values ?? [],
    })
  )

  const heatmapCells: HeatmapCell[] = (data.heatmapCells ?? []).map(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (c: any) => ({ powerDelta: c.powerDelta, effDelta: c.effDelta, dscr: c.dscr })
  )

  const breakevenMetrics: BreakevenMetric[] = (data.breakevenMetrics ?? []).map(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (m: any) => ({ label: m.label, value: m.value, description: m.description, breached: m.breached })
  )

  const monthlySeries: MonthlyDSCR[] = (data.monthlySeries ?? [])
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .filter((p: any) => p.dscr != null)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .map((p: any, i: number) => ({ month: p.month ?? i + 1, dscr: p.dscr }))

  return {
    baseDSCR: base,
    sensitivityRows,
    heatmapCells,
    breakevenMetrics,
    monthlySeries,
    isLive: true,
    debtServiceSource: data.debtServiceSource,
    hasEstimates: data.hasEstimates,
  }
}

// ═══════════════════════════════════════════════════════════════
// COLOR HELPERS
// ═══════════════════════════════════════════════════════════════

function dscrCellStyle(val: number): { bg: string; text: string } {
  if (val >= 1.30) return { bg: 'bg-green-100', text: 'text-green-800' }
  if (val >= 1.20) return { bg: 'bg-amber-100', text: 'text-amber-800' }
  return { bg: 'bg-red-100', text: 'text-red-800' }
}

function dscrToFill(val: number): string {
  if (val >= 1.40) return '#bbf7d0'
  if (val >= 1.30) return '#86efac'
  if (val >= 1.25) return '#fde68a'
  if (val >= 1.20) return '#fcd34d'
  if (val >= 1.10) return '#fca5a5'
  return '#f87171'
}

// ═══════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-3 flex items-center gap-2">
      {children}
    </h2>
  )
}

function BreachIcon() {
  return <AlertTriangle className="w-3 h-3 text-red-500 inline-block ml-1" aria-label="covenant breach" />
}

function SingleFactorTable({ rows }: { rows: SensitivityRow[] }) {
  if (!rows.length) return null
  const colLabels = rows[0].deltaLabels

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            <th className="text-left px-3 py-2 font-black text-gray-700 w-40">Factor</th>
            {colLabels.map((lbl, i) => (
              <th key={i} className={`text-center px-2 py-2 font-bold w-20 ${i === 2 ? 'bg-blue-50 text-blue-700' : 'text-gray-600'}`}>
                {lbl}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map(row => (
            <tr key={row.factor} className="hover:bg-gray-50/50">
              <td className="px-3 py-2 font-semibold text-gray-800">
                {row.label}
                <div className="text-gray-400 font-normal text-xs">{row.unit}</div>
              </td>
              {row.values.map((val, ci) => {
                const style = dscrCellStyle(val)
                return (
                  <td key={ci} className={`text-center px-2 py-2 font-bold tabular-nums ${style.bg} ${style.text} ${ci === 2 ? 'ring-2 ring-inset ring-blue-300' : ''}`}>
                    {val.toFixed(2)}x
                    {val < 1.20 && <BreachIcon />}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TwoFactorHeatmap({ cells, baseDSCR }: { cells: HeatmapCell[]; baseDSCR: number }) {
  const powerDeltas = [-20, -10, 0, 10, 20]
  const effDeltas   = [5, 2.5, 0, -2.5, -5]
  const cellW = 72, cellH = 40, labelW = 60, labelH = 28
  const svgW = labelW + powerDeltas.length * cellW + 20
  const svgH = labelH + effDeltas.length * cellH + 20

  return (
    <div className="overflow-x-auto">
      <div className="mb-2 text-xs text-gray-500 font-medium">
        <span className="font-black text-gray-700">DSCR P50 — Power Price × Efficiency Combined Shock</span>
        <span className="ml-2 text-gray-400">Base DSCR: {baseDSCR.toFixed(2)}x</span>
      </div>
      <svg width={svgW} height={svgH} className="font-mono">
        {powerDeltas.map((pd, xi) => (
          <text key={xi} x={labelW + xi * cellW + cellW / 2} y={14} textAnchor="middle" fontSize={9} fill="#6b7280" fontWeight={600}>
            {pd > 0 ? `+${pd}%` : `${pd}%`}
          </text>
        ))}
        <text x={labelW + powerDeltas.length * cellW / 2} y={26} textAnchor="middle" fontSize={8} fill="#9ca3af">Power Price Delta</text>
        {effDeltas.map((ed, yi) => (
          <text key={yi} x={labelW - 6} y={labelH + yi * cellH + cellH / 2 + 4} textAnchor="end" fontSize={9} fill="#6b7280" fontWeight={600}>
            {ed > 0 ? `+${ed}pp` : `${ed}pp`}
          </text>
        ))}
        <text x={10} y={labelH + effDeltas.length * cellH / 2} textAnchor="middle" fontSize={8} fill="#9ca3af" transform={`rotate(-90, 10, ${labelH + effDeltas.length * cellH / 2})`}>
          Efficiency Delta
        </text>
        {cells.map((cell, i) => {
          const xi = powerDeltas.indexOf(cell.powerDelta)
          const yi = effDeltas.indexOf(cell.effDelta)
          if (xi < 0 || yi < 0) return null
          const x = labelW + xi * cellW
          const y = labelH + yi * cellH
          const isBase = cell.powerDelta === 0 && cell.effDelta === 0
          const isBreach = cell.dscr < 1.20
          return (
            <g key={i}>
              <rect x={x + 1} y={y + 1} width={cellW - 2} height={cellH - 2} fill={dscrToFill(cell.dscr)} rx={4}
                stroke={isBase ? '#3b82f6' : isBreach ? '#ef4444' : 'transparent'}
                strokeWidth={isBase ? 2 : isBreach ? 1.5 : 0}
              />
              <text x={x + cellW / 2} y={y + cellH / 2 + 4} textAnchor="middle" fontSize={10} fontWeight={700}
                fill={cell.dscr >= 1.20 ? '#166534' : '#991b1b'}>
                {cell.dscr.toFixed(2)}
              </text>
              {isBreach && <text x={x + cellW - 10} y={y + 13} fontSize={9} fill="#dc2626">⚠</text>}
            </g>
          )
        })}
      </svg>
      <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
        <div className="flex items-center gap-1.5"><div className="w-4 h-4 rounded bg-green-300 border border-green-400" /><span>≥ 1.30x — above target</span></div>
        <div className="flex items-center gap-1.5"><div className="w-4 h-4 rounded bg-amber-300 border border-amber-400" /><span>1.20–1.30x — watch zone</span></div>
        <div className="flex items-center gap-1.5"><div className="w-4 h-4 rounded bg-red-400 border border-red-500" /><span>&lt; 1.20x — covenant breach</span></div>
        <div className="flex items-center gap-1.5"><div className="w-4 h-4 rounded bg-transparent border-2 border-blue-500" /><span>Base case</span></div>
      </div>
    </div>
  )
}

function BreakevenCards({ metrics }: { metrics: BreakevenMetric[] }) {
  return (
    <div className="space-y-3">
      {metrics.map((m, i) => (
        <div key={i} className={`rounded-xl border p-3 ${m.breached ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'}`}>
          <div className="flex items-start justify-between gap-2 mb-1">
            <span className="text-xs text-gray-500 font-medium leading-tight">{m.label}</span>
            {m.breached && <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />}
          </div>
          <div className={`text-xl font-black tabular-nums ${m.breached ? 'text-red-700' : 'text-gray-900'}`}>{m.value}</div>
          <div className="text-xs text-gray-400 mt-1 leading-tight">{m.description}</div>
        </div>
      ))}
    </div>
  )
}

function CovenantHeadroomChart({ series, baseDSCR: _baseDSCR }: { series: MonthlyDSCR[]; baseDSCR: number }) {
  const W = 580, H = 160
  const padL = 48, padR = 16, padT = 12, padB = 30
  const innerW = W - padL - padR
  const innerH = H - padT - padB
  const yMin = 0.80, yMax = 2.0, yRange = yMax - yMin

  if (!series.length) return (
    <div className="flex items-center justify-center h-32 text-xs text-gray-400">
      No monthly DSCR data — debt service periods not yet in cashflow projection.
    </div>
  )

  const count = series.length
  const toX = (i: number) => padL + (i / Math.max(count - 1, 1)) * innerW
  const toY = (dscr: number) => padT + innerH - ((dscr - yMin) / yRange) * innerH

  const linePath = series.map((d, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(d.dscr).toFixed(1)}`).join(' ')
  const floorY = toY(1.20)
  const areaPath = [
    ...series.map((d, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${Math.min(floorY, toY(d.dscr)).toFixed(1)}`),
    `L ${toX(count - 1).toFixed(1)} ${floorY.toFixed(1)}`,
    `L ${toX(0).toFixed(1)} ${floorY.toFixed(1)}`,
    'Z',
  ].join(' ')

  const yTicks = [0.80, 1.00, 1.20, 1.30, 1.50, 1.80, 2.00]
  const xTickIndices = count <= 6
    ? series.map((_, i) => i)
    : [0, Math.floor(count / 5), Math.floor(2 * count / 5), Math.floor(3 * count / 5), Math.floor(4 * count / 5), count - 1]

  return (
    <div className="overflow-x-auto">
      <svg width={W} height={H} className="font-sans">
        <defs>
          <linearGradient id="headroomGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#86efac" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#86efac" stopOpacity="0.1" />
          </linearGradient>
        </defs>
        {yTicks.map(v => (
          <line key={v} x1={padL} y1={toY(v)} x2={W - padR} y2={toY(v)} stroke="#f3f4f6" strokeWidth={1} />
        ))}
        <path d={areaPath} fill="url(#headroomGrad)" />
        <line x1={padL} y1={toY(1.20)} x2={W - padR} y2={toY(1.20)} stroke="#ef4444" strokeWidth={1.5} strokeDasharray="6 3" />
        <text x={W - padR + 2} y={toY(1.20) + 4} fontSize={8} fill="#ef4444" fontWeight={700}>1.20x</text>
        <line x1={padL} y1={toY(1.30)} x2={W - padR} y2={toY(1.30)} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 3" />
        <text x={W - padR + 2} y={toY(1.30) + 4} fontSize={8} fill="#f59e0b" fontWeight={700}>1.30x</text>
        <path d={linePath} fill="none" stroke="#16a34a" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
        {yTicks.map(v => (
          <text key={v} x={padL - 6} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#9ca3af" fontWeight={600}>{v.toFixed(2)}</text>
        ))}
        {xTickIndices.map(idx => (
          <text key={idx} x={toX(idx)} y={H - 6} textAnchor="middle" fontSize={9} fill="#9ca3af">M{series[idx].month}</text>
        ))}
        <text x={padL + innerW / 2} y={H - 1} textAnchor="middle" fontSize={8} fill="#9ca3af">Month of operations</text>
        <text x={10} y={padT + innerH / 2} textAnchor="middle" fontSize={8} fill="#9ca3af" transform={`rotate(-90, 10, ${padT + innerH / 2})`}>DSCR P50</text>
      </svg>
      <div className="flex items-center gap-5 mt-2 text-xs text-gray-500">
        <div className="flex items-center gap-1.5"><div className="w-5 h-0.5 bg-green-600 rounded" /><span>DSCR P50</span></div>
        <div className="flex items-center gap-1.5"><div className="w-5 h-0" style={{ borderBottom: '2px dashed #ef4444' }} /><span>Covenant floor 1.20x</span></div>
        <div className="flex items-center gap-1.5"><div className="w-5 h-0" style={{ borderBottom: '2px dashed #f59e0b' }} /><span>Target floor 1.30x</span></div>
        <div className="flex items-center gap-1.5"><div className="w-5 h-3 bg-green-200 rounded-sm opacity-70" /><span>Headroom</span></div>
      </div>
    </div>
  )
}

// ── Pre-COD readiness panel ──────────────────────────────────────

function PreCodReadiness({ project }: { project: CustomerProject }) {
  const { bankability } = project
  const gatesComplete = bankability.gates.filter(g => g.is_complete).length
  const gatesTotal = bankability.gates.length
  const blockingItems = bankability.gates
    .filter(g => !g.is_complete)
    .flatMap(g => g.blocking_items.map(item => ({ gate: g.name, item })))

  const fidReadiness =
    bankability.overall_completion >= 80
      ? { label: 'APPROACHING FID', cls: 'text-teal-700 bg-teal-50 border-teal-200' }
      : bankability.overall_completion >= 60
      ? { label: 'PROGRESSING TO FID', cls: 'text-blue-700 bg-blue-50 border-blue-200' }
      : { label: 'EARLY STAGE', cls: 'text-amber-700 bg-amber-50 border-amber-200' }

  const statusColor: Record<string, string> = {
    NONE:            'bg-gray-100 text-gray-500',
    INDICATIVE:      'bg-blue-100 text-blue-700',
    TERM_SHEET:      'bg-teal-100 text-teal-700',
    CREDIT_APPROVED: 'bg-green-100 text-green-700',
    LEGAL_COMPLETE:  'bg-green-200 text-green-800',
    DRAWN:           'bg-green-300 text-green-900',
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">

        {/* Bankability progress */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4">
          <div className="text-xs font-black uppercase tracking-widest text-gray-500 mb-3">Bankability Progress</div>
          <div className="text-3xl font-black text-gray-900 tabular-nums">{bankability.overall_completion}%</div>
          <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${bankability.overall_completion}%`,
                background: bankability.overall_completion >= 80 ? '#0ea5a0' : bankability.overall_completion >= 60 ? '#3b82f6' : '#f59e0b',
              }}
            />
          </div>
          <div className="text-xs text-gray-400 mt-2">{gatesComplete}/{gatesTotal} evidence gates complete</div>
        </div>

        {/* FID readiness */}
        <div className={`rounded-xl border p-4 ${fidReadiness.cls}`}>
          <div className="text-xs font-black uppercase tracking-widest opacity-70 mb-3">FID Readiness Signal</div>
          <div className="text-xl font-black mb-2">{fidReadiness.label}</div>
          <div className="text-xs opacity-70 leading-relaxed">{bankability.next_milestone}</div>
        </div>

        {/* Capital commitment */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-4">
          <div className="text-xs font-black uppercase tracking-widest text-gray-500 mb-3">Capital Commitment</div>
          <div className="space-y-2">
            {bankability.capital_status.map((c, i) => (
              <div key={i} className="flex items-center justify-between gap-2 text-xs">
                <div>
                  <span className="font-semibold text-gray-800">{c.name}</span>
                  <span className="ml-1 text-gray-400">{c.amount}</span>
                </div>
                <span className={`px-1.5 py-0.5 rounded font-semibold shrink-0 ${statusColor[c.commitment_status] ?? 'bg-gray-100 text-gray-500'}`}>
                  {c.commitment_status.replace(/_/g, ' ')}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Blocking items + risk alerts */}
      {(blockingItems.length > 0 || (bankability.risk_alerts?.length ?? 0) > 0) && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="text-xs font-black uppercase tracking-widest text-amber-800 mb-3 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            Open blockers — {blockingItems.length} item{blockingItems.length !== 1 ? 's' : ''} pending
          </div>
          <div className="space-y-1.5">
            {blockingItems.map((b, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-amber-600 font-semibold">{b.gate}</span>
                <span className="text-amber-400">→</span>
                <code className="text-amber-800">{b.item.replace(/_/g, ' ')}</code>
              </div>
            ))}
          </div>
          {bankability.risk_alerts?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-amber-200 space-y-1.5">
              {bankability.risk_alerts.map((alert, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs text-amber-700">
                  <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0 opacity-60" />
                  {alert}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function DSCRHeatmap() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId) ?? null
  const isPreCod = project?.status === 'development' || project?.status === 'construction'

  const codDateStr = project?.completion_date ?? null
  const codFormatted = codDateStr
    ? new Date(codDateStr).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : null
  const daysToCoD = codDateStr
    ? Math.ceil((new Date(codDateStr).getTime() - Date.now()) / 86400000)
    : null

  const [annualDebtService, setAnnualDebtService] = useState<string>('')
  const ads = annualDebtService ? parseFloat(annualDebtService) : undefined

  const { data: apiData, isLoading, isError, refetch } = useQuery({
    queryKey: ['dscr-heatmap', selectedProjectId, ads],
    queryFn: () => financeModelAPI.dscrHeatmap({
      assetId: selectedProjectId,
      annualDebtService: ads,
    }),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  // No local fallback: an unavailable model shows an empty state, never a
  // synthesised surface a lender could mistake for engine output.
  const data: SensitivityDataset | null =
    apiData && !isError ? adaptApiResponse(apiData) : null

  if (isLoading) {
    return (
      <div className="p-8 flex items-center gap-3 text-slate-500">
        <RefreshCw className="h-4 w-4 animate-spin" />
        <span className="text-sm">Computing sensitivity from the project cashflow basis…</span>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-8">
        <div className="max-w-2xl rounded-lg border border-amber-200 bg-amber-50 p-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Sensitivity unavailable for this project
              </h2>
              <p className="mt-2 text-sm text-slate-600 leading-relaxed">
                DSCR sensitivity is derived from the project&apos;s cashflow basis. This
                project has no cashflow projection yet, or the finance model engine
                is unreachable.
              </p>
              <p className="mt-3 text-sm text-slate-600 leading-relaxed">
                No figures are shown rather than estimated ones: a sensitivity surface
                that cannot be traced to a cashflow basis is not a lender-usable number.
              </p>
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-4 inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const baseDSCRStyle =
    data.baseDSCR >= 1.30 ? 'text-green-700 bg-green-50 border-green-200' :
    data.baseDSCR >= 1.20 ? 'text-amber-700 bg-amber-50 border-amber-200' :
    'text-red-700 bg-red-50 border-red-200'

  const breachCount = data.sensitivityRows.reduce((acc, row) => acc + row.values.filter(v => v < 1.20).length, 0)
  const totalCells = data.sensitivityRows.length * 5

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-8">

      {/* ── Page header ────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-black text-gray-900">DSCR Sensitivity Heatmap</h1>

          {/* Project identity row */}
          <div className="flex items-center gap-2 mt-1 flex-wrap text-sm">
            {project ? (
              <span className="font-semibold text-gray-900">{project.name}</span>
            ) : (
              <span className="text-gray-400 italic">No project selected</span>
            )}
            {project && <span className="text-gray-300">·</span>}
            {project && <span className="text-gray-500">{project.location}</span>}
            {codFormatted && (
              <>
                <span className="text-gray-300">·</span>
                <span className="flex items-center gap-1 text-gray-500">
                  <CalendarDays className="w-3.5 h-3.5 shrink-0" />
                  {isPreCod ? 'COD target' : 'COD'}: {codFormatted}
                  {isPreCod && daysToCoD !== null && daysToCoD > 0 && (
                    <span className="ml-0.5 text-xs font-bold px-1.5 py-0.5 rounded bg-blue-50 border border-blue-200 text-blue-700">
                      {daysToCoD > 365 ? `${Math.round(daysToCoD / 30)}mo` : `${daysToCoD}d`}
                    </span>
                  )}
                  {!isPreCod && daysToCoD !== null && daysToCoD <= 0 && (
                    <span className="ml-0.5 text-xs font-semibold px-1.5 py-0.5 rounded bg-green-50 border border-green-200 text-green-700">achieved</span>
                  )}
                </span>
              </>
            )}
            {project && (
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                project.status === 'operating'      ? 'bg-green-100 text-green-800' :
                project.status === 'commissioning'  ? 'bg-teal-100 text-teal-800' :
                project.status === 'construction'   ? 'bg-blue-100 text-blue-800' :
                                                      'bg-amber-100 text-amber-800'
              }`}>
                {project.phase}
              </span>
            )}
          </div>

          <p className="text-sm text-gray-500 mt-1">{TAB_DESCRIPTIONS.DSCR_SENSITIVITY}</p>
        </div>

        {/* Right KPI cluster — adapts to stage */}
        <div className="flex items-center gap-3 shrink-0 flex-wrap justify-end">
          {/* Data source badge */}
          {isLoading ? (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 text-xs">
              <RefreshCw className="w-3 h-3 animate-spin" />
              Loading…
            </div>
          ) : data.isLive ? (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-50 border border-teal-200 text-teal-700 text-xs font-semibold">
              <Database className="w-3 h-3" />
              Live — Trading Book
              {data.hasEstimates && <span className="ml-1 text-teal-500 font-normal">(fwd-extrapolated)</span>}
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 text-xs">
              <Info className="w-3 h-3" />
              Model estimates — no cashflow data yet
            </div>
          )}

          {/* Pre-COD: bankability summary instead of DSCR */}
          {isPreCod && project ? (
            <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border font-black text-lg tabular-nums ${
              project.bankability.overall_completion >= 80 ? 'text-teal-700 bg-teal-50 border-teal-200' :
              project.bankability.overall_completion >= 60 ? 'text-blue-700 bg-blue-50 border-blue-200' :
              'text-amber-700 bg-amber-50 border-amber-200'
            }`}>
              <span className="text-xs font-semibold opacity-70">Bankability</span>
              {project.bankability.overall_completion}%
            </div>
          ) : (
            <>
              {/* Post-COD: DSCR P50 card */}
              <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border font-black text-lg tabular-nums ${baseDSCRStyle}`}>
                <span className="text-xs font-semibold opacity-70 flex items-center gap-1">Base DSCR P50 <InfoTooltip text={HELP.DSCR_P50} /></span>
                {data.baseDSCR.toFixed(2)}x
              </div>
              {breachCount > 0 ? (
                <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-bold">
                  <AlertTriangle className="w-4 h-4" />
                  {breachCount}/{totalCells} scenarios breach covenant
                </div>
              ) : (
                <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-green-50 border border-green-200 text-green-700 text-sm font-bold">
                  <Shield className="w-4 h-4" />
                  No covenant breaches in single-factor analysis
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Pre-COD notice + readiness ─────────────────────────────── */}
      {isPreCod && project && (
        <>
          <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-50 border border-blue-200 text-sm">
            <Info className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
            <div className="text-blue-800">
              <span className="font-bold">DSCR not applicable pre-COD.</span>
              <span className="ml-2 text-blue-700">
                {project.name} targets COD {codFormatted}
                {daysToCoD !== null && daysToCoD > 0
                  ? ` — ${daysToCoD > 365 ? `${Math.round(daysToCoD / 30)} months` : `${daysToCoD} days`} from today.`
                  : '.'}
                {' '}The DSCR analysis below is a model projection for lender reference only, not a current operational ratio.
              </span>
            </div>
          </div>
          <PreCodReadiness project={project} />
        </>
      )}

      {/* ── Pre-financial-close: debt service input ────────────────── */}
      {data.isLive && data.debtServiceSource === 'none_pre_financial_close' && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200 text-sm">
          <Info className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-amber-800">No debt service contract lines found. Enter an annual debt service assumption to compute DSCR:</span>
          <input
            type="number"
            placeholder="e.g. 12000000"
            value={annualDebtService}
            onChange={e => setAnnualDebtService(e.target.value)}
            className="border border-amber-300 rounded-lg px-3 py-1.5 text-sm w-44 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
          />
          <span className="text-amber-600 text-xs">EUR/year</span>
          <button onClick={() => refetch()} className="px-3 py-1.5 rounded-lg bg-amber-600 text-white text-xs font-bold hover:bg-amber-700">
            Apply
          </button>
        </div>
      )}

      {/* ── Forward-projection label (pre-COD only) ────────────────── */}
      {isPreCod && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-700 font-semibold">
          <Info className="w-3.5 h-3.5 shrink-0" />
          Forward projection at COD — model estimates only, not a current ratio
        </div>
      )}

      {/* ── ZONE 1: Single-Factor Sensitivity Table ─────────────────── */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
        <SectionTitle>
          <TrendingDown className="w-4 h-4 text-gray-500" />
          Single-Factor Sensitivity Analysis
          <span className="ml-1 text-gray-400 text-xs font-normal normal-case tracking-normal">— DSCR P50 under isolated shocks</span>
        </SectionTitle>
        <SingleFactorTable rows={data.sensitivityRows} />
        <div className="mt-3 flex items-start gap-2 bg-gray-50 rounded-lg p-3 text-xs text-gray-500">
          <Info className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
          Shocks applied individually, holding all other factors at base case. Covenant floor: 1.20x (red cells). Target DSCR: 1.30x. Base column highlighted in blue.
        </div>
      </div>

      {/* ── ZONES 2 & 3: Heatmap + Breakeven sidebar ──────────────── */}
      <div className="grid grid-cols-4 gap-4">
        <div className="col-span-3 rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
          <SectionTitle>
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Two-Factor Combined Shock — Power Price × Efficiency
          </SectionTitle>
          <TwoFactorHeatmap cells={data.heatmapCells} baseDSCR={data.baseDSCR} />
        </div>
        <div className="col-span-1 rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
          <SectionTitle>
            <Shield className="w-4 h-4 text-gray-500" />
            Break-Even Floors
          </SectionTitle>
          <BreakevenCards metrics={data.breakevenMetrics} />
          <div className="mt-4 p-3 bg-amber-50 rounded-xl border border-amber-200">
            <div className="text-xs font-bold text-amber-800 mb-1">Covenant Floor</div>
            <div className="text-2xl font-black text-amber-700 tabular-nums">1.20x</div>
            <div className="text-xs text-amber-600 mt-1">Senior debt DSCR minimum — breach triggers cash lock-up and lender step-in rights</div>
          </div>
        </div>
      </div>

      {/* ── ZONE 4: Covenant Headroom Line Chart ───────────────────── */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
        <SectionTitle>
          <TrendingDown className="w-4 h-4 text-gray-500" />
          Covenant Headroom — Monthly DSCR P50
          {data.isLive
            ? <span className="ml-1 text-gray-400 text-xs font-normal normal-case tracking-normal">— from trading book cashflow projection</span>
            : <span className="ml-1 text-gray-400 text-xs font-normal normal-case tracking-normal">— years 1–3 of operations (model estimate)</span>
          }
        </SectionTitle>
        <CovenantHeadroomChart series={data.monthlySeries} baseDSCR={data.baseDSCR} />

        {data.monthlySeries.length > 0 && (
          <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-gray-100">
            {(() => {
              const vals = data.monthlySeries.map(d => d.dscr)
              const minVal = Math.min(...vals)
              const maxVal = Math.max(...vals)
              const minMonth = data.monthlySeries.find(d => d.dscr === minVal)?.month ?? 0
              const maxMonth = data.monthlySeries.find(d => d.dscr === maxVal)?.month ?? 0
              const avgVal = vals.reduce((a, b) => a + b, 0) / vals.length
              return [
                { label: `Minimum (M${minMonth})`, value: minVal.toFixed(2) + 'x', color: minVal >= 1.20 ? 'text-green-700' : 'text-red-700', bg: minVal >= 1.20 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200' },
                { label: 'Average', value: avgVal.toFixed(2) + 'x', color: avgVal >= 1.30 ? 'text-green-700' : avgVal >= 1.20 ? 'text-amber-700' : 'text-red-700', bg: avgVal >= 1.30 ? 'bg-green-50 border-green-200' : avgVal >= 1.20 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200' },
                { label: `Maximum (M${maxMonth})`, value: maxVal.toFixed(2) + 'x', color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
              ].map(m => (
                <div key={m.label} className={`rounded-xl border p-3 ${m.bg}`}>
                  <div className="text-xs text-gray-500 font-medium mb-1">{m.label}</div>
                  <div className={`text-2xl font-black tabular-nums ${m.color}`}>{m.value}</div>
                </div>
              ))
            })()}
          </div>
        )}
      </div>

    </div>
  )
}
