import { useEffect, useState } from 'react'
import { ShieldAlert, ArrowRight, AlertTriangle, MessagesSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { adversarialReviewsAPI, type AdversarialReviewSummary } from '@/lib/adversarialReviewsApi'

interface AdversarialReviewEntryCardProps {
  projectId: string
  actorType?: string
  title?: string
  compact?: boolean
}

export function AdversarialReviewEntryCard({
  projectId,
  actorType,
  title = 'Adversarial Review',
  compact = false,
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

  if (!summary && error && compact) {
    return (
      <button
        onClick={() => navigate(href)}
        className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"
      >
        <ShieldAlert className="h-4 w-4" />
        Open challenge review
      </button>
    )
  }

  if (compact) {
    return (
      <button
        onClick={() => navigate(href)}
        className="w-full rounded-xl border border-amber-200 bg-gradient-to-r from-amber-50 to-white px-4 py-3 text-left transition-colors hover:border-amber-300"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-amber-700">
              <ShieldAlert className="h-3.5 w-3.5" />
              {title}
            </div>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              {summary
                ? `${summary.open_reviews} open review${summary.open_reviews === 1 ? '' : 's'} · ${summary.blocking_findings} blocking finding${summary.blocking_findings === 1 ? '' : 's'}`
                : 'Open the challenge workspace'}
            </p>
            <p className="mt-0.5 text-xs text-gray-600">
              {summary
                ? `${summary.escalated_reviews} escalated · ${summary.critical_findings} critical · ${summary.net_trust_delta >= 0 ? '+' : ''}${summary.net_trust_delta} trust delta`
                : 'Capture skeptical findings, handoffs, and escalation notes.'}
            </p>
          </div>
          <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-700" />
        </div>
      </button>
    )
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 via-white to-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-amber-700">
            <ShieldAlert className="h-4 w-4" />
            {title}
          </div>
          <h3 className="mt-1 text-lg font-bold text-gray-900">
            Challenge the current setup before it hardens into process
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Record false premises, missing evidence, trust breaks, and clean handoff notes without touching the finance-engine boundary.
          </p>
        </div>
        <button
          onClick={() => navigate(href)}
          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-gray-800"
        >
          Open workspace
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-white bg-white/80 px-4 py-3">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">Open reviews</div>
          <div className="mt-1 text-2xl font-black text-gray-900">{summary?.open_reviews ?? '—'}</div>
          <div className="mt-1 text-xs text-gray-500">Active adversarial challenges on this project.</div>
        </div>
        <div className="rounded-lg border border-white bg-white/80 px-4 py-3">
            <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
            Blocking findings
          </div>
          <div className="mt-1 text-2xl font-black text-gray-900">{summary?.blocking_findings ?? '—'}</div>
          <div className="mt-1 text-xs text-gray-500">Issues still open across UX, logic, evidence, or handoffs.</div>
        </div>
        <div className="rounded-lg border border-white bg-white/80 px-4 py-3">
          <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-[0.12em] text-gray-500">
            <MessagesSquare className="h-3.5 w-3.5 text-blue-600" />
            Escalations
          </div>
          <div className="mt-1 text-2xl font-black text-gray-900">{summary?.escalated_reviews ?? '—'}</div>
          <div className="mt-1 text-xs text-gray-500">Reviews that already need cross-functional action.</div>
        </div>
      </div>

      {error && (
        <p className="mt-3 text-xs text-amber-700">
          Summary unavailable right now. The review workspace is still reachable.
        </p>
      )}
    </div>
  )
}
