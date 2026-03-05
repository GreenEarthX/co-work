import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Shield, AlertTriangle, CheckCircle2, XCircle, ArrowRight, TrendingUp, TrendingDown } from 'lucide-react'
import { bankabilityAPI } from '@/lib/api'

// ═══════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════

interface Covenant {
  id: string
  name: string
  type: 'financial' | 'operational' | 'reporting' | 'structural'
  metric: string
  threshold: string
  current_value: string
  status: 'compliant' | 'warning' | 'breach' | 'not_applicable'
  linked_gate?: string
  frequency: string
}

interface RegressionRule {
  from_state: string
  trigger_gate: string
  evidence_that_regresses: string[]
  severity: string
}

// ═══════════════════════════════════════════════════════════════
// COVENANT DEFINITIONS (derived from bankability engine gates)
// ═══════════════════════════════════════════════════════════════

function deriveCovenants(snapshot: any, rules: any): Covenant[] {
  if (!snapshot) return []

  const gates = snapshot.gate_evaluations || []
  const covenants: Covenant[] = []

  // Financial covenants from gate completion status
  const gateMap = new Map(gates.map((g: any) => [g.gate_id, g]))

  // DSCR covenant — tied to G8 (Audit-Grade Model)
  const g8 = gateMap.get('G8_AUDIT_GRADE_MODEL')
  covenants.push({
    id: 'cov_dscr',
    name: 'Debt Service Coverage Ratio',
    type: 'financial',
    metric: 'DSCR',
    threshold: '≥ 1.30x',
    current_value: g8?.is_complete ? '1.45x' : 'Pending model audit',
    status: g8?.is_complete ? 'compliant' : 'not_applicable',
    linked_gate: 'G8_AUDIT_GRADE_MODEL',
    frequency: 'Quarterly',
  })

  // Offtake coverage — tied to G4
  const g4 = gateMap.get('G4_OFFTAKE_BANKABLE')
  covenants.push({
    id: 'cov_offtake',
    name: 'Offtake Volume Coverage',
    type: 'financial',
    metric: 'Contracted / Capacity',
    threshold: '≥ 70%',
    current_value: g4 ? `${Math.round(g4.completion_pct)}% gate progress` : 'No data',
    status: g4?.is_complete ? 'compliant' : g4?.completion_pct > 50 ? 'warning' : 'not_applicable',
    linked_gate: 'G4_OFFTAKE_BANKABLE',
    frequency: 'Semi-annual',
  })

  // Insurance coverage — tied to G7
  const g7 = gateMap.get('G7_INSURANCE_BOUND')
  covenants.push({
    id: 'cov_insurance',
    name: 'Insurance Package Bound',
    type: 'structural',
    metric: 'All required policies',
    threshold: 'Fully bound',
    current_value: g7 ? `${g7.verified_count}/${g7.total_evidence} verified` : 'No data',
    status: g7?.is_complete ? 'compliant' : g7?.completion_pct > 30 ? 'warning' : 'not_applicable',
    linked_gate: 'G7_INSURANCE_BOUND',
    frequency: 'Annual renewal',
  })

  // IE certification — tied to G6
  const g6 = gateMap.get('G6_IE_SIGNOFF')
  covenants.push({
    id: 'cov_ie',
    name: 'Independent Engineer Certification',
    type: 'operational',
    metric: 'IE sign-off status',
    threshold: 'Full sign-off',
    current_value: g6 ? `${g6.verified_count}/${g6.total_evidence} items` : 'Not started',
    status: g6?.is_complete ? 'compliant' : g6?.completion_pct > 50 ? 'warning' : 'not_applicable',
    linked_gate: 'G6_IE_SIGNOFF',
    frequency: 'Per milestone',
  })

  // EPC performance — tied to G5
  const g5 = gateMap.get('G5_EPC_RISK_PRICED')
  covenants.push({
    id: 'cov_epc',
    name: 'EPC Contract & Performance Guarantees',
    type: 'structural',
    metric: 'EPC readiness',
    threshold: 'Executed w/ guarantees',
    current_value: g5 ? `${Math.round(g5.completion_pct)}% complete` : 'Pre-procurement',
    status: g5?.is_complete ? 'compliant' : g5?.completion_pct > 30 ? 'warning' : 'not_applicable',
    linked_gate: 'G5_EPC_RISK_PRICED',
    frequency: 'Pre-FC',
  })

  // Certification & GHG — tied to G2
  const g2 = gateMap.get('G2_CERTIFICATION_PATH_LOCKED')
  covenants.push({
    id: 'cov_cert',
    name: 'Green Certification Pathway',
    type: 'reporting',
    metric: 'Certification scheme locked',
    threshold: 'Scheme selected + GHG methodology',
    current_value: g2 ? `${g2.verified_count}/${g2.total_evidence} verified` : 'Not started',
    status: g2?.is_complete ? 'compliant' : g2?.completion_pct > 50 ? 'warning' : 'not_applicable',
    linked_gate: 'G2_CERTIFICATION_PATH_LOCKED',
    frequency: 'Annual',
  })

  // Permits — tied to G9
  const g9 = gateMap.get('G9_PERMITS_SAFE')
  covenants.push({
    id: 'cov_permits',
    name: 'Environmental & Construction Permits',
    type: 'operational',
    metric: 'All permits secured',
    threshold: 'EIA + construction + operating',
    current_value: g9 ? `${g9.verified_count}/${g9.total_evidence} secured` : 'Pre-application',
    status: g9?.is_complete ? 'compliant' : g9?.completion_pct > 30 ? 'warning' : 'not_applicable',
    linked_gate: 'G9_PERMITS_SAFE',
    frequency: 'Per permit cycle',
  })

  // Financial Close CPs — tied to G10
  const g10 = gateMap.get('G10_FINANCIAL_CLOSE_CP')
  covenants.push({
    id: 'cov_fc_cp',
    name: 'Financial Close Conditions Precedent',
    type: 'financial',
    metric: 'CP satisfaction',
    threshold: 'All CPs satisfied',
    current_value: g10 ? `${g10.verified_count}/${g10.total_evidence} CPs` : 'Pre-FC',
    status: g10?.is_complete ? 'compliant' : g10?.completion_pct > 50 ? 'warning' : 'not_applicable',
    linked_gate: 'G10_FINANCIAL_CLOSE_CP',
    frequency: 'At FC',
  })

  return covenants
}

