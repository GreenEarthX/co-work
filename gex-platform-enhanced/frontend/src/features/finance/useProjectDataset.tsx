// Screen: Hook (no screen)
/**
 * useProjectDataset — one recorded dataset of a project, from PostgreSQL
 * (GET /api/v1/projects/{id}/datasets/{kind}; alembic 069/071).
 *
 * Until 2026-10-25 fourteen screens held these as per-project dictionaries in
 * code, most with a default (often Wales SAF's figures) for every other
 * project. The figures moved verbatim and UNVERIFIED; the defaults did not. A
 * project with nothing recorded gets `notRecorded`, and the screen says so.
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, Info } from 'lucide-react'
import { getAuthHeader } from '@/lib/authToken'

export interface ProjectDataset<T> {
  data: T | null
  verification: string | null
  loading: boolean
  notRecorded: boolean
  error: string | null
}

export function useProjectDataset<T>(kind: string, projectId: string | null | undefined): ProjectDataset<T> {
  const [state, setState] = useState<ProjectDataset<T>>({
    data: null, verification: null, loading: true, notRecorded: false, error: null,
  })

  useEffect(() => {
    if (!projectId) {
      setState({ data: null, verification: null, loading: false, notRecorded: true, error: null })
      return
    }
    let cancelled = false
    setState(s => ({ ...s, loading: true }))
    fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/datasets/${kind}`, { headers: getAuthHeader() })
      .then(async res => {
        const body = await res.json().catch(() => ({}))
        if (cancelled) return
        if (res.ok) {
          setState({ data: body.payload as T, verification: body.verification_state, loading: false,
                     notRecorded: false, error: null })
        } else if (res.status === 404 && body?.detail?.code === 'NOT_RECORDED') {
          setState({ data: null, verification: null, loading: false, notRecorded: true, error: null })
        } else {
          const d = body?.detail
          setState({ data: null, verification: null, loading: false, notRecorded: false,
                     error: (d && typeof d === 'object' && d.message) || (typeof d === 'string' && d)
                       || `The server answered ${res.status}.` })
        }
      })
      .catch(e => { if (!cancelled) setState({ data: null, verification: null, loading: false, notRecorded: false, error: e.message }) })
    return () => { cancelled = true }
  }, [kind, projectId])

  return state
}

/** The state of a dataset when there is nothing to draw: loading, not recorded, or refused. */
export function DatasetNotice({ ds, what }: { ds: ProjectDataset<unknown>; what: string }) {
  if (ds.loading) return <div className="p-6 text-sm text-[var(--text-muted)]">Loading {what}…</div>
  return (
    <div className="m-6 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/10 dark:text-amber-300">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      {ds.error ? `${what} unavailable: ${ds.error}` : `No ${what} is recorded for this project yet.`}
    </div>
  )
}

/** Shown above figures that nobody has confirmed. */
export function UnverifiedBadge({ verification }: { verification: string | null }) {
  if (verification !== 'UNVERIFIED') return null
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
      title="Recorded, not yet confirmed by the project">
      <AlertTriangle className="h-3 w-3" /> Unverified
    </span>
  )
}
