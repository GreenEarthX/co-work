// Screen: Insurance schedule screen (/insurance-schedule, /finance/insurance-schedule)
/**
 * InsuranceSchedule — Structured insurance program schedule following Playbook §12A.
 * G7 gate evidence with lines, deductibles, endorsements, and completeness tracking.
 */

import { useState } from 'react'
import {
  ShieldCheck, AlertTriangle, CheckCircle2, Clock, XCircle,
  Building2, ChevronDown, ChevronUp,
} from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { useVisibleProjects } from '@/hooks/useVisibleProjects'
import { WorkflowBadge } from '@/components/workflow/WorkflowBadge'
import { WorkflowActions } from '@/components/workflow/WorkflowActions'
import { useProjectDataset, DatasetNotice, UnverifiedBadge } from './useProjectDataset'

// ─────────────────────────────── Types ───────────────────────────────────────

type LineStatus = 'PLACED' | 'QUOTED' | 'REQUIRED' | 'PENDING'

interface InsuranceLine {
  line: string
  insurer: string
  limit: string
  deductible: string
  trigger: string
  status: LineStatus
  renewal: string
  endorsements: string[]
}

interface EndorsementItem {
  name: string
  status: 'PLACED' | 'PENDING' | 'REQUIRED'
  note: string
}

interface G7EvidenceItem {
  item: string
  satisfied: boolean
}

interface InsuranceScheduleData {
  linesActive: number
  totalLimit: string
  annualPremium: string
  nextRenewal: string
  lines: InsuranceLine[]
  endorsements: EndorsementItem[]
  g7Evidence: G7EvidenceItem[]
}

// ─────────────────────────────── Status helpers ───────────────────────────────

function lineStatusBadge(status: LineStatus) {
  switch (status) {
    case 'PLACED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-xs font-semibold"><CheckCircle2 className="w-3 h-3" /> PLACED</span>
    case 'QUOTED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-xs font-semibold"><Clock className="w-3 h-3" /> QUOTED</span>
    case 'PENDING':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-100 border border-blue-300 text-blue-700 text-xs font-semibold"><Clock className="w-3 h-3" /> PENDING</span>
    case 'REQUIRED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-xs font-semibold"><XCircle className="w-3 h-3" /> REQUIRED</span>
  }
}

function endorsementStatusBadge(status: 'PLACED' | 'PENDING' | 'REQUIRED') {
  switch (status) {
    case 'PLACED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-green-100 border border-green-300 text-green-700 text-[10px] font-semibold"><CheckCircle2 className="w-3 h-3" /> PLACED</span>
    case 'PENDING':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 border border-amber-300 text-amber-700 text-[10px] font-semibold"><Clock className="w-3 h-3" /> PENDING</span>
    case 'REQUIRED':
      return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-100 border border-red-300 text-red-700 text-[10px] font-semibold"><AlertTriangle className="w-3 h-3" /> REQUIRED</span>
  }
}

// ─────────────────────────────── Component ───────────────────────────────────

export function InsuranceSchedule() {
  const { selectedProjectId } = useSelectedProject()
  const { projects: visibleProjects } = useVisibleProjects()
  const project = visibleProjects.find(p => p.id === selectedProjectId)
  // project_dataset insurance_schedule (PostgreSQL since 2026-10-25), UNVERIFIED.
  // Every project without an entry used to be shown Wales SAF's schedule.
  const ds = useProjectDataset<InsuranceScheduleData>('insurance_schedule', project?.id)
  if (!project || !ds.data) return <DatasetNotice ds={{ ...ds, loading: ds.loading && !!project }} what="insurance schedule" />
  return <InsuranceScheduleBody project={project} data={ds.data} verification={ds.verification} />
}

