// Screen: API client (no screen)
//
// Canvas documents from /api/v1/plant-canvas — the plant canvas JSON, its
// version history, site infrastructure and the per-user custom library.
// Replaces the Supabase Storage bucket `plant-data`.
//
// THIS IS A REPAIR AS WELL AS A CUTOVER. The old read path called
// `getPublicUrl()` and fetched that URL with no credentials. The bucket is not
// public, so it answered 404 "Bucket not found" every time: cloud saves
// worked, cloud loads never did, and the canvas fell back to localStorage
// without saying so. A user on a new device did not get their work back.
//
// There is no `getPublicUrl` equivalent here and there should not be. A URL
// anyone can fetch is precisely the property that made the bucket a problem;
// these reads are authenticated and return the bytes.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/plant-canvas'

export interface BlobMeta {
  kind: string
  slug: string
  version_id: string
  sha256: string
  size_bytes: number
  updated_at: string
}

export interface VersionEntry {
  version_id: string
  sha256: string
  size_bytes: number
  created_at: string
  updated_at: string
}

class NotFound extends Error {}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = getAuthToken()
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra }
}

async function call(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: authHeaders(init?.headers as Record<string, string> | undefined ?? {}),
  })
  if (res.status === 404) throw new NotFound()
  if (!res.ok) throw new Error(`plant-canvas: HTTP ${res.status}`)
  return res
}

/** The document, or null when it is not stored. Absence is not an error. */
async function getJson<T>(path: string): Promise<T | null> {
  try {
    return (await (await call(path)).json()) as T
  } catch (e) {
    if (e instanceof NotFound) return null
    throw e
  }
}

function putJson(path: string, document: unknown): Promise<BlobMeta> {
  return call(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  }).then((r) => r.json() as Promise<BlobMeta>)
}

const enc = encodeURIComponent

// ── canvas ───────────────────────────────────────────────────────────────────

export function loadCanvas<T>(slug: string): Promise<T | null> {
  return getJson<T>(`/canvas/${enc(slug)}`)
}

export function saveCanvas(slug: string, document: unknown): Promise<BlobMeta> {
  return putJson(`/canvas/${enc(slug)}`, document)
}

/** Removes the canvas and all of its snapshots. Already-gone is success. */
export async function deleteCanvas(slug: string): Promise<void> {
  try {
    await call(`/canvas/${enc(slug)}`, { method: 'DELETE' })
  } catch (e) {
    if (!(e instanceof NotFound)) throw e
  }
}

export async function listCanvasVersions(slug: string): Promise<VersionEntry[]> {
  return (await getJson<VersionEntry[]>(`/canvas/${enc(slug)}/versions`)) ?? []
}

/** Record a snapshot. The server prunes to its retention limit afterwards. */
export function saveCanvasVersion(slug: string, versionId: string,
                                  document: unknown): Promise<BlobMeta> {
  return putJson(`/canvas/${enc(slug)}/versions/${enc(versionId)}`, document)
}

export function loadCanvasVersion<T>(slug: string, versionId: string): Promise<T | null> {
  return getJson<T>(`/canvas/${enc(slug)}/versions/${enc(versionId)}`)
}

// ── site infrastructure ──────────────────────────────────────────────────────

export function loadSiteInfrastructure<T>(slug: string): Promise<T | null> {
  return getJson<T>(`/site/${enc(slug)}`)
}

export function saveSiteInfrastructure(slug: string, document: unknown): Promise<BlobMeta> {
  return putJson(`/site/${enc(slug)}`, document)
}

// ── custom library (one per user) ────────────────────────────────────────────

export function loadCustomLibrary<T>(): Promise<T | null> {
  return getJson<T>('/library')
}

export function saveCustomLibrary(document: unknown): Promise<BlobMeta> {
  return putJson('/library', document)
}
