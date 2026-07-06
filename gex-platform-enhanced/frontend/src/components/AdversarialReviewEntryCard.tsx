// Screen: Shared component — Adversarial review screen
import { useEffect, useState } from 'react'
import { ShieldAlert, ArrowRight, AlertTriangle, MessagesSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { adversarialReviewsAPI, type AdversarialReviewSummary } from '@/lib/adversarialReviewsApi'

interface AdversarialReviewEntryCardProps {
  projectId: string
  actorType?: string
  title?: string
  compact?: boolean
  /**
   * False when the card is rendered INSIDE the review workspace itself —
   * hides the "Open workspace" CTA, which would navigate to the page the
   * user is already on (a self-referential dead end).
   */
  linkToWorkspace?: boolean
}

export function AdversarialReviewEntryCard({
  projectId,
  actorType,
  title = 'Adversarial Review',
  compact = false,
  linkToWorkspace = true,
}: AdversarialReviewEntryCardProps) {
  const navigate = useNavigate()
  const [summary, setSummary] = useState<AdversarialReviewSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    adversarialReviewsAPI.getProjectSummary(projectId, actorType)
      .then(data => {
        if (!active) return
        setSummary(data)
        setError(null)
      })
      .catch(err => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Unable to load adversarial review summary')
      })
    return () => {
      active = false
    }
  }, [actorType, projectId])

  const href = `/adversarial-review?project=${encodeURIComponent(projectId)}${actorType ? `&actor=${encodeURIComponent(actorType)}` : ''}`

  // Tone derived from data so color appears only when there is signal.
  const hasFindings = !!summary && (summary.blocking_findings > 0 || summary.critical_findings > 0)
  const hasReviews  = !!summary && summary.open_reviews > 0
  const bandClass   = hasFindings ? 'border-l-amber-600' : hasReviews ? 'border-l-sky-600' : 'border-l-slate-400'

  if (!summary && error && compact) {
    return (
      <button
        onClick={() => navigate(href)}
        className={`inline-flex items-center gap-2 border border-l-2 border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 ${bandClass}`}
      >
        open challenge review →
      </button>
    )
  }

  if (compact) {
    return (
      <button
        onClick={() => navigate(href)}
        className={`w-full border border-l-2 border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-900 ${bandClass}`}
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-600 dark:text-slate-400">
            {title}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">open →</span>
        </div>
        <div className="mt-1 grid grid-cols-3 gap-2 font-mono text-[11px] tabular-nums text-slate-800 dark:text-slate-200">
          <span><span className="text-slate-500">open</span> {summary?.open_reviews ?? '—'}</span>
          <span><span className="text-slate-500">blocking</span> {summary?.blocking_findings ?? '—'}</span>
          <span><span className="text-slate-500">critical</span> {summary?.critical_findings ?? '—'}</span>
        </div>
        <div className="mt-0.5 grid grid-cols-3 gap-2 font-mono text-[10px] text-slate-500 dark:text-slate-400">
          <span>escalated {summary?.escalated_reviews ?? '—'}</span>
          <span>trust Δ {summary ? (summary.net_trust_delta >= 0 ? '+' : '') + summary.net_trust_delta : '—'}</span>
          <span />
        </div>
      </button>
    )
  }

  // Full variant — token-based flat panel matching the /projects aesthetic.
  // Colour appears only as the left signal band (Hidalgo: colour = signal);
  // category and hierarchy are carried by type, not background washes.
  return (
    <div className={`border border-l-2 border-[var(--border)] bg-[var(--surface)] p-4 ${bandClass}`}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            <ShieldAlert className="h-3.5 w-3.5" />
            {title}
          </div>
          <h3 className="mt-1 text-sm font-bold text-[var(--text-primary)]">
            Challenge the current setup before it hardens into process
          </h3>
          <p className="mt-0.5 text-xs leading-snug text-[var(--text-secondary)]">
            Record false premises, missing evidence, trust breaks, and clean handoff notes without touching the finance-engine boundary.
          </p>
        </div>
        {linkToWorkspace && (
          <button
            onClick={() => navigate(href)}
            className="inline-flex shrink-0 items-center gap-1.5 border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-primary)] transition-colors hover:bg-[var(--surface)]"
          >
            Open workspace
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="mt-3 grid gap-px sm:grid-cols-3 border border-[var(--border)] bg-[var(--border)]">
        <div className="bg-[var(--surface)] px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">Open reviews</div>
          <div className="mt-0.5 font-mono text-xl font-bold tabular-nums text-[var(--text-primary)]">{summary?.open_reviews ?? '—'}</div>
          <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">Active adversarial challenges on this project.</div>
        </div>
        <div className="bg-[var(--surface)] px-3 py-2">
          <div className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
            <AlertTriangle className="h-3 w-3 text-amber-600" />
            Blocking findings
          </div>
          <div className="mt-0.5 font-mono text-xl font-bold tabular-nums text-[var(--text-primary)]">{summary?.blocking_findings ?? '—'}</div>
          <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">Issues still open across UX, logic, evidence, or handoffs.</div>
        </div>
        <div className="bg-[var(--surface)] px-3 py-2">
          <div className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
            <MessagesSquare className="h-3 w-3 text-sky-600" />
            Escalations
          </div>
          <div className="mt-0.5 font-mono text-xl font-bold tabular-nums text-[var(--text-primary)]">{summary?.escalated_reviews ?? '—'}</div>
          <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">Reviews that already need cross-functional action.</div>
        </div>
      </div>

      {error && (
        <p className="mt-2 font-mono text-[10px] text-amber-700">
          Summary unavailable right now{linkToWorkspace ? ' — the review workspace is still reachable.' : '.'}
        </p>
      )}
    </div>
  )
}
