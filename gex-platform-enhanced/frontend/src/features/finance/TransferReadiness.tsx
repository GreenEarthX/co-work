/**
 * TransferReadiness — Transfer Readiness Index (0-100) for secondary market exit evaluation.
 * Arc gauge score, 4 sub-scores, consent matrix, and timeline to transfer.
 */

import { useState } from 'react'
import {
  ArrowRightLeft, FileCheck, TrendingUp, ShieldCheck, Award,
  CheckCircle2, AlertTriangle, Clock, ChevronDown, ChevronUp,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { CUSTOMER_PROJECTS } from '@/data/customerProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'

// ─────────────────────────────── Types ───────────────────────────────────────

type ConsentStatus = 'CLEAR' | 'CONDITIONAL' | 'REQUIRED' | 'MISSING'

interface ConsentRow {
  asset: string
  assignmentClause: string
  counterpartyConsent: string
  status: ConsentStatus
  timeToClear: string
}

interface SubScore {
  label: string
  score: number
  badge: string
  evidence: string[]
  notes: string
}

interface TransferData {
  overall: number
  assignable: SubScore
  dscrPostTransfer: SubScore
  warrantyTail: SubScore
  gooPorts: SubScore
  consentMatrix: ConsentRow[]
  timeToTransfer: string
}

// ─────────────────────────────── Demo data ────────────────────────────────────

const TRANSFER_DATA: Record<string, TransferData> = {
  proj_lehavre_eng: {
    overall: 88,
    assignable: {
      label: 'Assignable Contracts %',
      score: 92,
      badge: 'HIGH',
      evidence: [
        'Offtake TOTSA: Assignment clause present',
        'EPC Technip Energies: Yes (consent required, 20-day notice)',
        'Grid connection RTE: Yes — automatic upon lender notification',
        'Insurance AXA XL: Fully transferable with 10-day notice',
      ],
      notes: '92% of contracts by value carry explicit assignment provisions. Only the TOTSA offtake requires written consent (non-waivable).',
    },
    dscrPostTransfer: {
      label: 'DSCR Post-Transfer',
      score: 85,
      badge: 'STABLE',
      evidence: [
        'Base case DSCR: 1.58x',
        'Transfer WACC premium applied: +0.8pp',
        'Post-transfer DSCR estimate: 1.44x',
        'Minimum covenant: 1.20x — headroom maintained',
      ],
      notes: 'Transfer premium of +0.8pp WACC applied. DSCR headroom of 24bp above covenant floor. No waiver required.',
    },
    warrantyTail: {
      label: 'Warranty Tail Coverage',
      score: 90,
      badge: 'STRONG',
      evidence: [
        'SOEC stack OEM warranty: 10 years from COD',
        'Years remaining at transfer date: 6 years',
        'EPC defects liability period: 2 years remaining',
        'Performance guarantee: 92% efficiency floor maintained',
      ],
      notes: 'OEM SOEC warranty 10 years. 6 years remaining at transfer date. Warranty survives asset change of ownership under current terms.',
    },
    gooPorts: {
      label: 'GoO / PoS Portability',
      score: 82,
      badge: 'GOOD',
      evidence: [
        'GRTgaz injection licence: 5 business days transfer',
        'AIB GoO registry update: 8 business days',
        'RFNBO certification: Transferable — new holder notification to TÜV Rheinland',
        'French green gas tariff scheme: Assignment subject to CRE approval (30 days)',
      ],
      notes: 'GRTgaz injection licence: 5 days transfer. GoO registry update: 8 days. CRE approval is longest path at 30 days.',
    },
    consentMatrix: [
      { asset: 'Offtake — TOTSA TotalEnergies', assignmentClause: 'Yes', counterpartyConsent: 'Written consent required', status: 'CONDITIONAL', timeToClear: '10–20 business days' },
      { asset: 'EPC Contract — Technip Energies', assignmentClause: 'Yes (with consent)', counterpartyConsent: 'Not to be unreasonably withheld', status: 'CLEAR', timeToClear: '5 business days' },
      { asset: 'Grid Connection — RTE', assignmentClause: 'Yes', counterpartyConsent: 'Automatic on lender notification', status: 'CLEAR', timeToClear: '2 business days' },
      { asset: 'Insurance — AXA XL', assignmentClause: 'Fully transferable', counterpartyConsent: 'Endorsement update only', status: 'CLEAR', timeToClear: '3 business days' },
      { asset: 'PPA — EDF Renouvelables', assignmentClause: 'Yes', counterpartyConsent: 'Consent not unreasonably withheld', status: 'CLEAR', timeToClear: '10 business days' },
    ],
    timeToTransfer: '6–8 weeks',
  },

  proj_bremen_h2: {
    overall: 55,
    assignable: {
      label: 'Assignable Contracts %',
      score: 60,
      badge: 'PARTIAL',
      evidence: [
        'Vattenfall offtake: Consent required — counterparty discretionary',
        'EPC Linde Engineering: No explicit assignment clause',
        'Grid connection TenneT: Conditional on regulator sign-off',
        'Insurance Munich Re: Transferable',
      ],
      notes: '60% of contracts carry assignment provisions. EPC contract gap is material for lender comfort.',
    },
    dscrPostTransfer: {
      label: 'DSCR Post-Transfer',
      score: 52,
      badge: 'STRESSED',
      evidence: [
        'Base case DSCR: 1.34x',
        'Transfer WACC premium applied: +1.0pp',
        'Post-transfer DSCR estimate: 1.18x',
        'Minimum covenant: 1.20x — covenant breach on transfer',
      ],
      notes: 'Post-transfer DSCR of 1.18x falls below 1.20x covenant floor after WACC premium. Requires covenant waiver from lender group.',
    },
    warrantyTail: {
      label: 'Warranty Tail Coverage',
      score: 58,
      badge: 'LIMITED',
      evidence: [
        'PEM electrolyser OEM warranty: 8 years from COD',
        'Years remaining at transfer date: 4 years',
        'Stack degradation risk increases post year 5',
        'EPC defects liability: expired',
      ],
      notes: 'PEM warranty 8y — 4y remaining. Stack degradation risk post-transfer increases buyer exposure. No wrap insurance placed.',
    },
    gooPorts: {
      label: 'GoO / PoS Portability',
      score: 45,
      badge: 'SLOW',
      evidence: [
        'BNetzA hydrogen registry transfer: 15 business days',
        'Custom port setup at Hamburg terminal: 22 business days',
        'RFNBO certification re-notification: Required to Dena',
        'German Green H2 subsidies: Subject to BMWK review on transfer',
      ],
      notes: 'BNetzA registry transfer: 15 days. Custom port setup: 22 days. BMWK review path is longest — not yet tested.',
    },
    consentMatrix: [
      { asset: 'Offtake — Vattenfall Energy', assignmentClause: 'Requires consent', counterpartyConsent: 'Counterparty discretionary', status: 'REQUIRED', timeToClear: '20–30 business days' },
      { asset: 'EPC Contract — Linde Engineering', assignmentClause: 'Not present', counterpartyConsent: 'Renegotiation required', status: 'MISSING', timeToClear: 'TBD — material gap' },
      { asset: 'Grid Connection — TenneT', assignmentClause: 'Conditional', counterpartyConsent: 'BNetzA regulator sign-off', status: 'REQUIRED', timeToClear: '15–25 business days' },
      { asset: 'Insurance — Munich Re', assignmentClause: 'Transferable', counterpartyConsent: 'Endorsement update', status: 'CLEAR', timeToClear: '3 business days' },
      { asset: 'PPA — Vattenfall Wind', assignmentClause: 'Consent required', counterpartyConsent: 'Discretionary', status: 'CONDITIONAL', timeToClear: '15 business days' },
    ],
    timeToTransfer: '3–4 months',
  },

  proj_sansebastian_emethanol: {
    overall: 42,
    assignable: {
      label: 'Assignable Contracts %',
      score: 45,
      badge: 'PARTIAL',
      evidence: [
        'Maersk offtake: Assignment clause missing',
        'EPC contract: Consent required, terms unclear',
        'Grid: Conditional on Spanish regulator',
      ],
      notes: 'Assignment provisions are incomplete. Significant renegotiation likely required before transfer.',
    },
    dscrPostTransfer: {
      label: 'DSCR Post-Transfer',
      score: 40,
      badge: 'AT RISK',
      evidence: [
        'Base case DSCR: 1.22x',
        'Transfer WACC premium: +1.2pp estimated',
        'Post-transfer DSCR: ~1.05x',
        'Covenant floor: 1.20x — breach likely',
      ],
      notes: 'Slim DSCR headroom pre-transfer leaves insufficient buffer for any WACC premium. Equity injection or debt restructuring likely required.',
    },
    warrantyTail: {
      label: 'Warranty Tail Coverage',
      score: 44,
      badge: 'LIMITED',
      evidence: [
        'Electrolyser OEM warranty: 5 years remaining',
        'Fischer-Tropsch reactor: 3 years remaining',
        'No wrap insurance placed',
      ],
      notes: 'Multiple warranty components near expiry. Buyer will face elevated technical risk without new OEM wrap agreements.',
    },
    gooPorts: {
      label: 'GoO / PoS Portability',
      score: 38,
      badge: 'SLOW',
      evidence: [
        'Spanish MITECO registry: 20+ business days',
        'Maersk fuel blending certification: Transfer protocol undefined',
        'RFNBO re-audit required on change of owner',
      ],
      notes: 'Spanish regulatory pathway for GoO transfer is undefined for e-Methanol. Likely requires pilot process with MITECO.',
    },
    consentMatrix: [
      { asset: 'Offtake — Maersk', assignmentClause: 'Not present', counterpartyConsent: 'Full renegotiation', status: 'MISSING', timeToClear: 'TBD' },
      { asset: 'EPC Contract', assignmentClause: 'Requires consent', counterpartyConsent: 'Terms unclear', status: 'REQUIRED', timeToClear: '30+ days' },
      { asset: 'Grid — REE', assignmentClause: 'Conditional', counterpartyConsent: 'Spanish regulator sign-off', status: 'REQUIRED', timeToClear: '20–30 days' },
    ],
    timeToTransfer: '5–7 months',
  },

  proj_rotterdam_nh3: {
    overall: 20,
    assignable: {
      label: 'Assignable Contracts %',
      score: 22,
      badge: 'WEAK',
      evidence: [
        'Most contracts still in term-sheet stage',
        'Assignment provisions not yet negotiated',
      ],
      notes: 'At early development stage, assignment provisions have not been inserted. This is a critical gap to address in final contract drafts.',
    },
    dscrPostTransfer: {
      label: 'DSCR Post-Transfer',
      score: 18,
      badge: 'NOT MODELLED',
      evidence: [
        'Financial model not yet at audit-grade',
        'Offtake terms not finalised — DSCR highly uncertain',
      ],
      notes: 'Insufficient model maturity to estimate post-transfer DSCR. Gate G8 completion required before this metric is meaningful.',
    },
    warrantyTail: {
      label: 'Warranty Tail Coverage',
      score: 20,
      badge: 'NOT PLACED',
      evidence: ['EPC contractor not selected', 'OEM warranty terms not negotiated'],
      notes: 'Technology vendor not locked. Warranty tail coverage cannot be assessed until EPC/OEM contracts are executed.',
    },
    gooPorts: {
      label: 'GoO / PoS Portability',
      score: 22,
      badge: 'NOT MAPPED',
      evidence: ['Netherlands ACM registry onboarding not initiated', 'GoO framework for NH3 under development at AIB'],
      notes: 'No GoO registry enrolment initiated. NH3 PoS framework still being defined at EU level.',
    },
    consentMatrix: [
      { asset: 'Offtake (term sheet only)', assignmentClause: 'Not yet drafted', counterpartyConsent: 'N/A at this stage', status: 'MISSING', timeToClear: 'Requires FID' },
      { asset: 'EPC (vendor not selected)', assignmentClause: 'Not yet drafted', counterpartyConsent: 'N/A', status: 'MISSING', timeToClear: 'Requires EPC award' },
    ],
    timeToTransfer: '>12 months (post-FID)',
  },

  proj_wales_saf: {
    overall: 8,
    assignable: {
      label: 'Assignable Contracts %',
      score: 8,
      badge: 'NOT APPLICABLE',
      evidence: ['Project at pre-FID stage', 'No bankable contracts executed'],
      notes: 'Transfer readiness not applicable at current development stage. No executed contracts in place.',
    },
    dscrPostTransfer: {
      label: 'DSCR Post-Transfer',
      score: 5,
      badge: 'NOT MODELLED',
      evidence: ['No audit-grade financial model', 'Offtake discussions at MOU stage only'],
      notes: 'Transfer scenario analysis deferred until G8 (Audit-Grade Model) is complete.',
    },
    warrantyTail: {
      label: 'Warranty Tail Coverage',
      score: 10,
      badge: 'NOT PLACED',
      evidence: ['Fischer-Tropsch licensor selected but no wrap', 'OEM warranty negotiations not commenced'],
      notes: 'Technology wrap insurance not placed. License agreement only.',
    },
    gooPorts: {
      label: 'GoO / PoS Portability',
      score: 8,
      badge: 'NOT MAPPED',
      evidence: ['UK RTFO / SAF mandate registry undefined for transfer', 'No GoO registry enrolment'],
      notes: 'UK post-Brexit RTFO pathway for SAF GoO transfer not yet established. Regulatory engagement required.',
    },
    consentMatrix: [
      { asset: 'All contracts', assignmentClause: 'Not yet drafted', counterpartyConsent: 'N/A', status: 'MISSING', timeToClear: 'Requires FID + 18 months' },
    ],
    timeToTransfer: 'Not applicable — pre-FID',
  },
}

// ─────────────────────────────── Helpers ─────────────────────────────────────

function arcColor(score: number): string {
  if (score >= 70) return 'stroke-emerald-500'
  if (score >= 40) return 'stroke-amber-400'
  return 'stroke-red-500'
}

function arcTextColor(score: number): string {
  if (score >= 70) return 'text-emerald-600'
  if (score >= 40) return 'text-amber-500'
  return 'text-red-500'
}

function subScoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-600'
  if (score >= 40) return 'text-amber-600'
  return 'text-red-600'
}

