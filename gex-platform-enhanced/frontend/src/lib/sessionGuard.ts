/**
 * Ends a session the backend no longer honours and sends the user to sign in.
 *
 * Access tokens live ACCESS_TOKEN_EXPIRE_MINUTES (30). Nothing here used to
 * notice: a tab left open kept rendering signed-in routes while ABAC answered
 * every call `401 Authentication required`, and /pricing-curves silently drew
 * its seed curves, which read as "server data is wrong" (HANDOFF §8.11).
 *
 * The redirect is a full page load, not a router navigation, on purpose:
 * UserRoleProvider holds the session in React state initialised from storage,
 * so a reload is the one way every consumer sees the signed-out state.
 */
import { clearAuthSession, getAuthSession } from '@/lib/authToken'

export const LOGIN_PATH = '/login'

/**
 * Endpoints whose 401 means "these credentials are wrong", not "your session
 * ended". They are PUBLIC_ROUTES in backend/app/core/route_security.py, so ABAC
 * never answers them — a 401 there comes from the endpoint itself.
 */
export const CREDENTIAL_EXCHANGE_PATHS: ReadonlySet<string> = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/account/register',
])

let redirecting = false

export function expireSession(
  navigate: (path: string) => void = (path) => window.location.replace(path),
): void {
  clearAuthSession()
  // On the sign-in page clearing is enough; navigating again would loop.
  // One redirect per page load: /pricing-curves alone fires eight calls at once.
  if (redirecting || window.location.pathname === LOGIN_PATH) return
  redirecting = true
  navigate(LOGIN_PATH)
}

/**
 * True when a response proves the stored session is dead: a 401 to a request
 * that carried the bearer token that is STILL stored, other than a credential
 * exchange. A 401 for a guest, for a foreign token, or for a request issued
 * before the user signed in again must not sign anyone out.
 */
export function isSessionRejection(
  status: number,
  pathname: string,
  authorization: string | null,
): boolean {
  if (status !== 401 || CREDENTIAL_EXCHANGE_PATHS.has(pathname)) return false
  const token = getAuthSession().token
  return typeof token === 'string' && token.length > 0 && authorization === `Bearer ${token}`
}
