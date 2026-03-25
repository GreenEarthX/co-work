import { AlertTriangle, TrendingDown, Shield, Info } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { HELP, TAB_DESCRIPTIONS } from '@/config/helpText'
import { useSelectedProject } from '@/contexts/ProjectContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type SensitivityFactor = 'power_price' | 'efficiency' | 'capex' | 'cod_delay' | 'curtailment' | 'logistics_cost' | 'interest_rate'

interface SensitivityRow {
  factor: SensitivityFactor
  label: string
  unit: string
  deltas: number[]        // delta levels: -20, -10, 0, +10, +20 (or equivalent)
  deltaLabels: string[]   // display labels for column headers
  values: number[]        // DSCR at each delta
}

interface HeatmapCell {
  powerDelta: number   // %
  effDelta: number     // percentage points
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
}

// ═══════════════════════════════════════════════════════════════
// BASE DSCR PER PROJECT
// ═══════════════════════════════════════════════════════════════

const PROJECT_BASE_DSCR: Record<string, number> = {
  proj_lehavre_eng:           1.58,
  proj_bremen_h2:             1.34,
  proj_sansebastian_emethanol: 1.22,
  proj_rotterdam_nh3:         1.05,
  proj_wales_saf:             0.98,
}

// ═══════════════════════════════════════════════════════════════
// DATA GENERATOR
// ═══════════════════════════════════════════════════════════════

/**
 * Generates all DSCR sensitivity data scaled from the project's base DSCR.
 * Elasticities are based on typical greenfield renewable hydrogen project finance models.
 */
