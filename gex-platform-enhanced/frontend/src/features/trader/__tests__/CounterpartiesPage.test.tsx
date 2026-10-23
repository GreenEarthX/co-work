/**
 * Counterparties (2026-10-23) reads and adds to the register in PostgreSQL
 * (tb_counterparty) — it replaced a placeholder page and shows nothing of its own.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CounterpartiesPage } from '../CounterpartiesPage'

afterEach(() => vi.unstubAllGlobals())

describe('Counterparties', () => {
  it('lists the register the server returns, and nothing else', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([
      { id: 'c1', legal_name: 'TEST Offtaker plc', lei: null, country_code: 'GB', is_active: true,
        created_at: '2026-10-23', updated_at: '2026-10-23' }]), { status: 200 })))
    render(<CounterpartiesPage />)
    expect(await screen.findByText('TEST Offtaker plc')).toBeTruthy()
    expect(screen.getByText('1 in the register')).toBeTruthy()
  })

  it('adds an entity to the register', async () => {
    const calls: { url: string; init?: RequestInit }[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return new Response(JSON.stringify(init?.method === 'POST' ? { id: 'c2' } : []), { status: 200 })
    }))
    render(<CounterpartiesPage />)
    expect(await screen.findByText('The register is empty.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Legal name'), { target: { value: 'TEST Plant OpCo BV' } })
    fireEvent.change(screen.getByLabelText('Country'), { target: { value: 'nl' } })
    fireEvent.click(screen.getByRole('button', { name: /Add to the register/ }))
    await waitFor(() => expect(calls.some(c => c.init?.method === 'POST')).toBe(true))
    const post = calls.find(c => c.init?.method === 'POST')!
    expect(post.url).toBe('/api/v1/trading-book/counterparties')
    expect(JSON.parse(String(post.init!.body))).toEqual({ legal_name: 'TEST Plant OpCo BV', lei: null, country_code: 'NL' })
  })
})
