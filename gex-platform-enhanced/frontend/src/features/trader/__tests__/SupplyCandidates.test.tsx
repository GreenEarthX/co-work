/**
 * R7 on screen: the supply for one of my RFQs, eligibility first (the server's words, never
 * recomputed here); an excluded listing says why and offers no proposal; a proposal is confirmed
 * as binding first; Compare puts up to four side by side, requirement by requirement.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SupplyCandidates } from '../SupplyCandidates'
import { resetMarketPolicy } from '@/lib/marketPolicy'

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

const o = (requirement: string, label: string, outcome: string, reason: string, mandatory = false) =>
  ({ requirement, label, outcome, reason, mandatory })
const listing = (id: string, price: number) => ({ id, molecule: 'e-Methanol', volume_mtpd: 40, price_eur_kg: price,
  delivery_start: '2028-01-01', delivery_end: '2028-12-31', created_at: '2026-11-14', mine: false, incoterm: 'FOB',
  named_place: 'Rotterdam', seller_role: 'PRODUCER', seller_vetting: 'vetted', product: { certificates: [], quality: [] } })
const GOOD = { listing: listing('l_good', 1.2), assessment: { status: 'compatible', eligible: true,
  counts: { compatible: 4, needs_evidence: 0, incompatible: 0 },
  outcomes: [o('max_ci_gco2e_mj', 'Carbon intensity', 'compatible', 'CI 9.4 gCO2e/MJ (calculated).', true),
             o('price', 'Price', 'compatible', '€1.2/kg against your €1.3/kg ceiling.')] } }
const SOON = { listing: listing('l_soon', 1.25), assessment: { status: 'needs_evidence', eligible: true,
  counts: { compatible: 3, needs_evidence: 1, incompatible: 0 },
  outcomes: [o('max_ci_gco2e_mj', 'Carbon intensity', 'needs_evidence', 'No carbon intensity is recorded for this product.', true)] } }
const BAD = { listing: listing('l_bad', 0.01), assessment: { status: 'incompatible', eligible: false,
  counts: { compatible: 3, needs_evidence: 0, incompatible: 1 },
  outcomes: [o('max_ci_gco2e_mj', 'Carbon intensity', 'incompatible', 'CI 32 gCO2e/MJ exceeds your 28.2 limit.', true)] } }

function serve(allowed: string[]) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const body = url.endsWith('/market/policy') ? { allowed }
      : url.includes('/compatibility?offer_ids=') ? { candidates: [GOOD, BAD] }
      : url.includes('/compatibility') ? { candidates: [GOOD, SOON, BAD] }
      : url.endsWith('/market/matches') ? { id: 'm_new', status: 'pending' }
      : {}
    return new Response(JSON.stringify(body), { status: url.endsWith('/market/matches') ? 201 : 200 })
  }))
  return calls
}

describe('supply for my RFQ', () => {
  it('shows the server\'s eligibility in its order; an excluded listing says why and offers no proposal', async () => {
    serve(['proposal.create'])
    render(<SupplyCandidates rfqId="r1" onClose={() => {}} />)
    const bad = await screen.findByTestId('candidate-l_bad')
    const rows = screen.getAllByTestId(/^candidate-/).map(r => r.getAttribute('data-testid'))
    expect(rows).toEqual(['candidate-l_good', 'candidate-l_soon', 'candidate-l_bad'])   // never re-sorted by price here
    expect(within(bad).getByText('Excluded: CI 32 gCO2e/MJ exceeds your 28.2 limit.')).toBeInTheDocument()
    expect(within(bad).queryByRole('button', { name: /Propose/ })).toBeNull()
    expect(within(screen.getByTestId('candidate-l_soon')).getByText('Needs evidence')).toBeInTheDocument()
  })

  it('confirms a proposal as binding before sending it', async () => {
    const calls = serve(['proposal.create'])
    render(<SupplyCandidates rfqId="r1" onClose={() => {}} />)
    const good = await screen.findByTestId('candidate-l_good')
    fireEvent.click(within(good).getByRole('button', { name: 'Propose (binding)' }))
    expect(within(good).getByText(/It binds when the seller accepts/)).toBeInTheDocument()
    expect(calls.some(c => c.url.endsWith('/market/matches'))).toBe(false)
    fireEvent.click(within(good).getByRole('button', { name: 'Confirm proposal' }))
    await waitFor(() => expect(within(good).getByText('Proposed')).toBeInTheDocument())
    expect(JSON.parse(calls.find(c => c.url.endsWith('/market/matches'))!.init!.body as string)).toEqual({ offer_id: 'l_good', rfq_id: 'r1' })
  })

  it('offers no proposal to a role that may not make one', async () => {
    serve([])
    render(<SupplyCandidates rfqId="r1" onClose={() => {}} />)
    const good = await screen.findByTestId('candidate-l_good')
    await waitFor(() => expect(within(good).queryByRole('button', { name: /Propose/ })).toBeNull())
  })

  it('compares up to four, requirement by requirement', async () => {
    const calls = serve(['proposal.create'])
    render(<SupplyCandidates rfqId="r1" onClose={() => {}} />)
    await screen.findByTestId('candidate-l_bad')
    fireEvent.click(screen.getByLabelText('Compare listing l_good'))
    fireEvent.click(screen.getByLabelText('Compare listing l_bad'))
    fireEvent.click(screen.getByRole('button', { name: 'Compare selected (2/4)' }))
    const table = await screen.findByTestId('compare')
    expect(calls.some(c => c.url.endsWith('/compatibility?offer_ids=l_good,l_bad'))).toBe(true)
    expect(within(table).getByText('Carbon intensity · required')).toBeInTheDocument()
    expect(within(table).getByText('CI 32 gCO2e/MJ exceeds your 28.2 limit.')).toBeInTheDocument()
    expect(within(table).getByText('CI 9.4 gCO2e/MJ (calculated).')).toBeInTheDocument()
  })
})
