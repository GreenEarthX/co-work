import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Shield, CheckCircle2, Clock, AlertTriangle, ChevronDown, ChevronRight, Upload, XCircle, Eye, Lock, Unlock } from 'lucide-react'
import { bankabilityAPI } from '@/lib/api'

// ═══════════════════════════════════════════════════════════════
// TYPES (match engine output models)
// ═══════════════════════════════════════════════════════════════

interface EvidenceItem {
  key: string
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED'
  submitted_by?: string
  verified_by?: string
  notes?: string
}

interface GateEvaluation {
  gate_id: string
  gate_name: string
  owners: string[]
  total_evidence: number
  verified_count: number
  completion_pct: number
  is_complete: boolean
  evidence_detail: EvidenceItem[]
  unlocks_capital: string[]
  unlocks_state?: string
  blocking_items: string[]
}

interface CapitalUnlock {
  capital_type: string
  is_unlocked: boolean
  gating_gates: string[]
  best_progress_pct: number
}

interface Snapshot {
  project_id: string
  evaluated_at: string
  current_state: string
  previous_state?: string
  regression?: { from_state: string; to_state: string; trigger_gate: string; reason: string }
  gate_evaluations: GateEvaluation[]
  capital_unlocks: CapitalUnlock[]
  total_evidence: number
  total_verified: number
  overall_completion_pct: number
  next_state?: string
  gates_blocking_next_state: string[]
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: any; label: string }> = {
  NOT_STARTED: { color: 'text-gray-400', bg: 'bg-gray-50 border-gray-200', icon: Clock, label: 'Not Started' },
  IN_PROGRESS: { color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200', icon: Clock, label: 'In Progress' },
  SUBMITTED: { color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200', icon: Upload, label: 'Submitted' },
  UNDER_REVIEW: { color: 'text-purple-600', bg: 'bg-purple-50 border-purple-200', icon: Eye, label: 'Under Review' },
  VERIFIED: { color: 'text-green-600', bg: 'bg-green-50 border-green-200', icon: CheckCircle2, label: 'Verified' },
  REJECTED: { color: 'text-red-600', bg: 'bg-red-50 border-red-200', icon: XCircle, label: 'Rejected' },
  EXPIRED: { color: 'text-orange-600', bg: 'bg-orange-50 border-orange-200', icon: AlertTriangle, label: 'Expired' },
}

const STATE_LABELS: Record<string, string> = {
  SPECULATIVE: 'Speculative',
  TECHNICALLY_PLAUSIBLE: 'Technically Plausible',
  COMMERCIALLY_PLAUSIBLE: 'Commercially Plausible',
  BUILDABLE: 'Buildable',
  STRUCTURALLY_BANKABLE: 'Structurally Bankable',
  CREDIT_APPROVED: 'Credit Approved',
  FINANCEABLE: 'Financeable',
  OPERATIONAL: 'Operational',
  REFINANCING_ELIGIBLE: 'Refinancing Eligible',
}

const STATE_ORDER = Object.keys(STATE_LABELS)

const CAPITAL_LABELS: Record<string, string> = {
  GRANTS_TA: 'Grants & TA',
  SEED_VC_ANGEL: 'Seed / VC / Angel',
  STRATEGIC_EQUITY: 'Strategic Equity',
  PROJECT_EQUITY: 'Project Equity',
  DFI_MEZZ_GUARANTEES: 'DFI / Mezz / Guarantees',
  SENIOR_DEBT_COMMITMENT: 'Senior Debt Commitment',
  DEBT_DRAWDOWN: 'Debt Drawdown',
  REFINANCE_BONDS_INFRA: 'Refinance / Bonds / Infra',
}

function formatEvidenceKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ═══════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════

function StateProgressionBar({ currentState, nextState }: { currentState: string; nextState?: string }) {
  const currentIdx = STATE_ORDER.indexOf(currentState)
  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-2">
      {STATE_ORDER.map((state, idx) => {
        const isActive = idx === currentIdx
        const isPast = idx < currentIdx
        const isNext = state === nextState
        return (
          <div key={state} className="flex items-center gap-1 flex-shrink-0">
            <div className={`px-2 py-1 rounded text-xs font-semibold whitespace-nowrap border transition-all ${
              isActive ? 'bg-green-600 text-white border-green-700 shadow-md' :
              isPast ? 'bg-green-100 text-green-700 border-green-200' :
              isNext ? 'bg-amber-50 text-amber-700 border-amber-300 border-dashed' :
              'bg-gray-50 text-gray-400 border-gray-200'
            }`}>
              {STATE_LABELS[state] || state}
            </div>
            {idx < STATE_ORDER.length - 1 && (
              <div className={`w-3 h-0.5 flex-shrink-0 ${isPast ? 'bg-green-400' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function CapitalUnlockRow({ unlock }: { unlock: CapitalUnlock }) {
  const Icon = unlock.is_unlocked ? Unlock : Lock
  return (
    <div className={`flex items-center justify-between p-3 rounded-lg border ${
      unlock.is_unlocked ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'
    }`}>
      <div className="flex items-center gap-3">
        <Icon className={`w-4 h-4 ${unlock.is_unlocked ? 'text-green-600' : 'text-gray-400'}`} />
        <div>
          <div className={`text-sm font-semibold ${unlock.is_unlocked ? 'text-green-800' : 'text-gray-600'}`}>
            {CAPITAL_LABELS[unlock.capital_type] || unlock.capital_type}
          </div>
          <div className="text-xs text-gray-500">
            Gates: {unlock.gating_gates.map(g => g.split('_')[0]).join(', ')}
          </div>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-sm font-bold ${unlock.is_unlocked ? 'text-green-700' : 'text-gray-500'}`}>
          {unlock.is_unlocked ? 'Unlocked' : `${Math.round(unlock.best_progress_pct)}%`}
        </div>
      </div>
    </div>
  )
}

function GateCard({ gate, onUpdateEvidence }: { gate: GateEvaluation; onUpdateEvidence: (key: string, status: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const completePct = Math.round(gate.completion_pct)

  return (
    <div className={`bg-white rounded-xl border overflow-hidden ${
      gate.is_complete ? 'border-green-300 shadow-sm shadow-green-100' : 'border-gray-200'
    }`}>
      {/* Gate Header */}
      <div
        className="p-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {gate.is_complete ? (
              <CheckCircle2 className="w-6 h-6 text-green-600 flex-shrink-0" />
            ) : (
              <div className="w-6 h-6 rounded-full border-2 border-gray-300 flex items-center justify-center flex-shrink-0">
                <span className="text-xs font-bold text-gray-500">{completePct}</span>
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-gray-400">{gate.gate_id.split('_')[0]}</span>
                <h3 className="font-bold text-gray-900 text-sm">{gate.gate_name}</h3>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-gray-500">
                  {gate.verified_count}/{gate.total_evidence} verified
                </span>
                {gate.unlocks_state && (
                  <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded border border-blue-200">
                    → {STATE_LABELS[gate.unlocks_state] || gate.unlocks_state}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Progress bar */}
            <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${gate.is_complete ? 'bg-green-500' : 'bg-blue-500'}`}
                style={{ width: `${completePct}%` }}
              />
            </div>
            <span className="text-xs font-bold text-gray-500 w-8 text-right">{completePct}%</span>
            {expanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
          </div>
        </div>
      </div>

      {/* Evidence Detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 pb-4">
          {/* Capital unlocks for this gate */}
          {gate.unlocks_capital.length > 0 && (
            <div className="py-2 mb-2 border-b border-gray-50">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Unlocks: </span>
              {gate.unlocks_capital.map(c => (
                <span key={c} className="text-xs px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded border border-amber-200 ml-1">
                  {CAPITAL_LABELS[c] || c}
                </span>
              ))}
            </div>
          )}

          {/* Evidence items */}
          <div className="space-y-2 mt-3">
            {gate.evidence_detail.map(ev => {
              const cfg = STATUS_CONFIG[ev.status] || STATUS_CONFIG.NOT_STARTED
              const StatusIcon = cfg.icon
              return (
                <div key={ev.key} className={`flex items-center justify-between p-2.5 rounded-lg border ${cfg.bg}`}>
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <StatusIcon className={`w-4 h-4 flex-shrink-0 ${cfg.color}`} />
                    <span className="text-sm text-gray-800 truncate">{formatEvidenceKey(ev.key)}</span>
                  </div>
                  <div className="flex items-center gap-2 ml-3">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${cfg.color}`}>{cfg.label}</span>
                    {/* Status progression buttons */}
                    {ev.status === 'NOT_STARTED' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'IN_PROGRESS') }}
                        className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                      >Start</button>
                    )}
                    {ev.status === 'IN_PROGRESS' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'SUBMITTED') }}
                        className="text-xs px-2 py-1 bg-amber-600 text-white rounded hover:bg-amber-700"
                      >Submit</button>
                    )}
                    {ev.status === 'SUBMITTED' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'UNDER_REVIEW') }}
                        className="text-xs px-2 py-1 bg-purple-600 text-white rounded hover:bg-purple-700"
                      >Review</button>
                    )}
                    {ev.status === 'UNDER_REVIEW' && (
                      <div className="flex gap-1">
                        <button
                          onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'VERIFIED') }}
                          className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                        >Verify</button>
                        <button
                          onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'REJECTED') }}
                          className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700"
                        >Reject</button>
                      </div>
                    )}
                    {ev.status === 'REJECTED' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onUpdateEvidence(ev.key, 'IN_PROGRESS') }}
                        className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                      >Rework</button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Owners */}
          <div className="mt-3 pt-2 border-t border-gray-100">
            <span className="text-xs text-gray-500">
              Owners: {gate.owners.map(o => o.replace(/_/g, ' ')).join(', ')}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════

