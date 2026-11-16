/**
 * Discovery review F17: the Purchase and Sales buttons opened Your Matches. They now open
 * Market Discovery on the side they name, filtered to the molecule in hand, and only for a
 * role that may open it. Market Discovery honours ?side and ?molecule; Your Matches ?mode.
 */
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { UserRole } from '@/config/menuArchitecture'

const ROLE: { current: UserRole } = { current: null as unknown as UserRole }
vi.mock('@/contexts/UserRoleContext', () => ({ useUserRole: () => ({ role: ROLE.current }) }))

import { marketDiscoveryPath, MARKET_DISCOVERY, useCanOpen } from '@/lib/marketLinks'
import { MarketDiscoveryPage } from '../MarketDiscoveryPage'
import { MatchingPage } from '@/features/matching/MatchingPage'

const role = (company_type: UserRole['company_type'], business_function: UserRole['business_function'],
              service_type: UserRole['service_type'] = null): UserRole =>
  ({ company_type, business_function, service_type, company_name: 'TEST Co', user_name: 'TEST' })

afterEach(() => vi.unstubAllGlobals())

function stubMarket() {
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(url)
    const body = url.includes('/market/commodities')
      ? { commodities: [{ code: 'EMEOH', name: 'e-Methanol', default_unit: 't', market_molecule: 'e-Methanol' }] }
      : url.includes('/listings/offers') ? { offers: [] }
      : url.includes('/listings/rfqs') ? { rfqs: [] }
      : url.includes('/rfqs/mine') ? { rfqs: [] }
      : url.includes('/matches/mine') ? { matches: [] } : {}
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  return urls
}

describe('links into the market', () => {
  it('name the side and the molecule, and drop "all"', () => {
    expect(marketDiscoveryPath('supply', 'e-Methanol')).toBe('/market-discovery?side=supply&molecule=e-Methanol')
    expect(marketDiscoveryPath('demand', 'all')).toBe('/market-discovery?side=demand')
    expect(marketDiscoveryPath('demand')).toBe('/market-discovery?side=demand')
  })

  it('are offered only to a role that may open Market Discovery', () => {
    const can = (r: UserRole) => { ROLE.current = r; return renderHook(() => useCanOpen(MARKET_DISCOVERY)).result.current }
    expect(can(role('OFFTAKER', 'COMMERCIAL'))).toBe(true)
    expect(can(role('PRODUCER', 'COMMERCIAL'))).toBe(true)
    expect(can(role('PRODUCER', 'FINANCE_TREASURY'))).toBe(false)          // Sales is open to it, the market is not
    expect(can(role('THIRD_PARTY', 'FINANCE_TREASURY', 'BANK'))).toBe(false)
  })
})

describe('Market Discovery', () => {
  it('opens on the side the link named, filtered to its molecule', async () => {
    ROLE.current = role('OFFTAKER', 'COMMERCIAL')
    const urls = stubMarket()
    render(<MemoryRouter initialEntries={['/market-discovery?side=demand&molecule=e-Methanol']}><MarketDiscoveryPage /></MemoryRouter>)
    await waitFor(() => expect(urls.some(u => u.includes('/listings/rfqs?molecule=e-Methanol'))).toBe(true))
    expect((screen.getByLabelText('Molecule') as HTMLSelectElement).value).toBe('e-Methanol')
    expect(document.getElementById('md-demand')).toHaveAttribute('aria-current', 'true')
    expect(document.getElementById('md-supply')).not.toHaveAttribute('aria-current')
  })

  it('shows every molecule, and says so, when the link names one the market does not trade', async () => {
    ROLE.current = role('OFFTAKER', 'COMMERCIAL')
    stubMarket()
    render(<MemoryRouter initialEntries={['/market-discovery?side=supply&molecule=MEO']}><MarketDiscoveryPage /></MemoryRouter>)
    expect(await screen.findByText(/no molecule called "MEO"/)).toBeInTheDocument()
    expect((screen.getByLabelText('Molecule') as HTMLSelectElement).value).toBe('')
  })
})

describe('Your Matches', () => {
  it('opens on the selling side for ?mode=sell', async () => {
    ROLE.current = role('PRODUCER', 'COMMERCIAL')
    stubMarket()
    render(<MemoryRouter initialEntries={['/matching?mode=sell']}><MatchingPage /></MemoryRouter>)
    expect(await screen.findByText('No open match on your selling side.')).toBeInTheDocument()
  })
})

import purchaseSrc from '../OfftakerSupplyTable.tsx?raw'
import salesSrc from '@/features/finance/DemandPipeline.tsx?raw'

describe('the Purchase and Sales buttons', () => {
  it('no longer send anyone to Your Matches', () => {
    for (const src of [purchaseSrc, salesSrc]) {
      expect(src).not.toMatch(/navigate\([`'"]\/matching/)
      expect(src).toMatch(/marketDiscoveryPath\('(supply|demand)'/)
    }
  })
})
