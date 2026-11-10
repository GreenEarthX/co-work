/**
 * Revenue & offtake reads the contracts the company SELLS from the contract record
 * (contract record Phase 3). It invents nothing: no capacity of its own (coverage of
 * planned output is the gate engine's), and revenue only in the years a contract runs.
 */
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const getContracts = vi.fn()
vi.mock('@/lib/api', () => ({ financeAPI: { getContracts: () => getContracts() } }))

import { RevenueOfftakePage } from '../RevenueOfftakePage'

afterEach(() => getContracts.mockReset())

const CONTRACT = {
  id: 'c1', counterparty: 'TEST Buyer', molecule: 'H2', volume_mtpd: 10, price_eur_kg: 5,
  pricingBasis: '', startDate: '2028-07-01', endDate: '2029-06-30', tenor_years: 1, status: 'active',
  creditRating: '',
}

describe('RevenueOfftakePage', () => {
  it('says so when the company sells nothing on the record, and shows no invented capacity', async () => {
    getContracts.mockResolvedValue([])
    render(<RevenueOfftakePage />)
    expect(await screen.findByText(/No contract your company sells is on the record yet/)).toBeTruthy()
    expect(screen.queryByText(/50/)).toBeNull()
    expect(screen.getByText(/No confirmed, priced contract yet/)).toBeTruthy()
  })

  it('forecasts revenue only in the years each contract runs', async () => {
    getContracts.mockResolvedValue([CONTRACT])
    render(<RevenueOfftakePage />)
    expect(await screen.findByText('2028')).toBeTruthy()
    // 2028: 1 Jul–31 Dec = 184 days × 10 t/day × €5/kg = €9.2M; 2029: 181 days = €9.05M; 2030: nothing
    expect(screen.getByText('€9.2M')).toBeTruthy()
    expect(screen.getByText('€9.1M')).toBeTruthy()
    expect(screen.getAllByText('€0.0M').length).toBe(3)
    expect(screen.queryByText('2027')).toBeNull()
  })
})
