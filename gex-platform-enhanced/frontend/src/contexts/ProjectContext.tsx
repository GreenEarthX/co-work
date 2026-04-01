import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { DEFAULT_PROJECT_ID, CUSTOMER_PROJECTS } from '@/data/customerProjects';
import { useUserRole } from '@/contexts/UserRoleContext';

interface ProjectContextType {
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

/** Returns IDs of projects visible to the current role — same logic as useVisibleProjects(). */
function getVisibleIds(companyName: string, companyType: string): string[] {
  return CUSTOMER_PROJECTS
    .filter(p =>
      companyType === 'PRODUCER'
        ? p.owner_company === companyName
        : p.associated_companies.includes(companyName)
    )
    .map(p => p.id)
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { role, sessionTier } = useUserRole();

  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => localStorage.getItem('gex_selected_project') ?? DEFAULT_PROJECT_ID
  );

  // Auto-correct: when role changes (login/switch), ensure the selected project
  // is in the user's visible set. If not, pick their first visible project.
  useEffect(() => {
    if (sessionTier !== 'authenticated') return;

    const visibleIds = getVisibleIds(role.company_name, role.company_type);
    if (visibleIds.length === 0) return;           // no visible projects — leave as-is

    if (!visibleIds.includes(selectedProjectId)) {
      const first = visibleIds[0];
      setSelectedProjectId(first);
      localStorage.setItem('gex_selected_project', first);
    }
  }, [role.company_name, role.company_type, sessionTier]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id: string) => {
    setSelectedProjectId(id);
    localStorage.setItem('gex_selected_project', id);
  };

  return (
    <ProjectContext.Provider value={{ selectedProjectId, setSelectedProjectId: select }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useSelectedProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useSelectedProject must be used within ProjectProvider');
  return ctx;
}
