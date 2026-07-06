// Screen: Instrument compatibility screen (/instrument-compatibility)
/**
 * InstrumentCompatibility — Dynamic eligibility panel.
 * Shows which instruments are compatible with the current project state,
 * and WHY ineligible ones can't participate yet.
 *
 * The "where most platforms fail" view from Hidalgo's crystallization model.
 */

import { useState, useEffect } from 'react'
import {
  CheckCircle, XCircle, Shield, Layers, TrendingUp,
  AlertTriangle, ChevronDown, ChevronUp, RefreshCw, Leaf,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'

// ── Types ──

interface EsgMetric {
  kpi_name: string
  target_value: number
  target_unit: string
  penalty_bps: number
  verification_agent: string
}

interface DealKillerSummary {
  id: string
  gate: string
  severity: string
  plain_language: string
  resolution_action: string
  resolution_page: string
}

interface Instrument {
  id: string
  name: string
  type: string
  provider: string
  rate_reduction_bps: number
  coverage: number
  status: 'ELIGIBLE' | 'INELIGIBLE'
  reasons?: string[]
  proceeds_type: string
  bond_framework: string
  required_audit_nodes: string[]
  esg_metrics: EsgMetric[]
  blocked_by_killers?: DealKillerSummary[]
  remedy_eur_t?: number
}

interface InstrumentFamily {
  eligible: Instrument[]
  ineligible: Instrument[]
}

interface CompatibilityData {
  project_id: string
  project_state: string
  jurisdiction: string
  molecule: string
  total_instruments: number
  eligible_count: number
  ineligible_count: number
  families: Record<string, InstrumentFamily>
  active_killers?: DealKillerSummary[]
  committee_readiness?: string
  price_context?: {
    forward_price_eur_t: number
    financing_spread_eur_t: number
    molecule: string
  }
}

// ── Seed fallback data ──

const SEED_COMPATIBILITY: CompatibilityData = {
  project_id: 'proj_bremen_h2',
  project_state: 'BUILDABLE',
  jurisdiction: 'DE',
  molecule: 'H2',
  total_instruments: 25,
  eligible_count: 14,
  ineligible_count: 11,
  active_killers: [
    { id: 'DK_G5_NO_EPC', gate: 'G5', severity: 'FATAL', plain_language: 'No EPC or EPCM contract has been executed — construction cannot proceed without a signed engineering, procurement, and construction agreement.', resolution_action: 'Execute an EPC, EPCM, or hybrid EPC contract with an approved contractor.', resolution_page: '/finance/stage-gates' },
    { id: 'DK_G6_NO_IE', gate: 'G6', severity: 'FATAL', plain_language: 'No independent engineer has been appointed — lenders require an IE to certify CAPEX estimates.', resolution_action: 'Appoint a named, lender-accepted independent engineer.', resolution_page: '/finance/stage-gates' },
    { id: 'DK_G8_NO_AUDIT_MODEL', gate: 'G8', severity: 'FATAL', plain_language: 'The financial model has not been verified to audit grade.', resolution_action: 'Commission a financial model audit from a named firm.', resolution_page: '/finance/bankability' },
    { id: 'DK_G7_NO_INSURANCE', gate: 'G7', severity: 'CRITICAL', plain_language: 'The insurance programme has not been fully placed.', resolution_action: 'Bind all required insurance lines.', resolution_page: '/finance/insurance' },
  ],
  committee_readiness: 'NOT_READY',
  price_context: { forward_price_eur_t: 5620, financing_spread_eur_t: 148, molecule: 'H2' },
  families: {
    'Grants & Subsidies': {
      eligible: [
        { id: 'EU_INNOVATION_FUND', name: 'EU Innovation Fund', type: 'GRANT', provider: 'European Commission', rate_reduction_bps: 0, coverage: 0.60, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [] },
        { id: 'ADEME_H2_GRANT', name: 'ADEME Hydrogen Grant', type: 'GRANT', provider: 'ADEME', rate_reduction_bps: 0, coverage: 0.40, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [] },
      ],
      ineligible: [
        { id: 'US_45V_PTC', name: 'US 45V Tax Credit', type: 'TAX_CREDIT', provider: 'US Treasury', rate_reduction_bps: 120, coverage: 1.0, status: 'INELIGIBLE', reasons: ['Jurisdiction DE not covered — US only'], proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [] },
      ],
    },
    'Concessional / DFI Debt': {
      eligible: [
        { id: 'KFW_H2_PROGRAMME', name: 'KfW Hydrogen Programme', type: 'CONCESSIONAL_LOAN', provider: 'KfW', rate_reduction_bps: 90, coverage: 0.50, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], remedy_eur_t: 50.58 },
        { id: 'EBRD_GREEN_FINANCE', name: 'EBRD Green Finance', type: 'CONCESSIONAL_LOAN', provider: 'EBRD', rate_reduction_bps: 70, coverage: 0.35, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [] },
      ],
      ineligible: [],
    },
    'Green Bonds (Use of Proceeds)': {
      eligible: [],
      ineligible: [
        { id: 'GREEN_BOND_ICMA', name: 'Green Bond — ICMA GBP', type: 'GREEN_BOND', provider: 'Capital markets', rate_reduction_bps: 25, coverage: 0.44, status: 'INELIGIBLE', reasons: ['Stage BUILDABLE not eligible — requires: FINANCEABLE, OPERATIONAL'], proceeds_type: 'USE_OF_PROCEEDS', bond_framework: 'ICMA_GBP_2021', required_audit_nodes: ['SPO_PROVIDER'], esg_metrics: [] },
        { id: 'GREEN_PROJECT_BOND', name: 'Green Project Bond', type: 'GREEN_PROJECT_BOND', provider: 'Capital markets', rate_reduction_bps: 35, coverage: 0.35, status: 'INELIGIBLE', reasons: ['Stage BUILDABLE not eligible — requires: CREDIT_APPROVED, FINANCEABLE', 'Missing: Independent Engineer sign-off (G6)', 'Missing: Audit-grade financial model (G8)'], proceeds_type: 'USE_OF_PROCEEDS', bond_framework: 'ICMA_GBP_2021', required_audit_nodes: ['IE', 'SPO_PROVIDER', 'MODEL_AUDITOR'], esg_metrics: [], blocked_by_killers: [{ id: 'DK_G6_NO_IE', gate: 'G6', severity: 'FATAL', plain_language: 'No independent engineer has been appointed — lenders require an IE to certify CAPEX estimates.', resolution_action: 'Appoint a named IE.', resolution_page: '/finance/stage-gates' }, { id: 'DK_G8_NO_AUDIT_MODEL', gate: 'G8', severity: 'FATAL', plain_language: 'Financial model not audit-grade.', resolution_action: 'Commission model audit.', resolution_page: '/finance/bankability' }] },
        { id: 'GREEN_REVENUE_BOND', name: 'Green Revenue Bond', type: 'GREEN_REVENUE_BOND', provider: 'Capital markets', rate_reduction_bps: 30, coverage: 0.40, status: 'INELIGIBLE', reasons: ['Stage BUILDABLE not eligible — requires: FINANCEABLE, OPERATIONAL'], proceeds_type: 'REVENUE_BACKED', bond_framework: 'ICMA_GBP_2021', required_audit_nodes: ['SPO_PROVIDER', 'IMPACT_AUDITOR'], esg_metrics: [] },
      ],
    },
    'ESG-Linked (General Purpose)': {
      eligible: [
        { id: 'ESG_LINKED_BOND_GENERIC', name: 'ESG-Linked Bond — SLB', type: 'ESG_LINKED_BOND', provider: 'Capital markets', rate_reduction_bps: 15, coverage: 0.50, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'ICMA_SLB', required_audit_nodes: [], esg_metrics: [{ kpi_name: 'GHG Intensity Reduction', target_value: 50.0, target_unit: '% vs 2020 baseline', penalty_bps: 25, verification_agent: 'DNV' }], remedy_eur_t: 8.43 },
        { id: 'SLL_MARGIN_RATCHET', name: 'Sustainability-Linked Loan', type: 'SLL', provider: 'Commercial banks', rate_reduction_bps: 20, coverage: 0.60, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'LMA_SLLP', required_audit_nodes: [], esg_metrics: [{ kpi_name: 'Renewable Energy Share', target_value: 95.0, target_unit: '%', penalty_bps: 15, verification_agent: 'S&P Global' }], remedy_eur_t: 11.24 },
      ],
      ineligible: [],
    },
    'Guarantees & Credit Enhancement': {
      eligible: [
        { id: 'EIB_PROJECT_BOND', name: 'EIB Project Bond Enhancement', type: 'PARTIAL_CREDIT', provider: 'EIB', rate_reduction_bps: 60, coverage: 0.20, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], remedy_eur_t: 33.72 },
        { id: 'OEM_PERFORMANCE_WRAP', name: 'OEM Performance Guarantee', type: 'PERFORMANCE_GUARANTEE', provider: 'OEM', rate_reduction_bps: 30, coverage: 0.15, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], blocked_by_killers: [{ id: 'DK_G5_NO_EPC', gate: 'G5', severity: 'FATAL', plain_language: 'No EPC contract executed.', resolution_action: 'Execute EPC contract.', resolution_page: '/finance/stage-gates' }] },
      ],
      ineligible: [],
    },
    'Offtake & Revenue Support': {
      eligible: [
        { id: 'EU_H2_BANK_AUCTION', name: 'EU Hydrogen Bank CFD', type: 'CFD', provider: 'European Commission', rate_reduction_bps: 80, coverage: 1.0, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], remedy_eur_t: 44.96 },
        { id: 'H2GLOBAL_AUCTION', name: 'H2Global Offtake Guarantee', type: 'OFFTAKE_GUARANTEE', provider: 'H2Global Foundation', rate_reduction_bps: 100, coverage: 1.0, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], remedy_eur_t: 56.2 },
      ],
      ineligible: [],
    },
    Insurance: {
      eligible: [
        { id: 'INSURANCE_CAR_DSU', name: 'CAR + DSU Insurance', type: 'CAR_INSURANCE', provider: 'Commercial insurers', rate_reduction_bps: 25, coverage: 1.0, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [], blocked_by_killers: [{ id: 'DK_G5_NO_EPC', gate: 'G5', severity: 'FATAL', plain_language: 'No EPC contract executed.', resolution_action: 'Execute EPC contract.', resolution_page: '/finance/stage-gates' }] },
      ],
      ineligible: [],
    },
    'Export Credit & Political Risk': {
      eligible: [
        { id: 'MIGA_PRI', name: 'MIGA Political Risk Insurance', type: 'PRI', provider: 'World Bank / MIGA', rate_reduction_bps: 40, coverage: 0.90, status: 'ELIGIBLE', proceeds_type: 'GENERAL_PURPOSE', bond_framework: 'NONE', required_audit_nodes: [], esg_metrics: [] },
      ],
      ineligible: [],
    },
  },
}

