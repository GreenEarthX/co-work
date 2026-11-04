/**
 * Your telephone number: read from the server, saved with PUT, the server's
 * refusal shown as its reason.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TelephoneSection } from '../TelephoneSection'

function stub(put: { status: number; body: unknown }) {
  const calls: { method: string; body?: string }[] = []
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    calls.push({ method, body: init?.body as string | undefined })
    const r = method === 'PUT' ? put : { status: 200, body: { telephone: null } }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }))
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('Your telephone number', () => {
  it('saves a new number and shows what the server stored', async () => {
    const calls = stub({ status: 200, body: { telephone: '+49 160 1234567', changed: true } })
    render(<TelephoneSection />)
    const input = await screen.findByPlaceholderText('Not recorded')
    const save = screen.getByRole('button', { name: 'Save number' })
    expect(save).toBeDisabled()

    fireEvent.change(input, { target: { value: '+49 160  1234567' } })
    fireEvent.click(save)
    await waitFor(() => expect(screen.getByText('Telephone number saved.')).toBeInTheDocument())
    const put = calls.find(c => c.method === 'PUT')!
    expect(JSON.parse(put.body!)).toEqual({ telephone: '+49 160  1234567' })
    expect(screen.getByLabelText('Telephone')).toHaveValue('+49 160 1234567')
  })

  it("shows the server's reason when it refuses", async () => {
    stub({ status: 422, body: { detail: 'Enter a telephone number: digits, spaces, and an optional leading +.' } })
    render(<TelephoneSection />)
    fireEvent.change(await screen.findByPlaceholderText('Not recorded'), { target: { value: 'call me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save number' }))
    await waitFor(() => expect(screen.getByText(/Enter a telephone number/)).toBeInTheDocument())
  })
})
