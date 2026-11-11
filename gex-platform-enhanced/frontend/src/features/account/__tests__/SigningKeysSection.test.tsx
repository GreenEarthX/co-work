/**
 * Signing keys (Phase 5): the section lists what the server holds, posts each step to
 * its own endpoint, and shows the server's refusal (four eyes) rather than deciding.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SigningKeysSection } from '../SigningKeysSection'

const KEYS = [
  { key_ref: 'ed25519:aaaa', scheme: 'ed25519', public_key: 'A', label: 'HSM', status: 'PROPOSED', proposed_by: 'u_me',
    proposed_at: '2026-11-11', approved_by: null, revoked_by: null, revoke_reason: null },
  { key_ref: 'ed25519:bbbb', scheme: 'ed25519', public_key: 'B', label: null, status: 'ACTIVE', proposed_by: 'u_a',
    proposed_at: '2026-11-10', approved_by: 'u_b', revoked_by: null, revoke_reason: null },
]

function stub(post: { status: number; body: unknown } = { status: 200, body: {} }) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const r = init?.method === 'POST' ? post : { status: 200, body: { keys: KEYS } }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }))
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('SigningKeysSection', () => {
  it('lists the keys and posts activation, revocation with its reason, and a proposal', async () => {
    const calls = stub()
    render(<SigningKeysSection />)
    const proposed = await screen.findByTestId('key-ed25519:aaaa')
    fireEvent.click(within(proposed).getByRole('button', { name: 'Activate' }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/trading-book/party-keys/ed25519%3Aaaaa/activate'
      && c.init?.method === 'POST')).toBe(true))
    const active = screen.getByTestId('key-ed25519:bbbb')
    const revoke = within(active).getByRole('button', { name: 'Revoke' })
    expect(revoke).toBeDisabled()                                   // no reason, no revocation
    fireEvent.change(within(active).getByLabelText('Reason to revoke ed25519:bbbb'), { target: { value: 'laptop lost' } })
    fireEvent.click(revoke)
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/ed25519%3Abbbb/revoke')
      && JSON.parse(String(c.init?.body)).reason === 'laptop lost')).toBe(true))
    fireEvent.change(screen.getByLabelText('Public key (base64)'), { target: { value: 'cHVibGlj' } })
    fireEvent.click(screen.getByRole('button', { name: 'Propose key' }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/trading-book/party-keys' && c.init?.method === 'POST'
      && JSON.parse(String(c.init?.body)).public_key === 'cHVibGlj')).toBe(true))
  })

  it("shows the server's four-eyes refusal and keeps what was typed", async () => {
    stub({ status: 403, body: { detail: { code: 'FOUR_EYES', message: 'A second executive activates the key.' } } })
    render(<SigningKeysSection />)
    fireEvent.click(within(await screen.findByTestId('key-ed25519:aaaa')).getByRole('button', { name: 'Activate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A second executive activates the key.')
    fireEvent.change(screen.getByLabelText('Public key (base64)'), { target: { value: 'cHVibGlj' } })
    fireEvent.click(screen.getByRole('button', { name: 'Propose key' }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByLabelText('Public key (base64)')).toHaveValue('cHVibGlj')
  })
})
