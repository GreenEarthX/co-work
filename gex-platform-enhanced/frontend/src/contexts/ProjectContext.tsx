// Screen: Global context (no screen)
import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from "react";
import { DEFAULT_PROJECT_ID } from "@/data/customerProjects";
import { useUserRole } from "@/contexts/UserRoleContext";
import { useVisibleProjects } from "@/hooks/useVisibleProjects";

interface ProjectContextType {
  selectedProjectId: string;
  setSelectedProjectId: (id: string) => void;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);
const ALL_PROJECTS_ID = "all";

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { sessionTier } = useUserRole();
  // Server-owned, runtime-aware visibility — includes on-ramp (created) projects,
  // so a freshly-created project can stay selected instead of being bounced back
  // to a seeded one.
  const { projects, isFetching } = useVisibleProjects();
  const visibleIds = projects.map((p) => p.id);

  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    () => localStorage.getItem("gex_selected_project") ?? DEFAULT_PROJECT_ID,
  );

  // Auto-correct: once the AUTHORITATIVE visible set is known, ensure the
  // selected project is in it. Gated on !isFetching so we never bounce a valid
  // runtime project during the static-fallback window (initialData excludes
  // on-ramp projects until the server list arrives).
  useEffect(() => {
    if (sessionTier !== "authenticated") return;
    if (isFetching) return;              // server list still in flight
    if (visibleIds.length === 0) return; // not loaded yet — leave as-is

    if (
      selectedProjectId !== ALL_PROJECTS_ID &&
      !visibleIds.includes(selectedProjectId)
    ) {
      const first = visibleIds[0];
      setSelectedProjectId(first);
      localStorage.setItem("gex_selected_project", first);
    }
  }, [visibleIds.join(","), sessionTier, selectedProjectId, isFetching]); // eslint-disable-line react-hooks/exhaustive-deps

  const select = (id: string) => {
    setSelectedProjectId(id);
    localStorage.setItem("gex_selected_project", id);
  };

  return (
    <ProjectContext.Provider
      value={{ selectedProjectId, setSelectedProjectId: select }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useSelectedProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx)
    throw new Error("useSelectedProject must be used within ProjectProvider");
  return ctx;
}
