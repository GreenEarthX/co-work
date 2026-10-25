// Screen: Hook (no screen)
/**
 * useVisibleProjects — the projects this session may see, from PostgreSQL.
 *
 * GET /api/v1/projects/visible decides WHICH projects are visible and returns
 * each one's record: the headline fields from `projects` and the rest
 * (bankability snapshot, gates, offtakes, energy, certifications, incentives,
 * timeline, narrative) from `project_profile` (alembic 068).
 *
 * There is no static fallback (JML, 2026-10-25: project data out of code,
 * PostgreSQL as reference). When the server cannot answer, the list is empty and
 * isError says why — the screen must not show a client-side guess.
 *
 * Returns:
 *   projects         — visible CustomerProject array (empty while loading or on error)
 *   isLoading        — true while the backend request is in flight
 *   isError          — true if the backend returned an error
 *   isStaticFallback — always false; kept so existing callers keep compiling
 */

import { useQuery } from '@tanstack/react-query'
import type { CustomerProject } from '@/data/customerProjects'
import { useUserRole } from '@/contexts/UserRoleContext'

const IS_DEV = import.meta.env.DEV

/** Shape returned by GET /api/v1/projects/visible (VisibleProject). */
interface ServerProject {
  id: string
  name: string
  molecule: string
  location: string
  country: string
  lat: number | null
  lng: number | null
  capacity_mtpd: number
  capex_eur: number
  status: string
  phase: string
  completion_date: string
  description: string
  owner_company: string
  associated_companies: string[]
  jurisdiction: string
  /** project_profile.profile — everything beyond the headline fields. */
  profile: Partial<CustomerProject> | null
  profile_verification: string | null
}

const EMPTY_BANKABILITY: CustomerProject['bankability'] = {
  overall_completion: 0,
  gates: [],
  capital_status: [],
  next_milestone: 'Declare project context and open Gate G1',
  unlocked_capital: [],
  risk_alerts: [],
}

/** The server's record as a CustomerProject: headline fields from `projects`
 *  (the reference), the rest from the profile when one is recorded. */
export function serverToCustomerProject(sp: ServerProject): CustomerProject {
  const profile = sp.profile ?? {}
  return {
    ...profile,
    id: sp.id,
    name: sp.name,
    molecule: (sp.molecule || profile.molecule || 'H2') as CustomerProject['molecule'],
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
    bankability: profile.bankability ?? EMPTY_BANKABILITY,
  }
}

async function fetchVisibleProjects(token: string): Promise<CustomerProject[]> {
  const res = await fetch('/api/v1/projects/visible', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`projects/visible: ${res.status}`)
  const serverList: ServerProject[] = await res.json()
  return serverList.map(serverToCustomerProject)
}

export interface UseVisibleProjectsResult {
  projects: CustomerProject[]
  isLoading: boolean
  isError: boolean
  isStaticFallback: boolean
  isFetching: boolean
}

export function useVisibleProjects(): UseVisibleProjectsResult {
  const { sessionTier, authSession } = useUserRole()
  const token = authSession?.token ?? null

  const { data, isLoading, isError, isFetching } = useQuery<CustomerProject[]>({
    queryKey: ['projects', 'visible', token],
    queryFn: () => fetchVisibleProjects(token!),
    enabled: !!token && sessionTier === 'authenticated',
    staleTime: 2 * 60 * 1000,
    retry: IS_DEV ? 0 : 2,
  })

  const projects = data ?? []
  return {
    projects,
    isLoading: isLoading && projects.length === 0,
    isError,
    isStaticFallback: false,
    isFetching,
  }
}
