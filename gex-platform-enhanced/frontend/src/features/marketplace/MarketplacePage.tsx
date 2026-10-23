// Screen: Marketplace screen (/marketplace)
/**
 * Commercial Overview — Project-contextual, role-aware commercial dashboard
 *
 * Two-tab architecture (project finance rationale):
 *
 *   Tab 1 — PROJECT ECONOMICS
 *     Production Inputs + Sales & Offtake on one screen per project.
 *     These are two sides of the same operating cash flow waterfall:
 *       • Input costs → OPEX (variable) → drives break-even
 *       • Offtake contracts → Revenue line → drives DSCR
 *       • The margin between them = CFADS = bankability foundation
 *     A lender reads top-to-bottom: revenue, costs, margin, coverage.
 *
 *   Tab 2 — TRADING & PORTFOLIO
 *     Corporate/portfolio activity — molecules bought for resale, hedging,
 *     or portfolio management. Different legal entity (parent, not SPV),
 *     different financing (revolver, not project debt), different risk
 *     profile (mark-to-market, not contracted). Must NOT be commingled
 *     with project economics — it would distort DSCR and mislead lenders.
 *
 * Design rules:
 *   - ETFuels buying biogenic CO₂ → Production Input (it enters the reactor)
 *   - ETFuels buying e-methanol from a third party → Trading (not feedstock)
 *   - Behind-the-meter electricity → Production Input with evidence status
 *   - Purchased e-methanol for resale → Trading / Portfolio
 */

import { useEffect, useState, useMemo, type ReactNode } from 'react'
import {
  Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Line, ComposedChart,
} from 'recharts'
import { Package, DollarSign, AlertTriangle } from 'lucide-react'
import { type CustomerProject } from '@/data/customerProjects'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useQuery } from '@tanstack/react-query'
import {
  marketAPI, type InputLineRecord, type MarketContract, type MarketMatch, type ProjectEconomics,
  type SalesDetailRecord,
} from '@/api'

// ── Types ────────────────────────────────────────────────────────────────────

type Granularity = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'
type TableView = 'project_economics' | 'trading'

type ItemPurpose = 'PRODUCTION_INPUT' | 'TRADING_PROCUREMENT' | 'OFFTAKE_SALE' | 'CERTIFICATION_EVIDENCE'
type VerificationState = 'UNVERIFIED' | 'SUBMITTED' | 'CONFIRMED' | 'AUDITED'
type ContractStatus = 'CONTRACTED' | 'TERM_SHEET' | 'PLANNED' | 'SPOT' | 'INDICATIVE'
type CertRelevance = 'RFNBO' | '45V' | 'FUELEU' | 'CORSIA' | 'RED_III' | 'NONE'
type CapitalRelevance = 'BANKABILITY_CRITICAL' | 'COST_DRIVER' | 'EVIDENCE_ITEM' | 'COMMERCIAL_ONLY'

interface SalesDetail {
  region: string
  eSource: string
  greenEnergyPct: number
  certifier: string
  bePrice: number
  available: { start: string; end: string; volume_mtpd: number; basePrice: number; pct: number; status: string }
  tokenised: { start: string; end: string; volume_mtpd: number; price: number; pct: number; status: string }
  inMarket: { start: string; end: string; volume_mtpd: number; targetPrice: number; pct: number; status: 'open' | 'pending' | 'sold'; counterparty: string | null }[]
  verification: VerificationState
}

/** Production input line — physical or contractual input to a production process */
interface FeedstockLine {
  projectId: string
  project: string
  outputMolecule: string
  feedstock: string
  supplier: string
  ratio: number
  ratioUnit: 'MT/MT' | 'MWh/MT' | 'kL/MT'
  annualVolume_mt: number
  unitPrice: number
  priceUnit: 'EUR/MWh' | 'EUR/MT' | 'EUR/kL'
  /** LCOE × ratio (or unitPrice × ratio for non-electricity) */
  costPerMtOutput: number
  /** For electricity: LCOE/CF + firming. For others: same as unitPrice. */
  effectiveCostPerMtOutput: number
  /** Capacity factor (electricity only) — 0 means N/A */
  capacityFactor: number
  status: 'contracted' | 'planned' | 'spot'
  isUtility: boolean
  verification: VerificationState
}

export interface ProjectFeedstockSummary {
  projectId: string
  project: string
  molecule: string
  location: string
  capacity_mtpd: number
  /** Nameplate: capacity × 365. No operating-days assumption. */
  annualOutput_mt: number
  /** The registry's spot price for the molecule; null when none is recorded. */
  outputPrice: number | null
  outputPriceState: string | null
  /** Variable cost sum — LCOE-based */
  totalFeedstockCostPerMt: number
  /** Variable cost sum — effective (CF-adjusted + firming) */
  totalEffectiveCostPerMt: number
  /** outputPrice − totalEffectiveCostPerMt; null without a recorded price */
  grossMarginPerMt: number | null
  lines: FeedstockLine[]
  status: string
}

interface EnhancedChartPoint {
  period: string
  maxPotential: number
  sold: number
  pending: number
  open: number
  tokenised: number
}

// ── The records, from PostgreSQL (alembic 066) ──────────────────────────────
// Until 2026-10-23 spot prices, sales details, production inputs and their
// classification were constants in this file. They were moved, verbatim and
// marked UNVERIFIED (JML), by scripts/load_marketplace_unverified_20261023.py.

export const EMPTY_ECONOMICS: ProjectEconomics = {
  spot_prices: {}, sales_detail: {}, input_lines: {}, input_classification: {},
}

