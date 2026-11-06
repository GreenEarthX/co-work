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

vi.mock('@/contexts/ProjectContext', () => ({ useSelectedProject: () => ({ selectedProjectId: null }) }))
vi.mock('@/hooks/useVisibleProjects', () => ({ useVisibleProjects: () => ({
  projects: [{ id: 'proj_TEST', bankability: { risk_alerts: [], gates: [] } }], isLoading: false }) }))
vi.mock('@/components/AdversarialReviewEntryCard', () => ({ AdversarialReviewEntryCard: () => null }))
vi.mock('@/components/gantt/ProductionRoadmapGantt', () => ({ ProductionRoadmapGantt: () => null, default: () => null }))

const CONTRACT = { id: 'c_1', match_id: 'm_1', contract_id_external: 'GEX-TB-2026-000001', molecule: 'H2',
  volume_mtpd: 5, price_eur_kg: 6.1, status: 'pending_confirmation', seller_company_id: 'me',
  buyer_company_id: 'them', delivery_terms: 'TEST FOB', payment_terms: 'TEST 30 days', created_at: '2026-11-06' }

function serve() {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const body = url.endsWith('/market/contracts/mine') ? { contracts: [CONTRACT] }
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

afterEach(() => vi.unstubAllGlobals())

describe('Contracts to confirm', () => {
  it('offers confirmation by two people, and no longer "Write contract"', async () => {
    const calls = serve()
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><TraderDashboardPage /></MemoryRouter>
      </QueryClientProvider>)
    expect(await screen.findByText(/GEX-TB-2026-000001/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Write contract' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm for my company' }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/market/contracts/c_1/confirm'
      && c.init?.method === 'POST')).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: "Approve colleague's confirmation" }))
    await waitFor(() => expect(calls.some(c => c.url === '/api/v1/market/contracts/c_1/confirm/req_9/approve'
      && c.init?.method === 'POST')).toBe(true))
  })
})