export function StageGatesPage() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [seeding, setSeeding] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await bankabilityAPI.evaluate()
      setSnapshot(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load bankability data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleUpdateEvidence = async (evidenceKey: string, newStatus: string) => {
    try {
      const updated = await bankabilityAPI.updateEvidence({
        evidence_key: evidenceKey,
        new_status: newStatus,
      })
      setSnapshot(updated)
    } catch (err: any) {
      console.error('Evidence update failed:', err)
    }
  }

  const handleSeedDemo = async () => {
    setSeeding(true)
    try {
      await bankabilityAPI.seedDemo()
      await loadData()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSeeding(false)
    }
  }

  // ── Loading state ──
  if (loading && !snapshot) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-600">Evaluating bankability gates...</span>
      </div>
    )
  }

  // ── Error state ──
  if (error && !snapshot) {
    return (
      <div className="space-y-6">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h3 className="text-lg font-bold text-red-800 mb-2">Engine Connection Error</h3>
          <p className="text-sm text-red-700 mb-4">{error}</p>
          <p className="text-xs text-red-600 mb-4">
            Make sure gex_pf_engine is running on port 8001 with the bankability router mounted.
          </p>
          <div className="flex gap-3">
            <button onClick={loadData} className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700">
              Retry
            </button>
            <button onClick={handleSeedDemo} disabled={seeding} className="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-semibold hover:bg-amber-700">
              {seeding ? 'Seeding...' : 'Seed Demo Data'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!snapshot) return null

  const blockers = snapshot.gates_blocking_next_state || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-gray-900">Bankability Stage Gates</h1>
          <p className="text-sm text-gray-600 mt-1">
            {snapshot.total_verified}/{snapshot.total_evidence} evidence items verified
            — {Math.round(snapshot.overall_completion_pct)}% complete
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleSeedDemo} disabled={seeding} className="px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-gray-600">
            {seeding ? 'Seeding...' : 'Seed Demo'}
          </button>
          <button onClick={loadData} disabled={loading} className="p-2 hover:bg-gray-100 rounded-lg">
            <RefreshCw className={`w-5 h-5 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* State + Progression */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center gap-3 mb-4">
          <Shield className="w-6 h-6 text-green-600" />
          <div>
            <span className="text-sm text-gray-500">Current State</span>
            <h2 className="text-xl font-black text-gray-900">{STATE_LABELS[snapshot.current_state] || snapshot.current_state}</h2>
          </div>
          {snapshot.next_state && (
            <div className="ml-auto text-right">
              <span className="text-xs text-gray-400">Next target</span>
              <div className="text-sm font-bold text-amber-700">{STATE_LABELS[snapshot.next_state]}</div>
            </div>
          )}
        </div>
        <StateProgressionBar currentState={snapshot.current_state} nextState={snapshot.next_state || undefined} />

        {/* Regression Warning */}
        {snapshot.regression && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <span className="font-bold text-red-800 text-sm">Regression Detected</span>
            </div>
            <p className="text-sm text-red-700 mt-1">
              {STATE_LABELS[snapshot.regression.from_state]} → {STATE_LABELS[snapshot.regression.to_state]}:
              {' '}{snapshot.regression.reason}
            </p>
          </div>
        )}

        {/* Blockers */}
        {blockers.length > 0 && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <span className="text-xs font-semibold text-amber-700 uppercase tracking-wider">Blocking next state: </span>
            {blockers.map(g => (
              <span key={g} className="text-xs px-2 py-0.5 bg-amber-100 text-amber-800 rounded border border-amber-300 ml-1">
                {g.split('_')[0]}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Capital Unlocks */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-bold text-gray-900 mb-3">Capital Unlocks</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {snapshot.capital_unlocks.map(cu => (
            <CapitalUnlockRow key={cu.capital_type} unlock={cu} />
          ))}
        </div>
      </div>

      {/* Gate Cards */}
      <div className="space-y-3">
        <h3 className="font-bold text-gray-900">12 Gates — Evidence Progress</h3>
        {snapshot.gate_evaluations.map(gate => (
          <GateCard key={gate.gate_id} gate={gate} onUpdateEvidence={handleUpdateEvidence} />
        ))}
      </div>
    </div>
  )
}