export function generateSensitivityData(projectId: string): SensitivityDataset {
  const base = PROJECT_BASE_DSCR[projectId] ?? 1.20

  // Factor elasticities (DSCR delta per 10% shock in the factor)
  // Positive factor shock = adverse direction for DSCR
  const elasticities: Record<SensitivityFactor, number[]> = {
    // power_price: higher price = worse DSCR (cost driver). Columns: -20, -10, 0, +10, +20
    power_price:    [-0.14, -0.07, 0, +0.07, +0.14],
    // efficiency: lower efficiency = worse. -5pp, -2.5pp, 0, +2.5pp, +5pp
    efficiency:     [+0.18, +0.09, 0, -0.06, -0.10],
    // capex: higher capex = worse (debt service increases)
    capex:          [+0.12, +0.06, 0, -0.07, -0.15],
    // cod_delay: months delayed: 0, 3, 0(base), -3(early), -6(very early) — reindex as -6m, -3m, base, +3m, +6m
    cod_delay:      [+0.05, +0.02, 0, -0.06, -0.13],
    // curtailment: higher curtailment = worse
    curtailment:    [+0.08, +0.04, 0, -0.05, -0.10],
    // logistics_cost: higher logistics = worse
    logistics_cost: [+0.04, +0.02, 0, -0.04, -0.08],
    // interest_rate: rate shock in bps. -150bps improves DSCR (lower debt service); +150bps worsens.
    // At 60% debt ratio, each 75bps shock ≈ ±0.08 DSCR (Taghizadeh-Hesary 2022, §4.2).
    interest_rate: [+0.16, +0.08, 0, -0.08, -0.17],
  }

  const factorMeta: Record<SensitivityFactor, { label: string; unit: string; deltaLabels: string[] }> = {
    power_price:    { label: 'Power Price',     unit: '€/MWh', deltaLabels: ['-20%', '-10%', 'Base', '+10%', '+20%'] },
    efficiency:     { label: 'System Efficiency', unit: '%',   deltaLabels: ['-5pp', '-2.5pp', 'Base', '+2.5pp', '+5pp'] },
    capex:          { label: 'CapEx',           unit: '€M',    deltaLabels: ['-20%', '-10%', 'Base', '+10%', '+20%'] },
    cod_delay:      { label: 'COD Delay',       unit: 'months',deltaLabels: ['-6m', '-3m', 'Base', '+3m', '+6m'] },
    curtailment:    { label: 'Curtailment',     unit: '%',     deltaLabels: ['-20%', '-10%', 'Base', '+10%', '+20%'] },
    logistics_cost: { label: 'Logistics Cost',  unit: '€/kg',  deltaLabels: ['-20%', '-10%', 'Base', '+10%', '+20%'] },
    interest_rate:  { label: 'Interest Rate',   unit: 'bps',   deltaLabels: ['-150bps', '-75bps', 'Base', '+75bps', '+150bps'] },
  }

  const sensitivityRows: SensitivityRow[] = (Object.keys(elasticities) as SensitivityFactor[]).map(factor => {
    const meta = factorMeta[factor]
    const elast = elasticities[factor]
    return {
      factor,
      label: meta.label,
      unit: meta.unit,
      deltas: [-20, -10, 0, 10, 20],
      deltaLabels: meta.deltaLabels,
      values: elast.map(e => Math.max(0.60, parseFloat((base + e).toFixed(2))),
      ),
    }
  })

  // 5×5 heatmap: power price (-20..+20%) × efficiency (-5pp..+5pp)
  const powerDeltas = [-20, -10, 0, 10, 20]
  const effDeltas   = [5, 2.5, 0, -2.5, -5]   // positive effDelta = better efficiency (higher DSCR)

  const heatmapCells: HeatmapCell[] = []
  for (const pd of powerDeltas) {
    for (const ed of effDeltas) {
      // power price shock: +1% power price → -0.007 DSCR
      // efficiency shock: +1pp eff → +0.02 DSCR
      const powerEffect  = (pd / 10) * (-0.07)
      const effEffect    = (ed / 2.5) * 0.06
      const dscr = Math.max(0.60, parseFloat((base + powerEffect + effEffect).toFixed(2)))
      heatmapCells.push({ powerDelta: pd, effDelta: ed, dscr })
    }
  }

  // Breakeven metrics — floor at DSCR = 1.20
  const covenantFloor = 1.20
  // Power price floor: base - (covenantFloor - base) / 0.007 * 1% change
  const powerHeadroom = base - covenantFloor
  const floorPowerDelta = powerHeadroom / 0.007  // % reduction before breach
  const basePowerPrice = 65 // €/MWh typical for NW Europe electrolysis
  const floorPowerPrice = parseFloat((basePowerPrice * (1 + floorPowerDelta / 100)).toFixed(1))

  const effHeadroom = powerHeadroom / 0.02  // pp efficiency drop before breach
  const baseEfficiency = 72
  const minEfficiency = parseFloat((baseEfficiency - effHeadroom).toFixed(1))

  const capexHeadroom = powerHeadroom / 0.015  // % capex overrun before breach
  const maxCapexOverrun = parseFloat(capexHeadroom.toFixed(1))

  // Interest rate breakeven: per 75bps shock, DSCR changes by ~0.08 → per bps: 0.08/75
  const dscrPerBps = 0.08 / 75
  const maxRateBps = base >= covenantFloor ? Math.round((base - covenantFloor) / dscrPerBps) : 0

  const breakevenMetrics: BreakevenMetric[] = [
    {
      label: 'Floor power price',
      value: `€${floorPowerPrice}/MWh`,
      description: `Max power price before DSCR falls below ${covenantFloor}x covenant floor`,
      breached: base < covenantFloor,
    },
    {
      label: 'Min system efficiency',
      value: `${minEfficiency}%`,
      description: `Minimum electrolyser system efficiency before covenant breach`,
      breached: base < covenantFloor,
    },
    {
      label: 'Max CapEx overrun',
      value: base >= covenantFloor ? `+${maxCapexOverrun.toFixed(0)}%` : 'Already breached',
      description: `Maximum CapEx overrun (vs. base case) before DSCR < ${covenantFloor}x`,
      breached: base < covenantFloor,
    },
    {
      label: 'Max rate rise',
      value: base >= covenantFloor ? `+${maxRateBps}bps` : 'Already breached',
      description: `Maximum interest rate increase before DSCR < ${covenantFloor}x (60% debt ratio, Taghizadeh-Hesary 2022)`,
      breached: base < covenantFloor,
    },
  ]

  // Monthly DSCR P50 series — 36 months, years 1-3 of operations
  // Typical project finance profile: ramp-up in Y1, stable Y2, marginal improvement Y3
  const monthlySeries: MonthlyDSCR[] = Array.from({ length: 36 }, (_, i) => {
    const month = i + 1
    // Ramp factor: first 6 months have lower DSCR due to ramp-up
    const rampFactor = month <= 6 ? 0.75 + (month / 6) * 0.25 : 1.0
    // Seasonal variation (±3%)
    const seasonal = 1 + 0.03 * Math.sin((month / 12) * 2 * Math.PI)
    // Slight upward trend as operations mature
    const trend = 1 + (month / 36) * 0.04
    // Small noise
    const noise = (Math.sin(month * 2.7 + 1.3) * 0.015)
    const dscr = Math.max(0.70, parseFloat((base * rampFactor * seasonal * trend + noise).toFixed(2)))
    return { month, dscr }
  })

  return {
    baseDSCR: base,
    sensitivityRows,
    heatmapCells,
    breakevenMetrics,
    monthlySeries,
  }
}