// ── Family icons ──

const FAMILY_ICONS: Record<string, typeof Shield> = {
  'Grants & Subsidies': Leaf,
  'Concessional / DFI Debt': Shield,
  'Green Bonds (Use of Proceeds)': Layers,
  'ESG-Linked (General Purpose)': TrendingUp,
  'Guarantees & Credit Enhancement': Shield,
  'Offtake & Revenue Support': TrendingUp,
  Insurance: Shield,
  'Export Credit & Political Risk': AlertTriangle,
}

// Key families for compact mode and the green-bond vs ESG-linked fork
const KEY_FAMILIES = ['Green Bonds (Use of Proceeds)', 'ESG-Linked (General Purpose)']

// ── Component ──

export function InstrumentCompatibility({ compact = false }: { compact?: boolean }) {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)

  const [data, setData] = useState<CompatibilityData | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  useEffect(() => {
    setLoading(true)
    fetch(`/api/v1/instruments/compatibility/${selectedProjectId}`)
      .then(r => {
        if (!r.ok) throw new Error('API unavailable')
        return r.json()
      })
      .then((d: CompatibilityData) => {
        setData(d)
        setLoading(false)
      })
      .catch(() => {
        setData({ ...SEED_COMPATIBILITY, project_id: selectedProjectId })
        setLoading(false)
      })
  }, [selectedProjectId])

  const toggleFamily = (family: string) => {
    setExpanded(prev => ({ ...prev, [family]: !prev[family] }))
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center gap-2 text-[var(--text-muted)]">
        <RefreshCw className="w-4 h-4 animate-spin" />
        Loading compatibility...
      </div>
    )
  }

  if (!data) return null

  const families = Object.entries(data.families)
  const displayFamilies = compact
    ? families.filter(([name]) => KEY_FAMILIES.includes(name))
    : families

  const otherCount = compact
    ? families
        .filter(([name]) => !KEY_FAMILIES.includes(name))
        .reduce((sum, [, f]) => sum + f.eligible.length + f.ineligible.length, 0)
    : 0

  return (
    <div className={compact ? 'space-y-3' : 'p-6 space-y-5'}>
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className={`font-display font-bold text-[var(--text-primary)] ${compact ? 'text-base' : 'text-xl'}`}>
            Instrument Compatibility
          </h2>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-[#0ea5a0]/15 text-[#0ea5a0] font-semibold">
            {data.project_state}
          </span>
        </div>
        <span className="text-xs text-[var(--text-muted)]">
          {data.eligible_count}/{data.total_instruments} eligible
        </span>
      </div>

      {/* ── Deal Killer Banner ── */}
      {data.active_killers && data.active_killers.length > 0 && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 space-y-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            <span className="text-xs font-semibold text-red-500 uppercase tracking-wider">
              {data.committee_readiness === 'NOT_READY' ? 'Not Committee-Ready' : 'Conditional'}
            </span>
            <span className="text-xs text-[var(--text-muted)]">
              — {data.active_killers.length} active deal killer{data.active_killers.length > 1 ? 's' : ''} blocking instruments
            </span>
          </div>
          {data.active_killers.slice(0, compact ? 2 : undefined).map(dk => (
            <div key={dk.id} className="flex items-start gap-2 pl-6">
              <span className={`text-2xs font-mono px-1.5 py-0.5 rounded ${dk.severity === 'FATAL' ? 'bg-red-500/10 text-red-500' : 'bg-amber-500/10 text-amber-500'}`}>
                {dk.severity}
              </span>
              <span className="text-xs text-[var(--text-secondary)] flex-1">{dk.plain_language}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Summary strip ── */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-3 py-2">
          <div className="text-xs text-[var(--text-muted)]">Eligible</div>
          <div className="text-lg font-bold text-green-500">{data.eligible_count}</div>
        </div>
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
          <div className="text-xs text-[var(--text-muted)]">Ineligible</div>
          <div className="text-lg font-bold text-amber-500">{data.ineligible_count}</div>
        </div>
        <div className="rounded-lg border border-[#0ea5a0]/20 bg-[#0ea5a0]/5 px-3 py-2">
          <div className="text-xs text-[var(--text-muted)]">Project</div>
          <div className="text-sm font-semibold text-[#0ea5a0] truncate">
            {project?.name ?? data.project_id}
          </div>
        </div>
      </div>

      {/* ── Price context strip ── */}
      {!compact && data.price_context && (
        <div className="flex items-center gap-4 text-xs text-[var(--text-muted)] px-1">
          <span>Forward: <strong className="text-[var(--text-primary)]">{'\u20AC'}{data.price_context.forward_price_eur_t.toLocaleString()}/t</strong></span>
          <span>Financing spread: <strong className="text-amber-500">{'\u20AC'}{data.price_context.financing_spread_eur_t}/t</strong></span>
          <span className="text-[#0ea5a0]">Remedy values show cost reduction per tonne</span>
        </div>
      )}

      {/* ── Family sections ── */}
      <div className="space-y-2">
        {displayFamilies.map(([familyName, family]) => {
          const Icon = FAMILY_ICONS[familyName] ?? Layers
          const isOpen = expanded[familyName] ?? false
          const isGreenBond = familyName === 'Green Bonds (Use of Proceeds)'
          const isEsgLinked = familyName === 'ESG-Linked (General Purpose)'

          return (
            <div key={familyName} className="rounded-lg border border-[var(--border)] overflow-hidden">
              {/* Family header */}
              <button
                onClick={() => toggleFamily(familyName)}
                className="w-full flex items-center justify-between px-4 py-2.5 bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] transition-colors text-left"
              >
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-[var(--text-muted)]" />
                  <span className="text-sm font-semibold text-[var(--text-primary)]">
                    {familyName}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {family.eligible.length > 0 && (
                    <span className="text-xs text-green-500 font-medium">
                      {family.eligible.length} eligible
                    </span>
                  )}
                  {family.ineligible.length > 0 && (
                    <span className="text-xs text-amber-500 font-medium">
                      {family.ineligible.length} blocked
                    </span>
                  )}
                  {isOpen ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
                </div>
              </button>

              {isOpen && (
                <div className="px-4 py-3 space-y-3">
                  {/* Callout for Green Bond fork */}
                  {isGreenBond && (
                    <div className="border-l-4 border-[#0ea5a0] bg-[#0ea5a0]/5 px-3 py-2 rounded-r text-xs text-[var(--text-secondary)]">
                      <span className="font-semibold text-[#0ea5a0]">Use of Proceeds</span> — returns from project revenue. Requires predetermined allocation.
                    </div>
                  )}

                  {/* Callout for ESG-Linked fork */}
                  {isEsgLinked && (
                    <div className="border-l-4 border-purple-500 bg-purple-500/5 px-3 py-2 rounded-r text-xs text-[var(--text-secondary)]">
                      <span className="font-semibold text-purple-500">General Purpose</span> — returns dependent on ESG KPIs. No predetermined use of funds.
                    </div>
                  )}

                  {/* Eligible instruments */}
                  {family.eligible.map(inst => (
                    <div key={inst.id} className="flex items-start gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-2 flex-wrap">
                          <span className="text-sm font-medium text-[var(--text-primary)]">{inst.name}</span>
                          <span className="text-xs text-[var(--text-muted)]">{inst.provider}</span>
                          {inst.rate_reduction_bps > 0 && (
                            <span className="text-xs text-green-500 font-mono">-{inst.rate_reduction_bps}bps</span>
                          )}
                          {inst.remedy_eur_t != null && inst.remedy_eur_t > 0 && (
                            <span className="text-xs font-mono text-[#0ea5a0]">
                              -{'\u20AC'}{inst.remedy_eur_t.toFixed(0)}/t
                            </span>
                          )}
                        </div>
                        {/* ESG metrics for ESG-linked instruments */}
                        {inst.esg_metrics.length > 0 && (
                          <div className="mt-1 space-y-1">
                            {inst.esg_metrics.map((m, i) => (
                              <div key={i} className="text-xs text-[var(--text-muted)] pl-1 flex items-center gap-2 flex-wrap">
                                <span className="font-medium text-purple-400">{m.kpi_name}</span>
                                <span>{m.target_value}{m.target_unit}</span>
                                <span className="text-amber-400">penalty: +{m.penalty_bps}bps</span>
                                <span className="text-[var(--text-muted)]">verified by {m.verification_agent}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}

                  {/* Ineligible instruments */}
                  {family.ineligible.map(inst => (
                    <div key={inst.id} className="flex items-start gap-2">
                      <XCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline gap-2 flex-wrap">
                          <span className="text-sm font-medium text-[var(--text-primary)] opacity-60">{inst.name}</span>
                          <span className="text-xs text-[var(--text-muted)]">{inst.provider}</span>
                          {inst.rate_reduction_bps > 0 && (
                            <span className="text-xs text-[var(--text-muted)] font-mono">-{inst.rate_reduction_bps}bps</span>
                          )}
                        </div>
                        {!compact && inst.blocked_by_killers && inst.blocked_by_killers.length > 0 && (
                          <div className="mt-1 space-y-1">
                            {inst.blocked_by_killers.map(dk => (
                              <div key={dk.id} className="flex items-start gap-1.5 text-xs">
                                <span className={`shrink-0 font-mono px-1 py-0.5 rounded ${dk.severity === 'FATAL' ? 'bg-red-500/10 text-red-500' : 'bg-amber-500/10 text-amber-500'}`}>
                                  {dk.gate}
                                </span>
                                <span className="text-red-400/80">{dk.plain_language}</span>
                              </div>
                            ))}
                          </div>
                        )}
                        {inst.reasons && inst.reasons.length > 0 && (
                          <ul className="mt-1 space-y-0.5">
                            {inst.reasons.map((r, i) => (
                              <li key={i} className="text-xs text-red-400/80 pl-1">
                                {r}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  ))}

                  {family.eligible.length === 0 && family.ineligible.length === 0 && (
                    <div className="text-xs text-[var(--text-muted)] italic">No instruments in this family.</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Compact mode: collapsed other families count */}
      {compact && otherCount > 0 && (
        <div className="text-xs text-[var(--text-muted)] px-1">
          + {otherCount} instruments across {families.length - displayFamilies.length} other families
        </div>
      )}
    </div>
  )
}
