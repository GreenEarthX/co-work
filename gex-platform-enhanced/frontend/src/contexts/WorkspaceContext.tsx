import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { WorkspaceId, Workspace, getWorkspace } from '@/config/workspaces'

interface WorkspaceContextType {
  currentWorkspace: Workspace
  setWorkspace: (id: WorkspaceId) => void
  workspaceId: WorkspaceId
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined)

interface WorkspaceProviderProps {
  children: ReactNode
  defaultWorkspace?: WorkspaceId
}

export function WorkspaceProvider({ children, defaultWorkspace = 'producer' }: WorkspaceProviderProps) {
  const [workspaceId, setWorkspaceId] = useState<WorkspaceId>(() => {
    const saved = localStorage.getItem('gex_workspace')
    return (saved as WorkspaceId) || defaultWorkspace
  })

  const currentWorkspace = getWorkspace(workspaceId)

  const setWorkspace = (id: WorkspaceId) => {
    setWorkspaceId(id)
    localStorage.setItem('gex_workspace', id)
  }

  return (
    <WorkspaceContext.Provider value={{ currentWorkspace, setWorkspace, workspaceId }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used within WorkspaceProvider')
  }
  return context
}