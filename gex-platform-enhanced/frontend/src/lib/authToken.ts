/**
 * The ONE place the GEX bearer token is read.
 *
 * GEX issues its own JWT: POST /api/v1/auth/login → create_access_token, which
 * UserRoleContext persists to localStorage under `gex_auth_session` as
 * `{ token, email, expiresAt }`. Every authenticated call must take its token
 * from here.
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
 * Expiry (2026-09-14)
 * -------------------
 * Access tokens live 30 minutes, and nothing here used to check. A token past
 * its expiry is treated as absent by every getter, so no caller can send one.
 * The JWT `exp` claim is authoritative — it is what the backend enforces; the
 * stored `expiresAt` (login's `expires_at`) is the fallback. A token with
 * neither is left for the server to judge: lib/fetchAuthBridge ends the
 * session on a 401.
 *
 * Do not read `gex_auth_session` anywhere else, and do not take a bearer token
 * from the Supabase stub — GEX is the token issuer, not GoTrue.
 */
import { safeGetItem, safeGetJson, safeRemoveItem, safeSetItem } from '@/lib/safeStorage'

export const AUTH_SESSION_KEY = 'gex_auth_session'
/** 'authenticated' | 'guest', persisted by UserRoleContext. */
export const SESSION_TIER_KEY = 'gex_session_tier'
const USER_ROLE_KEY = 'gex_user_role'
const CISO_SESSION_KEY = 'gex_ciso_session'

export interface StoredAuthSession {
  token?: string
  email?: string
  /** ISO-8601 access-token expiry, from the login response's `expires_at`. */
  expiresAt?: string
}

/** The stored session, or an empty object when absent/unparseable. */
export function getAuthSession(): StoredAuthSession {
  return safeGetJson<StoredAuthSession>(AUTH_SESSION_KEY, {})
}

function storedToken(session: StoredAuthSession): string | null {
  const token = session.token
  return typeof token === 'string' && token.length > 0 ? token : null
}

function jwtExpiryMs(token: string): number | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const claims = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof claims?.exp === 'number' ? claims.exp * 1000 : null
  } catch {
    return null
  }
}

/** When the stored access token stops being accepted (epoch ms), or null when unknown. */
export function getSessionExpiry(session: StoredAuthSession = getAuthSession()): number | null {
  const token = storedToken(session)
  const fromJwt = token ? jwtExpiryMs(token) : null
  if (fromJwt !== null) return fromJwt
  const fromStore = typeof session.expiresAt === 'string' ? Date.parse(session.expiresAt) : NaN
  return Number.isNaN(fromStore) ? null : fromStore
}

/** True when a token is stored and its known expiry has passed. */
export function isSessionExpired(
  session: StoredAuthSession = getAuthSession(),
  now: number = Date.now(),
): boolean {
  if (!storedToken(session)) return false
  const expiry = getSessionExpiry(session)
  return expiry !== null && expiry <= now
}

/** The bearer token, or null when the user is not authenticated or it has expired. */
export function getAuthToken(): string | null {
  const session = getAuthSession()
  return isSessionExpired(session) ? null : storedToken(session)
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

/** True when a bearer token is available and unexpired. */
export function isAuthenticated(): boolean {
  return getAuthToken() !== null
}

/** Signed-out storage: what logout leaves behind, and what an ended session becomes. */
export function clearAuthSession(): void {
  safeRemoveItem(AUTH_SESSION_KEY)
  safeRemoveItem(USER_ROLE_KEY)
  safeSetItem(SESSION_TIER_KEY, 'guest')
  try { sessionStorage.removeItem(CISO_SESSION_KEY) } catch { /* ignore */ }
}

/**
 * Clears a session that can no longer authenticate: an expired token, or an
 * 'authenticated' tier with no token at all. main.tsx calls this before the
 * first render, because UserRoleProvider initialises its state from storage.
 * Returns true when it cleared something.
 */
export function discardExpiredSession(): boolean {
  const orphanedTier = safeGetItem(SESSION_TIER_KEY) === 'authenticated' && !isAuthenticated()
  if (!orphanedTier && !isSessionExpired()) return false
  clearAuthSession()
  return true
}


/**
 * The signed-in user's id, from the token's `sub` claim — or null.
 *
 * NOT an authorization decision: the server derives the owner from the bearer
 * token and accepts no other answer. This exists so per-user BROWSER state can
 * be namespaced, and so one person's cached work can never be read — or worse,
 * uploaded — under the next person's account on a shared browser.
 */
export function getAuthUserId(): string | null {
  const token = getAuthToken()
  if (!token) return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const claims = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
    const sub = claims?.sub ?? claims?.user_id
    return typeof sub === 'string' && sub.length > 0 ? sub : null
  } catch {
    return null
  }
}
