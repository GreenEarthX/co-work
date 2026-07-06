// Screen: route guard wrapper — sensitive project-finance routes (Ticket 1a)
//
// Layer 2 of three (menu visibility · ROUTE GUARD · backend 403). If a user
// manually types a sensitive URL, this blocks the page with an explicit state:
//   - no project selected        → "Project required"
//   - not authorised             → "Access denied" (with the reason)
//   - authorised                 → renders the screen
//
// The backend remains the real boundary (it 403s the data even if this guard is
// bypassed). When the backend check is unreachable, the guard degrades to the
// client-side role heuristic — still safe, because the data itself stays
// protected server-side.

import { useEffect, useState, type ReactNode } from 'react'
import { ShieldAlert, FolderSearch, Loader2 } from 'lucide-react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { checkFinanceEntitlement } from '@/lib/api/entitlements'

type State =
  | { kind: 'loading' }
  | { kind: 'no-project' }
  | { kind: 'allowed' }
  | { kind: 'denied'; reason: string }

export function FinanceRouteGuard({ routeLabel, children }: { routeLabel: string; children: ReactNode }) {
  const { selectedProjectId } = useSelectedProject()
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    if (!selectedProjectId) { setState({ kind: 'no-project' }); return }
    setState({ kind: 'loading' })
    checkFinanceEntitlement(selectedProjectId)
      .then(res => {
        if (cancelled) return
        setState(res.allowed ? { kind: 'allowed' } : { kind: 'denied', reason: res.reason })
      })
      .catch(() => {
        if (cancelled) return
        // FAIL CLOSED: if authorization cannot be verified, DENY. No client-side
        // role heuristic — sensitive views must never open on an unverified check.
        setState({ kind: 'denied', reason: 'Authorization could not be verified (fail-closed).' })
      })
    return () => { cancelled = true }
  }, [selectedProjectId])

  if (state.kind === 'loading') {
    return (
      <div className="flex h-48 items-center justify-center gap-2 text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="font-mono text-[11px] uppercase tracking-[0.08em]">Checking authorization…</span>
      </div>
    )
  }

  if (state.kind === 'no-project') {
    return (
      <div className="mx-auto max-w-md border border-l-2 border-slate-300 border-l-amber-600 bg-white dark:bg-slate-950 px-4 py-5 mt-8">
        <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300">
          <FolderSearch className="h-4 w-4" />
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.12em]">Project required</span>
        </div>
        <p className="mt-2 font-mono text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
          {routeLabel} is a project-scoped finance view. Select a project first — finance
          entitlements are granted per project, not globally.
        </p>
      </div>
    )
  }

  if (state.kind === 'denied') {
    return (
      <div className="mx-auto max-w-md border border-l-2 border-slate-300 border-l-red-700 bg-white dark:bg-slate-950 px-4 py-5 mt-8">
        <div className="flex items-center gap-2 text-red-700 dark:text-red-300">
          <ShieldAlert className="h-4 w-4" />
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.12em]">Access denied</span>
        </div>
        <p className="mt-2 font-mono text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
          {routeLabel} exposes project-finance-sensitive content. It requires a finance role
          (Finance/Treasury, Executive, Bank, DFI, Insurer) or a project-scoped FINANCE_REVIEW grant.
        </p>
        <p className="mt-2 font-mono text-[10px] text-slate-400">reason: {state.reason}</p>
      </div>
    )
  }

  return <>{children}</>
}
