// Screen: Hook (no screen)
/**
 * useVisibleProjects — server-owned visible project list.
 *
 * Fetches GET /api/v1/projects/visible using the bearer token from the
 * current auth session. Falls back to the static CUSTOMER_PROJECTS list
 * (client-side ABAC filter) only in development when the backend is
 * unreachable. In production the static fallback is never silently used —
 * an isStaticFallback flag is returned to allow UI warnings.
 *
 * Returns:
 *   projects         — visible CustomerProject array (may be empty while loading)
 *   isLoading        — true while the backend request is in flight
 *   isError          — true if the backend returned an error
 *   isStaticFallback — true when the static list is active (dev only)
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects'
import { useUserRole } from '@/contexts/UserRoleContext'

const IS_DEV = import.meta.env.DEV

/** Shape returned by GET /api/v1/projects/visible (VisibleProject). */
interface ServerProject {
  id: string
  name: string
  molecule: string
  location: string
  country: string
  lat: number
  lng: number
  capacity_mtpd: number
  capex_eur: number
  status: string
  phase: string
  completion_date: string
  description: string
  owner_company: string
  associated_companies: string[]
  jurisdiction: string
}

// Runtime-created projects (the on-ramp) have no static detail yet. Build a
// minimal CustomerProject so a freshly-created project is selectable and flows
// into every bridge stop. The rich bankability snapshot is fetched live per
// project; this is just the empty shell the list needs.
function serverToCustomerProject(sp: ServerProject): CustomerProject {
  return {
    id: sp.id,
    name: sp.name,
    molecule: (sp.molecule || 'H2') as CustomerProject['molecule'],
    location: sp.location,
    country: sp.country,
    lat: sp.lat ?? 0,
    lng: sp.lng ?? 0,
    capacity_mtpd: sp.capacity_mtpd ?? 0,
    capex_eur: sp.capex_eur ?? 0,
    status: (['development', 'construction', 'operating', 'commissioning'].includes(sp.status)
      ? sp.status
      : 'development') as CustomerProject['status'],
    phase: sp.phase || 'development',
    completion_date: sp.completion_date || '',
    description: sp.description || '',
    owner_company: sp.owner_company,
    associated_companies: sp.associated_companies ?? [],
    bankability: {
      overall_completion: 0,
      gates: [],
      capital_status: [],
      next_milestone: 'Declare project context and open Gate G1',
      unlocked_capital: [],
      risk_alerts: [],
    },
  }
}

async function fetchVisibleProjects(token: string): Promise<CustomerProject[]> {
  const res = await fetch('/api/v1/projects/visible', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`projects/visible: ${res.status}`)
  const serverList: ServerProject[] = await res.json()

  // Server owns WHICH projects are visible. Static data owns the rich detail
  // shape for seeded projects; runtime (on-ramp) projects fall back to the
  // server-provided shell so they are never silently dropped.
  return serverList.map(sp => CUSTOMER_PROJECTS.find(cp => cp.id === sp.id) ?? serverToCustomerProject(sp))
}

// Static fallback — mirrors the server-side visibility rules client-side.
// Only used when the backend is unreachable in development.
function staticFallback(role: ReturnType<typeof useUserRole>['role'], sessionTier: string): CustomerProject[] {
  if (sessionTier !== 'authenticated') return []

  const caps = role.capabilities ?? []
  const isProsumer = caps.includes('PRODUCE')

  return CUSTOMER_PROJECTS.filter(project => {
    if (role.company_type === 'PRODUCER' || isProsumer) {
      if (project.owner_company === role.company_name) return true
    }
    return project.associated_companies.includes(role.company_name)
  })
}

export interface UseVisibleProjectsResult {
  projects: CustomerProject[]
  isLoading: boolean
  isError: boolean
  isStaticFallback: boolean
  /** True while the authoritative server list is still in flight (initialData
   *  may be showing the static fallback, which excludes runtime projects). */
  isFetching: boolean
}

export function useVisibleProjects(): UseVisibleProjectsResult {
  const { role, sessionTier, authSession } = useUserRole()
  const token = authSession?.token ?? null

  const fallback = useMemo(
    () => staticFallback(role, sessionTier),
    [role, sessionTier],
  )

  const { data, isLoading, isError, isFetching } = useQuery<CustomerProject[]>({
    queryKey: ['projects', 'visible', token],
    queryFn: () => fetchVisibleProjects(token!),
    enabled: !!token && sessionTier === 'authenticated',
    staleTime: 2 * 60 * 1000,
    retry: IS_DEV ? 0 : 2,
    // Static list is instant — show it immediately while the server refines visibility
    initialData: fallback.length > 0 ? fallback : undefined,
    initialDataUpdatedAt: 0, // always consider stale so the server fetch still runs
  })

  const isStaticFallback = isError || (!data && fallback.length > 0)
  const projects = data ?? fallback

  return {
    projects,
    isLoading: isLoading && projects.length === 0,
    isError,
    isStaticFallback,
    isFetching,
  }
}
