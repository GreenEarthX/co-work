/**
 * The offtake frame (contract record Phase 3, Q2/Q5): each buyer confirms its own
 * sub-leg, and sees another buyer only as a hash and a share of the volume. The
 * screen offers the confirm button to the buyer whose sub-leg it is, and never the
 * single-counterparty controls on a frame. The server decides who is who.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ContractTokensPanel } from '../ContractTokensPanel'

const FRAME = {
  version: 2, shared_hash: 's'.repeat(64),
  buyers: [
    { company_id: null, sub_leg_hash: 'a'.repeat(64), confirmed: true, volume_share: 0.6 },
    { company_id: 'test_buyer_b', sub_leg_hash: 'b'.repeat(64), confirmed: false, volume_share: 0.4 },
  ],
}
const offtake = (frame: unknown) => ({
  kind: 'offtake', counterparty_company_id: null, confirmed_by: 'counterparty', frame,
  latest_version_sha256: 'f'.repeat(64), confirmed: false, held_back_fields: [], verifies_evidence: [],
  chain_intact: true, events: [],
})

function stub(tokens: unknown[], you: Record<string, unknown>) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    new Response(JSON.stringify(init?.method === 'POST' ? {} : {
      tokens, possible_counterparties: ['test_buyer_b'], you }), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('ContractTokensPanel — the offtake frame', () => {
  it('lets a buyer confirm its own sub-leg and shows the other buyer anonymously', async () => {
    const fetchMock = stub([offtake(FRAME)], { company_id: 'test_buyer_b', is_gex: false, is_owner_executive: false })
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText('test_buyer_b')).toBeTruthy()
    expect(screen.getByText('confirmed its sub-leg')).toBeTruthy()       // the other buyer, by hash only
    expect(screen.queryByText(/null/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm my sub-leg' }))
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'POST')!
    expect(post[0]).toBe('/api/v1/contract-tokens/p/offtake/buyers/test_buyer_b/confirm')
    expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({ sub_leg_hash: 'b'.repeat(64) })
  })

  it('offers no single-counterparty controls on a frame, even to the owner', async () => {
    stub([offtake(FRAME)], { company_id: 'test_owner', is_gex: false, is_owner_executive: true })
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText('test_buyer_b')).toBeTruthy()
    expect(screen.queryByText('Register counterparty…')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Confirm these terms' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Confirm my sub-leg' })).toBeNull()
  })

  it('keeps the single-counterparty controls when the offtake has one buyer', async () => {
    stub([offtake(null)], { company_id: 'test_owner', is_gex: false, is_owner_executive: true })
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText('Register counterparty…')).toBeTruthy()
  })
})

describe('ContractTokensPanel — adverse facts and novations', () => {
  it('shows an open fact and offers its clearing to another company, never to the reporter', async () => {
    const fact = { kind: 'epc', fact: 'COUNTERPARTY_INSOLVENT', subject_company_id: null, report_event_hash: 'h'.repeat(64),
      reported_by: 'u', reporter_company_id: 'test_owner', open: true, cleared_by: [] }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ tokens: [offtake(null)],
      possible_counterparties: [], adverse_facts: [fact], novations: [],
      you: { company_id: 'test_bank', is_gex: false, is_owner_executive: false } }), { status: 200 })))
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText('EPC contractor insolvent')).toBeTruthy()
    expect(screen.getByText(/0 of 2 clearing confirmations/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Confirm clearing' })).toBeTruthy()
  })

  it('lists a pending novation with who has confirmed it', async () => {
    const n = { proposal_event_hash: 'n'.repeat(64), outgoing_company_id: 'test_a', incoming_company_id: 'test_n',
      confirmed_by: ['outgoing'], awaiting: ['producer', 'incoming'], state: 'pending' }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ tokens: [offtake(FRAME)],
      possible_counterparties: [], adverse_facts: [], novations: [n],
      you: { company_id: 'test_owner', is_gex: false, is_owner_executive: true } }), { status: 200 })))
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText('test_a → test_n')).toBeTruthy()
    expect(screen.getByText(/awaiting producer, incoming/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Confirm this novation' })).toBeTruthy()
  })
})

describe('ContractTokensPanel — a market trade in the frame (Q6.4)', () => {
  it('offers its buyer no frame confirmation or hand-over: it is confirmed on the trade', async () => {
    const frame = { ...FRAME, buyers: [{ company_id: 'test_buyer_b', sub_leg_hash: 'b'.repeat(64), confirmed: false,
      volume_share: 1, locked: true }] }
    stub([offtake(frame)], { company_id: 'test_buyer_b', is_gex: false, is_owner_executive: false })
    render(<ContractTokensPanel projectId="p" onChanged={() => {}} />)
    expect(await screen.findByText(/confirmed on the trade, with four eyes/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Confirm my sub-leg' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Hand over…' })).toBeNull()
  })
})
