// Screen: Transfer readiness screen (/transfer-readiness, /finance/transfer-readiness)
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
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'
import { useProjectDataset, DatasetNotice, UnverifiedBadge } from './useProjectDataset'

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
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  // project_dataset transfer_readiness (PostgreSQL since 2026-10-25), UNVERIFIED.
  // Every project without an entry used to be shown Wales SAF's evaluation.
  const ds = useProjectDataset<TransferData>('transfer_readiness', project?.id)
  if (!project || !ds.data) return <DatasetNotice ds={{ ...ds, loading: ds.loading && !!project }} what="transfer readiness evaluation" />
  return <TransferReadinessBody project={project} data={ds.data} verification={ds.verification} />
}

function TransferReadinessBody({ project, data, verification }: {
  project: ReturnType<typeof useVisibleProjects>['projects'][number]; data: TransferData; verification: string | null
}) {

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
            <UnverifiedBadge verification={verification} />
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
        <div className="text-xs font-bold uppercase tracking-[0.14em] text-[var(--text-muted)]">Transfer Readiness Index (indicative)</div>
        <ArcGauge value={data.overall} />
        <div className={`text-sm font-bold ${arcTextColor(data.overall)}`}>
          {data.overall >= 70 ? 'Transfer Ready' : data.overall >= 40 ? 'Partially Ready — Remediation Required' : 'Not Transfer Ready'}
        </div>
        <p className="text-xs text-[var(--text-muted)] text-center max-w-xs">
          Indicative composite across assignable contracts, post-transfer debt cover, warranty tail and portability of guarantees of origin. A screening aid for a sale of the project, not a gate decision: the gates and their evidence decide readiness.
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
