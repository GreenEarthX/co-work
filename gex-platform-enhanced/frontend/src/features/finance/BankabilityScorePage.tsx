/**
 * BankabilityScorePage — R5 (Architectural Reform v6.0)
 *
 * PRIMARY VIEW: Status + Deal-Killers + Blockers + Next Action
 * SECONDARY:    Collapsible "Advanced: View Scores" panel (scores still exist, demoted)
 *
 * Replaces the arc-gauge-first layout with a decision-first layout:
 *   1. Committee Readiness binary (READY / NOT READY / CONDITIONAL)
 *   2. Active deal-killers with plain language and resolution links
 *   3. Items needing attention (verification gaps)
 *   4. Next action with direct link
 *   5. [Collapsible] Raw and effective scores for analysts
 */

import { useState } from 'react'
import {
  CheckCircle, XOctagon, AlertTriangle, ChevronDown, ChevronUp,
  ArrowRight, ShieldCheck, BarChart2, RefreshCw,
} from 'lucide-react'
import { DealKillerBanner, useActiveKillers } from '@/components/DealKillerBanner'
import { VerificationBadge } from '@/components/VerificationBadge'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS, getProjectById } from '@/data/customerProjects'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { useNavigate } from 'react-router-dom'
import { MoleculeGatingAlert } from '@/components/finance/MoleculeGatingAlert'

// ─── Types ────────────────────────────────────────────────────────────────────

interface GateEffectiveScore {
  gate_id:          string
  raw_score:        number
  effective_score:  number
  AUDITED:          number
  CONFIRMED:        number
  SUBMITTED:        number
  UNVERIFIED:       number
}

interface AttentionItem {
  gate:    string
  issue:   string
  action:  string
  page:    string
}

// ─── Demo data helpers ────────────────────────────────────────────────────────

