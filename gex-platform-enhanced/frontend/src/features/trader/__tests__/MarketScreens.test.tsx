/**
 * The market screens read the market engine, not sample data (gap register
 * G-04, 2026-10-23). Listings are anonymised (JML's decision): the screen shows
 * what the server sends and nothing names a counterparty before a match.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MarketDiscoveryPage } from '../MarketDiscoveryPage'
import RFQManagementPage from '../RFQManagementPage'

type Route = (url: string, init?: RequestInit) => unknown

function serve(route: Route) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    // Molecule lists come from tb_commodity via the API, never from a constant.
    const body = url.endsWith('/market/commodities') ? { commodities: COMMODITIES } : route(url, init)
    if (body instanceof Response) return body
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  return calls
}

afterEach(() => vi.unstubAllGlobals())

const COMMODITIES = [
  { code: 'H2', name: 'Hydrogen', default_unit: 't', market_molecule: 'H2' },
  { code: 'NH3', name: 'Ammonia', default_unit: 't', market_molecule: 'NH3' },
]

const OFFER = { id: 'off_1', molecule: 'H2', volume_mtpd: 20, price_eur_kg: 6.1, delivery_start: '2027-01-01',
  delivery_end: '2029-12-31', carbon_intensity_gco2e_mj: 12.5, certification_pathway: 'RFNBO',
  created_at: '2026-10-23', mine: false }
const RFQ = { id: 'rfq_1', molecule: 'H2', volume_mtpd: 5, max_price_eur_kg: null, delivery_start: '2027-01-01',
  delivery_end: '2027-12-31', created_at: '2026-10-23', mine: true }

describe('Market Discovery', () => {
  it('shows the anonymised listings the server returns and flags the caller\'s own', async () => {
    serve((url) => (url.includes('/listings/offers') ? { offers: [OFFER] } : { rfqs: [RFQ] }))
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    expect(await screen.findByText('€6.10/kg')).toBeTruthy()
    expect(screen.getByText('12.5 gCO₂e/MJ')).toBeTruthy()
    expect(screen.getByText(/Supply — open listings \(1\)/)).toBeTruthy()
    expect(screen.getByText(/Demand — open RFQs \(1\)/)).toBeTruthy()
    expect(screen.getAllByText('yours')).toHaveLength(1)
  })

  it('proposes one of the caller\'s RFQs to a listing; GEX runs no matching', async () => {
    const calls = serve((url, init) => (init?.method === 'POST' ? { id: 'm_1', status: 'pending' }
      : url.includes('/listings/offers') ? { offers: [OFFER] }
      : url.includes('/rfqs/mine') ? { rfqs: [{ ...RFQ, id: 'rfq_mine', status: 'open', buyer_company_id: 'me' }] }
      : { rfqs: [] }))
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Propose a match' }))
    expect(await screen.findByText(/binds only when both parties accept/)).toBeTruthy()
    const post = calls.find(c => c.init?.method === 'POST')!
    expect(post.url).toBe('/api/v1/market/matches')
    expect(JSON.parse(String(post.init!.body))).toEqual({ offer_id: 'off_1', rfq_id: 'rfq_mine' })
    expect(calls.some(c => c.url.includes('/matching/run'))).toBe(false)
    expect(screen.queryByRole('button', { name: /Find matches/ })).toBeNull()
  })

  it('shows a refusal rather than an empty market', async () => {
    serve(() => new Response(JSON.stringify({ detail: { code: 'AUTHENTICATION_REQUIRED',
      message: 'Sign in to use the market.' } }), { status: 401 }))
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    expect(await screen.findByText('Sign in to use the market.')).toBeTruthy()
  })
})

describe('RFQs & Negotiation', () => {
  it('lists the company\'s own RFQs from the market engine and offers only the allowed moves', async () => {
    serve(() => ({ rfqs: [
      { ...RFQ, id: 'r_draft', status: 'draft', buyer_company_id: 'me', correlation_id: 'RFQ-ab12' },
      { ...RFQ, id: 'r_open', molecule: 'NH3', status: 'open', buyer_company_id: 'me' },
      { ...RFQ, id: 'r_done', molecule: 'SAF', status: 'matched', buyer_company_id: 'me' },
    ] }))
    render(<RFQManagementPage />)
    expect(await screen.findByText('RFQ-ab12')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeTruthy()
    // 'matched' is set by the market: no button can set or leave it.
    expect(screen.getAllByRole('button', { name: /^(Publish|Cancel|Withdraw)$/ })).toHaveLength(3)
  })

  it('creates an RFQ without naming a buyer: the server takes it from the session', async () => {
    const calls = serve((url, init) => (init?.method === 'POST' ? { id: 'r_new', status: 'open' } : { rfqs: [] }))
    render(<RFQManagementPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Create RFQ' }))
    // The molecule list is the server's (tb_commodity), not a constant in the page.
    expect(await screen.findByRole('option', { name: 'Ammonia' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Molecule'), { target: { value: 'H2' } })
    fireEvent.change(screen.getByLabelText('Volume (MTPD)'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('Delivery Start'), { target: { value: '2027-01-01' } })
    fireEvent.change(screen.getByLabelText('Delivery End'), { target: { value: '2027-12-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Publish RFQ' }))
    await waitFor(() => expect(calls.some(c => c.init?.method === 'POST')).toBe(true))
    const post = calls.find(c => c.init?.method === 'POST')!
    expect(post.url).toBe('/api/v1/market/rfqs')
    const body = JSON.parse(String(post.init!.body))
    expect(body).toMatchObject({ molecule: 'H2', volume_mtpd: 12, status: 'open' })
    expect(body).not.toHaveProperty('buyer_name')
  })
})
