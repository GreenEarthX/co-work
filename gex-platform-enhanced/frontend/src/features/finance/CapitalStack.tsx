/**
 * CapitalStack — multi-tranche capital stack evaluation.
 * Shows per-tranche breakdown, blended WACC, phase-matching chart,
 * WACC sensitivity table, and gap analysis for the selected project.
 */
import { useState } from 'react'
import { Layers, TrendingUp, AlertTriangle, ChevronDown, ChevronUp, Leaf, Shield, BarChart3 } from 'lucide-react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { HELP } from '@/config/helpText'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'
import { CommitmentStatusBadge } from '@/components/finance/CommitmentStatusBadge'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

type TrancheType = 'GRANT' | 'DFI' | 'ECA/DFI' | 'SENIOR' | 'EQUITY' | 'MEZZ'
type TrancheStatus = 'COMMITTED' | 'MANDATE' | 'PIPELINE' | 'SECURED'
type Phase = 'ADVISORY' | 'FINANCIAL_CLOSE' | 'CONSTRUCTION'

interface Tranche {
  type: TrancheType
  source: string
  amount: number        // €M
  cost: number          // % (annual)
  tenor: number | null  // years, null for equity/grants
  phase: Phase
  status: TrancheStatus
}

interface ProjectCapitalData {
  blendedWacc: number
  tranches: Tranche[]
}

// ── Change 4: CAPEX Layer decomposition ──────────────────────────
type RiskProfile = 'LOW' | 'MEDIUM' | 'MEDIUM-HIGH' | 'HIGH'
type DepreciationMethod = 'STRAIGHT_LINE' | 'DECLINING_BALANCE' | 'UNITS_OF_PRODUCTION'

interface CapexLayer {
  id: string
  name: string
  description: string
  sharePct: number         // % of total capex
  riskProfile: RiskProfile
  usefulLifeYears: number
  residualValuePct: number
  optimalDebtPct: number   // % debt in optimal capital structure for this layer
  optimalEquityPct: number
  layerWacc: number        // % — blended for this layer's risk profile
  etvPremiumPct: number    // ETV uplift (Enterprise Technology Value)
  depreciation: DepreciationMethod
}

const CAPEX_LAYERS: CapexLayer[] = [
  {
    id: 'L1',
    name: 'Site & Entitlements',
    description: 'Land, permitting, grid connection rights, environmental consents',
    sharePct: 5,
    riskProfile: 'LOW',
    usefulLifeYears: 40,
    residualValuePct: 15,
    optimalDebtPct: 75,
    optimalEquityPct: 25,
    layerWacc: 5.2,
    etvPremiumPct: 0,
    depreciation: 'STRAIGHT_LINE',
  },
  {
    id: 'L2',
    name: 'Electrolyser + BoP',
    description: 'PEM/ALK electrolyser stacks, balance of plant, power electronics, utilities',
    sharePct: 45,
    riskProfile: 'MEDIUM',
    usefulLifeYears: 20,
    residualValuePct: 5,
    optimalDebtPct: 60,
    optimalEquityPct: 40,
    layerWacc: 7.8,
    etvPremiumPct: 4.2,
    depreciation: 'DECLINING_BALANCE',
  },
  {
    id: 'L3',
    name: 'Conversion & Storage',
    description: 'Fischer-Tropsch / Haber-Bosch / methanation reactor, storage & compression',
    sharePct: 20,
    riskProfile: 'MEDIUM-HIGH',
    usefulLifeYears: 25,
    residualValuePct: 8,
    optimalDebtPct: 55,
    optimalEquityPct: 45,
    layerWacc: 9.1,
    etvPremiumPct: 1.8,
    depreciation: 'STRAIGHT_LINE',
  },
  {
    id: 'L4',
    name: 'Infrastructure',
    description: 'Pipelines, jetty, tankage, logistics connections, substation',
    sharePct: 25,
    riskProfile: 'LOW',
    usefulLifeYears: 30,
    residualValuePct: 20,
    optimalDebtPct: 70,
    optimalEquityPct: 30,
    layerWacc: 5.8,
    etvPremiumPct: 0,
    depreciation: 'STRAIGHT_LINE',
  },
  {
    id: 'L5',
    name: 'GEX Platform',
    description: 'Digital twin, MRV stack, OT/IT gateway, tokenisation layer, GEX licensing',
    sharePct: 5,
    riskProfile: 'HIGH',
    usefulLifeYears: 7,
    residualValuePct: 0,
    optimalDebtPct: 20,
    optimalEquityPct: 80,
    layerWacc: 14.5,
    etvPremiumPct: 12.0,
    depreciation: 'DECLINING_BALANCE',
  },
]

const RISK_COLORS: Record<RiskProfile, string> = {
  LOW: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  'MEDIUM-HIGH': 'bg-orange-100 text-orange-700',
  HIGH: 'bg-red-100 text-red-700',
}

// ── Change 3: GCGC de-risking instruments ────────────────────────
interface DeRiskingInstrument {
  name: string
  type: string
  provider: string
  guaranteedDebtPct: number   // % of senior debt covered
  rateSavingBps: number       // bps reduction on guaranteed tranche
  premiumPct: number          // annual premium on guaranteed amount
  available: boolean
}

// ═══════════════════════════════════════════════════════════════
// DEMO DATA
// ═══════════════════════════════════════════════════════════════

