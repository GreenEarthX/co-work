// Screen: Hook (no screen)
/**
 * Hook that returns the canonical 5 customer projects.
 * Tries the API first; falls back to the static CUSTOMER_PROJECTS registry.
 * All workspace pages should use this instead of inline fetch + hardcoded fallback.
 */
import { useState, useEffect } from 'react';
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects';

interface UseCustomerProjectsResult {
  projects: CustomerProject[];
  loading: boolean;
}

export function useCustomerProjects(): UseCustomerProjectsResult {
  const [projects, setProjects] = useState<CustomerProject[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch('/api/v1/capacities/list');
        if (res.ok) {
          const data = await res.json();
          const apiProjects: CustomerProject[] = (data.capacities || [])
            .filter((c: any) => c.id?.startsWith('proj_'))
            .map((c: any) => {
              const canonical = CUSTOMER_PROJECTS.find(p => p.id === c.id);
              if (canonical) return canonical;
              // Unknown project from API — map as best we can
              return {
                ...CUSTOMER_PROJECTS[0],
                id: c.id,
                name: c.project_name,
                molecule: c.molecule,
                location: c.location ?? '',
                capacity_mtpd: c.capacity_mtpd,
                capex_eur: c.capex_eur ?? 0,
                status: c.status ?? 'development',
              } as CustomerProject;
            });
          if (!cancelled) setProjects(apiProjects.length > 0 ? apiProjects : CUSTOMER_PROJECTS);
        } else {
          if (!cancelled) setProjects(CUSTOMER_PROJECTS);
        }
      } catch {
        if (!cancelled) setProjects(CUSTOMER_PROJECTS);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return { projects, loading };
}
