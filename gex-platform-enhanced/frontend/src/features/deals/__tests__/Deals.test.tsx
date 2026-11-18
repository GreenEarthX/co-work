/**
 * R9 on screen (D-D): ask about a listing without binding anything; the receiver sees a badge, not a
 * name, and alone chooses Share contact or Decline; identities appear only after consent.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DealsPage from '../DealsPage'
import { MarketDiscoveryPage } from '@/features/trader/MarketDiscoveryPage'
import { resetMarketPolicy } from '@/lib/marketPolicy'

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

const OFFER = { id: 'o1', molecule: 'e-Methanol', volume_mtpd: 40, price_eur_kg: 1.1, delivery_start: '2028-01-01',
  delivery_end: '2028-12-31', created_at: '2026-11-14', mine: false, seller_role: 'PRODUCER', seller_vetting: 'vetted' }
const MY_RFQ = { id: 'r_mine', molecule: 'e-Methanol', volume_mtpd: 10, status: 'open', delivery_start: '2028-01-01',
  delivery_end: '2028-12-31' }
const base = { subject: { kind: 'listing', id: 'o1', molecule: 'e-Methanol', volume_mtpd: 40, price_eur_kg: 1.1,
  delivery_start: '2028-01-01', delivery_end: '2028-12-31' }, subject_state: 'OPEN', about_rfq_id: null, assessment_id: null,
  created_at: '2026-11-14T10:00:00Z', decided_at: null,
  messages: [{ side: 'them', body: 'Is Q1 firm?', evidence_request: 'ISCC EU 2028-Q1', at: '2026-11-14T10:00:00Z' }] }
const RECEIVED = { ...base, id: 'e1', role: 'received', status: 'open', counterparty: { role: 'OFFTAKER', vetting: 'vetted' },
  can: { reply: true, share_contact: true, decline: true, withdraw: false } }
const SHARED = { ...RECEIVED, status: 'contact_shared', decided_at: '2026-11-14T11:00:00Z',
  counterparty: { role: 'OFFTAKER', vetting: 'vetted', identity: { company_name: 'TEST Buyer GmbH',
    person: { name: 'TEST Buyer Person', email: 'buyer@test.invalid' } } },
  can: { reply: true, share_contact: false, decline: false, withdraw: false } }

function serve(allowed: string[], enquiry: unknown = RECEIVED) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const body = url.endsWith('/market/policy') ? { allowed }
      : url.endsWith('/market/commodities') ? { commodities: [] }
      : url.includes('/listings/offers') ? { offers: [OFFER] }
      : url.includes('/listings/rfqs') ? { rfqs: [] }
      : url.endsWith('/rfqs/mine') ? { rfqs: [MY_RFQ] }
      : url.endsWith('/market/enquiries') ? { ...base, id: 'e_new', role: 'sent', status: 'open' }
      : url.endsWith('/enquiries/mine') ? { enquiries: [enquiry] }
      : url.endsWith('/share-contact') ? SHARED
      : url.includes('/market/enquiries/') ? enquiry
      : {}
    return new Response(JSON.stringify(body), { status: url.endsWith('/market/enquiries') ? 201 : 200 })
  }))
  return calls
}

describe('asking about a listing', () => {
  it('sends a non-binding enquiry, optionally for my RFQ, once', async () => {
    const calls = serve(['enquiry.send', 'proposal.create'])
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask (non-binding)' }))
    const form = screen.getByLabelText('Send enquiry')
    fireEvent.change(within(form).getByLabelText('Message'), { target: { value: 'Is Q1 firm?' } })
    fireEvent.change(within(form).getByLabelText(/Evidence you would like/), { target: { value: 'ISCC EU 2028-Q1' } })
    fireEvent.change(within(form).getByLabelText(/For my RFQ/), { target: { value: 'r_mine' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Send enquiry' }))
    expect(await screen.findByRole('link', { name: 'Continue in Deals' })).toHaveAttribute('href', '/deals/e_new')
    const sent = calls.find(c => c.url.endsWith('/market/enquiries'))!
    expect(JSON.parse(sent.init!.body as string)).toEqual({ listing_id: 'o1', about_rfq_id: 'r_mine', body: 'Is Q1 firm?',
      evidence_request: 'ISCC EU 2028-Q1' })
    expect((sent.init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
  })

  it('offers no enquiry to a role that may not send one', async () => {
    serve([])
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    await screen.findByText('e-Methanol')
    expect(screen.queryByRole('button', { name: 'Ask (non-binding)' })).toBeNull()
  })
})

const deals = (path: string) => render(
  <MemoryRouter initialEntries={[path]}><Routes><Route path="/deals/:id?" element={<DealsPage />} /></Routes></MemoryRouter>)

describe('Deals', () => {
  it('shows the asker as a badge until the receiver shares contact, then both identities', async () => {
    const calls = serve(['enquiry.reply'])
    deals('/deals/e1')
    const who = await screen.findByTestId('counterparty')
    expect(within(who).getByText(/Offtaker/)).toBeInTheDocument()
    expect(screen.queryByText('TEST Buyer GmbH')).toBeNull()
    expect(screen.getByText('Evidence requested: ISCC EU 2028-Q1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Share contact' }))
    await waitFor(() => expect(within(screen.getByTestId('counterparty')).getByText('TEST Buyer GmbH')).toBeInTheDocument())
    expect(screen.getByText('buyer@test.invalid')).toBeInTheDocument()
    expect(calls.some(c => c.url.endsWith('/market/enquiries/e1/share-contact') && c.init?.method === 'POST')).toBe(true)
  })

  it('lets only the receiver decide, and only a role that may answer', async () => {
    serve([])                                                               // Engineering: reads
    deals('/deals/e1')
    await screen.findByTestId('counterparty')
    expect(screen.queryByRole('button', { name: 'Share contact' })).toBeNull()
    expect(screen.queryByRole('textbox', { name: 'Reply' })).toBeNull()
  })

  it('offers the asker Withdraw, never Share contact', async () => {
    serve(['enquiry.send', 'enquiry.reply'], { ...RECEIVED, role: 'sent',
      can: { reply: true, share_contact: false, decline: false, withdraw: true } })
    deals('/deals/e1')
    expect(await screen.findByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Share contact' })).toBeNull()
  })
})

describe('Changed since you looked (check 9)', () => {
  it('tells the asker what changed since its assessment, and nothing when nothing did', async () => {
    const change = { status_then: 'compatible', status_now: 'incompatible', eligible_now: false, purpose: 'enquiry',
      assessed_at: '2026-11-14T10:00:00Z', assessment_id: 'a1', listing_state_now: 'OPEN', listing_fields: ['product'],
      outcomes: [{ requirement: 'max_ci_gco2e_mj', label: 'Carbon intensity', then: 'compatible', now: 'incompatible',
        reason_now: 'CI 40 gCO2e/MJ exceeds your 28.2 limit.' }] }
    serve(['enquiry.send'], { ...RECEIVED, role: 'sent', changed_since_assessed: change,
      can: { reply: true, share_contact: false, decline: false, withdraw: true } })
    deals('/deals/e1')
    const box = await screen.findByTestId('changed-since')
    expect(within(box).getByText(/Compatible → Incompatible · now excluded by a required item/)).toBeInTheDocument()
    expect(within(box).getByText(/Carbon intensity: Compatible → Incompatible\. CI 40/)).toBeInTheDocument()
    expect(within(box).getByText('Changed on the listing: product evidence.')).toBeInTheDocument()
  })

  it('shows nothing when the assessment still holds', async () => {
    serve(['enquiry.send'], { ...RECEIVED, role: 'sent', changed_since_assessed: null,
      can: { reply: true, share_contact: false, decline: false, withdraw: true } })
    deals('/deals/e1')
    await screen.findByTestId('counterparty')
    expect(screen.queryByTestId('changed-since')).toBeNull()
  })
})
