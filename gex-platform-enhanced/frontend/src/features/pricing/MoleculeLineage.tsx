// Screen: Molecule lineage screen (/pricing-lineage)
/**
 * MoleculeLineage — Information Lineage for molecule pricing.
 * The "Bloomberg Terminal" view: shows WHY a molecule costs what it costs.
 *
 * Decomposes a forward price into:
 *   spot basis + convenience yield + mean reversion + seasonality
 *   + CAPEX floor + regulatory premium + financing spread
 *   + concessional absorption + grace period benefit - subsidies + insurance
 *
 * Each component is clickable, traceable, and auditable.
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, Layers, Shield, Award, Zap,
  AlertTriangle, RefreshCw, Info,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { useUserRole } from '@/contexts/UserRoleContext'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

interface PriceComponent {
  name: string
  slug: string
  value_eur_t: number
  pct_of_total: number
  source: string
  explanation: string
  correlation_id: string | null
}

interface FinancingContext {
  blended_wacc: number | null
  concessional_share: number | null
  catalytic_ratio: number | null
  dfi_providers: string[]
}

interface Decomposition {
  molecule: string
  tenor_months: number
  timestamp: string
  forward_price_eur_t: number
  spot_price_eur_t: number
  total_premium_eur_t: number
  components: PriceComponent[]
  financing: FinancingContext
  subsidies: Record<string, number>
  certifications: string[]
  insurance: { premium_eur_t: number; provider: string }
  lineage: {
    correlation_id: string
    gabillon_params_hash: string
    calibration_date: string
    n_observations: number
  }
  narrative: string
}

// ═══════════════════════════════════════════════════════════════
// NO SEED DATA (Ticket 1a, item 2)
// ═══════════════════════════════════════════════════════════════
// The full Gabillon decomposition (risk premium, basis, financing spread,
// margin, subsidies) is SENSITIVE model output and must NOT ship in the JS
// bundle. It is served only by the backend-protected /api/v1/pricing/decomposition
// endpoint (require_finance_entitlement → 403). When that endpoint is
// unavailable or denied, the component shows an empty "No lineage data" state —
// it does NOT fall back to a baked-in decomposition.

// ═══════════════════════════════════════════════════════════════
// STYLE HELPERS
// ═══════════════════════════════════════════════════════════════

const MOLECULE_META: Record<string, { label: string; unit: string; color: string }> = {
  H2: { label: 'e-Hydrogen', unit: '/t', color: 'sky' },
  NH3: { label: 'e-Ammonia', unit: '/t', color: 'violet' },
  E_METHANOL: { label: 'e-Methanol', unit: '/t', color: 'emerald' },
  SAF: { label: 'SAF', unit: '/t', color: 'amber' },
  E_NG: { label: 'e-Nat. Gas', unit: '/MWh', color: 'orange' },
  HVO: { label: 'HVO', unit: '/t', color: 'rose' },
}

// Project registry molecule names (customerProjects.ts) → engine enum keys.
// The engine also normalizes server-side, but the UI needs the canonical key
// for MOLECULE_META lookups and the <select> value.
const MOLECULE_ENUM: Record<string, string> = {
  'H2': 'H2',
  'NH3': 'NH3',
  'e-NH3': 'NH3',
  'e-Methanol': 'E_METHANOL',
  'SAF': 'SAF',
  'e-NG': 'E_NG',
  'e-Methane': 'E_NG',
  'HVO': 'HVO',
}

function toEngineEnum(molecule: string | undefined): string {
  if (!molecule) return 'H2'
  return MOLECULE_ENUM[molecule] ?? (MOLECULE_META[molecule] ? molecule : 'H2')
}

// Demo pricing context per molecule. Subsidies are €/kg — the engine converts
// ×1000 to €/t — so they must be scaled to each molecule's price level
// (45V ≈ $3/kg applies to HYDROGEN; derived molecules only inherit the
// embedded-H2 share per tonne of product). Production tonnage sizes the
// €/t insurance allocation realistically per plant scale.
const DEMO_CONTEXT: Record<string, { subsidies: Record<string, number>; production_tpa: number }> = {
  H2:         { subsidies: { '45V': 3.0, 'RED_III': 0.5 },  production_tpa: 18_250 },
  NH3:        { subsidies: { '45V': 0.5, 'RED_III': 0.06 }, production_tpa: 60_000 },
  E_METHANOL: { subsidies: { '45V': 0.55, 'RED_III': 0.05 }, production_tpa: 125_000 },
  SAF:        { subsidies: { 'RED_III': 0.25 },             production_tpa: 33_000 },
  E_NG:       { subsidies: { 'RED_III': 0.015 },            production_tpa: 80_000 },
  HVO:        { subsidies: { 'RED_III': 0.12 },             production_tpa: 250_000 },
}

// Sign-only tone — the single semantic colour a waterfall carries.
// Adds-to-cost (debit) vs reduces-cost (credit). Category is encoded by the
// row label + section grouping, NOT by background (Hidalgo: colour = sign).
function signTone(value: number): { band: string; bar: string } {
  if (value < 0) return { band: 'border-l-emerald-500', bar: 'bg-emerald-400/60' } // credit — reduces cost
  if (value > 0) return { band: 'border-l-red-400',     bar: 'bg-red-400/50'     } // debit — adds cost
  return { band: 'border-l-slate-300', bar: 'bg-slate-300' }
}

// Causal drill target — the screen where each cost driver is actually SET.
// Clicking traces the number to its origin instead of dead-ending on prose
// (Sung causal compression). Routes verified to exist in App.tsx.
const DRIVER_ROUTE: Record<string, { href: string; label: string }> = {
  spot_basis:              { href: '/pricing-curves',        label: 'Forward Curves (Gabillon)' },
  convenience_yield:       { href: '/pricing-curves',        label: 'Forward Curves (Gabillon)' },
  mean_reversion:          { href: '/pricing-curves',        label: 'Forward Curves (Gabillon)' },
  seasonality:             { href: '/pricing-curves',        label: 'Forward Curves (Gabillon)' },
  residual:                { href: '/pricing-curves',        label: 'Forward Curves (Gabillon)' },
  capex_floor:             { href: '/finance-plant-builder', label: 'Plant Builder (LCOH/LCOF)' },
  regulatory_premium:      { href: '/cert-readiness',        label: 'Cert Readiness (ETS / RFNBO)' },
  financing_spread:        { href: '/capital-stack',         label: 'Capital Stack (WACC)' },
  concessional_absorption: { href: '/capital-stack',         label: 'Capital Stack (DFI tranches)' },
  grace_period_benefit:    { href: '/capital-stack',         label: 'Capital Stack (grace terms)' },
  subsidy_45v:             { href: '/cert-readiness',        label: 'Cert Readiness (45V)' },
  subsidy_red_iii:         { href: '/cert-readiness',        label: 'Cert Readiness (RED III)' },
  insurance_premium:       { href: '/insurance',             label: 'Insurance Schedule' },
}

function driverRoute(slug: string): { href: string; label: string } | null {
  if (DRIVER_ROUTE[slug]) return DRIVER_ROUTE[slug]
  if (slug.startsWith('subsidy_')) return { href: '/cert-readiness', label: 'Cert Readiness' }
  return null
}

function componentIcon(slug: string) {
  if (slug.startsWith('subsidy_')) return <Award className="w-3.5 h-3.5" />
  if (slug === 'concessional_absorption' || slug === 'grace_period_benefit') return <Shield className="w-3.5 h-3.5" />
  if (slug === 'financing_spread') return <Layers className="w-3.5 h-3.5" />
  if (slug === 'regulatory_premium') return <Zap className="w-3.5 h-3.5" />
  if (slug === 'insurance_premium') return <AlertTriangle className="w-3.5 h-3.5" />
  return <TrendingUp className="w-3.5 h-3.5" />
}

function fmt(n: number, decimals = 0): string {
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

// ═══════════════════════════════════════════════════════════════
// WATERFALL BAR — single component in the visual waterfall
// ═══════════════════════════════════════════════════════════════

function WaterfallBar({ component, maxAbsValue }: { component: PriceComponent; maxAbsValue: number }) {
  const width = Math.min(Math.abs(component.value_eur_t) / maxAbsValue * 100, 100)
  const isNegative = component.value_eur_t < 0
  const isSpot = component.slug === 'spot_basis'

  if (isSpot) return null // Spot basis shown separately as the base

  const tone = signTone(component.value_eur_t)

  return (
    <div className={`flex items-center gap-2 py-1.5 px-2 border-l-2 border-y border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 text-xs hover:bg-slate-50 dark:hover:bg-slate-900 ${tone.band}`}>
      <div className="flex items-center gap-1.5 w-[180px] shrink-0 text-slate-700 dark:text-slate-300">
        <span className="text-slate-400">{componentIcon(component.slug)}</span>
        <span className="font-semibold truncate">{component.name}</span>
      </div>
      <div className="flex-1 relative h-4">
        <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300 dark:bg-slate-700" />
        <div
          className={`absolute top-0 h-full rounded-sm ${tone.bar}`}
          style={{
            width: `${width / 2}%`,
            ...(isNegative ? { right: '50%' } : { left: '50%' }),
          }}
        />
      </div>
      <div className="w-[90px] text-right font-mono tabular-nums shrink-0">
        <span className={isNegative ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-900 dark:text-slate-100'}>
          {isNegative ? '' : '+'}€{fmt(component.value_eur_t)}
        </span>
      </div>
      <div className="w-[50px] text-right font-mono tabular-nums text-slate-400 shrink-0">
        {component.pct_of_total > 0 ? '+' : ''}{component.pct_of_total.toFixed(1)}%
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// COMPONENT ROW — waterfall bar + causal drill-down (Sung trace)
// One row used by every section group, so the colour and drill
// behaviour can never drift between groups.
// ═══════════════════════════════════════════════════════════════

function ComponentRow({
  component,
  maxAbsValue,
  expanded,
  onToggle,
}: {
  component: PriceComponent
  maxAbsValue: number
  expanded: boolean
  onToggle: () => void
}) {
  const navigate = useNavigate()
  const drv = driverRoute(component.slug)

  return (
    <div>
      <div className="cursor-pointer" onClick={onToggle}>
        <WaterfallBar component={component} maxAbsValue={maxAbsValue} />
      </div>
      {expanded && (
        <div className="ml-[196px] pb-1.5 pl-2 border-l-2 border-slate-200 dark:border-slate-700 space-y-1">
          <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-snug">
            <span className="font-semibold text-slate-700 dark:text-slate-300">{component.source}</span> — {component.explanation}
          </p>
          <div className="flex items-center gap-3 font-mono text-[10px]">
            {drv ? (
              <button
                onClick={(e) => { e.stopPropagation(); navigate(drv.href) }}
                className="uppercase tracking-[0.06em] text-[var(--brand)] hover:underline"
                title={`Trace this driver to where it is set: ${drv.label}`}
              >
                → {drv.label}
              </button>
            ) : (
              <span className="italic text-slate-400">no driver screen</span>
            )}
            {component.correlation_id && (
              <span className="text-slate-400">lineage: {component.correlation_id}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// WHAT-IF PANEL — pass-through sensitivity (exact, no model needed)
// ═══════════════════════════════════════════════════════════════
//
// Honesty boundary (verified 2026-05-30): the Gabillon two-factor model and
// the WACC→financing waterfall do NOT exist in gex_pf_engine (Sprint-3 TODO),
// so those terms CANNOT be flexed without inventing acausal numbers.
//
// This panel flexes ONLY terms whose relationship to price is closed-form
// arithmetic, fully determined by numbers already on screen:
//   • subsidies (€/t)  → linear reduction of effective offtaker cost
//   • insurance (€/t)  → linear cost component inside the forward build
// Every other driver is held fixed and labelled with the reason.

function WhatIfPanel({ data, unit }: { data: Decomposition; unit: string }) {
  const subsidyKeys = Object.keys(data.subsidies)
  const [sub, setSub] = useState<Record<string, number>>(() => ({ ...data.subsidies }))
  const baseInsEurT = Math.round(data.insurance.premium_eur_t)
  const [insEurT, setInsEurT] = useState<number>(baseInsEurT)

  // Closed-form recomputation — no model, no engine, no approximation.
  const insDelta        = insEurT - baseInsEurT
  const scenarioForward = data.forward_price_eur_t + insDelta
  const baseSubTotal    = subsidyKeys.reduce((s, k) => s - data.subsidies[k], 0)
  const scenSubTotal    = subsidyKeys.reduce((s, k) => s - (sub[k] ?? 0), 0)
  const baseEffective   = data.forward_price_eur_t + baseSubTotal
  const scenEffective   = scenarioForward + scenSubTotal

  const dirty = insDelta !== 0 || subsidyKeys.some(k => sub[k] !== data.subsidies[k])
  const reset = () => { setSub({ ...data.subsidies }); setInsEurT(baseInsEurT) }

  // For the offtaker, a HIGHER effective cost is worse → red; lower → emerald.
  const effDelta = scenEffective - baseEffective
  const effColor = Math.abs(effDelta) < 0.5 ? 'text-slate-500'
    : effDelta > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-400'
  const fwdDelta = scenarioForward - data.forward_price_eur_t
  const fwdColor = Math.abs(fwdDelta) < 0.5 ? 'text-slate-500'
    : fwdDelta > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-700 dark:text-emerald-400'

  const Slider = ({ label, value, base, min, max, step, onChange }: {
    label: string; value: number; base: number; min: number; max: number; step: number; onChange: (v: number) => void
  }) => (
    <div className="grid grid-cols-[150px_minmax(0,1fr)_92px] items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-slate-500 dark:text-slate-400 truncate">{label}</span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-slate-700 dark:accent-slate-300"
      />
      <span className="text-right font-mono text-[11px] tabular-nums text-slate-900 dark:text-slate-100">
        €{fmt(value)}{unit}
        {value !== base && (
          <span className="ml-1 text-[9px] text-slate-400">(base €{fmt(base)})</span>
        )}
      </span>
    </div>
  )

  return (
    <div className="mt-3 border-l-2 border-l-slate-400 border-y border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-2 py-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">
          What-if · pass-through sensitivity
        </span>
        {dirty && (
          <button onClick={reset} className="font-mono text-[10px] uppercase tracking-[0.06em] text-slate-500 hover:text-slate-900 dark:hover:text-slate-100 hover:underline">
            reset
          </button>
        )}
      </div>

      <div className="px-2 py-2 space-y-1.5">
        {subsidyKeys.map(k => (
          <Slider
            key={k}
            label={`Subsidy ${k.replace('_', ' ')}`}
            value={sub[k] ?? 0}
            base={data.subsidies[k]}
            min={0}
            max={Math.max(Math.round(data.subsidies[k] * 2), 100)}
            step={50}
            onChange={v => setSub(prev => ({ ...prev, [k]: v }))}
          />
        ))}
        <Slider
          label="Insurance"
          value={insEurT}
          base={baseInsEurT}
          min={0}
          max={Math.max(baseInsEurT * 4, 100)}
          step={5}
          onChange={setInsEurT}
        />
      </div>

      {/* Scenario readout — base → scenario with signed delta */}
      <div className="border-t border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-900">
        <div className="grid grid-cols-[150px_minmax(0,1fr)_92px] items-center gap-2 px-2 py-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-slate-500">Forward {data.tenor_months}M</span>
          <span className="font-mono text-[10px] text-slate-400">€{fmt(data.forward_price_eur_t)} → €{fmt(scenarioForward)}</span>
          <span className={`text-right font-mono text-[11px] tabular-nums font-bold ${fwdColor}`}>
            {fwdDelta >= 0 ? '+' : ''}€{fmt(fwdDelta)}
          </span>
        </div>
        <div className="grid grid-cols-[150px_minmax(0,1fr)_92px] items-center gap-2 px-2 py-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-slate-500">Effective cost</span>
          <span className="font-mono text-[10px] text-slate-400">€{fmt(baseEffective)} → €{fmt(scenEffective)}</span>
          <span className={`text-right font-mono text-[11px] tabular-nums font-bold ${effColor}`}>
            {effDelta >= 0 ? '+' : ''}€{fmt(effDelta)}
          </span>
        </div>
      </div>

      {/* Honesty boundary note */}
      <div className="border-t border-slate-200 dark:border-slate-800 px-2 py-1">
        <p className="font-mono text-[9px] text-slate-500 dark:text-slate-400 leading-snug">
          Flexes linear pass-through terms only. Gabillon market dynamics and WACC-driven financing
          run through the pricing engine (Sprint 3) and are held fixed — not approximated.
        </p>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════