export function useProjectEconomics(): { econ: ProjectEconomics; error: Error | null } {
  const q = useQuery({ queryKey: ['market', 'project-economics'], queryFn: marketAPI.projectEconomics })
  return { econ: q.data ?? EMPTY_ECONOMICS, error: (q.error as Error | null) ?? null }
}

function asVerification(v: string | null | undefined): VerificationState {
  return (['UNVERIFIED', 'SUBMITTED', 'CONFIRMED', 'AUDITED'].includes(v ?? '') ? v : 'UNVERIFIED') as VerificationState
}

function toSalesDetail(r: SalesDetailRecord | undefined): SalesDetail | undefined {
  if (!r || !r.available || !r.tokenised) return undefined
  return {
    region: r.region ?? '—', eSource: r.e_source ?? '—', greenEnergyPct: r.green_energy_pct ?? 0,
    certifier: r.certifier ?? '—', bePrice: r.breakeven_price ?? 0,
    available: r.available, tokenised: r.tokenised, inMarket: r.in_market ?? [],
    verification: asVerification(r.verification_state),
  }
}

// ── Per-project production input specs ──────────────────────────────────────
// Renamed from PROJECT_FEEDSTOCK — these are production inputs, not "purchases"

interface FeedstockSpec {
  verification: VerificationState
  feedstock: string
  supplier: string
  ratio: number
  ratioUnit: 'MT/MT' | 'MWh/MT' | 'kL/MT'
  unitPrice: number           // LCOE or contract price (EUR/MWh or EUR/MT)
  priceUnit: 'EUR/MWh' | 'EUR/MT' | 'EUR/kL'
  status: 'contracted' | 'planned' | 'spot'
  isUtility: boolean
  /** For electricity: capacity factor (0–1). effectiveCost = unitPrice / CF + firmingCost */
  capacityFactor?: number
  /** Firming/storage adder (EUR/MWh) — battery, curtailment, backup */
  firmingCost?: number
}

/**
 * Production inputs (project_input_line in PostgreSQL) — unbundled.
 *
 * Design rules:
 *   1. On-site H₂ is an INTERMEDIATE, not a purchased input.
 *      Show the actual inputs: electricity + water → electrolyser (CAPEX).
 *      Do NOT list "Green Hydrogen at €5,xxx/t" AND electricity — that double-counts.
 *   2. Ratios are PRACTICAL (85–95% conversion), not theoretical stoichiometric minimums.
 *   3. Electricity shows LCOE + capacity factor + firming cost → effective cost.
 *   4. Electrolyser is CAPEX — not in this table.
 *   5. If H₂ is purchased from a THIRD PARTY (not on-site), it IS a production input.
 */

// ── Production Input enrichment ─────────────────────────────────────────────
// Maps feedstock names to certification & capital relevance

interface InputEnrichment {
  certRelevance: CertRelevance[]
  capitalRelevance: CapitalRelevance | null
  itemType: string
}


function getEnrichment(feedstock: string, econ: ProjectEconomics): InputEnrichment {
  const c = econ.input_classification[feedstock]
  // Unclassified is said plainly; no relevance is assumed for it.
  return c
    ? { certRelevance: c.cert_relevance as CertRelevance[], capitalRelevance: c.capital_relevance as CapitalRelevance,
        itemType: c.item_type }
    : { certRelevance: [], capitalRelevance: null, itemType: 'Unclassified' }
}

function toSpec(r: InputLineRecord): FeedstockSpec {
  return {
    verification: asVerification(r.verification_state), feedstock: r.feedstock, supplier: r.supplier ?? '—',
    ratio: r.ratio, ratioUnit: r.ratio_unit as FeedstockSpec['ratioUnit'], unitPrice: r.unit_price,
    priceUnit: r.price_unit as FeedstockSpec['priceUnit'], status: r.status, isUtility: r.is_utility,
    capacityFactor: r.capacity_factor ?? undefined, firmingCost: r.firming_cost ?? undefined,
  }
}

// ── Data builders ────────────────────────────────────────────────────────────

export function buildFeedstockSummary(p: CustomerProject, econ: ProjectEconomics): ProjectFeedstockSummary {
  const specs = (econ.input_lines[p.id] ?? []).map(toSpec)
  const annualOutput = Math.round(p.capacity_mtpd * 365)
  const spot = econ.spot_prices[p.molecule]
  const outputPrice = spot ? spot.value_base : null

  const lines: FeedstockLine[] = specs.map(s => {
    const annualVol = Math.round(annualOutput * s.ratio)
    const lcoeBasedCost = Math.round(s.ratio * s.unitPrice * 100) / 100

    // Effective cost: for electricity with CF data, adjust for capacity factor + firming
    let effectiveCost = lcoeBasedCost
    if (s.capacityFactor && s.capacityFactor > 0 && s.capacityFactor < 1) {
      const effectiveUnitPrice = s.unitPrice / s.capacityFactor + (s.firmingCost ?? 0)
      effectiveCost = Math.round(s.ratio * effectiveUnitPrice * 100) / 100
    }

    return {
      projectId: p.id,
      project: p.name,
      outputMolecule: p.molecule,
      feedstock: s.feedstock,
      supplier: s.supplier,
      ratio: s.ratio,
      ratioUnit: s.ratioUnit,
      annualVolume_mt: annualVol,
      unitPrice: s.unitPrice,
      priceUnit: s.priceUnit,
      costPerMtOutput: lcoeBasedCost,
      effectiveCostPerMtOutput: effectiveCost,
      capacityFactor: s.capacityFactor ?? 0,
      status: s.status,
      isUtility: s.isUtility,
      verification: s.verification,
    }
  })

  const totalFeedstockCostPerMt = lines.reduce((sum, l) => sum + l.costPerMtOutput, 0)
  const totalEffectiveCostPerMt = lines.reduce((sum, l) => sum + l.effectiveCostPerMtOutput, 0)

  return {
    projectId: p.id,
    project: p.name,
    molecule: p.molecule,
    location: p.location,
    capacity_mtpd: p.capacity_mtpd,
    annualOutput_mt: annualOutput,
    outputPrice,
    outputPriceState: spot ? spot.state : null,
    totalFeedstockCostPerMt: Math.round(totalFeedstockCostPerMt),
    totalEffectiveCostPerMt: Math.round(totalEffectiveCostPerMt),
    // No recorded inputs is not zero cost: without either side there is no margin.
    grossMarginPerMt: outputPrice === null || lines.length === 0 ? null : Math.round(outputPrice - totalEffectiveCostPerMt),
    lines,
    status: p.status,
  }
}

