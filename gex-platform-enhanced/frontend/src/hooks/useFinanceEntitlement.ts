// Screen: hook (no screen) — finance entitlement check for the selected project
//
// Powers screen-internal redaction (e.g. ProjectTimeline drawdown/CP rows) and
// route guards. Authoritative check is the backend; degrades to the client role
// heuristic only when the backend is unreachable (data stays 403-protected).

import { useEffect, useState } from 'react'
import { checkFinanceEntitlement } from '@/lib/api/entitlements'

export function useFinanceEntitlement(projectId: string | null | undefined): {
  allowed: boolean
  loading: boolean
} {
  const [state, setState] = useState<{ allowed: boolean; loading: boolean }>({ allowed: false, loading: true })

  useEffect(() => {
    let cancelled = false
    if (!projectId) { setState({ allowed: false, loading: false }); return }
    setState({ allowed: false, loading: true })
    checkFinanceEntitlement(projectId)
      .then(res => { if (!cancelled) setState({ allowed: res.allowed, loading: false }) })
      // FAIL CLOSED: unverifiable → not entitled (sensitive layers stay redacted).
      .catch(() => { if (!cancelled) setState({ allowed: false, loading: false }) })
    return () => { cancelled = true }
  }, [projectId])

  return state
}
