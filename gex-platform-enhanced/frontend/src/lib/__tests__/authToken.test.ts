import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  AUTH_SESSION_KEY,
  SESSION_TIER_KEY,
  clearAuthSession,
  discardExpiredSession,
  getAuthHeader,
  getAuthSession,
  getAuthToken,
  getSessionExpiry,
  isAuthenticated,
  isSessionExpired,
} from '../authToken'

/** An unsigned JWT-shaped token. Only the frontend reads it; nothing verifies it. */
function jwt(claims: Record<string, unknown>): string {
  const b64url = (s: string) =>
    btoa(unescape(encodeURIComponent(s))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${b64url('{"alg":"HS256","typ":"JWT"}')}.${b64url(JSON.stringify(claims))}.sig`
}

const nowSeconds = () => Math.floor(Date.now() / 1000)

// GEX issues its own JWT (POST /api/v1/auth/login → create_access_token) and
// UserRoleContext persists it as { token, email }. These tests pin that
// contract, and pin the regression that motivated the module: engineClient
// used to take its bearer from integrations/supabase/client.ts — a STUB whose
// getSession() always returns a truthy error — so every engine call threw
// EngineUnauthenticated("session error: …") before issuing a request. The
// message blamed the engine; the cause was a stub in the frontend.

function setSession(value: unknown) {
  localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(value))
}

describe('authToken', () => {
  beforeEach(() => localStorage.clear())

  it('reads the token UserRoleContext persists', () => {
    setSession({ token: 'jwt-abc', email: 'a@b.io' })
    expect(getAuthToken()).toBe('jwt-abc')
    expect(getAuthHeader()).toEqual({ Authorization: 'Bearer jwt-abc' })
    expect(isAuthenticated()).toBe(true)
  })

  it('returns null — not a partial header — when unauthenticated', () => {
    expect(getAuthToken()).toBeNull()
    expect(getAuthHeader()).toEqual({})
    expect(isAuthenticated()).toBe(false)
  })

  it('treats an empty-string token as unauthenticated', () => {
    setSession({ token: '' })
    expect(getAuthToken()).toBeNull()
    expect(getAuthHeader()).toEqual({})
  })

  it('treats a session without a token as unauthenticated', () => {
    setSession({ email: 'a@b.io' })
    expect(getAuthToken()).toBeNull()
  })

  it('survives malformed JSON rather than throwing', () => {
    localStorage.setItem(AUTH_SESSION_KEY, '{not json')
    expect(getAuthSession()).toEqual({})
    expect(getAuthToken()).toBeNull()
  })

  it('ignores a non-string token', () => {
    setSession({ token: 12345 })
    expect(getAuthToken()).toBeNull()
  })
})

describe('engineClient authorization', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sends the GEX bearer token, not a Supabase session', async () => {
    vi.stubEnv('VITE_GEX_ENGINE_URL', 'https://engine.test')
    setSession({ token: 'jwt-from-gex' })

    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { engineFetch } = await import('../engineClient')
    await engineFetch({ path: '/whoami' })

    expect(fetchMock).toHaveBeenCalled()
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer jwt-from-gex')
  })

  it('throws EngineUnauthenticated when there is no token — without calling fetch', async () => {
    vi.stubEnv('VITE_GEX_ENGINE_URL', 'https://engine.test')
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { engineFetch, EngineUnauthenticated } = await import('../engineClient')
    await expect(engineFetch({ path: '/whoami' })).rejects.toBeInstanceOf(EngineUnauthenticated)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not import the Supabase stub for authentication', () => {
    // The regression guard. engineClient must not reach GoTrue for a bearer
    // token — GEX is the issuer. A reintroduced import would make an
    // authenticated user look unauthenticated again.
    // Read from disk, not via `import ?raw`: a failed dynamic import would let
    // this assertion silently pass and the guard would be decorative.
    const src = readFileSync(
      resolve(__dirname, '../engineClient.ts'),
      'utf8',
    )
    expect(src).not.toMatch(/from ["']@\/integrations\/supabase\/client["']/)
    expect(src).toMatch(/from ["']@\/lib\/authToken["']/)
  })
})

// HANDOFF §8.11: access tokens live 30 minutes and nothing checked, so a tab
// left open kept rendering signed-in pages while every API call 401'd. These
// pin that an expired token is no token, whichever getter a caller uses.
describe('authToken expiry', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('treats a JWT past its exp as unauthenticated', () => {
    setSession({ token: jwt({ sub: 'u1', exp: nowSeconds() - 60 }), email: 'a@b.io' })
    expect(isSessionExpired()).toBe(true)
    expect(getAuthToken()).toBeNull()
    expect(getAuthHeader()).toEqual({})
    expect(isAuthenticated()).toBe(false)
    // The stored record stays visible so the guard can see what ended.
    expect(getAuthSession().email).toBe('a@b.io')
  })

  it('accepts a JWT before its exp', () => {
    const token = jwt({ sub: 'u1', exp: nowSeconds() + 1800 })
    setSession({ token })
    expect(isSessionExpired()).toBe(false)
    expect(getAuthToken()).toBe(token)
  })

  it('expires at exp exactly, not a second later', () => {
    const exp = nowSeconds() + 100
    const session = { token: jwt({ exp }) }
    expect(isSessionExpired(session, exp * 1000 - 1)).toBe(false)
    expect(isSessionExpired(session, exp * 1000)).toBe(true)
  })

  it('takes exp over the stored expiresAt — exp is what the backend enforces', () => {
    const future = new Date(Date.now() + 3_600_000).toISOString()
    const past = new Date(Date.now() - 3_600_000).toISOString()
    expect(isSessionExpired({ token: jwt({ exp: nowSeconds() - 60 }), expiresAt: future })).toBe(true)
    expect(isSessionExpired({ token: jwt({ exp: nowSeconds() + 60 }), expiresAt: past })).toBe(false)
  })

  it('falls back to the stored expiresAt when the token carries no exp', () => {
    setSession({ token: 'opaque', expiresAt: new Date(Date.now() - 1000).toISOString() })
    expect(getAuthToken()).toBeNull()
    setSession({ token: jwt({ sub: 'no-exp' }), expiresAt: new Date(Date.now() + 60_000).toISOString() })
    expect(getAuthToken()).not.toBeNull()
  })

  it('leaves an unknown expiry to the server rather than guessing', () => {
    setSession({ token: 'opaque' })
    expect(getSessionExpiry()).toBeNull()
    expect(isSessionExpired()).toBe(false)
    expect(getAuthToken()).toBe('opaque')
  })

  it('reads exp from claims that carry non-ASCII text', () => {
    // Real claims include company_name and user_name.
    setSession({ token: jwt({ company_name: 'Énergie Hydrogène', exp: nowSeconds() - 1 }) })
    expect(getAuthToken()).toBeNull()
  })

  it('has nothing to expire without a token', () => {
    setSession({ email: 'a@b.io', expiresAt: new Date(0).toISOString() })
    expect(isSessionExpired()).toBe(false)
  })
})

describe('clearAuthSession / discardExpiredSession', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it('clears to the same storage logout leaves', () => {
    setSession({ token: 'jwt-abc' })
    localStorage.setItem('gex_user_role', '{"company_name":"X"}')
    localStorage.setItem(SESSION_TIER_KEY, 'authenticated')
    sessionStorage.setItem('gex_ciso_session', '1')

    clearAuthSession()

    expect(localStorage.getItem(AUTH_SESSION_KEY)).toBeNull()
    expect(localStorage.getItem('gex_user_role')).toBeNull()
    expect(localStorage.getItem(SESSION_TIER_KEY)).toBe('guest')
    expect(sessionStorage.getItem('gex_ciso_session')).toBeNull()
  })

  it('discards an expired session', () => {
    setSession({ token: jwt({ exp: nowSeconds() - 60 }) })
    localStorage.setItem(SESSION_TIER_KEY, 'authenticated')
    expect(discardExpiredSession()).toBe(true)
    expect(localStorage.getItem(AUTH_SESSION_KEY)).toBeNull()
    expect(localStorage.getItem(SESSION_TIER_KEY)).toBe('guest')
  })

  it('discards an authenticated tier that has no token', () => {
    localStorage.setItem(SESSION_TIER_KEY, 'authenticated')
    expect(discardExpiredSession()).toBe(true)
    expect(localStorage.getItem(SESSION_TIER_KEY)).toBe('guest')
  })

  it('keeps a valid session, and writes nothing for a guest', () => {
    const token = jwt({ exp: nowSeconds() + 1800 })
    setSession({ token })
    localStorage.setItem(SESSION_TIER_KEY, 'authenticated')
    expect(discardExpiredSession()).toBe(false)
    expect(getAuthToken()).toBe(token)

    localStorage.clear()
    expect(discardExpiredSession()).toBe(false)
    expect(localStorage.getItem(SESSION_TIER_KEY)).toBeNull()
  })

  it('runs before the first render, and main.tsx keeps no second session reader', () => {
    // UserRoleProvider initialises from storage at mount; discarding after
    // render would leave signed-in routes rendered for a dead session.
    const src = readFileSync(resolve(__dirname, '../../main.tsx'), 'utf8')
    const discard = src.indexOf('discardExpiredSession()')
    expect(discard).toBeGreaterThan(-1)
    expect(discard).toBeLessThan(src.indexOf('ReactDOM.createRoot('))
    expect(src).not.toMatch(/gex_auth_session/)
  })
})