/**
 * Recorded volumes per period, nothing modelled: capacity × days, and the
 * sold / pending / open / tokenised volumes the sales record holds, held flat.
 * Until 2026-10-23 this generated ramps, seasonal sine waves, noise and a
 * "Gabillon forward" line from a formula — none of it was data.
 */
function generateEnhancedChartData(
  gran: Granularity,
  project: CustomerProject,
  detail: SalesDetail | undefined,
): EnhancedChartPoint[] {
  const counts: Record<Granularity, number> = { daily: 90, weekly: 52, monthly: 12, quarterly: 8, yearly: 5 }
  const days: Record<Granularity, number> = { daily: 1, weekly: 7, monthly: 30, quarterly: 91, yearly: 365 }
  const vol = (status: 'open' | 'pending' | 'sold') =>
    detail?.inMarket.filter(r => r.status === status).reduce((s, r) => s + r.volume_mtpd, 0) ?? 0
  const base = new Date()
  const pts: EnhancedChartPoint[] = []
  for (let i = 0; i < counts[gran]; i++) {
    const d = new Date(base)
    let label = ''
    switch (gran) {
      case 'daily':    d.setDate(d.getDate() + i); label = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }); break
      case 'weekly':   d.setDate(d.getDate() + i * 7); label = `W${i + 1}`; break
      case 'monthly':  d.setMonth(d.getMonth() + i); label = d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }); break
      case 'quarterly':d.setMonth(d.getMonth() + i * 3); label = `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`; break
      case 'yearly':   d.setFullYear(d.getFullYear() + i); label = String(d.getFullYear()); break
    }
    const n = days[gran]
    pts.push({
      period: label,
      maxPotential: Math.round(project.capacity_mtpd * n),
      sold: Math.round(vol('sold') * n),
      pending: Math.round(vol('pending') * n),
      open: Math.round(vol('open') * n),
      tokenised: Math.round((detail?.tokenised.volume_mtpd ?? 0) * n),
    })
  }
  return pts
}

// ── Badge components ────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border bg-gray-100 text-gray-600 border-gray-200">
      {status}
    </span>
  )
}

function MarketStatusBadge({ status }: { status: 'open' | 'pending' | 'sold' }) {
  const styles = {
    sold:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    pending: 'bg-amber-50 text-amber-700 border-amber-200',
    open:    'bg-gray-100 text-gray-600 border-gray-200',
  }
  return (
    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${styles[status]}`}>
      {status}
    </span>
  )
}

function VerifBadge({ state }: { state: VerificationState }) {
  const styles: Record<VerificationState, string> = {
    UNVERIFIED: 'bg-gray-100 text-gray-500 border-gray-300',
    SUBMITTED:  'bg-amber-50 text-amber-600 border-amber-300',
    CONFIRMED:  'bg-teal-50 text-teal-700 border-teal-300',
    AUDITED:    'bg-emerald-50 text-emerald-700 border-emerald-300',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[state]}`}>
      {state}
    </span>
  )
}

