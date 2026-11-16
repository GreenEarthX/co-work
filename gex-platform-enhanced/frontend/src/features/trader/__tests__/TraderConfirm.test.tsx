/**
 * Contracts are confirmed, not written (Phase 1 of "One contract record",
 * 2026-11-06). The contract exists from the moment both parties accept; the desk
 * no longer offers "Write contract". Each party confirms with four eyes: one
 * person raises the confirmation, a colleague approves it (TRADE_CONFIRM).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TraderDashboardPage } from '../TraderDashboardPage'
import { resetMarketPolicy } from '@/lib/marketPolicy'

vi.mock('@/contexts/ProjectContext', () => ({ useSelectedProject: () => ({ selectedProjectId: null }) }))
vi.mock('@/hooks/useVisibleProjects', () => ({ useVisibleProjects: () => ({
  projects: [{ id: 'proj_TEST', bankability: { risk_alerts: [], gates: [] } }], isLoading: false }) }))
vi.mock('@/components/AdversarialReviewEntryCard', () => ({ AdversarialReviewEntryCard: () => null }))
vi.mock('@/components/gantt/ProductionRoadmapGantt', () => ({ ProductionRoadmapGantt: () => null, default: () => null }))

const CONTRACT = { id: 'c_1', match_id: 'm_1', contract_id_external: 'GEX-TB-2026-000001', molecule: 'H2',
  volume_mtpd: 5, price_eur_kg: 6.1, status: 'pending_confirmation', seller_company_id: 'me',
  buyer_company_id: 'them', delivery_terms: 'TEST FOB', payment_terms: 'TEST 30 days', created_at: '2026-11-06' }

function serve(allowed: string[]) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const body = url.endsWith('/market/policy') ? { allowed }
      : url.endsWith('/market/contracts/mine') ? { contracts: [CONTRACT] }
      : url.endsWith('/market/matches/mine') ? { matches: [{ id: 'm_1', status: 'accepted', side: 'seller',
          molecule: 'H2', volume_mtpd: 5, price_eur_kg: 6.1, match_score: 80 }] }
      : url.endsWith('/market/rfqs/mine') ? { rfqs: [] }
      : url.endsWith('/c_1/confirmations') ? { confirmations: [{ id: 'req_9', status: 'PENDING',
          initiator_user_id: 'u_colleague', created_at: '2026-11-06' }] }
      : url.includes('/c_1/confirm') ? { request_id: 'req_9', trade_status: 'pending_confirmation' }
      : {}
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  return calls
}

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

const page = () => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><TraderDashboardPage /></MemoryRouter>
  </QueryClientProvider>)

describe('Contracts to confirm (D-B: Commercial raises, the CEO or the CFO approves)', () => {
  it('lets Commercial raise its company\'s confirmation, and not approve it', async () => {
    const calls = serve(['trade.confirm.request', 'proposal.accept', 'proposal.decline'])
    page()
    expect(await screen.findByText(/GEX-TB-2026-000001/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Write contract' })).toBeNull()
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm for my company' }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/market/contracts/c_1/confirm'
      && c.init?.method === 'POST')).toBe(true))
    expect(screen.queryByRole('button', { name: "Approve colleague's confirmation" })).toBeNull()
  })

  it('lets the CEO approve a colleague\'s confirmation, and not raise one', async () => {
    const calls = serve(['trade.confirm.approve'])
    page()
    fireEvent.click(await screen.findByRole('button', { name: "Approve colleague's confirmation" }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/market/contracts/c_1/confirm/req_9/approve'
      && c.init?.method === 'POST')).toBe(true))
    expect(screen.queryByRole('button', { name: 'Confirm for my company' })).toBeNull()
  })
})
