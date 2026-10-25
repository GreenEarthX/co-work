// Screen: Hook (no screen)
/**
 * useProjectResource — GET a per-project API resource for the SELECTED project.
 *
 * The structuring and instrument screens each fetched `proj_bremen_h2` (hard-
 * coded) without the bearer token, and swallowed any failure into an empty
 * screen. This reads the selected project, sends the session's token, and turns
 * a refusal into a message — notably 404 STRUCTURING_CONTEXT_NOT_RECORDED, which
 * means the project has no recorded inputs (2026-10-25: no invented default
 * answers for it any more).
 */
import { useEffect, useState } from 'react'
import { useSelectedProject } from '@/contexts/ProjectContext'
import { getAuthHeader } from '@/lib/authToken'

export interface ProjectResource<T> {
  projectId: string
  data: T | null
  loading: boolean
  error: string | null
}

export function useProjectResource<T>(path: (projectId: string) => string): ProjectResource<T> {
  const { selectedProjectId: projectId } = useSelectedProject()
  const [state, setState] = useState<Omit<ProjectResource<T>, 'projectId'>>({ data: null, loading: true, error: null })
  const url = projectId ? path(projectId) : null

  useEffect(() => {
    if (!url) {
      setState({ data: null, loading: false, error: 'Select a project first.' })
      return
    }
    let cancelled = false
    setState({ data: null, loading: true, error: null })
    fetch(url, { headers: getAuthHeader() })
      .then(async (res) => {
        const body = await res.json().catch(() => ({}))
        if (cancelled) return
        if (!res.ok) {
          const detail = body?.detail
          const message = (detail && typeof detail === 'object' && detail.message)
            || (typeof detail === 'string' && detail) || `The server answered ${res.status}.`
          setState({ data: null, loading: false, error: message })
        } else {
          setState({ data: body as T, loading: false, error: null })
        }
      })
      .catch((e) => { if (!cancelled) setState({ data: null, loading: false, error: (e as Error).message }) })
    return () => { cancelled = true }
  }, [url])

  return { projectId, ...state }
}
