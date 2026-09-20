// Screen: API client (no screen)
//
// The canvas portfolio, from /api/v1/plants. Replaces the
// `supabase.from("plants")` reads and writes in PlantBuilder, plantStore,
// iterations and useCanvasData.
//
// THE POINT OF THIS FILE: no function here takes a user id. The server reads
// the owner from the bearer token and accepts no other answer. Previously the
// browser passed `user_id` and PostgREST trusted it, so naming somebody else's
// id — and the live ids were `admin-001`, `demo-user`, `user-003` — read or
// overwrote their portfolio. That is now unsayable, which also means the
// stubbed AuthContext can no longer decide whose plants these are.
import { getAuthToken } from '@/lib/authToken'

const API_PREFIX = '/api/v1/plants'

/** A stored plant. `data` is the frontend's own ProjectRecord, kept whole. */
export interface StoredPlant<T = Record<string, unknown>> {
  slug: string
  data: T
  updated_at: string
  created_at: string
}

class NotFound extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAuthToken()
  const res = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  })
  if (res.status === 404) throw new NotFound()
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch { /* keep the status */ }
    throw new Error(`plants: ${detail}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export function listPlants<T>(): Promise<StoredPlant<T>[]> {
  return call<StoredPlant<T>[]>('')
}

export async function getPlant<T>(slug: string): Promise<StoredPlant<T> | null> {
  try {
    return await call<StoredPlant<T>>(`/${encodeURIComponent(slug)}`)
  } catch (e) {
    if (e instanceof NotFound) return null
    throw e
  }
}

export function upsertPlant<T>(slug: string, data: T): Promise<StoredPlant<T>> {
  return call<StoredPlant<T>>(`/${encodeURIComponent(slug)}`, {
    method: 'PUT',
    body: JSON.stringify({ data }),
  })
}

/** Deleting something already gone is success, not an error. */
export async function deletePlant(slug: string): Promise<void> {
  try {
    await call<void>(`/${encodeURIComponent(slug)}`, { method: 'DELETE' })
  } catch (e) {
    if (!(e instanceof NotFound)) throw e
  }
}

/** Bump `updated_at` only. Returns null if the plant is not stored yet. */
export async function touchPlant<T>(slug: string): Promise<StoredPlant<T> | null> {
  try {
    return await call<StoredPlant<T>>(`/${encodeURIComponent(slug)}/touch`,
      { method: 'POST' })
  } catch (e) {
    if (e instanceof NotFound) return null
    throw e
  }
}

/**
 * Replace the whole portfolio in one transaction.
 *
 * `confirmDelete` states how many plants the caller expects to lose; the
 * server answers 409 and changes nothing if the real number differs. Pass it
 * whenever the count is knowable — it is the guard against an empty list from
 * a half-loaded client meaning "delete everything".
 */
export function replacePortfolio<T>(
  plants: Array<{ slug: string; data: T }>,
  opts: { confirmDelete?: number } = {},
): Promise<StoredPlant<T>[]> {
  const q = opts.confirmDelete === undefined
    ? '' : `?confirm_delete=${opts.confirmDelete}`
  return call<StoredPlant<T>[]>(q, {
    method: 'PUT',
    body: JSON.stringify({ plants }),
  })
}
