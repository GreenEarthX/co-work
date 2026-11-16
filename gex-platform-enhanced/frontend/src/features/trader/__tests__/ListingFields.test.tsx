/**
 * Phase 1, D-C: Market Discovery shows the product with the evidence status of each claim, the
 * origin, the Incoterm and the counterparty's badge; RFQs show their requirements, with the
 * required ones marked; the RFQ form sends structured requirements (backend core/requirements.py).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MarketDiscoveryPage } from '../MarketDiscoveryPage'
import RFQManagementPage, { buildRequirements } from '../RFQManagementPage'
import { resetMarketPolicy } from '@/lib/marketPolicy'

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

const OFFER = {
  id: 'o1', molecule: 'e-Methanol', volume_mtpd: 40, price_eur_kg: 1.1, delivery_start: '2028-01-01',
  delivery_end: '2028-12-31', created_at: '2026-11-14', mine: false, offer_type: 'firm', valid_until: '2027-12-31T23:59:59+00:00',
  incoterm: 'FOB', named_place: 'Rotterdam', production_country: 'DE', seller_role: 'PRODUCER', seller_vetting: 'vetted',
  product: {
    production_pathway: 'PEM + DAC synthesis', physical_form: 'liquid', specification_standard: 'IMPCA',
    carbon_intensity: { value_gco2e_mj: 9.4, method: 'DA 2023/1185', system_boundary: 'WtW', basis: 'calculated' },
    quality: [], certificates: [
      { kind: 'certificate', scheme: 'ISCC EU', body: 'TEST', scope: 'site', covers: 'covers the site', status: 'verified' },
      { kind: 'certificate', scheme: 'CertifHy', body: 'TEST', scope: 'batch', covers: 'covers this quantity', status: 'expired' },
    ],
  },
}
const RFQ = {
  id: 'r1', molecule: 'e-Methanol', volume_mtpd: 10, max_price_eur_kg: 1.3, delivery_start: '2028-01-01',
  delivery_end: '2028-12-31', created_at: '2026-11-14', mine: false, buyer_role: 'OFFTAKER', buyer_vetting: 'not_yet_vetted',
  requirements: { max_ci_gco2e_mj: 28.2, regimes: ['RFNBO'], physical_form: 'liquid', mandatory: ['max_ci_gco2e_mj'] },
}

function serve(extra: (url: string, init?: RequestInit) => unknown = () => ({})) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const body = url.endsWith('/market/policy') ? { allowed: ['rfq.create', 'rfq.change', 'proposal.create'] }
      : url.endsWith('/market/commodities') ? { commodities: [{ code: 'EMEOH', name: 'e-Methanol', default_unit: 't', market_molecule: 'e-Methanol' }] }
      : url.includes('/listings/offers') ? { offers: [OFFER] }
      : url.includes('/listings/rfqs') ? { rfqs: [RFQ] }
      : url.includes('/rfqs/mine') ? { rfqs: [] }
      : extra(url, init)
    return new Response(JSON.stringify(body), { status: url.endsWith('/market/rfqs') && init?.method === 'POST' ? 201 : 200 })
  }))
  return calls
}

describe('Market Discovery (D-C)', () => {
  it('shows the product, its evidence status, origin, Incoterm and the seller badge', async () => {
    serve()
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    const supply = await screen.findByText('PEM + DAC synthesis · liquid · IMPCA')
    const row = supply.closest('tr')!
    expect(within(row).getByText(/ISCC EU \(site\) · Verified/)).toBeInTheDocument()
    expect(within(row).getByText(/CertifHy · Expired/)).toBeInTheDocument()     // never shown as verified
    expect(within(row).getByText('DE')).toBeInTheDocument()
    expect(within(row).getByText('FOB Rotterdam')).toBeInTheDocument()
    expect(within(row).getByText(/\(calculated\)/)).toBeInTheDocument()
    expect(within(row).getByText('vetted')).toBeInTheDocument()
    expect(within(row).getByText(/Firm · valid to 2027-12-31/)).toBeInTheDocument()
  })

  it('shows an RFQ\'s requirements, the required ones marked', async () => {
    serve()
    render(<MemoryRouter><MarketDiscoveryPage /></MemoryRouter>)
    expect(await screen.findByText('CI ≤ 28.2 gCO₂e/MJ · required')).toBeInTheDocument()
    expect(screen.getByText('RFNBO')).toBeInTheDocument()
    expect(screen.getByText('not yet vetted')).toBeInTheDocument()
  })
})

describe('the RFQ form', () => {
  it('builds only the requirements that were filled in, and marks required ones it can check', () => {
    const empty = { molecule: '', volume_mtpd: '', max_price_eur_kg: '', delivery_start: '', delivery_end: '', location: '',
      buyer_contact: '', max_ci: '', regimes: '', schemes: '', min_evidence: '', physical_form: '', incoterms: '',
      named_place: '', delivery_country: '', required: [] as string[] }
    expect(buildRequirements(empty)).toEqual({})
    expect(buildRequirements({ ...empty, max_ci: '28.2', regimes: 'RFNBO, RED III', incoterms: 'fob,cif',
      delivery_country: 'nl', required: ['max_ci_gco2e_mj', 'physical_form'] })).toEqual({
      max_ci_gco2e_mj: 28.2, regimes: ['RFNBO', 'RED III'], incoterms: ['FOB', 'CIF'], delivery_country: 'NL',
      mandatory: ['max_ci_gco2e_mj'] })                                     // physical_form was not stated
  })

  it('sends the requirements with the RFQ', async () => {
    const calls = serve((url, init) => (url.endsWith('/market/rfqs') && init?.method === 'POST' ? { id: 'new' } : {}))
    render(<MemoryRouter><RFQManagementPage /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /Create RFQ/ }))
    fireEvent.change(screen.getByLabelText('Molecule'), { target: { value: 'e-Methanol' } })
    fireEvent.change(screen.getByLabelText('Volume (MTPD)'), { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText('Delivery Start'), { target: { value: '2028-01-01' } })
    fireEvent.change(screen.getByLabelText('Delivery End'), { target: { value: '2028-12-31' } })
    fireEvent.change(screen.getByLabelText('Max carbon intensity (gCO₂e/MJ)'), { target: { value: '28.2' } })
    fireEvent.change(screen.getByLabelText('Physical form'), { target: { value: 'liquid' } })
    fireEvent.click(screen.getByRole('button', { name: 'Publish RFQ' }))
    await waitFor(() => expect(calls.some(c => c.url.endsWith('/market/rfqs') && c.init?.method === 'POST')).toBe(true))
    const sent = JSON.parse(calls.find(c => c.url.endsWith('/market/rfqs') && c.init?.method === 'POST')!.init!.body as string)
    expect(sent.requirements).toEqual({ max_ci_gco2e_mj: 28.2, physical_form: 'liquid' })
  })
})
