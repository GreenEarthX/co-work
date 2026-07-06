/**
 * useGateConfig — fetches the canonical screen-to-gate map from the backend.
 *
 * Returns the backend's `GET /api/v1/gates/screen-gates` response, which maps
 * route path → gate ID (e.g. "/capital-stack" → "G5_EPC_RISK_PRICED").
 *
 * Falls back to undefined while loading or on error; callers should degrade
 * gracefully to the menu-derived PATH_GATE_MAP in useGateAccess.
 */

import { useQuery } from '@tanstack/react-query'

export interface ScreenGateMap {
  [path: string]: string
}

async function fetchScreenGates(): Promise<ScreenGateMap> {
  const res = await fetch('/api/v1/gates/screen-gates')
  if (!res.ok) throw new Error(`gates/screen-gates: ${res.status}`)
  return res.json()
}

export function useGateConfig() {
  const { data, isLoading, isError } = useQuery<ScreenGateMap>({
    queryKey: ['gates', 'screen-gates'],
    queryFn: fetchScreenGates,
    staleTime: 5 * 60 * 1000, // 5 min — gate definitions rarely change
    retry: 1,
  })

  return {
    screenGateMap: data,
    isLoading,
    isError,
  }
}
