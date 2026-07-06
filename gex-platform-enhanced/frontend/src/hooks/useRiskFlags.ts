// Screen: Hook (no screen)
/**
 * useRiskFlags — server-filtered structured risk flags for one project.
 *
 * Fetches GET /api/v1/projects/{id}/risk-flags with the caller's bearer
 * token. The SERVER decides which flags this user may see (classification ×
 * stakeholding × clearance) — the static copy in customerProjects.ts is a
 * dev fallback only and must never be treated as the authoritative list.
 */

import { useQuery } from '@tanstack/react-query'
import { useUserRole } from '@/contexts/UserRoleContext'
import { getProjectById, type RiskFlag } from '@/data/customerProjects'

async function fetchRiskFlags(projectId: string, token: string): Promise<RiskFlag[]> {
  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/risk-flags`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`risk-flags: ${res.status}`)
  const json = await res.json() as { flags: RiskFlag[] }
  return json.flags
}

export interface UseRiskFlagsResult {
  flags: RiskFlag[]
  isStaticFallback: boolean
}

export function useRiskFlags(projectId: string): UseRiskFlagsResult {
  const { authSession, sessionTier } = useUserRole()
  const token = authSession?.token ?? null

  const { data, isError } = useQuery<RiskFlag[]>({
    queryKey: ['projects', projectId, 'risk-flags', token],
    queryFn: () => fetchRiskFlags(projectId, token!),
    enabled: !!token && sessionTier === 'authenticated' && !!projectId,
    staleTime: 2 * 60 * 1000,
    retry: import.meta.env.DEV ? 0 : 2,
  })

  const staticFlags = getProjectById(projectId)?.bankability.risk_flags ?? []
  return {
    flags: data ?? staticFlags,
    isStaticFallback: !data && (isError || staticFlags.length > 0),
  }
}