function ContractBadge({ status }: { status: ContractStatus }) {
  const styles: Record<ContractStatus, string> = {
    CONTRACTED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    TERM_SHEET: 'bg-blue-50 text-blue-700 border-blue-200',
    PLANNED:    'bg-amber-50 text-amber-600 border-amber-200',
    SPOT:       'bg-gray-100 text-gray-600 border-gray-200',
    INDICATIVE: 'bg-gray-50 text-gray-500 border-gray-200',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[status]}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function CertBadges({ certs }: { certs: CertRelevance[] }) {
  if (certs.length === 0 || (certs.length === 1 && certs[0] === 'NONE')) return <span className="text-[9px] text-gray-300">—</span>
  return (
    <div className="flex items-center gap-0.5 flex-wrap">
      {certs.filter(c => c !== 'NONE').map(c => (
        <span key={c} className="text-[8px] font-bold uppercase px-1 py-[1px] rounded bg-violet-50 text-violet-600 border border-violet-200">
          {c}
        </span>
      ))}
    </div>
  )
}

function CapitalBadge({ rel }: { rel: CapitalRelevance }) {
  const styles: Record<CapitalRelevance, string> = {
    BANKABILITY_CRITICAL: 'text-rose-600 bg-rose-50 border-rose-200',
    COST_DRIVER:          'text-amber-600 bg-amber-50 border-amber-200',
    EVIDENCE_ITEM:        'text-blue-600 bg-blue-50 border-blue-200',
    COMMERCIAL_ONLY:      'text-gray-500 bg-gray-50 border-gray-200',
  }
  const labels: Record<CapitalRelevance, string> = {
    BANKABILITY_CRITICAL: 'Bankability',
    COST_DRIVER:          'Cost driver',
    EVIDENCE_ITEM:        'Evidence',
    COMMERCIAL_ONLY:      'Commercial',
  }
  return (
    <span className={`text-[8px] font-bold uppercase px-1 py-[1px] rounded border ${styles[rel]}`}>
      {labels[rel]}
    </span>
  )
}

function PurposeBadge({ purpose }: { purpose: ItemPurpose }) {
  const styles: Record<ItemPurpose, string> = {
    PRODUCTION_INPUT:        'bg-teal-50 text-teal-700 border-teal-200',
    TRADING_PROCUREMENT:     'bg-orange-50 text-orange-700 border-orange-200',
    OFFTAKE_SALE:            'bg-blue-50 text-blue-700 border-blue-200',
    CERTIFICATION_EVIDENCE:  'bg-violet-50 text-violet-700 border-violet-200',
  }
  const labels: Record<ItemPurpose, string> = {
    PRODUCTION_INPUT:        'Production Input',
    TRADING_PROCUREMENT:     'Trading',
    OFFTAKE_SALE:            'Offtake',
    CERTIFICATION_EVIDENCE:  'Evidence',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[purpose]}`}>
      {labels[purpose]}
    </span>
  )
}

function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
      <div className="font-bold text-gray-900 mb-1.5">{label}</div>
      {payload.map((e: any) => (
        <div key={e.dataKey} className="flex items-center gap-2 py-0.5">
          <span className="w-2 h-2 rounded-full" style={{ background: e.color }} />
          <span className="text-gray-600">{e.name}:</span>
          <span className="font-mono font-bold text-gray-900">
            {`${Math.abs(e.value).toLocaleString()} MT`}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Offtake binding status badge ────────────────────────────────────────────

function BindingBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    BINDING:     'bg-emerald-50 text-emerald-700 border-emerald-200',
    TERM_SHEET:  'bg-blue-50 text-blue-700 border-blue-200',
    LOI:         'bg-amber-50 text-amber-600 border-amber-200',
    MOU:         'bg-amber-50 text-amber-600 border-amber-200',
    INDICATIVE:  'bg-gray-50 text-gray-500 border-gray-200',
  }
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border ${styles[status] ?? styles.INDICATIVE}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function RelatedPartyFlag({ isRelated }: { isRelated: boolean }) {
  if (!isRelated) return null
  return (
    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-rose-50 text-rose-600 border-rose-200 flex items-center gap-0.5">
      <AlertTriangle className="w-2.5 h-2.5" /> Related
    </span>
  )
}

// ── Project Economics card — flat Bloomberg-density layout ──────────────────
// Revenue (offtake) + Variable costs (inputs) → Margin. All flat, no toggles.

function ProjectEconomicsCard({
  project,
  summary,
  detail,
  econ,
}: {
  project: CustomerProject
  summary: ProjectFeedstockSummary
  detail: SalesDetail | undefined
  econ: ProjectEconomics
}) {
  const allLines = summary.lines
  const offtakes = project.offtakes ?? []
  const annualOutput = summary.annualOutput_mt

  // Offtake coverage
  const bindingOfftakes = offtakes.filter(o => o.binding_status === 'BINDING')
  const thirdPartyBinding = bindingOfftakes.filter(o => !o.is_related_party)
  const hasBindingThirdParty = thirdPartyBinding.length > 0
  const bindingVol = bindingOfftakes.reduce((s, o) => s + (o.volume_tpy ?? 0), 0)
  const coveragePct = annualOutput > 0 && bindingVol > 0 ? Math.round((bindingVol / annualOutput) * 100) : 0

  // Offtake price
  const inMarketVol = detail?.inMarket.reduce((s, r) => s + r.volume_mtpd, 0) ?? 0
  const avgOfftakePrice = detail && inMarketVol > 0
    ? Math.round(detail.inMarket.reduce((s, r) => s + r.targetPrice * r.volume_mtpd, 0) / inMarketVol)
    : summary.outputPrice
  const costRecorded = summary.lines.length > 0
  const cost = costRecorded ? summary.totalEffectiveCostPerMt.toLocaleString() : '—'
  const margin = avgOfftakePrice === null || !costRecorded ? null : avgOfftakePrice - summary.totalEffectiveCostPerMt
  // Any figure on this card that comes from an unconfirmed record says so.
  const unverified = detail?.verification === 'UNVERIFIED' || summary.outputPriceState === 'proposed'
    || summary.lines.some(l => l.verification === 'UNVERIFIED')

  return (
    <div className="border-b border-gray-200 last:border-0">
      {/* ── Project header: identity + economics on one line ── */}
      <div className="px-5 py-2 bg-gray-50/60 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-bold text-gray-900 whitespace-nowrap">{project.name}</span>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-200 text-gray-600">{project.molecule}</span>
          <span className="text-[10px] text-gray-500">{project.location}</span>
          <StatusBadge status={project.status} />
          {unverified && <VerifBadge state="UNVERIFIED" />}
        </div>
        <div className="flex items-center gap-4 text-xs font-mono whitespace-nowrap">
          <span className="text-gray-400">{annualOutput.toLocaleString()} <span className="text-[9px]">MT/yr nameplate</span></span>
          <span className="text-gray-400">Offtake <span className="font-bold text-emerald-700">{avgOfftakePrice === null ? '—' : avgOfftakePrice.toLocaleString()}</span></span>
          <span className="text-gray-400">Cost <span className="text-gray-700">{cost}</span></span>
          <span className={`font-bold ${margin === null ? 'text-gray-400' : margin > 0 ? 'text-emerald-600' : 'text-red-600'}`}>
            Margin {margin === null ? '—' : `${margin > 0 ? '+' : ''}${margin.toLocaleString()}`}
          </span>
          <span className="text-gray-400">B/E <span className="text-gray-600">{cost}</span></span>
          {offtakes.length > 0 && (
            <span className={coveragePct >= 50 ? 'text-emerald-600' : coveragePct > 0 ? 'text-amber-600' : 'text-rose-500'}>
              Bdg {coveragePct}%
            </span>
          )}
          {!hasBindingThirdParty && offtakes.length > 0 && (
            <span className="text-rose-500 text-[9px] font-bold">NO 3RD-PTY</span>
          )}
        </div>
      </div>

      {/* ── Revenue: offtake contracts ── */}
      <div className="px-5 py-1 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider border-t border-gray-100">
        <div className="w-[20%] pl-2">Revenue — Counterparty</div>
        <div className="w-[11%]">Binding</div>
        <div className="w-[6%]">Rel.</div>
        <div className="w-[12%] text-right">Volume</div>
        <div className="w-[8%] text-right">Term</div>
        <div className="w-[10%] text-right">Price</div>
        <div className="w-[8%]">Delivery</div>
        <div className="w-[7%] text-center">Verif.</div>
        <div className="w-[18%] text-right">
          {detail && (
            <span className="normal-case tracking-normal font-mono text-gray-400">
              {detail.region} · {detail.eSource} · {detail.greenEnergyPct}% green
            </span>
          )}
        </div>
      </div>

      {offtakes.length === 0 ? (
        <div className="px-5 py-2 pl-7 text-xs text-rose-400 border-t border-gray-50">
          No offtake on file — DK_G4 ACTIVE
        </div>
      ) : (
        offtakes.map((o, i) => (
          <div key={i} className="px-5 py-1 flex items-center text-xs border-t border-gray-50">
            <div className="w-[20%] pl-2 text-gray-900 font-medium truncate">{o.party}</div>
            <div className="w-[11%]"><BindingBadge status={o.binding_status} /></div>
            <div className="w-[6%]">{o.is_related_party ? <RelatedPartyFlag isRelated /> : null}</div>
            <div className="w-[12%] text-right font-mono text-gray-700">
              {o.volume_tpy ? `${o.volume_tpy.toLocaleString()} t/yr` : <span className="text-gray-400">undisclosed</span>}
            </div>
            <div className="w-[8%] text-right font-mono text-gray-500">{o.term_years ? `${o.term_years}yr` : '—'}</div>
            <div className="w-[10%] text-right text-[10px] text-gray-500">{o.price_type ?? '—'}</div>
            <div className="w-[8%] font-mono text-[10px] text-gray-500">{o.delivery_start?.slice(0, 7) ?? '—'}</div>
            <div className="w-[7%] text-center"><VerifBadge state={o.verification as VerificationState} /></div>
            <div className="w-[18%]" />
          </div>
        ))
      )}

      {/* Market allocation inline (if detail exists) — one compact line */}
      {detail && (
        <div className="px-5 py-1 pl-7 flex items-center gap-4 text-[10px] text-gray-400 border-t border-gray-50">
          {detail.inMarket.map((row, i) => (
            <span key={i} className="flex items-center gap-1">
              <MarketStatusBadge status={row.status} />
              <span className="font-mono">{row.volume_mtpd}</span>
              <span>@ {row.targetPrice.toLocaleString()}</span>
              {row.counterparty && <span className="text-gray-500">→ {row.counterparty}</span>}
            </span>
          ))}
          <span className="ml-auto">Tok: {detail.tokenised.pct}%</span>
        </div>
      )}

      {/* ── Variable costs: production inputs — all flat, no toggle ── */}
      <div className="px-5 py-1 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider border-t border-gray-100">
        <div className="w-[7%] pl-2">Costs — Type</div>
        <div className="w-[14%]">Input</div>
        <div className="w-[16%]">Supplier</div>
        <div className="w-[9%] text-right">Ratio</div>
        <div className="w-[8%] text-right">Volume/yr</div>
        <div className="w-[8%] text-right">Unit &#8364;</div>
        <div className="w-[8%] text-right">Eff. &#8364;/MT</div>
        <div className="w-[4%] text-center">CF</div>
        <div className="w-[6%] text-center">Ctr.</div>
        <div className="w-[5%] text-center">Vrf.</div>
        <div className="w-[7%] text-center">Cert</div>
        <div className="w-[8%] text-center">Capital</div>
      </div>

      {allLines.map((line, i) => {
        const enrich = getEnrichment(line.feedstock, econ)
        const contractStatus: ContractStatus = line.status === 'contracted' ? 'CONTRACTED' : line.status === 'spot' ? 'SPOT' : 'PLANNED'
        // The record's own state — a "contracted" line is not thereby verified.
        const verifState: VerificationState = line.verification
        return (
          <div key={i} className={`px-5 py-1 flex items-center text-xs border-t border-gray-50 ${line.isUtility ? 'text-gray-400' : ''}`}>
            <div className="w-[7%] pl-2 text-[10px] text-gray-500">{enrich.itemType}</div>
            <div className={`w-[14%] ${line.isUtility ? '' : 'text-gray-900 font-medium'}`}>{line.feedstock}</div>
            <div className="w-[16%] text-[11px] truncate">{line.supplier}</div>
            <div className="w-[9%] text-right font-mono">{line.ratio} <span className="text-[9px]">{line.ratioUnit}</span></div>
            <div className="w-[8%] text-right font-mono">{line.annualVolume_mt.toLocaleString()}</div>
            <div className="w-[8%] text-right font-mono">{line.unitPrice} <span className="text-[9px]">{line.priceUnit.replace('EUR/', '€/')}</span></div>
            <div className={`w-[8%] text-right font-mono ${line.isUtility ? '' : 'font-bold text-gray-700'}`}>{line.effectiveCostPerMtOutput.toLocaleString()}</div>
            <div className="w-[4%] text-center font-mono text-[10px]">{line.capacityFactor > 0 ? `${Math.round(line.capacityFactor * 100)}%` : ''}</div>
            <div className="w-[6%] text-center"><ContractBadge status={contractStatus} /></div>
            <div className="w-[5%] text-center"><VerifBadge state={verifState} /></div>
            <div className="w-[7%] text-center"><CertBadges certs={enrich.certRelevance} /></div>
            <div className="w-[8%] text-center">{enrich.capitalRelevance ? <CapitalBadge rel={enrich.capitalRelevance} /> : <span className="text-[10px] text-gray-400">—</span>}</div>
          </div>
        )
      })}
    </div>
  )
}

// ── Project Economics panel ─────────────────────────────────────────────────

function ProjectEconomicsPanel({
  projects,
  feedstockSummaries,
  econ,
}: {
  projects: CustomerProject[]
  feedstockSummaries: ProjectFeedstockSummary[]
  econ: ProjectEconomics
}) {
  const summaryMap = useMemo(() => {
    const m = new Map<string, ProjectFeedstockSummary>()
    feedstockSummaries.forEach(s => m.set(s.projectId, s))
    return m
  }, [feedstockSummaries])

  if (projects.length === 0) {
    return <div className="px-5 py-8 text-center text-sm text-gray-400">No projects match the current filter</div>
  }

  return (
    <div>
      {projects.map(p => {
        const summary = summaryMap.get(p.id)
        if (!summary) return null
        return (
          <ProjectEconomicsCard
            key={p.id}
            project={p}
            summary={summary}
            detail={toSalesDetail(econ.sales_detail[p.id])}
            econ={econ}
          />
        )
      })}
    </div>
  )
}

// ── Legacy exports for backward compat (OfftakerSupplyTable) ───────────────

export function ProductionInputsPanel({
  feedstockSummaries,
  emptyMessage = 'No production inputs match the current filter',
}: {
  feedstockSummaries: ProjectFeedstockSummary[]
  emptyMessage?: string
  renderProjectAction?: (summary: ProjectFeedstockSummary) => ReactNode
}) {
  // Legacy: renders just the input lines without offtake context
  return (
    <div>
      {feedstockSummaries.length === 0 && (
        <div className="px-5 py-8 text-center text-sm text-gray-400">{emptyMessage}</div>
      )}
      {feedstockSummaries.map(summary => (
        <div key={summary.projectId} className="border-b border-gray-100 last:border-0 px-5 py-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-gray-900">{summary.project}</span>
            <span className="text-xs font-bold px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">{summary.molecule}</span>
            <span className="text-xs text-gray-500">{summary.location}</span>
            <span className="ml-auto text-xs font-mono text-gray-500">Eff. cost: {summary.totalEffectiveCostPerMt.toLocaleString()} EUR/MT</span>
          </div>
          {summary.lines.map((line, i) => (
            <div key={i} className="flex items-center gap-3 text-xs py-0.5">
              <span className="text-gray-900 w-40">{line.feedstock}</span>
              <span className="text-gray-500 w-48 truncate">{line.supplier}</span>
              <span className="font-mono text-gray-500 w-24 text-right">{line.ratio} {line.ratioUnit}</span>
              <span className="font-mono font-bold text-gray-700 w-20 text-right">{line.effectiveCostPerMtOutput.toLocaleString()} €/MT</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function FeedstockPurchasesPanel(props: {
  feedstockSummaries: ProjectFeedstockSummary[]
  emptyMessage?: string
  renderProjectAction?: (summary: ProjectFeedstockSummary) => ReactNode
}) {
  return <ProductionInputsPanel {...props} />
}

// ── Trading Procurement panel ───────────────────────────────────────────────

function TradingProcurementPanel() {
  // The company's own buying on the market: contracts from matches where it is
  // the BUYER. Until 2026-10-23 this panel showed three invented ETFuels
  // positions (gap register G-04).
  const [contracts, setContracts] = useState<MarketContract[]>([])
  const [matches, setMatches] = useState<MarketMatch[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([marketAPI.myContracts(), marketAPI.myMatches()])
      .then(([c, m]) => { setContracts(c.contracts); setMatches(m.matches) })
      .catch(e => setError((e as Error).message))
  }, [])

  const bySide = new Map(matches.map(m => [m.id, m]))
  const positions = contracts
    .filter(c => bySide.get(c.match_id)?.side === 'buyer')
    .map(c => ({
      id: c.id,
      molecule: c.molecule,
      counterparty: bySide.get(c.match_id)?.seller_company_name ?? '—',
      annualVolume_mt: Math.round(c.volume_mtpd * 365),
      unitPrice: Math.round(c.price_eur_kg * 1000),
      contractStatus: (c.status === 'active' ? 'CONTRACTED' : 'TERM_SHEET') as ContractStatus,
      project: c.correlation_id ?? '—',
      notes: [c.start_date, c.end_date].filter(Boolean).join(' → ') || c.status,
    }))
  if (error) {
    return <div role="alert" className="px-5 py-8 text-center text-sm text-red-700">{error}</div>
  }
  if (positions.length === 0) {
    return <div className="px-5 py-8 text-center text-sm text-gray-400">No molecules bought on the market yet</div>
  }

  return (
    <div>
      {/* Header */}
      <div className="px-5 py-2 flex items-center text-[10px] font-bold text-gray-400 uppercase tracking-wider bg-gray-50 border-b border-gray-100">
        <div className="w-[7%] pl-4">Purpose</div>
        <div className="w-[10%]">Molecule</div>
        <div className="w-[16%]">Counterparty</div>
        <div className="w-[10%] text-right">Volume/yr</div>
        <div className="w-[9%] text-right">Unit Price</div>
        <div className="w-[8%] text-center">Contract</div>
        <div className="w-[8%] text-center" />
        <div className="w-[12%]">Trail</div>
        <div className="w-[20%]">Delivery</div>
      </div>
      {positions.map(item => (
        <div key={item.id} className="px-5 py-2 flex items-center text-xs border-t border-gray-50">
          <div className="w-[7%] pl-4"><PurposeBadge purpose="TRADING_PROCUREMENT" /></div>
          <div className="w-[10%]">
            <span className="font-bold px-2 py-0.5 rounded bg-orange-50 text-orange-700 border border-orange-200 text-[10px]">
              {item.molecule}
            </span>
          </div>
          <div className="w-[16%] text-gray-900 font-medium truncate">{item.counterparty}</div>
          <div className="w-[10%] text-right font-mono text-gray-900 font-bold">{item.annualVolume_mt.toLocaleString()} MT</div>
          <div className="w-[9%] text-right font-mono text-gray-700">{item.unitPrice.toLocaleString()} EUR/t</div>
          <div className="w-[8%] text-center"><ContractBadge status={item.contractStatus} /></div>
          <div className="w-[8%]" />
          <div className="w-[12%] text-[10px] font-mono text-gray-400 truncate">{item.project}</div>
          <div className="w-[20%] text-[10px] text-gray-500 truncate">{item.notes}</div>
        </div>
      ))}

      {/* Classification notice */}
      <div className="px-5 py-2 bg-orange-50/50 border-t border-orange-100">
        <div className="text-[10px] text-orange-600 font-mono">
          These molecules are bought for resale, hedging, or portfolio management — not production inputs.
          They do not enter any project reactor or production pathway.
        </div>
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────

export function MarketplacePage() {
  const [tableView, setTableView] = useState<TableView>('project_economics')
  const [gran, setGran] = useState<Granularity>('monthly')
  const [filterMol, setFilterMol] = useState('all')
  const [filterProj, setFilterProj] = useState('all')

  const { projects } = useVisibleProjects()
  const { econ, error: econError } = useProjectEconomics()
  const molecules = [...new Set(projects.map(p => p.molecule))]

  const filteredProjects = useMemo(() => {
    return projects.filter(p => {
      if (filterMol !== 'all' && p.molecule !== filterMol) return false
      if (filterProj !== 'all' && p.id !== filterProj) return false
      return true
    })
  }, [projects, filterMol, filterProj])

  const chartProject = useMemo(() => {
    if (filterProj !== 'all') return projects.find(p => p.id === filterProj) ?? projects[0]
    if (filterMol !== 'all') return projects.find(p => p.molecule === filterMol) ?? projects[0]
    return projects[0]
  }, [filterProj, filterMol, projects])

  const chartDetail = chartProject ? toSalesDetail(econ.sales_detail[chartProject.id]) : undefined

  const chartData = useMemo(
    () => (chartProject ? generateEnhancedChartData(gran, chartProject, chartDetail) : []),
    [gran, chartProject, chartDetail],
  )

  const feedstockSummaries = useMemo(() => {
    const subset = filterProj !== 'all' ? projects.filter(p => p.id === filterProj)
      : filterMol !== 'all' ? projects.filter(p => p.molecule === filterMol) : projects
    return subset.map(p => buildFeedstockSummary(p, econ))
  }, [projects, filterProj, filterMol, econ])

  // KPIs
  const totalSalesVol = filteredProjects.reduce((s, p) => s + Math.round(p.capacity_mtpd * 365), 0)
  const totalInputLines = feedstockSummaries.reduce((s, fs) => s + fs.lines.length, 0)
  const bankabilityCriticalCount = feedstockSummaries.reduce((s, fs) =>
    s + fs.lines.filter(l => {
      const e = getEnrichment(l.feedstock, econ)
      return e.capitalRelevance === 'BANKABILITY_CRITICAL'
    }).length, 0)
  const margins = feedstockSummaries.map(fs => fs.grossMarginPerMt).filter((m): m is number => m !== null)
  const avgGrossMargin = margins.length > 0 ? Math.round(margins.reduce((s, m) => s + m, 0) / margins.length) : null
  const anyUnverified = Object.values(econ.sales_detail).some(r => r.verification_state === 'UNVERIFIED')
    || Object.values(econ.spot_prices).some(r => r.state !== 'approved')
    || Object.values(econ.input_lines).flat().some(r => r.verification_state === 'UNVERIFIED')

  const grans: { v: Granularity; l: string }[] = [
    { v: 'daily', l: 'D' }, { v: 'weekly', l: 'W' }, { v: 'monthly', l: 'M' }, { v: 'quarterly', l: 'Q' }, { v: 'yearly', l: 'Y' },
  ]

  return (
    <div className="max-w-[1440px] mx-auto space-y-6">
      {/* Header + Filters */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-black text-gray-900">Commercial</h1>
        </div>
        <div className="flex items-center gap-2">
          <select value={filterMol} onChange={e => { setFilterMol(e.target.value); setFilterProj('all') }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
            <option value="all">All Molecules</option>
            {molecules.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <select value={filterProj} onChange={e => setFilterProj(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white">
            <option value="all">All Projects</option>
            {(filterMol !== 'all' ? projects.filter(p => p.molecule === filterMol) : projects)
              .map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>

      {econError && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{econError.message}</div>
      )}
      {anyUnverified && (
        <div role="note" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          Figures marked <strong>UNVERIFIED</strong> — spot prices, sales details and production inputs — were moved
          from this screen's code into PostgreSQL on 23 Oct 2026. Their source is not recorded; do not rely on
          them until each is confirmed. A figure that is not recorded shows as —.
        </div>
      )}

      {/* KPI Strip — 3 bankability signals */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Output</span>
            <span className="text-[10px] text-gray-400">{filteredProjects.length} project{filteredProjects.length !== 1 ? 's' : ''}</span>
          </div>
          <span className="text-xl font-black text-gray-900 font-mono">{totalSalesVol.toLocaleString()}</span>
          <span className="text-[10px] text-gray-400 ml-1">MT/yr</span>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Avg Margin</span>
            <span className="text-[10px] text-gray-400">{totalInputLines} inputs · {bankabilityCriticalCount} critical</span>
          </div>
          <span className={`text-xl font-black font-mono ${avgGrossMargin === null || avgGrossMargin >= 0 ? 'text-gray-900' : 'text-red-600'}`}>
            {avgGrossMargin === null ? '—' : `${avgGrossMargin >= 0 ? '+' : ''}${avgGrossMargin.toLocaleString()}`}
          </span>
          <span className="text-[10px] text-gray-400 ml-1">EUR/MT</span>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 px-4 py-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Offtake Coverage</span>
            <span className="text-[10px] text-gray-400">{feedstockSummaries.reduce((s, fs) => s + (projects.find(p => p.id === fs.projectId)?.offtakes?.length ?? 0), 0)} contracts</span>
          </div>
          <span className="text-xl font-black text-gray-900 font-mono">
            {feedstockSummaries.length > 0
              ? Math.round(feedstockSummaries.reduce((s, fs) => {
                  const p = projects.find(pp => pp.id === fs.projectId)
                  const binding = (p?.offtakes ?? []).filter(o => o.binding_status === 'BINDING')
                  const bv = binding.reduce((a, o) => a + (o.volume_tpy ?? 0), 0)
                  return s + (fs.annualOutput_mt > 0 && bv > 0 ? (bv / fs.annualOutput_mt) * 100 : 0)
                }, 0) / feedstockSummaries.length)
              : 0}%
          </span>
          <span className="text-[10px] text-gray-400 ml-1">binding avg</span>
        </div>
      </div>

      {/* ─── Table: 2 tabs — Project Economics vs Trading ─────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-1">
          <button onClick={() => setTableView('project_economics')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-colors ${tableView === 'project_economics' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
            <DollarSign className="w-3 h-3" /> Project Economics
          </button>
          <button onClick={() => setTableView('trading')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-colors ${tableView === 'trading' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
            <Package className="w-3 h-3" /> Trading & Portfolio
          </button>
        </div>

        {tableView === 'project_economics' && (
          <ProjectEconomicsPanel
            projects={filteredProjects}
            feedstockSummaries={feedstockSummaries}
            econ={econ}
          />
        )}

        {tableView === 'trading' && (
          <TradingProcurementPanel />
        )}
      </div>

      {/* ─── Charts ───────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-gray-900 mr-2">{chartProject.name} — {chartProject.molecule}</h2>
          </div>
          <div className="flex items-center gap-1">
            {grans.map(g => (
              <button key={g.v} onClick={() => setGran(g.v)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${gran === g.v ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                {g.l}
              </button>
            ))}
          </div>
        </div>

        {(
          <div className="px-5 pt-5 pb-2">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Production Segments (MT) — recorded volumes; no forward curve on this chart</span>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="period" tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={{ stroke: '#e5e7eb' }} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} axisLine={false} tickLine={false} width={50} tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)} />
                <Tooltip content={<Tip />} />
                <Bar dataKey="sold" name="Sold" stackId="output" fill="#047857" radius={[0, 0, 0, 0]} maxBarSize={36} />
                <Bar dataKey="pending" name="Pending" stackId="output" fill="#10b981" radius={[0, 0, 0, 0]} maxBarSize={36} />
                <Bar dataKey="open" name="Open" stackId="output" fill="#6ee7b7" radius={[3, 3, 0, 0]} maxBarSize={36} />
                <Line dataKey="maxPotential" name="Max Potential" type="monotone" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="6 3" dot={false} />
                <Line dataKey="tokenised" name="Tokenised" type="monotone" stroke="#0ea5a0" strokeWidth={2} dot={{ r: 2.5, fill: '#0ea5a0' }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="px-5 pb-4 flex items-center gap-5 text-xs text-gray-500 flex-wrap">
          {(
            <>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#047857' }} /> Sold</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#10b981' }} /> Pending</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: '#6ee7b7' }} /> Open</span>
              <span className="flex items-center gap-1.5"><span className="w-6 h-0 border-t-[1.5px] border-dashed" style={{ borderColor: '#94a3b8' }} /> Max Potential</span>
              <span className="flex items-center gap-1.5"><span className="w-6 h-0 border-t-2" style={{ borderColor: '#0ea5a0' }} /> Tokenised</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