interface Props {
  molecule?: string
  compact?: boolean
}

export default function MoleculeLineage({ molecule: moleculeProp, compact }: Props) {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const { authSession } = useUserRole()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  const token = authSession?.token ?? null

  const [molecule, setMolecule] = useState(() => toEngineEnum(moleculeProp || project?.molecule))
  const [data, setData] = useState<Decomposition | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [showNarrative, setShowNarrative] = useState(false)

  // Keep molecule in sync when the selected project resolves after first render
  // (visibleProjects loads async — without this the screen stays on the H2 default).
  useEffect(() => {
    if (!moleculeProp && project?.molecule) setMolecule(toEngineEnum(project.molecule))
  }, [moleculeProp, project?.molecule])

  // Load decomposition
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        // Route through the PROTECTED platform proxy (same-origin) with project_id
        // so backend authorization (require_finance_entitlement) applies. The
        // direct :8001 engine call is bypassed — unauthorized callers get 403.
        // The bearer token is REQUIRED: ABAC middleware returns 401 without it.
        const pid = project?.id ?? ''
        const res = await fetch(`/api/v1/pricing/decomposition${pid ? `?project_id=${encodeURIComponent(pid)}` : ''}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            project_id: pid,
            molecule,
            tenor_months: 12,
            // Demo DFI financing structure (generic concessional + senior stack)
            tranches: [
              { name: 'EIB Concessional', tranche_type: 'concessional', amount: 80_000_000, rate: 0.041, tenor: 15, grace_period_years: 3, dfi_provider: 'EIB' },
              { name: 'KfW Climate Action', tranche_type: 'concessional', amount: 17_000_000, rate: 0.072, tenor: 10, grace_period_years: 2, dfi_provider: 'KFW' },
              { name: 'DZ Bank Senior', tranche_type: 'senior', amount: 65_000_000, rate: 0.052, tenor: 15 },
            ],
            equity_amount: 58_000_000,
            grants_amount: 22_000_000,
            // Molecule-scaled subsidy + production context (see DEMO_CONTEXT)
            subsidies: (DEMO_CONTEXT[molecule] ?? DEMO_CONTEXT.H2).subsidies,
            insurance_annual_eur: 1_000_000,
            insurance_provider: 'Allianz GCS',
            annual_production_tonnes: (DEMO_CONTEXT[molecule] ?? DEMO_CONTEXT.H2).production_tpa,
            certifications: ['RED_III', 'RFNBO', '45V'],
          }),
        })
        if (res.ok) {
          const json = await res.json()
          const d = json.decomposition as Decomposition
          // Sanity guard: Gabillon parameter explosion produces absurd forwards.
          // No real commodity forward exceeds 20× spot in a 12-month tenor.
          // If the engine returns garbage, fall back to seed data.
          if (d && d.spot_price_eur_t > 0 && Math.abs(d.forward_price_eur_t / d.spot_price_eur_t) > 20) {
            console.warn(
              `[MoleculeLineage] Gabillon parameter explosion: forward ${d.forward_price_eur_t} vs spot ${d.spot_price_eur_t} — falling back to seed data`
            )
          } else if (!cancelled && d) {
            setData(d)
            return
          }
        }
      } catch { /* engine not running */ }

      // NO seed fallback — sensitive decomposition must not be baked into the
      // bundle. On unavailable/denied, render the empty "No lineage data" state.
      if (!cancelled) setData(null)
    }

    load().finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [molecule, token, project?.id])

  const meta = MOLECULE_META[molecule] || MOLECULE_META.H2

  if (!data) {
    return (
      <div className="p-6 text-center text-gray-400 text-sm space-y-1">
        {loading ? (
          <RefreshCw className="w-5 h-5 animate-spin mx-auto" />
        ) : (
          <>
            <div className="font-semibold text-gray-500">No lineage data</div>
            <div className="text-xs max-w-md mx-auto">
              {!token
                ? 'Price decomposition is finance-restricted — sign in with a finance role to view it.'
                : 'The pricing engine (gex_pf_engine, port 8001) is unavailable or returned an invalid decomposition. Check that the engine is running.'}
            </div>
          </>
        )}
      </div>
    )
  }

  const nonSpotComponents = data.components.filter(c => c.slug !== 'spot_basis')
  const maxAbsValue = Math.max(...nonSpotComponents.map(c => Math.abs(c.value_eur_t)), 1)

  // Group components
  const marketComponents = nonSpotComponents.filter(c =>
    ['convenience_yield', 'mean_reversion', 'seasonality', 'residual'].includes(c.slug)
  )
  const costComponents = nonSpotComponents.filter(c =>
    ['capex_floor', 'regulatory_premium', 'financing_spread', 'insurance_premium'].includes(c.slug)
  )
  const dfiComponents = nonSpotComponents.filter(c =>
    ['concessional_absorption', 'grace_period_benefit'].includes(c.slug)
  )
  const subsidyComponents = nonSpotComponents.filter(c => c.slug.startsWith('subsidy_'))

  const effectiveOfftakerCost = data.forward_price_eur_t + data.components
    .filter(c => c.slug.startsWith('subsidy_'))
    .reduce((sum, c) => sum + c.value_eur_t, 0)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-gray-900 flex items-center gap-2">
            <Layers className="w-5 h-5 text-teal-600" />
            Information Lineage
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">Why this molecule costs what it costs</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
            value={molecule}
            onChange={e => setMolecule(e.target.value)}
          >
            {Object.entries(MOLECULE_META).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          {loading && <RefreshCw className="w-4 h-4 animate-spin text-gray-400" />}
        </div>
      </div>

      {/* Price Summary Strip */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-gray-900 rounded-lg p-3 text-white">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-bold">Forward 12M</div>
          <div className="text-2xl font-black tabular-nums mt-1">€{fmt(data.forward_price_eur_t)}<span className="text-sm text-gray-400">{meta.unit}</span></div>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider font-bold">Spot</div>
          <div className="text-2xl font-black tabular-nums text-gray-800 mt-1">€{fmt(data.spot_price_eur_t)}</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <div className="text-xs text-green-700 uppercase tracking-wider font-bold">Effective Offtaker Cost</div>
          <div className="text-2xl font-black tabular-nums text-green-800 mt-1">€{fmt(effectiveOfftakerCost)}</div>
          <div className="text-xs text-green-600 mt-0.5">After subsidies</div>
        </div>
        <div className="bg-teal-50 border border-teal-200 rounded-lg p-3">
          <div className="text-xs text-teal-700 uppercase tracking-wider font-bold">WACC Impact</div>
          <div className="text-2xl font-black tabular-nums text-teal-800 mt-1">
            {data.financing.blended_wacc != null ? `${(data.financing.blended_wacc * 100).toFixed(1)}%` : 'N/A'}
          </div>
          <div className="text-xs text-teal-600 mt-0.5">
            {data.financing.dfi_providers.length > 0 ? data.financing.dfi_providers.join(', ') : 'No DFI'}
          </div>
        </div>
      </div>

      {/* Waterfall Chart */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-black uppercase tracking-widest text-gray-600">Cost DNA Waterfall</h3>
          <button
            onClick={() => setShowNarrative(!showNarrative)}
            className="text-xs text-teal-600 hover:text-teal-800 font-semibold flex items-center gap-1"
          >
            <Info className="w-3 h-3" />
            {showNarrative ? 'Hide' : 'Show'} narrative
          </button>
        </div>

        {/* Spot base */}
        <div className="flex items-center gap-2 py-1.5 px-2 rounded border bg-gray-900 text-white text-xs mb-1">
          <div className="w-[180px] shrink-0 font-black">Spot Basis</div>
          <div className="flex-1" />
          <div className="w-[90px] text-right font-mono tabular-nums shrink-0 font-black">€{fmt(data.spot_price_eur_t)}</div>
          <div className="w-[50px] text-right font-mono tabular-nums text-gray-400 shrink-0">base</div>
        </div>

        {/* Market dynamics */}
        {marketComponents.length > 0 && (
          <div className="mt-1">
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold pl-2 mb-0.5">Market Dynamics</div>
            {marketComponents.map(c => (
              <ComponentRow
                key={c.slug}
                component={c}
                maxAbsValue={maxAbsValue}
                expanded={expanded === c.slug}
                onToggle={() => setExpanded(expanded === c.slug ? null : c.slug)}
              />
            ))}
          </div>
        )}

        {/* Cost structure */}
        {costComponents.length > 0 && (
          <div className="mt-1">
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold pl-2 mb-0.5">Cost Structure</div>
            {costComponents.map(c => (
              <ComponentRow
                key={c.slug}
                component={c}
                maxAbsValue={maxAbsValue}
                expanded={expanded === c.slug}
                onToggle={() => setExpanded(expanded === c.slug ? null : c.slug)}
              />
            ))}
          </div>
        )}

        {/* DFI / Concessional */}
        {dfiComponents.length > 0 && (
          <div className="mt-1">
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold pl-2 mb-0.5">DFI / Concessional Impact</div>
            {dfiComponents.map(c => (
              <ComponentRow
                key={c.slug}
                component={c}
                maxAbsValue={maxAbsValue}
                expanded={expanded === c.slug}
                onToggle={() => setExpanded(expanded === c.slug ? null : c.slug)}
              />
            ))}
          </div>
        )}

        {/* Subsidies */}
        {subsidyComponents.length > 0 && (
          <div className="mt-1">
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold pl-2 mb-0.5">Subsidy Reductions</div>
            {subsidyComponents.map(c => (
              <ComponentRow
                key={c.slug}
                component={c}
                maxAbsValue={maxAbsValue}
                expanded={expanded === c.slug}
                onToggle={() => setExpanded(expanded === c.slug ? null : c.slug)}
              />
            ))}
          </div>
        )}

        {/* Forward result */}
        <div className="flex items-center gap-2 py-1.5 px-2 rounded border-2 border-gray-900 bg-gray-50 text-xs mt-2">
          <div className="w-[180px] shrink-0 font-black text-gray-900">Forward Price 12M</div>
          <div className="flex-1" />
          <div className="w-[90px] text-right font-mono tabular-nums shrink-0 font-black text-gray-900 text-sm">€{fmt(data.forward_price_eur_t)}</div>
          <div className="w-[50px] text-right font-mono tabular-nums text-gray-500 shrink-0">total</div>
        </div>

        {/* What-if sensitivity (pass-through terms only — exact, no engine) */}
        <WhatIfPanel key={data.molecule} data={data} unit={meta.unit} />

        {/* Narrative */}
        {showNarrative && (
          <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
            <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">
              {data.narrative || `This ${data.molecule} forward (${data.tenor_months}M) is priced at €${fmt(data.forward_price_eur_t)}${meta.unit}`}
            </pre>
          </div>
        )}
      </div>

      {/* Financing + Certification Context Cards */}
      {!compact && (
        <div className="grid grid-cols-3 gap-3">
          {/* Financing card */}
          <div className="bg-white border border-gray-200 rounded-xl p-3">
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-2 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" /> Financing Structure
            </h4>
            <div className="space-y-1 text-xs">
              {data.financing.blended_wacc != null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Blended WACC</span>
                  <span className="font-semibold tabular-nums">{(data.financing.blended_wacc * 100).toFixed(1)}%</span>
                </div>
              )}
              {data.financing.concessional_share != null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Concessional share</span>
                  <span className="font-semibold tabular-nums text-teal-700">{(data.financing.concessional_share * 100).toFixed(0)}%</span>
                </div>
              )}
              {data.financing.catalytic_ratio != null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">Catalytic ratio</span>
                  <span className={`font-semibold tabular-nums ${data.financing.catalytic_ratio >= 5 ? 'text-green-600' : 'text-amber-600'}`}>
                    {data.financing.catalytic_ratio.toFixed(1)}:1
                  </span>
                </div>
              )}
              {data.financing.dfi_providers.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-500">DFI providers</span>
                  <span className="font-semibold">{data.financing.dfi_providers.join(', ')}</span>
                </div>
              )}
            </div>
          </div>

          {/* Subsidies card */}
          <div className="bg-white border border-gray-200 rounded-xl p-3">
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-2 flex items-center gap-1">
              <Award className="w-3.5 h-3.5" /> Active Subsidies
            </h4>
            <div className="space-y-1 text-xs">
              {Object.entries(data.subsidies).map(([name, value]) => (
                <div key={name} className="flex justify-between">
                  <span className="text-gray-500">{name}</span>
                  <span className="font-semibold tabular-nums text-green-700">-€{fmt(value)}{meta.unit}</span>
                </div>
              ))}
              {data.certifications.length > 0 && (
                <div className="pt-1 border-t border-gray-100 mt-1 flex flex-wrap gap-1">
                  {data.certifications.map(cert => (
                    <span key={cert} className="px-1.5 py-0.5 bg-green-50 text-green-700 rounded text-[10px] font-bold">{cert}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Insurance + Lineage card */}
          <div className="bg-white border border-gray-200 rounded-xl p-3">
            <h4 className="text-xs font-black uppercase tracking-widest text-gray-600 mb-2 flex items-center gap-1">
              <Shield className="w-3.5 h-3.5" /> Insurance & Lineage
            </h4>
            <div className="space-y-1 text-xs">
              {data.insurance.premium_eur_t > 0 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Premium</span>
                    <span className="font-semibold tabular-nums">€{fmt(data.insurance.premium_eur_t)}{meta.unit}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Provider</span>
                    <span className="font-semibold">{data.insurance.provider}</span>
                  </div>
                </>
              )}
              <div className="pt-1 border-t border-gray-100 mt-1">
                <div className="flex justify-between">
                  <span className="text-gray-500">Calibration</span>
                  <span className="font-semibold">{data.lineage.calibration_date}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Observations</span>
                  <span className="font-semibold tabular-nums">{data.lineage.n_observations || 'Seed'}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