function subScoreBarColor(score: number): string {
  if (score >= 70) return 'bg-emerald-500'
  if (score >= 40) return 'bg-amber-400'
  return 'bg-red-500'
}

function consentStatusBadge(status: ConsentStatus) {
  switch (status) {
    case 'CLEAR':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-xs font-semibold"><CheckCircle2 className="w-3 h-3" /> CLEAR</span>
    case 'CONDITIONAL':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-xs font-semibold"><Clock className="w-3 h-3" /> CONDITIONAL</span>
    case 'REQUIRED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-orange-100 border border-orange-300 text-orange-700 text-xs font-semibold"><AlertTriangle className="w-3 h-3" /> REQUIRED</span>
    case 'MISSING':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-xs font-semibold"><AlertTriangle className="w-3 h-3" /> MISSING</span>
  }
}

// ─────────────────────────────── Arc Gauge ───────────────────────────────────

function ArcGauge({ value }: { value: number }) {
  const r = 54
  const circ = 2 * Math.PI * r
  const arc = circ * 0.75
  const dash = (value / 100) * arc
  const cx = 70, cy = 70

  return (
    <svg width={140} height={105} viewBox="0 0 140 105">
      {/* Track */}
      <circle cx={cx} cy={cy} r={r} fill="none" strokeWidth="10"
        className="stroke-[var(--border)]"
        strokeDasharray={`${arc} ${circ}`}
        strokeDashoffset={-circ * 0.125}
        transform={`rotate(-225, ${cx}, ${cy})`}
      />
      {/* Fill */}
      <circle cx={cx} cy={cy} r={r} fill="none" strokeWidth="10"
        strokeLinecap="round"
        className={arcColor(value)}
        strokeDasharray={`${dash} ${circ}`}
        strokeDashoffset={-circ * 0.125}
        transform={`rotate(-225, ${cx}, ${cy})`}
        style={{ transition: 'stroke-dasharray 0.8s ease' }}
      />
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize="28" fontWeight="800"
        className={arcTextColor(value)}
        style={{ fill: 'currentColor' }}>{value}</text>
      <text x={cx} y={cy + 22} textAnchor="middle" fontSize="10" fill="var(--text-muted)">/100</text>
    </svg>
  )
}

