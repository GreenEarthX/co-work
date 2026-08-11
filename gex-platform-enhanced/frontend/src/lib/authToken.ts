/**
 * The ONE place the GEX bearer token is read.
 *
 * GEX issues its own JWT: POST /api/v1/auth/login → create_access_token, which
 * UserRoleContext persists to localStorage under `gex_auth_session` as
 * `{ token, email }`. Every authenticated call must take its token from here.
 *
 * Why this module exists
 * ----------------------
 * The read was copy-pasted into four clients with slightly different shapes,
 * and a fifth — engineClient — read from `integrations/supabase/client.ts`
 * instead. That file is a STUB whose getSession() always returns
 * `{ session: null, error: { message: "Supabase not configured — stub client" } }`,
 * so engineClient threw EngineUnauthenticated("session error: …") before it
 * could issue a request. The message pointed at the engine; the cause was a
 * stub in the frontend.
 *
 * Do not read `gex_auth_session` anywhere else, and do not take a bearer token
 * from the Supabase stub — GEX is the token issuer, not GoTrue.
 */
import { safeGetJson } from '@/lib/safeStorage'

export const AUTH_SESSION_KEY = 'gex_auth_session'

export interface StoredAuthSession {
  token?: string
  email?: string
}

/** The stored session, or an empty object when absent/unparseable. */
export function getAuthSession(): StoredAuthSession {
  return safeGetJson<StoredAuthSession>(AUTH_SESSION_KEY, {})
}

/** The bearer token, or null when the user is not authenticated. */
export function getAuthToken(): string | null {
  const token = getAuthSession().token
  return typeof token === 'string' && token.length > 0 ? token : null
}

/**
 * Authorization header, or `{}` when unauthenticated — spread into fetch
 * headers. Callers that must fail loudly should use getAuthToken() and raise
 * their own domain error instead.
 */
export function getAuthHeader(): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** True when a bearer token is available. */
export function isAuthenticated(): boolean {
  return getAuthToken() !== null
}
