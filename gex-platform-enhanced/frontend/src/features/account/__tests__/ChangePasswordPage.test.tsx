/**
 * Change your password: the rule is stated before typing, the server's refusal
 * is shown as its reason, and the new refresh token replaces the old one. The
 * banner appears while a GEX-chosen temporary password is in force.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ChangePasswordPage } from '../ChangePasswordPage'
import { TemporaryPasswordBanner } from '@/components/TemporaryPasswordBanner'

const STATUS = { temporary: true, policy: { min_length: 12, max_length: 128, note: 'Length is what matters.' } }

function stub(change: { status: number; body: unknown } = { status: 200, body: { message: 'Password changed. Your other sessions were signed out.', refresh_token: 'rt_new' } }) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const r = url.endsWith('/password-status') ? { status: 200, body: STATUS } : change
    return new Response(JSON.stringify(r.body), { status: r.status })
  }))
  return calls
}

function fill(current: string, next: string, again = next) {
  fireEvent.change(screen.getByLabelText('Current password'), { target: { value: current } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: next } })
  fireEvent.change(screen.getByLabelText('New password again'), { target: { value: again } })
}

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('Change your password', () => {
  it('states the rule and holds the button until both entries match the minimum', async () => {
    stub()
    render(<ChangePasswordPage />)
    await waitFor(() => expect(screen.getByText(/temporary password chosen by GEX/)).toBeInTheDocument())
    expect(screen.getByText(/At least 12 characters/)).toBeInTheDocument()

    const button = screen.getByRole('button', { name: 'Change password' })
    fill('old one', 'too short')
    expect(button).toBeDisabled()
    fill('old one', 'orange kettle under a bridge', 'orange kettle under a bridgX')
    expect(button).toBeDisabled()
    expect(screen.getByText('The two entries differ.')).toBeInTheDocument()
    fill('old one', 'orange kettle under a bridge')
    expect(button).toBeEnabled()
  })

  it('posts the change and keeps this session with the new refresh token', async () => {
    localStorage.setItem('gex_auth_session', JSON.stringify({ token: 't', refreshToken: 'rt_old', email: 'a@b.c' }))
    const calls = stub()
    render(<ChangePasswordPage />)
    await waitFor(() => expect(screen.getByText(/At least 12/)).toBeInTheDocument())
    fill('the current one', 'orange kettle under a bridge')
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() => expect(screen.getByText('Password changed. Your other sessions were signed out.')).toBeInTheDocument())
    const post = calls.find(c => c.url === '/api/v1/auth/change-password')!
    expect(JSON.parse(String(post.init?.body))).toEqual({ current_password: 'the current one', new_password: 'orange kettle under a bridge' })
    expect(JSON.parse(localStorage.getItem('gex_auth_session')!).refreshToken).toBe('rt_new')
    expect(screen.queryByText(/temporary password chosen by GEX/)).toBeNull()
  })

  it("shows the server's reason when it refuses", async () => {
    stub({ status: 422, body: { detail: 'That password is one of the most commonly used ones.' } })
    render(<ChangePasswordPage />)
    await waitFor(() => expect(screen.getByText(/At least 12/)).toBeInTheDocument())
    fill('the current one', 'password1234')
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    await waitFor(() => expect(screen.getByText('That password is one of the most commonly used ones.')).toBeInTheDocument())
  })
})

describe('Temporary password banner', () => {
  it('shows while a temporary password is in force and goes once it is changed', async () => {
    stub()
    render(<MemoryRouter><TemporaryPasswordBanner signedIn /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('temporary password chosen by GEX'))
    expect(screen.getByRole('link', { name: 'Change it now' })).toHaveAttribute('href', '/account/password')
    window.dispatchEvent(new Event('gex-password-changed'))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('asks nothing when signed out', () => {
    const calls = stub()
    render(<MemoryRouter><TemporaryPasswordBanner signedIn={false} /></MemoryRouter>)
    expect(calls).toHaveLength(0)
  })
})