function InsuranceScheduleBody({ project, data, verification }: {
  project: ReturnType<typeof useVisibleProjects>['projects'][number]; data: InsuranceScheduleData; verification: string | null
}) {
  const [showEndorsements, setShowEndorsements] = useState(true)

  const placedCount = data.lines.filter(l => l.status === 'PLACED').length
  const quotedCount = data.lines.filter(l => l.status === 'QUOTED').length
  const requiredCount = data.lines.filter(l => l.status === 'REQUIRED' || l.status === 'PENDING').length

  const g7Satisfied = data.g7Evidence.filter(e => e.satisfied).length
  const g7Total = data.g7Evidence.length
  const g7Pct = Math.round((g7Satisfied / g7Total) * 100)

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-6 py-4 shadow-card">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-display text-2xl font-bold text-[var(--text-primary)] flex items-center gap-2">
              <ShieldCheck className="w-6 h-6 text-[var(--brand)]" />
              Insurance Schedule
            </h1>
            <UnverifiedBadge verification={verification} />
            <WorkflowBadge state="COMPUTED" />
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{project.name} · Playbook §12A · G7 Gate Evidence</p>
        </div>
        <WorkflowActions
          state="COMPUTED"
          objectType="Insurance Schedule"
          userRole="analyst"
          projectId={project.id}
          workflowObjectType="InsuranceSchedule"
          workflowObjectId={`insurance-schedule-${project.id}`}
        />
      </div>

      {/* ── Program Summary strip ── */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-4 h-4 text-[var(--brand)]" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Lines Active</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.linesActive}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">of {data.lines.length} required</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Total Limit</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.totalLimit}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Aggregate placed cover</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="w-4 h-4 text-blue-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Annual Premium</span>
          </div>
          <div className="text-3xl font-black text-[var(--text-primary)]">{data.annualPremium}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Total insurance cost</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4 shadow-card">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-amber-600" />
            <span className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-[0.1em]">Next Renewal</span>
          </div>
          <div className="text-2xl font-black text-[var(--text-primary)]">{data.nextRenewal}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">Earliest policy renewal date</div>
        </div>
      </div>

      {/* ── Insurance lines table ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <div className="border-b border-[var(--border)] px-5 py-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">Insurance Program Lines</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              <span className="text-green-600 font-semibold">{placedCount} Placed</span>
              {' · '}
              <span className="text-amber-600 font-semibold">{quotedCount} Quoted</span>
              {' · '}
              <span className="text-red-600 font-semibold">{requiredCount} Required</span>
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--surface-hover)]">
                <th className="text-left py-2.5 px-4 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Line</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Insurer</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Limit</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Deductible</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Trigger</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Status</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Renewal</th>
                <th className="text-left py-2.5 px-3 font-semibold text-[var(--text-muted)] uppercase tracking-[0.08em]">Endorsements</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.lines.map((line, idx) => (
                <tr key={idx} className="hover:bg-[var(--surface-hover)] transition-colors">
                  <td className="py-3 px-4 font-medium text-[var(--text-primary)]">{line.line}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{line.insurer}</td>
                  <td className="py-3 px-3 font-mono text-[var(--text-primary)] font-semibold">{line.limit}</td>
                  <td className="py-3 px-3 text-[var(--text-secondary)]">{line.deductible}</td>
                  <td className="py-3 px-3 text-[var(--text-muted)] max-w-[160px]">{line.trigger}</td>
                  <td className="py-3 px-3">{lineStatusBadge(line.status)}</td>
                  <td className="py-3 px-3 font-mono text-[var(--text-muted)]">{line.renewal}</td>
                  <td className="py-3 px-3">
                    {line.endorsements.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {line.endorsements.map((e, i) => (
                          <span key={i} className="inline-block px-1.5 py-0.5 rounded bg-[var(--border)] text-[var(--text-muted)] text-[10px]">{e}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-[var(--text-muted)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Endorsements panel ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-card overflow-hidden">
        <button
          onClick={() => setShowEndorsements(v => !v)}
          className="w-full border-b border-[var(--border)] px-5 py-3 flex items-center justify-between hover:bg-[var(--surface-hover)] transition-colors"
        >
          <div>
            <h2 className="text-sm font-bold text-[var(--text-primary)] text-left">Lender Endorsement Requirements</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5 text-left">Key endorsements required by senior lender group for financial close</p>
          </div>
          {showEndorsements ? <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />}
        </button>
        {showEndorsements && (
          <div className="divide-y divide-[var(--border)]">
            {data.endorsements.map((end, idx) => (
              <div key={idx} className="px-5 py-3.5 flex items-start gap-4">
                <div className="shrink-0 pt-0.5">{endorsementStatusBadge(end.status)}</div>
                <div>
                  <div className="text-xs font-semibold text-[var(--text-primary)]">{end.name}</div>
                  <div className="text-xs text-[var(--text-muted)] mt-0.5">{end.note}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── G7 Gate Completeness ── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-5 py-5 shadow-card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">G7 Gate Completeness</h2>
          <span className={`text-sm font-bold font-mono ${g7Pct >= 75 ? 'text-emerald-600' : g7Pct >= 40 ? 'text-amber-600' : 'text-red-600'}`}>
            {g7Pct}% ({g7Satisfied}/{g7Total})
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-[var(--border)] overflow-hidden mb-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${g7Pct >= 75 ? 'bg-emerald-500' : g7Pct >= 40 ? 'bg-amber-400' : 'bg-red-500'}`}
            style={{ width: `${g7Pct}%` }}
          />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {data.g7Evidence.map((item, idx) => (
            <div key={idx} className="flex items-center gap-2 text-xs">
              {item.satisfied
                ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                : <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />}
              <span className={item.satisfied ? 'text-[var(--text-secondary)]' : 'text-[var(--text-muted)]'}>
                {item.item}
              </span>
            </div>
          ))}
        </div>
        {g7Pct < 100 && (
          <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
            <AlertTriangle className="w-3.5 h-3.5 inline mr-1.5 text-amber-600" />
            <strong>{g7Total - g7Satisfied} item{g7Total - g7Satisfied !== 1 ? 's' : ''}</strong> outstanding before G7 gate can be confirmed as complete.
          </div>
        )}
      </div>

    </div>
  )
}
