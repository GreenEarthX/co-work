/**
 * T6 — the login page's molecule count is the length of the list it names
 * (it once said "4 Fuel Molecules" beside a sentence naming five).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FUEL_MOLECULES, LoginPage, loginErrorText } from '../LoginPage'

vi.mock('@/contexts/UserRoleContext', () => ({
  useUserRole: () => ({ login: vi.fn(), continueAsGuest: vi.fn() }),
}))

describe('LoginPage fuel molecules', () => {
  it('counts exactly the molecules it names', () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    const count = screen.getByText('Fuel Molecules').previousElementSibling
    expect(count).toHaveTextContent(String(FUEL_MOLECULES.length))
    expect(FUEL_MOLECULES).toHaveLength(5)

    const sentence = screen.getByText(/Bankability assessment, capital structuring, and compliance/)
    for (const molecule of FUEL_MOLECULES) expect(sentence).toHaveTextContent(molecule)
    expect(sentence.textContent).not.toMatch(/\s,/)
  })
})

// A correct password on an account that is not ACTIVE yet is refused with 403
// and an OBJECT detail ({error, account_state, reason}). The page rendered that
// object as a React child, threw, and left a blank screen (2026-11-03).
describe('LoginPage refusals', () => {
  afterEach(() => vi.unstubAllGlobals())

  function submitWith(status: number, body: unknown) {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })))
    const { container } = render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.change(container.querySelector('input[type="email"]')!, { target: { value: 'applicant@example.com' } })
    fireEvent.change(container.querySelector('input[placeholder="••••••••"]')!, { target: { value: 'a long enough passphrase' } })
    fireEvent.click(container.querySelector('button[type="submit"]')!)
  }

  it('shows the reason when the account is not active yet (403, object detail)', async () => {
    submitWith(403, { detail: { error: 'account_not_active', account_state: 'PENDING', reason: 'This account is not yet active.' } })
    expect(await screen.findByText('This account is not yet active.')).toBeInTheDocument()
    expect(screen.getByText('Welcome back')).toBeInTheDocument()
  })

  it('still shows a plain-string refusal (401)', async () => {
    submitWith(401, { detail: 'Invalid credentials' })
    expect(await screen.findByText('Invalid credentials')).toBeInTheDocument()
  })
})

describe('loginErrorText', () => {
  it('reads string and object refusals, and nothing else', () => {
    expect(loginErrorText({ detail: 'Invalid credentials' })).toBe('Invalid credentials')
    expect(loginErrorText({ detail: { error: 'account_not_active', reason: 'Not yet active.' } })).toBe('Not yet active.')
    expect(loginErrorText({ detail: { error: 'account_not_active' } })).toBe('account_not_active')
    expect(loginErrorText({ detail: { account_state: 'PENDING' } })).toBeNull()
    expect(loginErrorText(null)).toBeNull()
  })
})

// The FortaVerde demo sign-ins have their own password (the policy refuses
// demo1234), so "fill" puts in the address and leaves the password to be typed.
describe('LoginPage FortaVerde demo sign-ins', () => {
  it('fills the address only', () => {
    const { container } = render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('Jan Block (demo)'))
    expect(container.querySelector('input[type="email"]')).toHaveValue('jan.block@fortaverde.test')
    expect(container.querySelector('input[placeholder="••••••••"]')).toHaveValue('')
    expect(screen.getByText('FortaVerde Pecém (TEST) · own password')).toBeInTheDocument()
  })

  it('still fills demo1234 for the seeded demo accounts', () => {
    const { container } = render(<MemoryRouter><LoginPage /></MemoryRouter>)
    fireEvent.click(screen.getByText('Lisa Friedrich'))
    expect(container.querySelector('input[placeholder="••••••••"]')).toHaveValue('demo1234')
  })
})
