/**
 * GEX staff console: the screen greys out what the server would refuse, posts
 * each vetting step to its own endpoint, and is in the menu of GEX staff only.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GexStaffConsolePage } from '../GexStaffConsolePage'
import { cisoMenuItems } from '@/config/menuArchitecture'

const ME = 'u_staff_me'
const summary = {
  caller_user_id: ME,
  administrators: [{ user_id: ME, email: 'me@greenearthx.com', user_name: 'Me', account_state: 'ACTIVE', activated_by: 'MANUAL_ADMIN_GRANT', last_sign_in: null }],
  companies: [{ company_id: 'mohring_energie', company_name: 'Möhring Energie', company_type: 'PRODUCER', is_test: false, accounts: {}, projects_owned: 0, test_projects_owned: 0 }],
  vetting_queue_count: 2,
  staff_rights: { readable_on_every_project: ['EVIDENCE', 'GATE_EVALUATION'], may: ['Read gates'], may_not: ['Verify evidence'], reviewer_gates: { CERTIFIER: ['G2', 'G11'] } },
}
const queue = {
  applications: [
    { user_id: 'u_called_by_me', email: 'a@x.test', user_name: 'Called By Me', company_name: 'X', account_state: 'IN_VETTING', phone_verified_by: ME, agreement_ref: 'USA-1' },
    { user_id: 'u_fresh', email: 'b@x.test', user_name: 'Fresh Applicant', company_name: 'X', account_state: 'PENDING', phone_verified_by: null, agreement_ref: null, telephone: '+49 160 0000000' },
  ],
}
const onboarding = { company_id: 'mohring_energie', company_name: 'Möhring Energie', accounts: [], steps: [
  { key: 'tenant', label: 'Company registered', actor: 'GEX', status: 'done', detail: 'Möhring Energie (mohring_energie)' },
  { key: 'register', label: 'Accounts registered', actor: 'Client', status: 'waiting', detail: 'No account registered for this company yet' },
] }

function stub(overrides: Record<string, { status: number; body: unknown }> = {}) {
  const calls: { url: string; init?: RequestInit }[] = []
  const routes: Record<string, { status: number; body: unknown }> = {
    '/api/v1/gex-console/summary': { status: 200, body: summary },
    '/api/v1/account/vetting-queue': { status: 200, body: queue },
    '/api/v1/gex-console/onboarding/mohring_energie': { status: 200, body: onboarding },
    ...overrides,
  }
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const r = routes[url] ?? { status: 200, body: {} }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }))
  return calls
}

const row = (name: string) => screen.getByText(name).closest('tr') as HTMLElement

afterEach(() => vi.unstubAllGlobals())

describe('GEX staff console', () => {
  it('refuses activation by the admin who made the call, and before vetting is on file', async () => {
    stub()
    render(<GexStaffConsolePage />)
    await waitFor(() => expect(screen.getByText('Called By Me')).toBeInTheDocument())

    const mine = within(row('Called By Me')).getByRole('button', { name: 'Activate' })
    expect(mine).toBeDisabled()
    expect(mine).toHaveAttribute('title', 'You made the verification call: another GEX admin must activate')

    const fresh = within(row('Fresh Applicant')).getByRole('button', { name: 'Activate' })
    expect(fresh).toBeDisabled()
    expect(fresh.getAttribute('title')).toMatch(/verification call and the signed agreement/)
  })

  it('posts the verification call to its own endpoint', async () => {
    const calls = stub()
    render(<GexStaffConsolePage />)
    await waitFor(() => expect(screen.getByText('Fresh Applicant')).toBeInTheDocument())

    fireEvent.click(within(row('Fresh Applicant')).getByRole('button', { name: 'Record call' }))
    const form = screen.getByRole('form', { name: 'Record call' })
    // Prefilled with the account's own number; staff correct it if they dialled another.
    expect(within(form).getByLabelText('Number called')).toHaveValue('+49 160 0000000')
    fireEvent.change(within(form).getByLabelText('Number called'), { target: { value: '+49 30 1234567' } })
    fireEvent.change(within(form).getByLabelText('Spoke with'), { target: { value: 'Fresh Applicant' } })
    fireEvent.click(within(form).getByLabelText('Identity confirmed'))
    fireEvent.click(within(form).getByLabelText('Organisation confirmed'))
    fireEvent.click(within(form).getByRole('button', { name: 'Record' }))

    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/account/u_fresh/telephone-verification')).toBe(true))
    const post = calls.find(c => c.url === '/api/v1/account/u_fresh/telephone-verification')!
    expect(post.init?.method).toBe('POST')
    expect(JSON.parse(String(post.init?.body))).toMatchObject({
      telephone_called: '+49 30 1234567', spoke_with: 'Fresh Applicant',
      identity_confirmed: true, organisation_confirmed: true,
    })
  })

  it('shows the onboarding steps from the server', async () => {
    stub()
    render(<GexStaffConsolePage />)
    await waitFor(() => expect(screen.getByTestId('step-register')).toHaveTextContent('No account registered for this company yet'))
    expect(screen.getByTestId('step-tenant')).toHaveTextContent('Company registered')
  })

  it("says the server's refusal rather than showing an empty console", async () => {
    stub({ '/api/v1/gex-console/summary': { status: 403, body: { detail: { code: 'GEX_STAFF_ONLY', message: 'The GEX staff console is for GEX platform administrators.' } } } })
    render(<GexStaffConsolePage />)
    await waitFor(() => expect(screen.getByText('The GEX staff console is for GEX platform administrators.')).toBeInTheDocument())
  })
})

describe('menu', () => {
  it('offers the console to GEX staff only', () => {
    expect(cisoMenuItems({ service_type: 'PLATFORM' }).map(i => i.id)).toContain('gex-console')
    expect(cisoMenuItems({ service_type: 'BANK' }).map(i => i.id)).not.toContain('gex-console')
    expect(cisoMenuItems(null).map(i => i.id)).not.toContain('gex-console')
  })
})
