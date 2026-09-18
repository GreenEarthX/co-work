import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AUTH_SESSION_KEY } from '../authToken'
import { expireSession } from '../sessionGuard'
import { installFetchAuthBridge } from '../fetchAuthBridge'

// HANDOFF §8.11: a tab left open past the 30-minute token kept rendering
// signed-in routes while ABAC answered every call 401, and /pricing-curves
// silently drew seed curves. The bridge decorates every /api/ fetch, so it is
// where a dead session is noticed — before sending (clock) and after (401).

vi.mock('../sessionGuard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../sessionGuard')>()),
  expireSession: vi.fn(),
}))

function jwt(expSecondsFromNow: number, sub = 'u1'): string {
  const b64url = (s: string) => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow
  return `${b64url('{"alg":"HS256"}')}.${b64url(JSON.stringify({ sub, exp }))}.sig`
}

function setSession(token: string) {
  localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify({ token, email: 'a@b.io' }))
}

const TERM_CURVE = '/api/v1/pricing/term-curve/e-methanol'
const originalFetch = window.fetch
let nativeFetch: ReturnType<typeof vi.fn>
let onSessionRejected: ReturnType<typeof vi.fn>

function install(options?: Parameters<typeof installFetchAuthBridge>[0]) {
  delete window.__gexFetchAuthInstalled__
  window.fetch = nativeFetch as unknown as typeof fetch
  installFetchAuthBridge(options)
}

function sentAuthorization(call = 0): string | null {
  const [input, init] = nativeFetch.mock.calls[call] as [RequestInfo, RequestInit | undefined]
  const headers = input instanceof Request ? input.headers : new Headers(init?.headers)
  return headers.get('Authorization')
}

describe('installFetchAuthBridge', () => {
  beforeEach(() => {
    localStorage.clear()
    nativeFetch = vi.fn(async () => new Response('{}', { status: 200 }))
    onSessionRejected = vi.fn()
    vi.mocked(expireSession).mockClear()
    install({ onSessionRejected })
  })

  afterEach(() => {
    window.fetch = originalFetch
    delete window.__gexFetchAuthInstalled__
  })

  it('attaches the stored bearer to /api/ requests and leaves other hosts alone', async () => {
    const token = jwt(1800)
    setSession(token)

    await fetch(TERM_CURVE)
    await fetch('https://engine.test/whoami')

    expect(sentAuthorization(0)).toBe(`Bearer ${token}`)
    expect(nativeFetch.mock.calls[1]).toEqual(['https://engine.test/whoami', undefined])
    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('ends the session on a 401 to a request that carried the stored bearer', async () => {
    setSession(jwt(1800))
    nativeFetch.mockResolvedValue(new Response('{"detail":"Authentication required"}', { status: 401 }))

    const response = await fetch(TERM_CURVE)

    expect(onSessionRejected).toHaveBeenCalledTimes(1)
    // Callers still see the real response; the bridge does not invent one.
    expect(response.status).toBe(401)
  })

  it('handles Request objects the same way', async () => {
    const token = jwt(1800)
    setSession(token)
    nativeFetch.mockResolvedValue(new Response('{}', { status: 401 }))

    await fetch(new Request(`${window.location.origin}${TERM_CURVE}`))

    expect(sentAuthorization(0)).toBe(`Bearer ${token}`)
    expect(onSessionRejected).toHaveBeenCalledTimes(1)
  })

  it('does not end the session on a 401 from a credential exchange', async () => {
    // A wrong password on /login is a 401 too; it must not clear the session
    // or redirect onto the page the user is already on.
    setSession(jwt(1800))
    nativeFetch.mockImplementation(async () => new Response('{}', { status: 401 }))

    // Named literally: iterating CREDENTIAL_EXCHANGE_PATHS passed with login
    // deleted from the set — negative-verified 2026-09-14.
    const exchanges = ['/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/account/register']
    for (const path of exchanges) {
      await fetch(path, { method: 'POST' })
    }

    expect(nativeFetch).toHaveBeenCalledTimes(exchanges.length)
    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('does not act on a guest 401 — there is no session to end', async () => {
    nativeFetch.mockResolvedValue(new Response('{}', { status: 401 }))

    await fetch(TERM_CURVE)

    expect(sentAuthorization(0)).toBeNull()
    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('keeps a newer session when a request issued before signing in again 401s', async () => {
    setSession(jwt(1800, 'old'))
    nativeFetch.mockImplementation(async () => {
      setSession(jwt(1800, 'new'))
      return new Response('{}', { status: 401 })
    })

    await fetch(TERM_CURVE)

    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('does not act on a 401 for a token the caller supplied itself', async () => {
    setSession(jwt(1800))
    nativeFetch.mockResolvedValue(new Response('{}', { status: 401 }))

    await fetch(TERM_CURVE, { headers: { Authorization: 'Bearer some-other-token' } })

    expect(sentAuthorization(0)).toBe('Bearer some-other-token')
    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('ignores responses other than 401', async () => {
    setSession(jwt(1800))
    for (const status of [200, 403, 404, 500]) {
      nativeFetch.mockResolvedValueOnce(new Response('{}', { status }))
      await fetch(TERM_CURVE)
    }
    expect(onSessionRejected).not.toHaveBeenCalled()
  })

  it('ends an expired session before sending, and never sends its bearer', async () => {
    setSession(jwt(-60))

    const response = await fetch(TERM_CURVE)

    expect(onSessionRejected).toHaveBeenCalledTimes(1)
    expect(sentAuthorization(0)).toBeNull()
    // Sent anyway, without the dead bearer: public routes still answer.
    expect(response.status).toBe(200)
  })

  it('defaults to expireSession', async () => {
    install()
    setSession(jwt(1800))
    nativeFetch.mockResolvedValue(new Response('{}', { status: 401 }))

    await fetch(TERM_CURVE)

    expect(expireSession).toHaveBeenCalledTimes(1)
  })
})
