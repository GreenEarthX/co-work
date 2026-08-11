import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  AUTH_SESSION_KEY,
  getAuthHeader,
  getAuthSession,
  getAuthToken,
  isAuthenticated,
} from '../authToken'

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