const DEMO_GATE_SCORES: GateEffectiveScore[] = [
  { gate_id: 'G0', raw_score: 100, effective_score: 90, AUDITED: 1, CONFIRMED: 3, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G1', raw_score: 95,  effective_score: 76, AUDITED: 1, CONFIRMED: 2, SUBMITTED: 1, UNVERIFIED: 0 },
  { gate_id: 'G2', raw_score: 90,  effective_score: 85, AUDITED: 2, CONFIRMED: 2, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G3', raw_score: 80,  effective_score: 44, AUDITED: 0, CONFIRMED: 1, SUBMITTED: 2, UNVERIFIED: 1 },
  { gate_id: 'G4', raw_score: 78,  effective_score: 39, AUDITED: 0, CONFIRMED: 3, SUBMITTED: 2, UNVERIFIED: 1 },
  { gate_id: 'G5', raw_score: 45,  effective_score: 11, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 4 },
  { gate_id: 'G6', raw_score: 40,  effective_score: 10, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 1, UNVERIFIED: 2 },
  { gate_id: 'G7', raw_score: 30,  effective_score:  8, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 3 },
  { gate_id: 'G8', raw_score: 68,  effective_score: 65, AUDITED: 1, CONFIRMED: 5, SUBMITTED: 0, UNVERIFIED: 0 },
  { gate_id: 'G9', raw_score: 20,  effective_score:  9, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 2, UNVERIFIED: 2 },
  { gate_id: 'G10', raw_score: 10, effective_score:  3, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 4 },
  { gate_id: 'G11', raw_score: 5,  effective_score:  1, AUDITED: 0, CONFIRMED: 0, SUBMITTED: 0, UNVERIFIED: 2 },
]

const DEMO_ATTENTION: AttentionItem[] = [
  {
    gate: 'G5', issue: '4 evidence items are UNVERIFIED — EPC risk gate cannot advance.',
    action: 'Submit EPC contract and performance guarantee for third-party confirmation.',
    page: '/finance/stage-gates',
  },
  {
    gate: 'G6', issue: 'No independent engineer appointed. Gate cannot progress.',
    action: 'Appoint named IE firm and confirm scope.',
    page: '/finance/stage-gates',
  },
  {
    gate: 'G7', issue: 'Insurance programme not placed. All items UNVERIFIED.',
    action: 'Bind CAR/EAR and DSU insurance lines.',
    page: '/finance/insurance',
  },
]

// ─── Main component ───────────────────────────────────────────────────────────

export default function BankabilityScorePage() {
  const navigate = useNavigate()
  const { selectedProjectId } = useSelectedProject()
  const project = getProjectById(selectedProjectId) ?? CUSTOMER_PROJECTS[0]
  const { killers } = useActiveKillers(project.id)

  const [showAdvanced, setShowAdvanced] = useState(false)

  const fatalKillers = killers.filter(k => k.severity === 'FATAL')
  const readiness =
    fatalKillers.length > 0 ? 'NOT_READY' :
    killers.length > 0      ? 'CONDITIONAL' :
                              'READY'

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-gray-900">Bankability Status</h1>
          <p className="text-xs text-gray-500 mt-0.5">{project.name}</p>
        </div>
        <button className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-600 hover:bg-gray-50">
          <RefreshCw className="w-3.5 h-3.5" />
          Re-evaluate
        </button>
      </div>

      {/* ── 0. Molecule-specific hazmat gating (NH3 / SAF only) ── */}
      <MoleculeGatingAlert project={project} />

      {/* ── 1. Deal-Killer Banner (always first) ── */}
      <DealKillerBanner killers={killers} projectName={project.name} />

      {/* ── 2. Committee Readiness — binary signal ── */}
      <ReadinessBadge readiness={readiness} killerCount={killers.length} />

      {/* ── 3. Attention items (verification gaps) ── */}
      {DEMO_ATTENTION.length > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <h2 className="text-sm font-bold text-amber-800">
              Attention required — {DEMO_ATTENTION.length} verification gaps
            </h2>
          </div>
          {DEMO_ATTENTION.map(item => (
            <div key={item.gate} className="flex items-start gap-3 py-1.5 border-t border-amber-200 first:border-0">
              <span className="mt-0.5 flex-shrink-0 text-xs font-bold text-amber-700 w-6">{item.gate}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-amber-800">{item.issue}</p>
                <p className="text-xs text-amber-600 mt-0.5">{item.action}</p>
              </div>
              <button
                onClick={() => navigate(item.page)}
                className="flex-shrink-0 text-xs font-semibold text-amber-700 hover:text-amber-900 underline underline-offset-2 flex items-center gap-0.5"
              >
                Go <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          ))}
        </section>
      )}

      {/* ── 4. Next action ── */}
      <NextAction readiness={readiness} killerCount={killers.length} navigate={navigate} />

      {/* ── 5. Advanced: scores (collapsible, demoted) ── */}
      <div className="rounded-lg border border-gray-200 overflow-hidden">
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-600"
        >
          <div className="flex items-center gap-2">
            <BarChart2 className="w-4 h-4 text-gray-400" />
            Advanced: Gate scores
            <InfoTooltip text="Raw scores reflect evidence completion. Effective scores are weighted by verification state (UNVERIFIED×0.25 → AUDITED×1.00). State machine uses effective scores." />
          </div>
          {showAdvanced
            ? <ChevronUp className="w-4 h-4 text-gray-400" />
            : <ChevronDown className="w-4 h-4 text-gray-400" />
          }
        </button>

        {showAdvanced && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-2 font-semibold text-gray-500">Gate</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-500">Raw</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-700">Effective</th>
                  <th className="text-right px-3 py-2 font-semibold text-green-600">Aud</th>
                  <th className="text-right px-3 py-2 font-semibold text-blue-600">Conf</th>
                  <th className="text-right px-3 py-2 font-semibold text-amber-600">Sub</th>
                  <th className="text-right px-3 py-2 font-semibold text-gray-400">Unver</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_GATE_SCORES.map(g => (
                  <tr key={g.gate_id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-semibold text-gray-700">{g.gate_id}</td>
                    <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{g.raw_score}</td>
                    <td className="px-3 py-2 text-right font-semibold text-gray-800 tabular-nums">
                      {g.effective_score}
                      <span className="ml-1 text-gray-400 font-normal">
                        ({Math.round((g.effective_score / Math.max(g.raw_score, 1)) * 100)}%)
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-green-700 tabular-nums">{g.AUDITED}</td>
                    <td className="px-3 py-2 text-right text-blue-700 tabular-nums">{g.CONFIRMED}</td>
                    <td className="px-3 py-2 text-right text-amber-600 tabular-nums">{g.SUBMITTED}</td>
                    <td className="px-3 py-2 text-right text-gray-400 tabular-nums">{g.UNVERIFIED}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-2 bg-gray-50 border-t border-gray-200">
              <p className="text-[10px] text-gray-400">
                Effective = Raw × mean(verification weights). State machine transitions use effective scores.
                Raw scores are retained for reference only.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ReadinessBadge({
  readiness, killerCount,
}: { readiness: string; killerCount: number }) {
  if (readiness === 'READY') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-green-300 bg-green-50 px-4 py-3">
        <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-bold text-green-800">READY — No blocking items</p>
          <p className="text-xs text-green-600 mt-0.5">
            All deal-killers resolved. Project may proceed to committee.
          </p>
        </div>
      </div>
    )
  }

  if (readiness === 'CONDITIONAL') {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
        <div>
          <p className="text-sm font-bold text-amber-800">
            CONDITIONAL — {killerCount} critical item{killerCount > 1 ? 's' : ''} require attention
          </p>
          <p className="text-xs text-amber-600 mt-0.5">
            No FATAL killers. CRITICAL items must be formally waived or resolved before committee.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3">
      <XOctagon className="w-5 h-5 text-red-600 flex-shrink-0" />
      <div>
        <p className="text-sm font-bold text-red-800">NOT READY — FATAL deal-killers active</p>
        <p className="text-xs text-red-600 mt-0.5">
          IC Pack export, committee submission, and capital unlock classification are blocked.
        </p>
      </div>
    </div>
  )
}

function NextAction({
  readiness, killerCount, navigate,
}: { readiness: string; killerCount: number; navigate: (path: string) => void }) {
  if (readiness === 'READY') {
    return (
      <div className="flex items-center justify-between rounded-lg border border-green-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-green-600" />
          <span className="text-sm font-semibold text-gray-800">Next: Generate IC Pack</span>
        </div>
        <button
          onClick={() => navigate('/finance/ic-pack')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600 text-white text-xs font-semibold hover:bg-green-700 transition-colors"
        >
          IC Pack Builder <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  if (readiness === 'CONDITIONAL') {
    return (
      <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-semibold text-gray-800">Next: Resolve critical items or obtain formal waivers</span>
        </div>
        <button
          onClick={() => navigate('/finance/stage-gates')}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 text-white text-xs font-semibold hover:bg-amber-700 transition-colors"
        >
          View Gates <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between rounded-lg border border-red-200 bg-white px-4 py-3">
      <div className="flex items-center gap-2">
        <XOctagon className="w-4 h-4 text-red-500" />
        <span className="text-sm font-semibold text-gray-800">Next: Resolve FATAL deal-killers</span>
      </div>
      <button
        onClick={() => navigate('/finance/stage-gates')}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-semibold hover:bg-red-700 transition-colors"
      >
        View Blockers <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
