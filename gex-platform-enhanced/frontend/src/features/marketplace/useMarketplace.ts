// src/features/marketplace/useMarketplace.ts
// ─────────────────────────────────────────────────────────────────────────────
// React Query hook for marketplace offers & RFQs.
// Mock data mirrors what is visible on staging.greenearthx.com/trade/market.
// Swap the mock* functions for real API calls when the backend is ready.
// ─────────────────────────────────────────────────────────────────────────────

import { useQuery } from '@tanstack/react-query'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Trade {
  id: string
  startDate: string
  endDate: string
  volume: string
  targetPrice: string | null
  status: string
}

export interface Slot {
  id: string
  startDate: string
  endDate: string
  volume: string
  inMarket: string
  status: string
  trades?: Trade[]
}

export interface Offer {
  id: string
  product: string
  producer: string
  region: string
  project: string
  stage: string
  startDate: string
  endDate: string
  volume: string
  purchasePrice: string | null
  deposited: string
  energySource: string
  greenEnergyPct: number
  certification: string
  slots?: Slot[]
}

export interface RFQ {
  id: string
  product: string
  buyer: string
  region: string
  volume: string
  price: string | null
  stage: string
  startDate: string
  endDate: string
}

// ── Mock data ─────────────────────────────────────────────────────────────────

function mockOffers(): Offer[] {
  return [
    {
      id: 'offer-1',
      product: 'GEX:H2',
      producer: 'Hanover Gas GmbH',
      region: 'EUROPE',
      project: 'Hanover H2',
      stage: 'ProductionReady',
      startDate: '2024-08-20',
      endDate: '2028-08-20',
      volume: '50 MTPD',
      purchasePrice: null,
      deposited: '19.98%',
      energySource: 'Solar',
      greenEnergyPct: 97,
      certification: 'DNV',
      slots: [
        {
          id: 'slot-1',
          startDate: '2025-01-01',
          endDate: '2025-12-31',
          volume: '40 MTPD',
          inMarket: '75.00%',
          status: 'Deposited',
          trades: [
            {
              id: 'trade-1',
              startDate: '2025-01-01',
              endDate: '2025-12-31',
              volume: '30 MTPD',
              targetPrice: null,
              status: 'L2 Pending',
            },
          ],
        },
      ],
    },
  ]
}

function mockRFQs(): RFQ[] {
  return []
}

// ── API fetchers (swap for real calls) ────────────────────────────────────────

async function fetchOffers(): Promise<Offer[]> {
  // TODO: replace with real API call, e.g.:
  // const { data } = await api.get<Offer[]>('/api/v1/offers')
  // return data
  await new Promise((r) => setTimeout(r, 400)) // simulate network
  return mockOffers()
}

async function fetchRFQs(): Promise<RFQ[]> {
  // TODO: replace with real API call, e.g.:
  // const { data } = await api.get<RFQ[]>('/api/v1/rfqs')
  // return data
  await new Promise((r) => setTimeout(r, 400))
  return mockRFQs()
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useMarketplace() {
  const offersQuery = useQuery<Offer[], Error>({
    queryKey: ['marketplace', 'offers'],
    queryFn: fetchOffers,
    staleTime: 30_000,
  })

  const rfqsQuery = useQuery<RFQ[], Error>({
    queryKey: ['marketplace', 'rfqs'],
    queryFn: fetchRFQs,
    staleTime: 30_000,
  })

  return {
    offers:    offersQuery.data  ?? [],
    rfqs:      rfqsQuery.data    ?? [],
    isLoading: offersQuery.isLoading || rfqsQuery.isLoading,
    isError:   offersQuery.isError   || rfqsQuery.isError,
    refetch: () => {
      offersQuery.refetch()
      rfqsQuery.refetch()
    },
  }
}