const CAPITAL_DATA: Record<string, ProjectCapitalData> = {
  proj_le_havre_eng: {
    blendedWacc: 7.2,
    tranches: [
      { type: 'GRANT',   source: 'H2Global + EU IH2',        amount: 18,  cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'DFI',     source: 'BPI France',                amount: 95,  cost: 3.2,  tenor: 20,   phase: 'FINANCIAL_CLOSE', status: 'MANDATE'   },
      { type: 'ECA/DFI', source: 'EIB Project Finance',       amount: 115, cost: 3.8,  tenor: 18,   phase: 'FINANCIAL_CLOSE', status: 'MANDATE'   },
      { type: 'SENIOR',  source: 'Credit Agricole CIB lead',  amount: 0,   cost: 0,    tenor: 0,    phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'EQUITY',  source: 'Project sponsors',          amount: 82,  cost: 12.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'MEZZ',    source: 'GreenFin Mezz Fund',        amount: 18,  cost: 8.5,  tenor: 12,   phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
    ],
  },
  // Alias for canonical ID in customerProjects
  proj_lehavre_eng: {
    blendedWacc: 7.2,
    tranches: [
      { type: 'GRANT',   source: 'H2Global + EU IH2',        amount: 18,  cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'DFI',     source: 'BPI France',                amount: 95,  cost: 3.2,  tenor: 20,   phase: 'FINANCIAL_CLOSE', status: 'MANDATE'   },
      { type: 'ECA/DFI', source: 'EIB Project Finance',       amount: 115, cost: 3.8,  tenor: 18,   phase: 'FINANCIAL_CLOSE', status: 'MANDATE'   },
      { type: 'SENIOR',  source: 'Credit Agricole CIB lead',  amount: 0,   cost: 0,    tenor: 0,    phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'EQUITY',  source: 'Project sponsors',          amount: 82,  cost: 12.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'MEZZ',    source: 'GreenFin Mezz Fund',        amount: 18,  cost: 8.5,  tenor: 12,   phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
    ],
  },
  proj_bremen_h2: {
    blendedWacc: 8.9,
    tranches: [
      { type: 'GRANT',  source: 'IPCEI H2 + BMWK',      amount: 22, cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'DFI',    source: 'EIB (indicative)',       amount: 80, cost: 4.1,  tenor: 15,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'EQUITY', source: 'Project sponsors',       amount: 58, cost: 14.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'MEZZ',   source: 'KfW Climate Action',    amount: 17, cost: 7.2,  tenor: 10,   phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
      { type: 'SENIOR', source: 'DZ Bank syndicate',      amount: 65, cost: 5.2,  tenor: 15,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
    ],
  },
  proj_helios_emethanol: {
    blendedWacc: 10.2,
    tranches: [
      { type: 'GRANT',   source: 'CEF + Spanish IDAE',          amount: 12, cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'ECA/DFI', source: 'EKF Denmark (pre-app)',        amount: 55, cost: 4.5,  tenor: 15,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'EQUITY',  source: 'Project sponsors',             amount: 52, cost: 15.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'MEZZ',    source: 'TBD',                          amount: 15, cost: 10.0, tenor: 8,    phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
      { type: 'SENIOR',  source: 'Banco Santander (unsolicited)',amount: 43, cost: 5.8,  tenor: 12,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
    ],
  },
  // Alias for canonical ID
  proj_sansebastian_emethanol: {
    blendedWacc: 10.2,
    tranches: [
      { type: 'GRANT',   source: 'CEF + Spanish IDAE',          amount: 12, cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'ECA/DFI', source: 'EKF Denmark (pre-app)',        amount: 55, cost: 4.5,  tenor: 15,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'EQUITY',  source: 'Project sponsors',             amount: 52, cost: 15.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'MEZZ',    source: 'TBD',                          amount: 15, cost: 10.0, tenor: 8,    phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
      { type: 'SENIOR',  source: 'Banco Santander (unsolicited)',amount: 43, cost: 5.8,  tenor: 12,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
    ],
  },
  proj_rotterdam_nh3: {
    blendedWacc: 12.1,
    tranches: [
      { type: 'GRANT',  source: 'NL RVO IPCEI',           amount: 8,  cost: 0,    tenor: null, phase: 'ADVISORY',        status: 'PIPELINE'  },
      { type: 'EQUITY', source: 'Project sponsors',        amount: 65, cost: 18.0, tenor: null, phase: 'ADVISORY',        status: 'COMMITTED' },
      { type: 'SENIOR', source: 'ING/Rabobank (no mandate)',amount:40, cost: 6.5,  tenor: 10,   phase: 'FINANCIAL_CLOSE', status: 'PIPELINE'  },
      { type: 'MEZZ',   source: 'None',                    amount: 15, cost: 12.0, tenor: 8,    phase: 'CONSTRUCTION',    status: 'PIPELINE'  },
    ],
  },
  proj_wales_saf: {
    blendedWacc: 15.5,
    tranches: [
      { type: 'EQUITY', source: 'Project sponsors',      amount: 45, cost: 22.0, tenor: null, phase: 'ADVISORY', status: 'COMMITTED' },
      { type: 'GRANT',  source: 'UK JETCO (applied)',    amount: 10, cost: 0,    tenor: null, phase: 'ADVISORY', status: 'PIPELINE'  },
    ],
  },
}

// GCGC instruments (applicable to all projects, availability varies by project maturity)
const GCGC_INSTRUMENTS: DeRiskingInstrument[] = [
  {
    name: 'GCGC First-Loss Guarantee',
    type: 'First-Loss Credit Enhancement',
    provider: 'Green Credit Guarantee Corporation (GCGC)',
    guaranteedDebtPct: 30,
    rateSavingBps: 90,
    premiumPct: 0.35,
    available: true,
  },
  {
    name: 'EIB Project Bond Initiative',
    type: 'Credit Enhancement',
    provider: 'European Investment Bank',
    guaranteedDebtPct: 20,
    rateSavingBps: 60,
    premiumPct: 0.25,
    available: true,
  },
  {
    name: 'MIGA Political Risk Insurance',
    type: 'Political Risk / Regulatory',
    provider: 'Multilateral Investment Guarantee Agency',
    guaranteedDebtPct: 50,
    rateSavingBps: 40,
    premiumPct: 0.45,
    available: false,
  },
]

// ═══════════════════════════════════════════════════════════════
// STYLE MAPS
// ═══════════════════════════════════════════════════════════════

const STATUS_STYLES: Record<TrancheStatus, { bg: string; text: string; border: string; label: string }> = {
  COMMITTED: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-300', label: 'Committed' },
  MANDATE:   { bg: 'bg-blue-100',  text: 'text-blue-700',  border: 'border-blue-300',  label: 'Mandate'   },
  PIPELINE:  { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-300', label: 'Pipeline'  },
  SECURED:   { bg: 'bg-teal-100',  text: 'text-teal-700',  border: 'border-teal-300',  label: 'Secured'   },
}

const TYPE_STYLES: Record<TrancheType, string> = {
  GRANT:     'bg-emerald-50 text-emerald-700',
  DFI:       'bg-sky-50 text-sky-700',
  'ECA/DFI': 'bg-cyan-50 text-cyan-700',
  SENIOR:    'bg-indigo-50 text-indigo-700',
  EQUITY:    'bg-violet-50 text-violet-700',
  MEZZ:      'bg-orange-50 text-orange-700',
}

const PHASE_LABELS: Record<Phase, string> = {
  ADVISORY:        'Advisory',
  FINANCIAL_CLOSE: 'Financial Close',
  CONSTRUCTION:    'Construction',
}

// ═══════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════

function waccColor(wacc: number): string {
  if (wacc <= 9)  return 'text-green-600'
  if (wacc <= 12) return 'text-amber-600'
  return 'text-red-600'
}

function waccBg(wacc: number): string {
  if (wacc <= 9)  return 'bg-green-50 border-green-200'
  if (wacc <= 12) return 'bg-amber-50 border-amber-200'
  return 'bg-red-50 border-red-200'
}

function fmt(n: number, decimals = 1): string {
  return n.toFixed(decimals)
}

/** Compute blended WACC from tranches (weighted average of cost by amount, excluding zero-cost grants). */
function computeBlendedWacc(tranches: Tranche[]): number {
  const costingTranches = tranches.filter(t => t.amount > 0 && t.cost > 0)
  const totalWeighted = costingTranches.reduce((sum, t) => sum + t.cost * t.amount, 0)
  const totalAmount = costingTranches.reduce((sum, t) => sum + t.amount, 0)
  if (totalAmount === 0) return 0
  return totalWeighted / totalAmount
}

/** Build WACC sensitivity: for each tranche with cost > 0, what if it's removed? */
function buildSensitivity(tranches: Tranche[], baseWacc: number) {
  return tranches
    .filter(t => t.amount > 0 && t.cost > 0)
    .map(t => {
      const remaining = tranches.filter(r => r !== t)
      const newWacc = computeBlendedWacc(remaining)
      const delta = newWacc - baseWacc
      return { tranche: t, newWacc, delta }
    })
    .sort((a, b) => b.delta - a.delta)
}

// ═══════════════════════════════════════════════════════════════
// PHASE-MATCHING CHART (inline SVG)
// ═══════════════════════════════════════════════════════════════

const CHART_W = 700
const CHART_H = 200
const PAD = { top: 20, right: 20, bottom: 40, left: 52 }

const QUARTERS = [
  'Q1-26','Q2-26','Q3-26','Q4-26',
  'Q1-27','Q2-27','Q3-27','Q4-27',
  'Q1-28','Q2-28','Q3-28','Q4-28',
]
const N = QUARTERS.length

/** S-curve: spend is concentrated in the middle quarters. */
function sCurveCapex(totalCapex: number): number[] {
  // logistic positions normalised 0..1 across N quarters
  const raw = QUARTERS.map((_, i) => {
    const x = (i / (N - 1)) * 10 - 5  // map to -5..5
    return 1 / (1 + Math.exp(-x))
  })
  const min = raw[0], max = raw[N - 1]
  const cumulative = raw.map(v => ((v - min) / (max - min)) * totalCapex)
  return cumulative
}

/** Capital available: ramp up by phase over quarters (advisory → financial close Q4 → construction Q8). */
function capitalAvailableCurve(tranches: Tranche[]): number[] {
  const committed = tranches.filter(t => t.status === 'COMMITTED' || t.status === 'MANDATE')
  const advisory   = committed.filter(t => t.phase === 'ADVISORY').reduce((s, t) => s + t.amount, 0)
  const finClose   = committed.filter(t => t.phase === 'FINANCIAL_CLOSE').reduce((s, t) => s + t.amount, 0)
  const construction = committed.filter(t => t.phase === 'CONSTRUCTION').reduce((s, t) => s + t.amount, 0)

  return QUARTERS.map((_, i) => {
    let cap = advisory
    if (i >= 4)  cap += finClose       // Q1-27 onwards
    if (i >= 8)  cap += construction   // Q1-28 onwards
    return cap
  })
}

function PhaseMatchChart({ tranches, totalCapex }: { tranches: Tranche[]; totalCapex: number }) {
  const capex = sCurveCapex(totalCapex)
  const capital = capitalAvailableCurve(tranches)
  const yMax = Math.max(totalCapex, ...capital) * 1.05

  const plotW = CHART_W - PAD.left - PAD.right
  const plotH = CHART_H - PAD.top - PAD.bottom

  function xOf(i: number) { return PAD.left + (i / (N - 1)) * plotW }
  function yOf(v: number) { return PAD.top + plotH - (v / yMax) * plotH }

  // Build SVG path strings
  function polyline(values: number[]) {
    return values.map((v, i) => `${xOf(i)},${yOf(v)}`).join(' ')
  }
  function areaPath(values: number[]) {
    const top = values.map((v, i) => `${xOf(i)},${yOf(v)}`).join(' L ')
    return `M ${xOf(0)},${yOf(values[0])} L ${top} L ${xOf(N - 1)},${yOf(0)} L ${xOf(0)},${yOf(0)} Z`
  }

  // Gap areas: where capex > capital (red shading)
  // Build per-segment gap polygons
  function gapSegments() {
    const segs: { x1: number; x2: number; y1capex: number; y2capex: number; y1cap: number; y2cap: number }[] = []
    for (let i = 0; i < N - 1; i++) {
      if (capex[i] > capital[i] || capex[i + 1] > capital[i + 1]) {
        segs.push({
          x1: xOf(i), x2: xOf(i + 1),
          y1capex: yOf(capex[i]), y2capex: yOf(capex[i + 1]),
          y1cap: yOf(capital[i]), y2cap: yOf(capital[i + 1]),
        })
      }
    }
    return segs
  }

  const gaps = gapSegments()
  const capitalPoints = polyline(capital)
  const capexPoints = polyline(capex)

  return (
    <svg width={CHART_W} height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`} className="w-full h-auto">
      {/* Y-axis gridlines */}
      {[0, 0.25, 0.5, 0.75, 1].map(frac => {
        const y = PAD.top + plotH * (1 - frac)
        const val = yMax * frac
        return (
          <g key={frac}>
            <line x1={PAD.left} y1={y} x2={CHART_W - PAD.right} y2={y} stroke="#f0f0f0" strokeWidth="1" />
            <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize="9" fill="#9ca3af">
              {val >= 100 ? `${Math.round(val / 10) * 10}` : fmt(val, 0)}M
            </text>
          </g>
        )
      })}

      {/* Capital available filled area (green) */}
      <path d={areaPath(capital)} fill="#bbf7d0" fillOpacity="0.6" />

      {/* Gap segments (red) */}
      {gaps.map((s, i) => (
        <polygon
          key={i}
          points={`${s.x1},${s.y1capex} ${s.x2},${s.y2capex} ${s.x2},${s.y2cap} ${s.x1},${s.y1cap}`}
          fill="#fca5a5"
          fillOpacity="0.5"
        />
      ))}

      {/* Capex demand line (blue) */}
      <polyline points={capexPoints} fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />

      {/* Capital available line (green) */}
      <polyline points={capitalPoints} fill="none" stroke="#16a34a" strokeWidth="2" strokeDasharray="5 3" strokeLinejoin="round" />

      {/* X-axis quarter labels */}
      {QUARTERS.map((q, i) => (
        <text
          key={q}
          x={xOf(i)}
          y={CHART_H - PAD.bottom + 14}
          textAnchor="middle"
          fontSize="8"
          fill="#6b7280"
          transform={`rotate(-30, ${xOf(i)}, ${CHART_H - PAD.bottom + 14})`}
        >
          {q}
        </text>
      ))}

      {/* Phase dividers */}
      {[4, 8].map(qi => (
        <line
          key={qi}
          x1={xOf(qi)} y1={PAD.top}
          x2={xOf(qi)} y2={PAD.top + plotH}
          stroke="#d1d5db" strokeWidth="1" strokeDasharray="4 3"
        />
      ))}
      <text x={xOf(2)}  y={PAD.top - 5} textAnchor="middle" fontSize="8" fill="#9ca3af">Advisory</text>
      <text x={xOf(6)}  y={PAD.top - 5} textAnchor="middle" fontSize="8" fill="#9ca3af">Financial Close</text>
      <text x={xOf(10)} y={PAD.top - 5} textAnchor="middle" fontSize="8" fill="#9ca3af">Construction</text>

      {/* Legend */}
      <rect x={PAD.left + 4} y={PAD.top + 4} width="10" height="10" fill="#bbf7d0" stroke="#16a34a" strokeWidth="1" rx="2" />
      <text x={PAD.left + 18} y={PAD.top + 13} fontSize="9" fill="#374151">Capital Available</text>
      <line x1={PAD.left + 100} y1={PAD.top + 9} x2={PAD.left + 110} y2={PAD.top + 9} stroke="#3b82f6" strokeWidth="2.5" />
      <text x={PAD.left + 114} y={PAD.top + 13} fontSize="9" fill="#374151">Capex Demand</text>
      <rect x={PAD.left + 185} y={PAD.top + 4} width="10" height="10" fill="#fca5a5" fillOpacity="0.6" stroke="#ef4444" strokeWidth="1" rx="2" />
      <text x={PAD.left + 199} y={PAD.top + 13} fontSize="9" fill="#374151">Funding Gap</text>
    </svg>
  )
}

// ═══════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════

function SectionCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-sm ${className}`}>
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 rounded-t-xl">
        <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">{title}</h3>
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  )
}

function StatusBadge({ status }: { status: TrancheStatus }) {
  const s = STATUS_STYLES[status]
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-semibold ${s.bg} ${s.text} ${s.border}`}>
      {s.label}
    </span>
  )
}

function TypePill({ type }: { type: TrancheType }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono font-semibold ${TYPE_STYLES[type]}`}>
      {type}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════════
// CHANGE 4: CAPEX LAYER DECOMPOSITION VIEW
// ═══════════════════════════════════════════════════════════════

function CapexLayersView({ totalCapex, projectName }: { totalCapex: number; projectName: string }) {
  const layers = CAPEX_LAYERS.map(l => ({
    ...l,
    amount: parseFloat((totalCapex * l.sharePct / 100).toFixed(1)),
  }))

  // Blended WACC across layers (amount-weighted)
  const layerBlendedWacc = layers.reduce((sum, l) => sum + l.layerWacc * l.sharePct / 100, 0)
  // Traditional single-WACC (flat 9% typical project finance assumption)
  const traditionalWacc = 9.0
  const waccSaving = traditionalWacc - layerBlendedWacc

  // Weighted avg ETV premium
  const etvBlended = layers.reduce((sum, l) => sum + l.etvPremiumPct * l.sharePct / 100, 0)

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Layer-Blended WACC', value: `${layerBlendedWacc.toFixed(1)}%`, color: waccColor(layerBlendedWacc), note: 'Weighted by capex share' },
          { label: 'Traditional WACC', value: `${traditionalWacc.toFixed(1)}%`, color: 'text-gray-600', note: 'Single-tranche assumption' },
          { label: 'WACC Saving', value: `${waccSaving >= 0 ? '+' : ''}${waccSaving.toFixed(2)}pp`, color: waccSaving > 0 ? 'text-green-600' : 'text-red-600', note: 'vs. traditional approach' },
          { label: 'Blended ETV Premium', value: `+${etvBlended.toFixed(1)}%`, color: 'text-indigo-600', note: 'Optionality not on B/S' },
        ].map(s => (
          <div key={s.label} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm text-center">
            <div className={`text-2xl font-black tabular-nums ${s.color}`}>{s.value}</div>
            <div className="text-xs font-semibold text-gray-700 mt-1">{s.label}</div>
            <div className="text-xs text-gray-400">{s.note}</div>
          </div>
        ))}
      </div>

      {/* Layer table */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
        <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">
            CAPEX Layer Decomposition — {projectName}
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                {[
                  { label: 'Layer', tip: HELP.CAPEX_LAYER },
                  { label: 'Description', tip: null },
                  { label: 'Share', tip: null },
                  { label: 'Amount (€M)', tip: null },
                  { label: 'Risk', tip: null },
                  { label: 'Useful Life', tip: null },
                  { label: 'Residual', tip: null },
                  { label: 'Optimal Debt', tip: null },
                  { label: 'Layer WACC', tip: HELP.LAYER_WACC },
                  { label: 'ETV Premium', tip: HELP.ETV },
                  { label: 'Depreciation', tip: null },
                ].map(({ label, tip }) => (
                  <th key={label} className="text-left px-3 py-2 font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    <span className="flex items-center gap-1">{label}{tip && <InfoTooltip text={tip} />}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {layers.map(l => (
                <tr key={l.id} className="hover:bg-gray-50/50">
                  <td className="px-3 py-2.5">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-gray-900 text-white text-xs font-black">{l.id}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="font-semibold text-gray-800">{l.name}</div>
                    <div className="text-gray-400 text-xs max-w-[200px] truncate" title={l.description}>{l.description}</div>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums font-semibold text-gray-700">{l.sharePct}%</td>
                  <td className="px-3 py-2.5 tabular-nums font-bold text-gray-900">€{l.amount}M</td>
                  <td className="px-3 py-2.5">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${RISK_COLORS[l.riskProfile]}`}>{l.riskProfile}</span>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-gray-700">{l.usefulLifeYears}yr</td>
                  <td className="px-3 py-2.5 tabular-nums text-gray-700">{l.residualValuePct}%</td>
                  <td className="px-3 py-2.5 tabular-nums text-gray-700">
                    {l.optimalDebtPct}% / {l.optimalEquityPct}%
                  </td>
                  <td className={`px-3 py-2.5 tabular-nums font-bold ${waccColor(l.layerWacc)}`}>{l.layerWacc}%</td>
                  <td className="px-3 py-2.5 tabular-nums text-indigo-600 font-semibold">
                    {l.etvPremiumPct > 0 ? `+${l.etvPremiumPct}%` : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">
                    {l.depreciation === 'STRAIGHT_LINE' ? 'S/L' : l.depreciation === 'DECLINING_BALANCE' ? 'DB' : 'UoP'}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-gray-200 bg-gray-50/80">
                <td colSpan={3} className="px-3 pt-2 pb-2 text-xs font-black text-gray-700 uppercase tracking-wide">Total / Blended</td>
                <td className="px-3 pt-2 pb-2 font-black text-gray-900 tabular-nums">€{totalCapex.toFixed(0)}M</td>
                <td colSpan={4} />
                <td className={`px-3 pt-2 pb-2 font-black tabular-nums ${waccColor(layerBlendedWacc)}`}>{layerBlendedWacc.toFixed(1)}%</td>
                <td className="px-3 pt-2 pb-2 font-black text-indigo-600 tabular-nums">+{etvBlended.toFixed(1)}%</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* WACC comparison note */}
      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-xs text-indigo-900 space-y-1">
        <p className="font-bold">Layer-Stratified Financing vs. Traditional Single-Tranche</p>
        <p>
          Traditional project finance applies a uniform WACC across all capex layers, ignoring their heterogeneous
          risk, useful life, and optimal capital structure. Stratifying the stack by layer reduces the blended WACC
          by <strong>{waccSaving >= 0 ? `${waccSaving.toFixed(2)}pp` : `${Math.abs(waccSaving).toFixed(2)}pp (dis-advantage for this project)`}</strong> and
          unlocks ETV optionality of <strong>+{etvBlended.toFixed(1)}%</strong> not reflected on the balance sheet
          (product switching, GoO appreciation, carbon premium escalation, refinancing option).
        </p>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// CHANGE 3: GCGC DE-RISKING VIEW
// ═══════════════════════════════════════════════════════════════

function DeRiskingView({ tranches, baseWacc, baseDscr }: { tranches: Tranche[]; baseWacc: number; baseDscr: number }) {
  const [activeInstrument, setActiveInstrument] = useState<string | null>(null)

  // Find senior debt tranches
  const seniorTranches = tranches.filter(t => t.type === 'SENIOR' || t.type === 'DFI' || t.type === 'ECA/DFI')
  const seniorTotal = seniorTranches.reduce((s, t) => s + t.amount, 0)
  const totalCapital = tranches.reduce((s, t) => s + t.amount, 0)
  const avgSeniorCost = seniorTotal > 0
    ? seniorTranches.reduce((s, t) => s + t.cost * t.amount, 0) / seniorTotal
    : 0

  function computeImpact(inst: DeRiskingInstrument) {
    if (seniorTotal === 0) return { newWacc: baseWacc, waccDelta: 0, dscrDelta: 0, annualSaving: 0, netSaving: 0 }
    const guaranteedAmt = seniorTotal * inst.guaranteedDebtPct / 100
    const savingAmt = guaranteedAmt * inst.rateSavingBps / 10000
    const premiumCost = guaranteedAmt * inst.premiumPct / 100
    const netSaving = savingAmt - premiumCost
    // WACC impact: net saving as % of total capital
    const waccDelta = -(netSaving / totalCapital) * 100
    // DSCR impact: DSCR ≈ CFADS / DebtService. Reducing debt service by netSaving improves DSCR
    // rough: 1% WACC reduction ≈ +0.06 DSCR improvement
    const dscrDelta = Math.abs(waccDelta) * 0.06 * (waccDelta < 0 ? 1 : -1)
    const newWacc = Math.max(0, baseWacc + waccDelta)
    return { newWacc, waccDelta, dscrDelta, annualSaving: savingAmt, netSaving }
  }

  return (
    <div className="space-y-4">
      {/* Senior debt context */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-3">Senior Debt Subject to De-Risking</h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-500">Total Senior / DFI / ECA</div>
            <div className="text-xl font-black text-gray-900">€{seniorTotal}M</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Avg Senior Cost</div>
            <div className="text-xl font-black text-blue-600">{avgSeniorCost.toFixed(2)}%</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Base DSCR</div>
            <div className="text-xl font-black text-emerald-600">{baseDscr.toFixed(2)}x</div>
          </div>
        </div>
      </div>

      {/* Instrument cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {GCGC_INSTRUMENTS.map(inst => {
          const impact = computeImpact(inst)
          const isActive = activeInstrument === inst.name
          return (
            <div
              key={inst.name}
              onClick={() => inst.available && setActiveInstrument(isActive ? null : inst.name)}
              className={`rounded-xl border p-4 shadow-sm transition-all ${
                !inst.available ? 'opacity-50 cursor-not-allowed border-gray-200 bg-gray-50' :
                isActive ? 'border-blue-400 bg-blue-50 cursor-pointer' :
                'border-gray-200 bg-white cursor-pointer hover:border-blue-300 hover:shadow-md'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-bold text-gray-900 text-sm">{inst.name}</div>
                  <div className="text-xs text-gray-500">{inst.provider}</div>
                </div>
                <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${
                  inst.available ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                }`}>
                  {inst.available ? 'Available' : 'N/A'}
                </span>
              </div>
              <div className="space-y-1 text-xs mt-3">
                <div className="flex justify-between">
                  <span className="text-gray-500">Coverage</span>
                  <span className="font-semibold">{inst.guaranteedDebtPct}% of senior debt</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Rate saving</span>
                  <span className="font-semibold text-green-700">-{inst.rateSavingBps}bps</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Annual premium</span>
                  <span className="font-semibold text-amber-700">{inst.premiumPct}%</span>
                </div>
              </div>
              {inst.available && (
                <div className="mt-3 pt-3 border-t border-gray-100 space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">New WACC</span>
                    <span className={`font-black ${waccColor(impact.newWacc)}`}>{impact.newWacc.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">WACC delta</span>
                    <span className={`font-semibold ${impact.waccDelta < 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {impact.waccDelta > 0 ? '+' : ''}{impact.waccDelta.toFixed(2)}pp
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">DSCR improvement</span>
                    <span className="font-semibold text-emerald-600">+{impact.dscrDelta.toFixed(2)}x</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Net annual saving</span>
                    <span className="font-bold text-gray-900">€{(impact.netSaving / 1).toFixed(1)}M/yr</span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-xs text-indigo-900 space-y-1">
        <p className="font-bold">GCGC Mechanism (Taghizadeh-Hesary et al., 2022)</p>
        <p>
          Green Credit Guarantee Corporations absorb first-loss risk on renewable energy debt, reducing lender credit risk and enabling interest rate savings of 60–100bps on the guaranteed tranche.
          The net saving (rate reduction minus guarantee premium) directly reduces debt service and improves DSCR and WACC.
          Instruments are listed in priority order for green hydrogen PF structures.
        </p>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// CHANGE 2: GREEN BOND COMPARISON PANEL
// ═══════════════════════════════════════════════════════════════

function GreenBondComparison({ tranches, baseWacc }: { tranches: Tranche[]; baseWacc: number }) {
  // Taghizadeh-Hesary (2022): optimal split is 56% bank loans / 44% green bonds
  // Green bonds carry a 25bps greenium (lower yield vs equivalent bank loan)
  const OPTIMAL_BANK_SHARE = 0.56
  const OPTIMAL_BOND_SHARE = 0.44
  const GREENIUM_BPS = 25

  const debtTranches = tranches.filter(t => t.type === 'SENIOR' || t.type === 'DFI' || t.type === 'ECA/DFI' || t.type === 'MEZZ')
  const debtTotal = debtTranches.reduce((s, t) => s + t.amount, 0)
  const avgDebtCost = debtTotal > 0
    ? debtTranches.reduce((s, t) => s + t.cost * t.amount, 0) / debtTotal
    : 0

  const nonDebt = tranches.filter(t => t.type === 'GRANT' || t.type === 'EQUITY')
  const totalCapital = tranches.reduce((s, t) => s + t.amount, 0)

  // Scenario A: current structure
  const scenAWacc = baseWacc

  // Scenario B: 56/44 split, green bonds at (avgDebtCost - 0.25)
  const bankLoanAmt = debtTotal * OPTIMAL_BANK_SHARE
  const greenBondAmt = debtTotal * OPTIMAL_BOND_SHARE
  const bankLoanCost = avgDebtCost
  const greenBondCost = Math.max(0, avgDebtCost - GREENIUM_BPS / 100)

  // Recompute blended WACC for Scenario B
  const scenBTranches: Tranche[] = [
    ...nonDebt,
    { type: 'SENIOR', source: 'Bank Loan (56%)', amount: bankLoanAmt, cost: bankLoanCost, tenor: 15, phase: 'FINANCIAL_CLOSE', status: 'PIPELINE' },
    { type: 'SENIOR', source: 'Green Bond (44%)', amount: greenBondAmt, cost: greenBondCost, tenor: 15, phase: 'FINANCIAL_CLOSE', status: 'PIPELINE' },
  ]
  const scenBWacc = computeBlendedWacc(scenBTranches)
  const waccDelta = scenBWacc - scenAWacc
  // DSCR improvement from lower debt service: per 1pp WACC reduction ≈ +0.06 DSCR
  const dscrImpact = -waccDelta * 0.06

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <Leaf className="w-4 h-4 text-emerald-700" />
        <h3 className="text-xs font-black uppercase tracking-widest text-emerald-800">
          Optimal Bank / Green Bond Split — Taghizadeh-Hesary (2022)
        </h3>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {/* Scenario A */}
        <div className="bg-white rounded-lg border border-gray-200 p-3">
          <div className="text-xs font-bold text-gray-600 mb-2 uppercase tracking-wide">Scenario A — Current Structure</div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Total debt</span>
              <span className="font-semibold">€{debtTotal.toFixed(0)}M</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Avg debt cost</span>
              <span className="font-semibold">{avgDebtCost.toFixed(2)}%</span>
            </div>
            <div className={`flex justify-between pt-1 border-t border-gray-100`}>
              <span className="font-semibold text-gray-700">Blended WACC</span>
              <span className={`font-black ${waccColor(scenAWacc)}`}>{scenAWacc.toFixed(1)}%</span>
            </div>
          </div>
        </div>
        {/* Scenario B */}
        <div className="bg-white rounded-lg border border-emerald-300 p-3">
          <div className="text-xs font-bold text-emerald-700 mb-2 uppercase tracking-wide">Scenario B — 56/44 Optimal Split</div>
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Bank loans (56%)</span>
              <span className="font-semibold">€{bankLoanAmt.toFixed(0)}M @ {bankLoanCost.toFixed(2)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Green bonds (44%)</span>
              <span className="font-semibold text-emerald-700">€{greenBondAmt.toFixed(0)}M @ {greenBondCost.toFixed(2)}% <span className="text-emerald-500">(-{GREENIUM_BPS}bps)</span></span>
            </div>
            <div className={`flex justify-between pt-1 border-t border-emerald-100`}>
              <span className="font-semibold text-emerald-700">New WACC</span>
              <span className={`font-black ${waccColor(scenBWacc)}`}>{scenBWacc.toFixed(1)}%</span>
            </div>
          </div>
        </div>
      </div>
      {/* Delta summary */}
      <div className="grid grid-cols-3 gap-3 text-center text-xs">
        <div className="bg-white rounded-lg border border-gray-100 p-2">
          <div className={`text-lg font-black ${waccDelta < 0 ? 'text-green-600' : 'text-red-600'}`}>
            {waccDelta > 0 ? '+' : ''}{waccDelta.toFixed(2)}pp
          </div>
          <div className="text-gray-500">WACC delta</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-100 p-2">
          <div className="text-lg font-black text-emerald-600">
            +{dscrImpact.toFixed(2)}x
          </div>
          <div className="text-gray-500">DSCR improvement</div>
        </div>
        <div className="bg-white rounded-lg border border-gray-100 p-2">
          <div className="text-lg font-black text-blue-600">
            €{(debtTotal * GREENIUM_BPS / 10000 * OPTIMAL_BOND_SHARE / 1).toFixed(1)}M/yr
          </div>
          <div className="text-gray-500">Annual interest saving</div>
        </div>
      </div>
      <p className="text-xs text-emerald-700">
        Source: Taghizadeh-Hesary &amp; Yoshino (2022), ADB Working Paper — optimal debt mix for renewable H₂ projects at 56% bank loans / 44% green bonds; green bond greenium of 20–30bps vs. equivalent bank facility.
        Total capital: €{totalCapital.toFixed(0)}M.
      </p>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

export function CapitalStack() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId)

  const data: ProjectCapitalData =
    CAPITAL_DATA[selectedProjectId] ?? CAPITAL_DATA['proj_lehavre_eng']

  const { tranches, blendedWacc } = data

  // Totals
  const totalCapital = tranches.reduce((s, t) => s + t.amount, 0)
  const committedCapital = tranches
    .filter(t => t.status === 'COMMITTED' || t.status === 'MANDATE')
    .reduce((s, t) => s + t.amount, 0)

  // Use capex_eur from project data if available (it's stored in €M in customerProjects),
  // otherwise fall back to total capital as proxy.
  const totalCapex = project ? project.capex_eur / 1_000_000 : totalCapital
  const unfunded = Math.max(0, totalCapex - committedCapital)
  const gapPct = totalCapex > 0 ? (unfunded / totalCapex) * 100 : 0

  const sensitivity = buildSensitivity(tranches, blendedWacc)

  const [sensitivityOpen, setSensitivityOpen] = useState(true)
  const [showBondComparison, setShowBondComparison] = useState(false)
  const [activeTab, setActiveTab] = useState<'stack' | 'capex_layers' | 'derisk'>('stack')

  // Approximate base DSCR from WACC (used in de-risking view)
  const approxBaseDscr = Math.max(0.8, 2.5 - blendedWacc * 0.10)

  return (
    <div className="space-y-4 max-w-7xl mx-auto pb-8">
      {/* ── HEADER ──────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="flex items-start justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Layers className="w-4 h-4 text-gray-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-gray-400">Capital Stack</span>
            </div>
            <h1 className="text-2xl font-black text-white">{project?.name ?? 'Project'}</h1>
            <p className="text-sm text-gray-400 mt-0.5">{project?.location ?? '—'}</p>
          </div>
          <div className="flex flex-col items-end gap-2 mt-1">
            <WorkflowBadge state="COMPUTED" computedAt="2026-03-10" showStale />
            <WorkflowActions
              state="COMPUTED"
              objectType="Capital Stack"
              userRole="analyst"
              projectId={project?.id}
              workflowObjectType="CapitalStackScenario"
              workflowObjectId={`capital-stack-${project?.id ?? 'default'}`}
            />
          </div>
        </div>
      </div>

      {/* ── TAB NAVIGATION ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1 border-b border-gray-200 pb-0">
        {([
          { id: 'stack',       label: 'Capital Stack',       icon: <Layers className="w-3.5 h-3.5" /> },
          { id: 'capex_layers',label: 'CAPEX Layers',        icon: <BarChart3 className="w-3.5 h-3.5" /> },
          { id: 'derisk',      label: 'De-Risking',          icon: <Shield className="w-3.5 h-3.5" /> },
        ] as const).map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold rounded-t-lg border border-b-0 transition-colors ${
              activeTab === tab.id
                ? 'bg-white border-gray-200 text-gray-900 -mb-px z-10 relative'
                : 'bg-gray-50 border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── STACK TAB ──────────────────────────────────────────────── */}
      {activeTab === 'stack' && <>

      {/* ── MAIN GRID ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">

        {/* LEFT + CENTER: Tranche table (span 2) */}
        <div className="col-span-2 space-y-4">
          <SectionCard title="Tranche Breakdown">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Source</th>
                    <th className="text-left py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Type</th>
                    <th className="text-right py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Amount (€M)</th>
                    <th className="text-right py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Cost (%)</th>
                    <th className="text-right py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Tenor (yr)</th>
                    <th className="text-left  py-1.5 pr-3 font-semibold text-gray-500 uppercase tracking-wide">Phase</th>
                    <th className="text-left  py-1.5 font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tranches.map((t, i) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                      <td className="py-2 pr-3 font-medium text-gray-800 max-w-[180px] truncate" title={t.source}>
                        {t.source}
                      </td>
                      <td className="py-2 pr-3">
                        <TypePill type={t.type} />
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums font-semibold text-gray-800">
                        {t.amount > 0 ? fmt(t.amount, 0) : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-gray-700">
                        {t.cost > 0 ? `${fmt(t.cost, 1)}%` : '—'}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-gray-600">
                        {t.tenor != null && t.tenor > 0 ? t.tenor : '—'}
                      </td>
                      <td className="py-2 pr-3 text-gray-600">{PHASE_LABELS[t.phase]}</td>
                      <td className="py-2">
                        <StatusBadge status={t.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-gray-200">
                    <td colSpan={2} className="pt-2 text-xs font-black text-gray-700 uppercase tracking-wide">Total</td>
                    <td className="pt-2 text-right tabular-nums font-black text-gray-900">{fmt(totalCapital, 0)}</td>
                    <td colSpan={4} />
                  </tr>
                </tfoot>
              </table>
            </div>
          </SectionCard>

          {/* Phase-Matching Chart */}
          <SectionCard title="Phase-Matching Chart — Capital vs. Capex Demand">
            <div className="overflow-x-auto">
              <PhaseMatchChart tranches={tranches} totalCapex={totalCapex} />
            </div>
          </SectionCard>
        </div>

        {/* RIGHT SIDEBAR */}
        <div className="col-span-1 space-y-4">
          {/* Blended WACC Card */}
          <div className={`rounded-xl border p-4 shadow-sm ${waccBg(blendedWacc)}`}>
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-gray-500" />
              <span className="text-xs font-black uppercase tracking-widest text-gray-600 flex items-center gap-1">Blended WACC <InfoTooltip text={HELP.BLENDED_WACC} /></span>
            </div>
            <div className={`text-5xl font-black tabular-nums ${waccColor(blendedWacc)}`}>
              {fmt(blendedWacc, 1)}%
            </div>
            <div className="mt-3 space-y-1 border-t border-gray-200 pt-2">
              <p className="text-xs font-semibold text-gray-500 mb-1">Weighted average formula</p>
              {tranches.filter(t => t.amount > 0 && t.cost > 0).map((t, i) => {
                const weight = totalCapital > 0 ? (t.amount / totalCapital) * 100 : 0
                const contribution = (weight / 100) * t.cost
                return (
                  <div key={i} className="flex items-center justify-between text-xs text-gray-600">
                    <span className="truncate max-w-[120px]" title={t.source}>{t.source}</span>
                    <span className="tabular-nums font-mono text-right ml-2 shrink-0">
                      {fmt(weight, 0)}% × {fmt(t.cost, 1)}% = <span className="font-semibold">{fmt(contribution, 2)}pp</span>
                    </span>
                  </div>
                )
              })}
            </div>
            <div className="mt-2 pt-2 border-t border-gray-200">
              <span className={`text-xs font-semibold ${
                blendedWacc <= 9 ? 'text-green-600' :
                blendedWacc <= 12 ? 'text-amber-600' :
                'text-red-600'
              }`}>
                {blendedWacc <= 9 ? 'Within bankable range' :
                 blendedWacc <= 12 ? 'Elevated — review structure' :
                 'High — refinancing required'}
              </span>
            </div>
          </div>

          {/* Gap Analysis Card */}
          <div className={`rounded-xl border p-4 shadow-sm ${
            gapPct > 20 ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'
          }`}>
            <div className="flex items-center gap-2 mb-2">
              {gapPct > 20 && <AlertTriangle className="w-4 h-4 text-red-500" />}
              <span className="text-xs font-black uppercase tracking-widest text-gray-600">Gap Analysis</span>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">Total Capex</span>
                <span className="font-semibold tabular-nums">€{fmt(totalCapex, 0)}M</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Committed / Mandate</span>
                <span className="font-semibold tabular-nums text-green-700">€{fmt(committedCapital, 0)}M</span>
              </div>
              <div className={`flex justify-between pt-1 border-t ${gapPct > 20 ? 'border-red-200' : 'border-gray-100'}`}>
                <span className={`font-semibold ${gapPct > 20 ? 'text-red-700' : 'text-gray-700'}`}>Unfunded gap</span>
                <span className={`font-black tabular-nums ${gapPct > 20 ? 'text-red-600' : 'text-gray-800'}`}>
                  €{fmt(unfunded, 0)}M ({fmt(gapPct, 0)}%)
                </span>
              </div>
            </div>
            {gapPct > 20 && (
              <p className="mt-2 text-xs text-red-600 font-semibold">
                Unfunded gap exceeds 20% of capex — additional capital sources required.
              </p>
            )}
            {gapPct === 0 && (
              <p className="mt-2 text-xs text-green-600 font-semibold">
                Fully funded by committed &amp; mandate tranches.
              </p>
            )}
          </div>

          {/* Commitment Pipeline — from live project data */}
          {project?.capital_status && project.capital_status.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className="text-xs font-black uppercase tracking-widest text-gray-600 mb-3">
                Commitment Pipeline
              </div>
              <div className="space-y-2.5">
                {project.capital_status.map((item, i) => (
                  <div key={i} className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-gray-700 truncate max-w-[110px]" title={item.name}>
                      {item.name}
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-xs tabular-nums text-gray-500">{item.amount}</span>
                      <CommitmentStatusBadge status={item.commitment_status} size="sm" showProgress />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── WACC SENSITIVITY TABLE ────────────────────────────────── */}
      <SectionCard title="WACC Sensitivity — Tranche Drop-Out Analysis">
        <button
          type="button"
          onClick={() => setSensitivityOpen(v => !v)}
          className="flex items-center gap-1.5 text-xs text-gray-500 mb-2 hover:text-gray-700 transition-colors"
        >
          {sensitivityOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          {sensitivityOpen ? 'Collapse' : 'Expand'} sensitivity table
        </button>
        {sensitivityOpen && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left py-1.5 pr-4 font-semibold text-gray-500 uppercase tracking-wide">Tranche dropped</th>
                  <th className="text-right py-1.5 pr-4 font-semibold text-gray-500 uppercase tracking-wide">Base WACC</th>
                  <th className="text-right py-1.5 pr-4 font-semibold text-gray-500 uppercase tracking-wide">New WACC</th>
                  <th className="text-right py-1.5 font-semibold text-gray-500 uppercase tracking-wide">Delta</th>
                </tr>
              </thead>
              <tbody>
                {sensitivity.map((row, i) => {
                  const deltaColor = row.delta >= 3 ? 'text-red-600 font-black' :
                    row.delta >= 1.5 ? 'text-amber-600 font-semibold' : 'text-gray-700'
                  return (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-2">
                          <TypePill type={row.tranche.type} />
                          <span className="text-gray-700 truncate max-w-[200px]" title={row.tranche.source}>
                            {row.tranche.source}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums text-gray-600">
                        {fmt(blendedWacc, 1)}%
                      </td>
                      <td className={`py-2 pr-4 text-right tabular-nums ${waccColor(row.newWacc)} font-semibold`}>
                        {fmt(row.newWacc, 1)}%
                      </td>
                      <td className={`py-2 text-right tabular-nums ${deltaColor}`}>
                        +{fmt(row.delta, 1)}pp
                      </td>
                    </tr>
                  )
                })}
                {sensitivity.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 text-center text-gray-400 italic">
                      No interest-bearing tranches to analyse.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* ── GREEN BOND COMPARISON (Change 2) ─────────────────────── */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <button
          type="button"
          onClick={() => setShowBondComparison(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Leaf className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-black uppercase tracking-widest text-gray-600">
              Compare with Optimal Bank / Green Bond Split
            </span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 text-xs font-semibold">Taghizadeh-Hesary 2022</span>
          </div>
          {showBondComparison ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </button>
        {showBondComparison && (
          <div className="p-4">
            <GreenBondComparison tranches={tranches} baseWacc={blendedWacc} />
          </div>
        )}
      </div>

      {/* close stack tab fragment */}
      </>}

      {/* ── CAPEX LAYERS TAB (Change 4) ────────────────────────────── */}
      {activeTab === 'capex_layers' && (
        <CapexLayersView totalCapex={totalCapex} projectName={project?.name ?? 'Project'} />
      )}

      {/* ── DE-RISKING TAB (Change 3) ──────────────────────────────── */}
      {activeTab === 'derisk' && (
        <DeRiskingView tranches={tranches} baseWacc={blendedWacc} baseDscr={approxBaseDscr} />
      )}

    </div>
  )
}
