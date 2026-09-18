// RequireAuth used to trust sessionTier alone. sessionTier is set at login and
// outlives the 30-minute token, so an expired tab kept rendering signed-in
// routes while every call 401'd (HANDOFF §8.11).

import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { UserRoleProvider } from '@/contexts/UserRoleContext'
import { expireSession } from '@/lib/sessionGuard'
import { RequireAuth } from './RequireAuth'

vi.mock('@/lib/sessionGuard', () => ({ expireSession: vi.fn() }))

function jwt(expSecondsFromNow: number): string {
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow
  return `e30.${btoa(JSON.stringify({ exp })).replace(/=+$/, '')}.sig`
}

function signIn(token?: string) {
  localStorage.setItem('gex_session_tier', 'authenticated')
  if (token) localStorage.setItem('gex_auth_session', JSON.stringify({ token, email: 'a@b.io' }))
}

function renderGuarded() {
  return render(
    <UserRoleProvider>
      <MemoryRouter initialEntries={['/pricing-curves']}>
        <Routes>
          <Route path="/login" element={<div>LOGIN_PAGE</div>} />
          <Route
            path="/pricing-curves"
            element={<RequireAuth><div>SIGNED_IN_CONTENT</div></RequireAuth>}
          />
        </Routes>
      </MemoryRouter>
    </UserRoleProvider>,
  )
}

describe('RequireAuth', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(expireSession).mockClear()
  })

  it('renders children for a signed-in user with a valid token', () => {
    signIn(jwt(1800))
    renderGuarded()
    expect(screen.getByText('SIGNED_IN_CONTENT')).toBeInTheDocument()
    expect(expireSession).not.toHaveBeenCalled()
  })

  it('redirects a guest to /login', () => {
    renderGuarded()
    expect(screen.getByText('LOGIN_PAGE')).toBeInTheDocument()
    expect(expireSession).not.toHaveBeenCalled()
  })

  it('ends an expired session instead of rendering signed-in content', () => {
    signIn(jwt(-60))
    renderGuarded()
    expect(screen.queryByText('SIGNED_IN_CONTENT')).not.toBeInTheDocument()
    expect(expireSession).toHaveBeenCalledTimes(1)
  })

  it('ends an authenticated tier that has no token', () => {
    signIn()
    renderGuarded()
    expect(screen.queryByText('SIGNED_IN_CONTENT')).not.toBeInTheDocument()
    expect(expireSession).toHaveBeenCalledTimes(1)
  })
})