// ─────────────────────────────── Sub-score card ───────────────────────────────

const SUB_ICONS = [FileCheck, TrendingUp, ShieldCheck, Award]

function SubScoreCard({ sub, icon: Icon }: { sub: SubScore; icon: React.ElementType }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-card">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-[var(--brand)] shrink-0" />
          <span className="text-xs font-bold text-[var(--text-primary)]">{sub.label}</span>
        </div>
        <span className={`text-xl font-extrabold font-mono ${subScoreColor(sub.score)}`}>{sub.score}</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--border)] overflow-hidden mb-2">
        <div
          className={`h-full rounded-full transition-all duration-700 ${subScoreBarColor(sub.score)}`}
          style={{ width: `${sub.score}%` }}
        />
      </div>
      <span className={`inline-block px-2 py-0.5 rounded-md text-[10px] font-bold border mb-2 ${
        sub.score >= 70 ? 'bg-green-100 border-green-300 text-green-700' :
        sub.score >= 40 ? 'bg-amber-100 border-amber-300 text-amber-700' :
        'bg-red-100 border-red-300 text-red-700'
      }`}>{sub.badge}</span>
      <button
        onClick={() => setExpanded(v => !v)}
        className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors mt-1"
      >
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {expanded ? 'Hide evidence' : 'Show evidence'}
      </button>
      {expanded && (
        <div className="mt-2 space-y-1.5 border-t border-[var(--border)] pt-2">
          {sub.evidence.map((e, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-[var(--text-secondary)]">
              <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0 mt-0.5" />
              {e}
            </div>
          ))}
          <p className="text-xs text-[var(--text-muted)] mt-1.5 italic">{sub.notes}</p>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────── Component ───────────────────────────────────

export function TransferReadiness() {
  const { selectedProjectId } = useSelectedProject()
  const project = CUSTOMER_PROJECTS.find(p => p.id === selectedProjectId) ?? CUSTOMER_PROJECTS[0]
  const data = TRANSFER_DATA[project.id] ?? TRANSFER_DATA['proj_wales_saf']

  const subScores: SubScore[] = [data.assignable, data.dscrPostTransfer, data.warrantyTail, data.gooPorts]

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
              <ArrowRightLeft className="w-6 h-6 text-[var(--brand)]" />
              Transfer Readiness
            </h1>
            <WorkflowBadge state="COMPUTED" />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{project.name} · Secondary Market Exit Evaluation</p>
        </div>
        <WorkflowActions
          state="COMPUTED"
          objectType="Transfer Readiness"
          userRole="analyst"
          projectId={project.id}
          workflowObjectType="TransferReadiness"
          workflowObjectId={`transfer-readiness-${project.id}`}
        />
      </div>

      {/* ── TRI Score card ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-6 shadow-card flex flex-col items-center gap-2">
        <div className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Transfer Readiness Index</div>
        <ArcGauge value={data.overall} />
        <div className={`text-sm font-bold ${arcTextColor(data.overall)}`}>
          {data.overall >= 70 ? 'Transfer Ready' : data.overall >= 40 ? 'Partially Ready — Remediation Required' : 'Not Transfer Ready'}
        </div>
        <p className="text-xs text-[var(--text-muted)] text-center max-w-xs">
          Composite score across assignable contracts, post-transfer DSCR, warranty tail, and GoO portability.
        </p>
      </div>

      {/* ── 4 sub-score cards in 2×2 grid ── */}
      <div className="grid grid-cols-2 gap-4">
        {subScores.map((sub, i) => (
          <SubScoreCard key={sub.label} sub={sub} icon={SUB_ICONS[i]} />
        ))}
      </div>

      {/* ── Consent Matrix ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <div className="border-b border-[var(--border)] px-5 py-3">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">Consent Matrix</h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">Contract-by-contract assignment and counterparty consent status</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface-hover)]">
                <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Asset / Agreement</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Assignment Clause</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Counterparty Consent</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Status</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Time to Clear</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.consentMatrix.map((row, idx) => (
                <tr key={idx} className="hover:bg-[var(--surface-hover)] transition-colors">
                  <td className="py-3 px-4 font-medium text-[var(--text-primary)]">{row.asset}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{row.assignmentClause}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{row.counterpartyConsent}</td>
                  <td className="py-3 px-3">{consentStatusBadge(row.status)}</td>
                  <td className="py-3 px-3 text-[var(--text-muted)] font-mono">{row.timeToClear}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Timeline to Transfer ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-5 shadow-card">
        <h2 className="text-sm font-bold text-[var(--text-primary)] mb-3">Estimated Timeline to Transfer</h2>
        <div className="flex items-center gap-4">
          <div className={`text-3xl font-extrabold font-mono ${arcTextColor(data.overall)}`}>
            {data.timeToTransfer}
          </div>
          <div className="flex-1 text-xs text-[var(--text-muted)] border-l border-[var(--border)] pl-4">
            Estimate based on outstanding consent clearances, regulatory approvals, and GoO registry transfers.
            Assumes all parties act promptly once transfer notice is issued.
            {data.overall < 40 && (
              <span className="block mt-1 font-semibold text-red-600">
                Note: Several critical consent gaps must be resolved before a transfer timeline can be reliably estimated.
              </span>
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
