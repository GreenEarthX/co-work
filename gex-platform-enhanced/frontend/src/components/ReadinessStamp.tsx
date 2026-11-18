// Screen: Shared component (no screen)
/**
 * The identity and freshness of a gate-engine result (handoff v4, task 1).
 * A STALE result is shown as stale and supports no pass/fail judgement; a
 * project with no evaluation reads "not evaluated", never a figure.
 */
export interface Readiness {
  project_id: string
  scenario: string
  status: 'CURRENT' | 'STALE' | 'NOT_EVALUATED'
  evaluated_at: string | null
  rules_version: string | null
  evidence_fingerprint: string | null
  stale_reasons: string[]
  supports_judgement: boolean
  state: string | null
  message: string | null
}

const STYLE: Record<Readiness['status'], string> = {
  CURRENT: 'border-emerald-300 text-emerald-800 bg-emerald-50',
  STALE: 'border-amber-400 text-amber-900 bg-amber-50',
  NOT_EVALUATED: 'border-slate-300 text-slate-700 bg-slate-50',
}

export function ReadinessStamp({ readiness }: { readiness?: Readiness | null }) {
  if (!readiness) return null
  return (
    <div data-testid="readiness-stamp" className={`rounded-lg border px-3 py-2 text-xs ${STYLE[readiness.status]}`}>
      <span className="font-bold uppercase tracking-wide">
        {readiness.status === 'CURRENT' ? 'Current' : readiness.status === 'STALE' ? 'Stale' : 'Not evaluated'}
      </span>
      {readiness.status !== 'NOT_EVALUATED' && (
        <span className="ml-2 font-mono">
          state {readiness.state ?? '—'} · evaluated {readiness.evaluated_at ?? '—'} · rules {readiness.rules_version ?? '—'} ·
          {' '}evidence {readiness.evidence_fingerprint ? readiness.evidence_fingerprint.slice(0, 12) : 'unknown'}
        </span>
      )}
      {readiness.message && <p className="mt-1">{readiness.message}</p>}
    </div>
  )
}