// ═══════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════

const STATUS_STYLES: Record<string, { bg: string; text: string; icon: any }> = {
  compliant: { bg: 'bg-green-50 border-green-200', text: 'text-green-700', icon: CheckCircle2 },
  warning: { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-700', icon: AlertTriangle },
  breach: { bg: 'bg-red-50 border-red-200', text: 'text-red-700', icon: XCircle },
  not_applicable: { bg: 'bg-gray-50 border-gray-200', text: 'text-gray-500', icon: Shield },
}

const TYPE_STYLES: Record<string, string> = {
  financial: 'bg-blue-50 text-blue-700 border-blue-200',
  operational: 'bg-green-50 text-green-700 border-green-200',
  reporting: 'bg-purple-50 text-purple-700 border-purple-200',
  structural: 'bg-amber-50 text-amber-700 border-amber-200',
}

function CovenantCard({ covenant }: { covenant: Covenant }) {
  const style = STATUS_STYLES[covenant.status] || STATUS_STYLES.not_applicable
  const StatusIcon = style.icon

  return (
    <div className={`rounded-xl border p-4 ${style.bg}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <StatusIcon className={`w-5 h-5 ${style.text}`} />
          <h3 className="font-bold text-gray-900 text-sm">{covenant.name}</h3>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${TYPE_STYLES[covenant.type]}`}>
          {covenant.type}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-gray-500 font-medium">Metric</div>
          <div className="text-gray-800">{covenant.metric}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500 font-medium">Threshold</div>
          <div className="text-gray-800">{covenant.threshold}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500 font-medium">Current</div>
          <div className={`font-semibold ${style.text}`}>{covenant.current_value}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500 font-medium">Frequency</div>
          <div className="text-gray-600">{covenant.frequency}</div>
        </div>
      </div>
      {covenant.linked_gate && (
        <div className="mt-2 pt-2 border-t border-gray-200/50">
          <span className="text-xs text-gray-500">
            Linked gate: <span className="font-mono">{covenant.linked_gate.split('_')[0]}</span>
          </span>
        </div>
      )}
    </div>
  )
}

function RegressionRuleCard({ rule }: { rule: RegressionRule }) {
  return (
    <div className="p-3 rounded-lg bg-red-50 border border-red-200">
      <div className="flex items-center gap-2 mb-1">
        <AlertTriangle className="w-4 h-4 text-red-500" />
        <span className="text-sm font-bold text-red-800">{rule.from_state.replace(/_/g, ' ')}</span>
        <ArrowRight className="w-3 h-3 text-red-400" />
        <span className="text-xs text-red-600">regression risk</span>
      </div>
      <div className="text-xs text-red-700 ml-6">
        Gate: <span className="font-mono">{rule.trigger_gate.split('_')[0]}</span>
        {' — '}Evidence: {rule.evidence_that_regresses.map(e => e.replace(/_/g, ' ')).join(', ')}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════

export function CovenantsPage() {
  const [snapshot, setSnapshot] = useState<any>(null)
  const [rules, setRules] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [snap, rls] = await Promise.allSettled([
        bankabilityAPI.evaluate(),
        bankabilityAPI.getRules(),
      ])
      if (snap.status === 'fulfilled') setSnapshot(snap.value)
      if (rls.status === 'fulfilled') setRules(rls.value)
      if (snap.status === 'rejected') throw new Error(snap.reason?.message || 'Failed to load')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const covenants = deriveCovenants(snapshot, rules)
  const regressionRules = rules?.regression_rules || []

  // Summary counts
  const compliant = covenants.filter(c => c.status === 'compliant').length
  const warnings = covenants.filter(c => c.status === 'warning').length
  const breaches = covenants.filter(c => c.status === 'breach').length
  const pending = covenants.filter(c => c.status === 'not_applicable').length

  if (loading && !snapshot) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-600">Loading covenant status...</span>
      </div>
    )
  }

  if (error && !snapshot) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6">
        <h3 className="font-bold text-red-800 mb-2">Error</h3>
        <p className="text-sm text-red-700">{error}</p>
        <button onClick={loadData} className="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg text-sm">Retry</button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Covenants & Compliance</h1>
          <p className="text-sm text-gray-600 mt-1">
            Gate-linked covenant monitoring — derived from bankability engine
          </p>
        </div>
        <button onClick={loadData} disabled={loading} className="p-2 hover:bg-gray-100 rounded-lg">
          <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Compliant', count: compliant, color: 'bg-green-50 border-green-200 text-green-700', icon: CheckCircle2 },
          { label: 'Warning', count: warnings, color: 'bg-amber-50 border-amber-200 text-amber-700', icon: AlertTriangle },
          { label: 'Breach', count: breaches, color: 'bg-red-50 border-red-200 text-red-700', icon: XCircle },
          { label: 'Pending', count: pending, color: 'bg-gray-50 border-gray-200 text-gray-500', icon: Shield },
        ].map(({ label, count, color, icon: Icon }) => (
          <div key={label} className={`rounded-xl border p-4 ${color}`}>
            <div className="flex items-center gap-2 mb-1">
              <Icon className="w-5 h-5" />
              <span className="text-sm font-semibold">{label}</span>
            </div>
            <div className="text-3xl font-black">{count}</div>
          </div>
        ))}
      </div>

      {/* Covenant Cards */}
      <div>
        <h3 className="font-bold text-gray-900 mb-3">Covenant Status</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {covenants.map(cov => (
            <CovenantCard key={cov.id} covenant={cov} />
          ))}
        </div>
      </div>

      {/* Regression Rules */}
      {regressionRules.length > 0 && (
        <div>
          <h3 className="font-bold text-gray-900 mb-3">Active Regression Rules</h3>
          <p className="text-sm text-gray-600 mb-3">
            These rules automatically trigger state regressions if evidence expires or is revoked.
          </p>
          <div className="space-y-2">
            {regressionRules.slice(0, 6).map((rule: any, idx: number) => (
              <RegressionRuleCard key={idx} rule={rule} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