// ═══════════════════════════════════════════════════════════════
// COLOR HELPERS
// ═══════════════════════════════════════════════════════════════

function dscrCellStyle(val: number): { bg: string; text: string; border: string } {
  if (val >= 1.30) return { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' }
  if (val >= 1.20) return { bg: 'bg-amber-100', text: 'text-amber-800', border: 'border-amber-200' }
  return { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-200' }
}

/** Returns an interpolated green→amber→red fill color for SVG heatmap cells */
function dscrToFill(val: number): string {
  if (val >= 1.40) return '#bbf7d0'  // green-200
  if (val >= 1.30) return '#86efac'  // green-300
  if (val >= 1.25) return '#fde68a'  // amber-200
  if (val >= 1.20) return '#fcd34d'  // amber-300
  if (val >= 1.10) return '#fca5a5'  // red-300
  return '#f87171'                   // red-400
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

/** Single-factor sensitivity table */
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
                const isBase = ci === 2
                return (
                  <td key={ci} className={`text-center px-2 py-2 font-bold tabular-nums ${style.bg} ${style.text} ${isBase ? 'ring-2 ring-inset ring-blue-300' : ''}`}>
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

/** 5×5 heatmap grid */
function TwoFactorHeatmap({ cells, baseDSCR }: { cells: HeatmapCell[]; baseDSCR: number }) {
  const powerDeltas = [-20, -10, 0, 10, 20]
  const effDeltas   = [5, 2.5, 0, -2.5, -5]

  const cellW = 72, cellH = 40
  const labelW = 60, labelH = 28
  const svgW = labelW + powerDeltas.length * cellW + 20
  const svgH = labelH + effDeltas.length * cellH + 20

  return (
    <div className="overflow-x-auto">
      <div className="mb-2 text-xs text-gray-500 font-medium">
        <span className="font-black text-gray-700">DSCR P50 — Power Price × Efficiency Combined Shock</span>
        <span className="ml-2 text-gray-400">Base DSCR: {baseDSCR.toFixed(2)}x</span>
      </div>
      <svg width={svgW} height={svgH} className="font-mono">
        {/* X-axis: power price deltas */}
        {powerDeltas.map((pd, xi) => (
          <text
            key={xi}
            x={labelW + xi * cellW + cellW / 2}
            y={14}
            textAnchor="middle"
            fontSize={9}
            fill="#6b7280"
            fontWeight={600}
          >
            {pd > 0 ? `+${pd}%` : `${pd}%`}
          </text>
        ))}
        {/* X-axis label */}
        <text x={labelW + powerDeltas.length * cellW / 2} y={26} textAnchor="middle" fontSize={8} fill="#9ca3af">
          Power Price Delta
        </text>

        {/* Y-axis: efficiency deltas */}
        {effDeltas.map((ed, yi) => (
          <text
            key={yi}
            x={labelW - 6}
            y={labelH + yi * cellH + cellH / 2 + 4}
            textAnchor="end"
            fontSize={9}
            fill="#6b7280"
            fontWeight={600}
          >
            {ed > 0 ? `+${ed}pp` : `${ed}pp`}
          </text>
        ))}
        {/* Y-axis label */}
        <text
          x={10}
          y={labelH + effDeltas.length * cellH / 2}
          textAnchor="middle"
          fontSize={8}
          fill="#9ca3af"
          transform={`rotate(-90, 10, ${labelH + effDeltas.length * cellH / 2})`}
        >
          Efficiency Delta
        </text>

        {/* Cells */}
        {cells.map((cell, i) => {
          const xi = powerDeltas.indexOf(cell.powerDelta)
          const yi = effDeltas.indexOf(cell.effDelta)
          if (xi < 0 || yi < 0) return null
          const x = labelW + xi * cellW
          const y = labelH + yi * cellH
          const fill = dscrToFill(cell.dscr)
          const isBase = cell.powerDelta === 0 && cell.effDelta === 0
          const isBreach = cell.dscr < 1.20

          return (
            <g key={i}>
              <rect
                x={x + 1} y={y + 1}
                width={cellW - 2} height={cellH - 2}
                fill={fill}
                rx={4}
                stroke={isBase ? '#3b82f6' : isBreach ? '#ef4444' : 'transparent'}
                strokeWidth={isBase ? 2 : isBreach ? 1.5 : 0}
              />
              <text
                x={x + cellW / 2}
                y={y + cellH / 2 + 4}
                textAnchor="middle"
                fontSize={10}
                fontWeight={700}
                fill={cell.dscr >= 1.20 ? '#166534' : '#991b1b'}
              >
                {cell.dscr.toFixed(2)}
              </text>
              {isBreach && (
                <text x={x + cellW - 10} y={y + 13} fontSize={9} fill="#dc2626">⚠</text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-green-300 border border-green-400" />
          <span>≥ 1.30x — above target</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-amber-300 border border-amber-400" />
          <span>1.20–1.30x — watch zone</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-red-400 border border-red-500" />
          <span>&lt; 1.20x — covenant breach</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-transparent border-2 border-blue-500" />
          <span>Base case</span>
        </div>
      </div>
    </div>
  )
}

/** Breakeven sidebar cards */
function BreakevenCards({ metrics }: { metrics: BreakevenMetric[] }) {
  return (
    <div className="space-y-3">
      {metrics.map((m, i) => (
        <div
          key={i}
          className={`rounded-xl border p-3 ${
            m.breached
              ? 'bg-red-50 border-red-200'
              : 'bg-white border-gray-200'
          }`}
        >
          <div className="flex items-start justify-between gap-2 mb-1">
            <span className="text-xs text-gray-500 font-medium leading-tight">{m.label}</span>
            {m.breached && <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />}
          </div>
          <div className={`text-xl font-black tabular-nums ${m.breached ? 'text-red-700' : 'text-gray-900'}`}>
            {m.value}
          </div>
          <div className="text-xs text-gray-400 mt-1 leading-tight">{m.description}</div>
        </div>
      ))}
    </div>
  )
}

/** Covenant headroom SVG line chart */
function CovenantHeadroomChart({ series, baseDSCR: _baseDSCR }: { series: MonthlyDSCR[]; baseDSCR: number }) {
  const W = 580, H = 160
  const padL = 48, padR = 16, padT = 12, padB = 30
  const innerW = W - padL - padR
  const innerH = H - padT - padB

  const yMin = 0.80, yMax = 2.0
  const yRange = yMax - yMin

  const toX = (month: number) => padL + ((month - 1) / 35) * innerW
  const toY = (dscr: number) => padT + innerH - ((dscr - yMin) / yRange) * innerH

  // DSCR line path
  const linePath = series.map((d, i) =>
    `${i === 0 ? 'M' : 'L'} ${toX(d.month).toFixed(1)} ${toY(d.dscr).toFixed(1)}`
  ).join(' ')

  // Area fill (between DSCR line and covenant floor 1.20)
  const floorY = toY(1.20)
  const areaPath = [
    ...series.map((d, i) => `${i === 0 ? 'M' : 'L'} ${toX(d.month).toFixed(1)} ${Math.min(floorY, toY(d.dscr)).toFixed(1)}`),
    `L ${toX(36).toFixed(1)} ${floorY.toFixed(1)}`,
    `L ${toX(1).toFixed(1)} ${floorY.toFixed(1)}`,
    'Z'
  ].join(' ')

  // Y-axis ticks
  const yTicks = [0.80, 1.00, 1.20, 1.30, 1.50, 1.80, 2.00].filter(v => v >= yMin && v <= yMax)

  // X-axis ticks every 6 months
  const xTicks = [1, 6, 12, 18, 24, 30, 36]

  return (
    <div className="overflow-x-auto">
      <svg width={W} height={H} className="font-sans">
        <defs>
          <linearGradient id="headroomGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#86efac" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#86efac" stopOpacity="0.1" />
          </linearGradient>
          <linearGradient id="breachGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fca5a5" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#fca5a5" stopOpacity="0.1" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yTicks.map(v => (
          <line
            key={v}
            x1={padL} y1={toY(v)}
            x2={W - padR} y2={toY(v)}
            stroke="#f3f4f6" strokeWidth={1}
          />
        ))}

        {/* Breach area (below 1.20) */}
        {series.some(d => d.dscr < 1.20) && (
          <path
            d={[
              ...series.filter((_, i) => {
                const curr = series[i]
                return curr.dscr < 1.20
              }).map((d, i) =>
                `${i === 0 ? 'M' : 'L'} ${toX(d.month).toFixed(1)} ${toY(d.dscr).toFixed(1)}`
              ),
            ].join(' ')}
            fill="url(#breachGrad)"
          />
        )}

        {/* Headroom shaded area */}
        <path d={areaPath} fill="url(#headroomGrad)" />

        {/* Covenant floor — red dashed at 1.20 */}
        <line
          x1={padL} y1={toY(1.20)}
          x2={W - padR} y2={toY(1.20)}
          stroke="#ef4444" strokeWidth={1.5} strokeDasharray="6 3"
        />
        <text x={W - padR + 2} y={toY(1.20) + 4} fontSize={8} fill="#ef4444" fontWeight={700}>1.20x</text>

        {/* Target floor — amber dashed at 1.30 */}
        <line
          x1={padL} y1={toY(1.30)}
          x2={W - padR} y2={toY(1.30)}
          stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="4 3"
        />
        <text x={W - padR + 2} y={toY(1.30) + 4} fontSize={8} fill="#f59e0b" fontWeight={700}>1.30x</text>

        {/* DSCR line */}
        <path d={linePath} fill="none" stroke="#16a34a" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {/* Data points at key months */}
        {series.filter(d => d.month % 6 === 0 || d.month === 1).map(d => (
          <circle
            key={d.month}
            cx={toX(d.month)} cy={toY(d.dscr)}
            r={3}
            fill={d.dscr >= 1.30 ? '#16a34a' : d.dscr >= 1.20 ? '#d97706' : '#dc2626'}
            stroke="white" strokeWidth={1}
          />
        ))}

        {/* Y-axis labels */}
        {yTicks.map(v => (
          <text key={v} x={padL - 6} y={toY(v) + 4} textAnchor="end" fontSize={9} fill="#9ca3af" fontWeight={600}>
            {v.toFixed(2)}
          </text>
        ))}

        {/* X-axis labels */}
        {xTicks.map(m => (
          <text key={m} x={toX(m)} y={H - 6} textAnchor="middle" fontSize={9} fill="#9ca3af">
            M{m}
          </text>
        ))}

        {/* Axis labels */}
        <text x={padL + innerW / 2} y={H - 1} textAnchor="middle" fontSize={8} fill="#9ca3af">
          Month of operations (Year 1–3)
        </text>
        <text
          x={10}
          y={padT + innerH / 2}
          textAnchor="middle"
          fontSize={8}
          fill="#9ca3af"
          transform={`rotate(-90, 10, ${padT + innerH / 2})`}
        >
          DSCR P50
        </text>
      </svg>

      {/* Chart legend */}
      <div className="flex items-center gap-5 mt-2 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0.5 bg-green-600 rounded" />
          <span>DSCR P50</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0" style={{ borderBottom: '2px dashed #ef4444' }} />
          <span>Covenant floor 1.20x</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0" style={{ borderBottom: '2px dashed #f59e0b' }} />
          <span>Target floor 1.30x</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-3 bg-green-200 rounded-sm opacity-70" />
          <span>Headroom (above covenant)</span>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function DSCRHeatmap() {
  const { selectedProjectId } = useSelectedProject()
  const data = generateSensitivityData(selectedProjectId)

  const baseDSCRStyle =
    data.baseDSCR >= 1.30 ? 'text-green-700 bg-green-50 border-green-200' :
    data.baseDSCR >= 1.20 ? 'text-amber-700 bg-amber-50 border-amber-200' :
    'text-red-700 bg-red-50 border-red-200'

  const breachCount = data.sensitivityRows.reduce((acc, row) =>
    acc + row.values.filter(v => v < 1.20).length, 0
  )
  const totalCells = data.sensitivityRows.length * 5

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-8">

      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">DSCR Sensitivity Heatmap</h1>
          <p className="text-sm text-gray-500 mt-1">
            {TAB_DESCRIPTIONS.DSCR_SENSITIVITY}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-4 py-2 rounded-xl border font-black text-lg tabular-nums ${baseDSCRStyle}`}>
            <span className="text-xs font-semibold opacity-70 flex items-center gap-1">Base DSCR P50 <InfoTooltip text={HELP.DSCR_P50} /></span>
            {data.baseDSCR.toFixed(2)}x
          </div>
          {breachCount > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-bold">
              <AlertTriangle className="w-4 h-4" />
              {breachCount}/{totalCells} scenarios breach covenant
            </div>
          )}
          {breachCount === 0 && (
            <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-green-50 border border-green-200 text-green-700 text-sm font-bold">
              <Shield className="w-4 h-4" />
              No covenant breaches in single-factor analysis
            </div>
          )}
        </div>
      </div>

      {/* ── ZONE 1: Single-Factor Sensitivity Table ─────────────────── */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
        <SectionTitle>
          <TrendingDown className="w-4 h-4 text-gray-500" />
          Single-Factor Sensitivity Analysis
          <span className="ml-1 text-gray-400 text-xs font-normal normal-case tracking-normal">
            — DSCR P50 under isolated shocks
          </span>
        </SectionTitle>
        <SingleFactorTable rows={data.sensitivityRows} />
        <div className="mt-3 flex items-start gap-2 bg-gray-50 rounded-lg p-3 text-xs text-gray-500">
          <Info className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
          Shocks applied individually, holding all other factors at base case. Covenant floor: 1.20x (red cells).
          Target DSCR: 1.30x. Base column highlighted in blue.
        </div>
      </div>

      {/* ── ZONES 2 & 3: Heatmap + Breakeven sidebar ──────────────── */}
      <div className="grid grid-cols-4 gap-4">

        {/* Heatmap — 3/4 width */}
        <div className="col-span-3 rounded-2xl border border-gray-200 bg-white shadow-sm p-5">
          <SectionTitle>
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            Two-Factor Combined Shock — Power Price × Efficiency
          </SectionTitle>
          <TwoFactorHeatmap cells={data.heatmapCells} baseDSCR={data.baseDSCR} />
        </div>

        {/* Breakeven metrics sidebar — 1/4 width */}
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
          Covenant Headroom — Monthly DSCR P50 (Years 1–3 of Operations)
          <span className="ml-1 text-gray-400 text-xs font-normal normal-case tracking-normal">
            — shaded area = headroom above 1.20x floor
          </span>
        </SectionTitle>
        <CovenantHeadroomChart series={data.monthlySeries} baseDSCR={data.baseDSCR} />

        {/* Min / max callouts */}
        <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-gray-100">
          {(() => {
            const vals = data.monthlySeries.map(d => d.dscr)
            const minVal = Math.min(...vals)
            const maxVal = Math.max(...vals)
            const minMonth = data.monthlySeries.find(d => d.dscr === minVal)?.month ?? 0
            const maxMonth = data.monthlySeries.find(d => d.dscr === maxVal)?.month ?? 0
            const avgVal = vals.reduce((a, b) => a + b, 0) / vals.length
            return [
              { label: 'Minimum (Month ' + minMonth + ')', value: minVal.toFixed(2) + 'x', color: minVal >= 1.20 ? 'text-green-700' : 'text-red-700', bg: minVal >= 1.20 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200' },
              { label: 'Average (M1–M36)',     value: avgVal.toFixed(2) + 'x', color: avgVal >= 1.30 ? 'text-green-700' : avgVal >= 1.20 ? 'text-amber-700' : 'text-red-700', bg: avgVal >= 1.30 ? 'bg-green-50 border-green-200' : avgVal >= 1.20 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200' },
              { label: 'Maximum (Month ' + maxMonth + ')', value: maxVal.toFixed(2) + 'x', color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
            ].map(m => (
              <div key={m.label} className={`rounded-xl border p-3 ${m.bg}`}>
                <div className="text-xs text-gray-500 font-medium mb-1">{m.label}</div>
                <div className={`text-2xl font-black tabular-nums ${m.color}`}>{m.value}</div>
              </div>
            ))
          })()}
        </div>
      </div>

    </div>
  )
}
