/**
 * Pre-FID, derived and returns queries are never shown from cache (handoff v4, task 9).
 *
 * The server sends these with `Cache-Control: no-store` (backend app/core/no_store.py).
 * Here, for every query whose key starts with one of SENSITIVE_ROOTS:
 *   - nothing is kept once no screen uses it (gcTime 0), and a screen that mounts
 *     always refetches, so a revoked share is never shown from an earlier answer;
 *   - a 403 or 503 clears the data the query held, so the refusal or outage is
 *     shown, never the figures from before it.
 */
import { QueryCache, QueryClient, type Query } from '@tanstack/react-query'

export const SENSITIVE_ROOTS = [
  'packages', 'devex-brief', 'devex-shares', 'spend-wave', 'returns-cases', 'returns-shares',
  'returns-case', 'pre-cod-metrics', 'capital-bridge', 'lineage',
] as const

export function isSensitive(queryKey: readonly unknown[]): boolean {
  return typeof queryKey[0] === 'string' && (SENSITIVE_ROOTS as readonly string[]).includes(queryKey[0])
}

export function failureStatus(error: unknown): number | undefined {
  const e = error as { status?: number; response?: { status?: number }; message?: string } | null
  const status = e?.status ?? e?.response?.status
  if (typeof status === 'number') return status
  const m = /\b(403|503)\b/.exec(e?.message ?? '')
  return m ? Number(m[1]) : undefined
}

export function clearOnRefusal(error: unknown, query: Query<unknown, unknown, unknown, readonly unknown[]>): boolean {
  const status = failureStatus(error)
  if (!isSensitive(query.queryKey) || (status !== 403 && status !== 503)) return false
  // Keep the error, drop the data: the screen shows the refusal, not the old figures.
  query.setState({ data: undefined, dataUpdatedAt: 0 })
  return true
}

export function createQueryClient(): QueryClient {
  const client = new QueryClient({ queryCache: new QueryCache({ onError: (error, query) => { clearOnRefusal(error, query) } }) })
  for (const root of SENSITIVE_ROOTS) {
    client.setQueryDefaults([root], { gcTime: 0, staleTime: 0, refetchOnMount: 'always' })
  }
  return client
}
