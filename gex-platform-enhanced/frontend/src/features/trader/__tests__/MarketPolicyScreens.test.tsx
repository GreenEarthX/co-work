/**
 * D-B: a user who may not raise RFQs or make proposals sees no button for it, and is told who
 * does (the server refuses it anyway: backend core/market_policy).
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import RFQManagementPage from '../RFQManagementPage'
import { resetMarketPolicy } from '@/lib/marketPolicy'

afterEach(() => { vi.unstubAllGlobals(); resetMarketPolicy() })

function serve(allowed: string[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const body = url.endsWith('/market/policy') ? { allowed }
      : url.endsWith('/market/commodities') ? { commodities: [] }
      : url.endsWith('/market/rfqs/mine') ? { rfqs: [{ id: 'r1', molecule: 'H2', volume_mtpd: 5, delivery_start: '2028-01-01',
          delivery_end: '2028-12-31', status: 'draft', buyer_company_id: 'me', mine: true, created_at: '2026-11-14' }] }
      : {}
    return new Response(JSON.stringify(body), { status: 200 })
  }))
}

describe('RFQs for a function that does not raise them', () => {
  it('shows who does, and no create or publish button', async () => {
    serve(['trade.confirm.approve'])                     // the CFO
    render(<MemoryRouter><RFQManagementPage /></MemoryRouter>)
    expect(await screen.findByText('RFQs are raised by Commercial in your company.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Create RFQ/ })).toBeNull()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Publish' })).toBeNull())
  })

  it('offers them to Commercial', async () => {
    serve(['rfq.create', 'rfq.change'])
    render(<MemoryRouter><RFQManagementPage /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: /Create RFQ/ })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Publish' })).toBeInTheDocument()
  })
})
