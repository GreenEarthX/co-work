import { createContext, useContext, useState, ReactNode } from 'react';
import { DEFAULT_PROJECT_ID } from '@/data/customerProjects';

interface ProjectContextType {
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => localStorage.getItem('gex_selected_project') ?? DEFAULT_PROJECT_ID
  );

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
