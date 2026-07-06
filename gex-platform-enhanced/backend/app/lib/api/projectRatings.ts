import type { ProjectRatingCreateRequest, ProjectRatingResponse } from "@/types/projectRating";

const API_BASE = (import.meta as ImportMeta & { env: Record<string, string> }).env?.VITE_API_BASE_URL ?? "";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json() as Promise<T>;
}

/**
 * Compute a GEX Project Quality Rating (stateless — no DB write on the server).
 * Primary function used by useProjectRating hook.
 */
export async function scoreProjectRating(
  payload: ProjectRatingCreateRequest
): Promise<ProjectRatingResponse> {
  const response = await fetch(`${API_BASE}/api/v1/project-ratings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  return parseJson<ProjectRatingResponse>(response);
}

/** Alias for callers that prefer the longer name. */
export const createProjectRating = scoreProjectRating;

export async function getCurrentProjectRating(projectId: string): Promise<ProjectRatingResponse> {
  const response = await fetch(`${API_BASE}/api/v1/project-ratings/projects/${projectId}/current`, {
    credentials: "include",
  });
  return parseJson<ProjectRatingResponse>(response);
}

export async function getProjectRatingHistory(projectId: string): Promise<ProjectRatingResponse[]> {
  const response = await fetch(`${API_BASE}/api/v1/project-ratings/projects/${projectId}/history`, {
    credentials: "include",
  });
  return parseJson<ProjectRatingResponse[]>(response);
}
