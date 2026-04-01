/**
 * useVisibleProjects — ABAC-aware project filter.
 *
 * Visibility rules (mirrors server-side JWT scope enforcement):
 *
 *   PRODUCER   → projects where owner_company === role.company_name
 *   OFFTAKER   → projects where associated_companies includes role.company_name
 *   THIRD_PARTY (BANK / INSURER / ENGINEER / …)
 *              → projects where associated_companies includes role.company_name
 *   guest      → empty list (no project data until authenticated)
 *
 * Returns a stable filtered array. Components should call this instead
 * of importing CUSTOMER_PROJECTS directly when listing or selecting projects.
 */
import { useMemo } from 'react'
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects'
import { useUserRole } from '@/contexts/UserRoleContext'

export function useVisibleProjects(): CustomerProject[] {
  const { role, sessionTier } = useUserRole()

  return useMemo(() => {
    if (sessionTier !== 'authenticated') return []

    return CUSTOMER_PROJECTS.filter(project => {
      if (role.company_type === 'PRODUCER') {
        return project.owner_company === role.company_name
      }
      // OFFTAKER + all THIRD_PARTY roles (bank, insurer, engineer, certifier…)
      return project.associated_companies.includes(role.company_name)
    })
  }, [role.company_name, role.company_type, sessionTier])
}
