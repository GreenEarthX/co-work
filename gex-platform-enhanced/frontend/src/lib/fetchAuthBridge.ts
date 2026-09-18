/**
 * Decorates platform /api/ fetches with the caller's identity, and ends the
 * session when the backend refuses it.
 *
 * Moved out of main.tsx 2026-09-14 so it can be tested — main.tsx renders on
 * import. The bearer now comes from lib/authToken (the single session reader),
 * which also means an expired token is never sent.
 */
import { getAuthSession, getAuthToken, isSessionExpired } from '@/lib/authToken'
import { safeGetJson } from '@/lib/safeStorage'
import { expireSession, isSessionRejection } from '@/lib/sessionGuard'

const USER_ROLE_KEY = 'gex_user_role'

type StoredRole = {
  company_name?: string
  company_type?: string
  business_function?: string
  service_type?: string | null
  capabilities?: string[]
}

declare global {
  interface Window {
    __gexFetchAuthInstalled__?: boolean
  }
}

function toCompanySlug(value?: string): string {
  if (!value) return 'demo-company'
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function requestUrl(input: RequestInfo | URL): URL {
  const rawUrl =
    typeof input === 'string'
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url
  return new URL(rawUrl, window.location.origin)
}

export function shouldDecorateRequest(input: RequestInfo | URL): boolean {
  const url = requestUrl(input)
  const isPlatformApiPath = url.pathname.startsWith('/api/')
  const isLocalPlatformApi =
    url.hostname === 'localhost' &&
    url.port === '8000' &&
    url.pathname.startsWith('/api/')

  return isPlatformApiPath || isLocalPlatformApi
}

export interface FetchAuthBridgeOptions {
  /** Called when the stored session is expired or the backend rejects it. */
  onSessionRejected?: () => void
}

export function installFetchAuthBridge(
  { onSessionRejected = () => expireSession() }: FetchAuthBridgeOptions = {},
): void {
  if (window.__gexFetchAuthInstalled__) return
  window.__gexFetchAuthInstalled__ = true

  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!shouldDecorateRequest(input)) {
      return nativeFetch(input, init)
    }

    // Expired by the clock: no need to spend a round trip learning it. The
    // request still goes out, without the dead bearer — public routes answer.
    if (isSessionExpired()) onSessionRejected()

    const token = getAuthToken()
    const session = getAuthSession()
    const role = safeGetJson<StoredRole | null>(USER_ROLE_KEY, null)
    const headers = new Headers(input instanceof Request ? input.headers : undefined)

    if (init?.headers) {
      new Headers(init.headers).forEach((value, key) => headers.set(key, value))
    }

    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    if (session.email && !headers.has('x-demo-user')) {
      headers.set('x-demo-user', session.email)
    }
    if (role?.company_name && !headers.has('x-demo-company')) {
      headers.set('x-demo-company', toCompanySlug(role.company_name))
    }
    if (role?.company_type && !headers.has('x-demo-company-type')) {
      headers.set('x-demo-company-type', role.company_type)
    }
    if (role?.business_function && !headers.has('x-demo-function')) {
      headers.set('x-demo-function', role.business_function)
    }
    if (role?.service_type && !headers.has('x-demo-service-type')) {
      headers.set('x-demo-service-type', role.service_type)
    }
    if (role?.capabilities?.length && !headers.has('x-demo-capabilities')) {
      headers.set('x-demo-capabilities', role.capabilities.join(','))
    }

    const response = input instanceof Request
      ? await nativeFetch(new Request(input, { ...init, headers }))
      : await nativeFetch(input, { ...init, headers })

    // Rejected by the server: revoked, signed with a rotated key, or expired
    // under clock skew. Callers still receive the 401; the page is leaving.
    if (isSessionRejection(response.status, requestUrl(input).pathname, headers.get('Authorization'))) {
      onSessionRejected()
    }

    return response
  }
}
