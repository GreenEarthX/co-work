import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// expireSession keeps a once-per-page-load flag, so each test takes a fresh
// module instance.
async function loadGuard() {
  vi.resetModules()
  return import('../sessionGuard')
}

function setSession(token: string) {
  localStorage.setItem('gex_auth_session', JSON.stringify({ token, email: 'a@b.io' }))
}

describe('expireSession', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.replaceState(null, '', '/pricing-curves')
  })
  afterEach(() => window.history.replaceState(null, '', '/'))

  it('clears the session and sends the user to /login', async () => {
    const { expireSession, LOGIN_PATH } = await loadGuard()
    setSession('jwt-abc')
    localStorage.setItem('gex_session_tier', 'authenticated')
    localStorage.setItem('gex_user_role', '{"company_name":"X"}')
    const navigate = vi.fn()

    expireSession(navigate)

    expect(localStorage.getItem('gex_auth_session')).toBeNull()
    expect(localStorage.getItem('gex_user_role')).toBeNull()
    expect(localStorage.getItem('gex_session_tier')).toBe('guest')
    expect(navigate).toHaveBeenCalledWith(LOGIN_PATH)
  })

  it('redirects once for a burst of rejections', async () => {
    // /pricing-curves fires eight term-curve requests; eight 401s must not
    // queue eight navigations.
    const { expireSession } = await loadGuard()
    const navigate = vi.fn()
    for (let i = 0; i < 8; i++) expireSession(navigate)
    expect(navigate).toHaveBeenCalledTimes(1)
  })

  it('does not navigate when already on /login — no redirect loop', async () => {
    const { expireSession } = await loadGuard()
    window.history.replaceState(null, '', '/login')
    setSession('jwt-abc')
    const navigate = vi.fn()

    expireSession(navigate)

    expect(navigate).not.toHaveBeenCalled()
    expect(localStorage.getItem('gex_auth_session')).toBeNull()
  })
})

describe('isSessionRejection', () => {
  beforeEach(() => localStorage.clear())

  it('is a 401 carrying the bearer that is still stored', async () => {
    const { isSessionRejection } = await loadGuard()
    setSession('jwt-abc')
    expect(isSessionRejection(401, '/api/v1/pricing/term-curve/x', 'Bearer jwt-abc')).toBe(true)
    expect(isSessionRejection(403, '/api/v1/pricing/term-curve/x', 'Bearer jwt-abc')).toBe(false)
    expect(isSessionRejection(401, '/api/v1/pricing/term-curve/x', 'Bearer other')).toBe(false)
    expect(isSessionRejection(401, '/api/v1/pricing/term-curve/x', null)).toBe(false)
  })

  it('is never a credential exchange, and never without a stored session', async () => {
    const { isSessionRejection } = await loadGuard()
    setSession('jwt-abc')
    // Named literally, not read from CREDENTIAL_EXCHANGE_PATHS — a loop over
    // the set passes whatever the set holds (negative-verified 2026-09-14).
    for (const path of ['/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/account/register']) {
      expect(isSessionRejection(401, path, 'Bearer jwt-abc')).toBe(false)
    }
    // The exemption is those three routes, not the /auth/ prefix: these
    // require a session, so their 401 means it ended.
    expect(isSessionRejection(401, '/api/v1/auth/login-history', 'Bearer jwt-abc')).toBe(true)
    expect(isSessionRejection(401, '/api/v1/auth/me', 'Bearer jwt-abc')).toBe(true)
    localStorage.clear()
    expect(isSessionRejection(401, '/api/v1/auth/me', 'Bearer jwt-abc')).toBe(false)
  })
})
