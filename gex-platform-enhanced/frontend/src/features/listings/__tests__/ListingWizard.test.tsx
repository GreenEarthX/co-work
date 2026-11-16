/**
 * The listing wizard (discovery Phase 1, R8): project → capacity → token → terms → preview →
 * publish, on the existing APIs; each record is created once (Idempotency-Key); the preview is
 * the market's own anonymous summary; a role the server would refuse is not offered the step.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ListingWizard, { buildOffer, termsProblems, type Terms } from '../ListingWizard'
import { resetMarketPolicy } from '@/lib/marketPolicy'

vi.mock('@/contexts/UserRoleContext', () => ({ useUserRole: () => ({ role: { company_name: 'TEST Producer' } }) }))
vi.mock('@/hooks/useVisibleProjects', () => ({ useVisibleProjects: () => ({ isLoading: false, projects: [
  { id: 'proj_TEST_a', name: 'TEST Plant A', molecule: 'e-Methanol', location: 'TEST', capacity_mtpd: 100, owner_company: 'TEST Producer' },
  { id: 'proj_TEST_other', name: 'TEST Someone else', molecule: 'H2', capacity_mtpd: 5, owner_company: 'TEST Other' },
] }) }))

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

const SELLER = ['capacity.create', 'token.mint', 'listing.create', 'listing.open', 'listing.withdraw', 'product.declare']
const PREVIEW = { production_pathway: 'TEST PEM + DAC', physical_form: 'liquid', specification_standard: 'IMPCA',
  carbon_intensity: { value_gco2e_mj: 9.4, method: 'DA 2023/1185', system_boundary: 'WtW', basis: 'calculated' },
  quality: [], certificates: [{ kind: 'certificate', scheme: 'ISCC EU', body: 'TEST', scope: 'site', covers: 'covers the site', status: 'asserted' }] }

function serve(allowed: string[], drafts: unknown[] = []) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const post = init?.method === 'POST'
    const body = url.endsWith('/market/policy') ? { allowed }
      : url.includes('/capacities/?project_id=') ? { capacities: [] }
      : url.endsWith('/capacities/') && post ? { id: 'cap_TEST', project_id: 'proj_TEST_a', molecule: 'e-Methanol',
          capacity_mtpd: 100, production_start: '2028-01-01', production_end: '2028-12-31' }
      : url.includes('/tokens/?capacity_id=') ? { tokens: [] }
      : url.endsWith('/tokens/') && post ? { id: 'tok_TEST', capacity_id: 'cap_TEST', tokenised_mtpd: 40,
          delivery_start: '2028-01-01', delivery_end: '2028-12-31' }
      : url.includes('/listing-preview') ? { token_id: 'tok_TEST', product: PREVIEW }
      : url.endsWith('/products/parameters') ? { parameters: [] }
      : url.includes('/marketplace/offers?listing_state=DRAFT') ? { offers: drafts }
      : url.endsWith('/marketplace/offers') && post ? { id: 'ord_TEST', listing_state: 'OPEN' }
      : url.includes('/transition') ? { offer_id: 'ord_draft', new_state: 'OPEN' }
      : {}
    return new Response(JSON.stringify(body), { status: post && !url.includes('/transition') ? 201 : 200 })
  }))
  return calls
}

const page = (q = '?project=proj_TEST_a') =>
  render(<MemoryRouter initialEntries={[`/listings/new${q}`]}><ListingWizard /></MemoryRouter>)
const sent = (calls: { url: string; init?: RequestInit }[], end: string) => calls.find(c => c.url.endsWith(end) && c.init?.method === 'POST')

const TERMS: Terms = { volume_mtpd: '20', price_eur_kg: '1.1', price_basis: 'FIXED', delivery_start: '2028-01-01',
  delivery_end: '2028-06-30', incoterm: '', named_place: '', shipment_point: '', min_parcel_t: '', valid_until: '', offer_type: 'firm' }
const TOKEN = { id: 't', capacity_id: 'c', tokenised_mtpd: 40, delivery_start: '2028-01-01', delivery_end: '2028-12-31', lifecycle_state: 'MINTED' }

describe('the terms', () => {
  it('sends only what was stated, the minimum parcel in kg and the shipment point only for a C term', () => {
    expect(buildOffer('t', TERMS, false)).toEqual({ token_id: 't', volume_mtpd: 20, price_eur_kg: 1.1, delivery_start: '2028-01-01',
      delivery_end: '2028-06-30', offer_type: 'firm', listing_state: 'DRAFT', price_basis: 'FIXED' })
    const cif = buildOffer('t', { ...TERMS, incoterm: 'CIF', named_place: 'Rotterdam', shipment_point: 'Pecém', min_parcel_t: '2.5' }, true)
    expect(cif).toMatchObject({ incoterm: 'CIF', named_place: 'Rotterdam', shipment_point: 'Pecém', min_order_kg: 2500, listing_state: 'OPEN' })
    expect(buildOffer('t', { ...TERMS, incoterm: 'FOB', named_place: 'Rotterdam', shipment_point: 'ignored' }, true)).not.toHaveProperty('shipment_point')
  })

  it('refuses before sending what the server would refuse', () => {
    expect(termsProblems(TERMS, TOKEN)).toEqual([])
    expect(termsProblems({ ...TERMS, volume_mtpd: '41' }, TOKEN)).toEqual(['The token holds 40 MTPD; offer at most that.'])
    expect(termsProblems({ ...TERMS, delivery_end: '2029-01-31' }, TOKEN)[0]).toMatch(/deliver inside it/)
    expect(termsProblems({ ...TERMS, incoterm: 'CFR', named_place: 'Rotterdam' }, TOKEN)).toEqual(['CFR needs the point of shipment (where risk passes).'])
    expect(termsProblems({ ...TERMS, valid_until: '2028-07-01' }, TOKEN)).toEqual(['The offer cannot stay valid after its delivery window ends.'])
  })
})

describe('the wizard', () => {
  it('offers nothing to a role that may not list, and says who does', async () => {
    serve(['rfq.create'])
    page()
    expect(await screen.findByText(/listed by your company's Commercial function/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull()
  })

  it('offers only the projects the company owns', async () => {
    serve(SELLER)
    page('')
    const select = await screen.findByRole('combobox', { name: 'Project' })
    expect(within(select).getByText('TEST Plant A · e-Methanol')).toBeInTheDocument()
    expect(within(select).queryByText(/TEST Someone else/)).toBeNull()
  })

  it('goes from a project to a published listing, each record made once, the preview the market\'s own', async () => {
    const calls = serve(SELLER)
    page()
    fireEvent.change(await screen.findByLabelText('Capacity (MTPD)'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Declare capacity' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).not.toBeDisabled())
    expect(JSON.parse(sent(calls, '/capacities/')!.init!.body as string)).toMatchObject({ project_id: 'proj_TEST_a', molecule: 'e-Methanol', capacity_mtpd: 100 })
    expect((sent(calls, '/capacities/')!.init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    fireEvent.change(await screen.findByLabelText('Rate (MTPD)'), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mint token' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).not.toBeDisabled())
    const mint = JSON.parse(sent(calls, '/tokens/')!.init!.body as string)
    expect(mint).toMatchObject({ capacity_id: 'cap_TEST', tokenised_mtpd: 40, delivery_start: '2028-01-01', delivery_end: '2028-12-31' })
    expect(mint).not.toHaveProperty('verification_state')                 // never declared by the minter
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    fireEvent.change(await screen.findByLabelText(/^Price \(€\/kg\)/), { target: { value: '1.1' } })
    expect(screen.getByText('= € 1,100 per tonne')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Incoterm/), { target: { value: 'FOB' } })
    expect(screen.getByText('Name the place for FOB.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Named place'), { target: { value: 'Rotterdam' } })
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))

    const row = await screen.findByTestId('preview-row')
    expect(await within(row).findByText('TEST PEM + DAC · liquid · IMPCA')).toBeInTheDocument()
    expect(within(row).getByText(/ISCC EU \(site\) · Claimed/)).toBeInTheDocument()   // never shown as verified
    expect(within(row).getByText('FOB Rotterdam')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Publish listing' }))
    expect(await screen.findByText('Listing published')).toBeInTheDocument()
    const offer = sent(calls, '/marketplace/offers')!
    expect(JSON.parse(offer.init!.body as string)).toMatchObject({ token_id: 'tok_TEST', volume_mtpd: 40, price_eur_kg: 1.1,
      incoterm: 'FOB', named_place: 'Rotterdam', listing_state: 'OPEN', offer_type: 'firm' })
    expect((offer.init!.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
  })

  it('resumes: a saved draft of the project can be published from the first step', async () => {
    const calls = serve(SELLER, [{ id: 'ord_draft', token_id: 'tok_old', capacity_project_id: 'proj_TEST_a', listing_state: 'DRAFT',
      volume_mtpd: 10, price_eur_kg: 1.2, delivery_start: '2028-01-01', delivery_end: '2028-03-31' }])
    page()
    expect(await screen.findByText('10 MTPD · €1.2/kg · 2028-01-01 to 2028-03-31')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Publish' }))
    expect(await screen.findByText('Listing published')).toBeInTheDocument()
    expect(JSON.parse(sent(calls, '/offers/ord_draft/transition')!.init!.body as string)).toEqual({ new_state: 'OPEN' })
  })

  it('lets Commercial save a draft but not publish when the server does not allow opening', async () => {
    serve(SELLER.filter(a => a !== 'listing.open'))
    page()
    await screen.findByLabelText('Capacity (MTPD)')
    expect(screen.queryByRole('button', { name: 'Publish' })).toBeNull()
  })
})
