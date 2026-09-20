/**
 * The Team directory now comes from the backend, not Supabase.
 *
 * The regression this guards against is specific: the server OMITS `email`
 * and `phone` for a caller who is not GEX staff, and the panel used to call
 * `u.email.toLowerCase()` unguarded. A directory that arrives without those
 * keys must produce an org chart, not a TypeError.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useTeamData } from '../useTeamData'

const STAFF_MEMBER = {
  id: 'M1', full_name: 'Anna Petersen', organisation: 'GreenEarthX',
  status: 'active', primary_team_id: 'T1', primary_role_id: 'R1',
  secondary_team_id: null, secondary_role_id: null,
  email: 'anna.petersen@greenearthx.com', phone: '',
}
const REDACTED_MEMBER = {
  id: 'M1', full_name: 'Anna Petersen', organisation: 'GreenEarthX',
  status: 'active', primary_team_id: 'T1', primary_role_id: 'R1',
  secondary_team_id: null, secondary_role_id: null,
}

function overview(members: unknown[], personal: boolean) {
  return {
    teams: [{ id: 'T1', name: 'T01 — Project Development', description: '', primary_modules: '' }],
    roles: [{ id: 'R1', role_code: 'T01-A', role_name: 'Lead', permission_tier: 'ELEVATED', is_default_admin: true, team_id: 'T1' }],
    members,
    gates: [{ id: 'G01', gate_name: 'NDA', trigger_description: '' }],
    gate_statuses: [{ user_id: 'M1', gate_id: 'G01', status: 'unlocked' }],
    personal_data_included: personal,
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response)
}

describe('useTeamData', () => {
  it('reads the directory from the backend, not Supabase', async () => {
    fetchMock.mockImplementation(() => respond(overview([STAFF_MEMBER], true)))
    const { result } = renderHook(() => useTeamData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/directory/overview')
    expect(result.current.teams).toHaveLength(1)
    expect(result.current.users[0].full_name).toBe('Anna Petersen')
    expect(result.current.gateStatuses[0].gate_id).toBe('G01')
    expect(result.current.personalDataIncluded).toBe(true)
  })

  it('survives a directory served without email or phone', async () => {
    fetchMock.mockImplementation(() => respond(overview([REDACTED_MEMBER], false)))
    const { result } = renderHook(() => useTeamData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const [member] = result.current.users
    expect(member.full_name).toBe('Anna Petersen')
    expect(member.email).toBeUndefined()
    expect(member.phone).toBeUndefined()
    expect(result.current.personalDataIncluded).toBe(false)
  })

  it('sends the bearer token when one is present', async () => {
    localStorage.setItem('gex_auth_session', JSON.stringify({ token: 'tok', email: 'a@b.io' }))
    fetchMock.mockImplementation(() => respond(overview([STAFF_MEMBER], true)))
    const { result } = renderHook(() => useTeamData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tok')
    localStorage.clear()
  })

  it('refetches only the members, and keeps the rest of the cache', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.endsWith('/members')
        ? respond([{ ...STAFF_MEMBER, full_name: 'Anna Renamed' }])
        : respond(overview([STAFF_MEMBER], true)))
    const { result } = renderHook(() => useTeamData(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await result.current.refetchUsers()

    await waitFor(() => expect(result.current.users[0].full_name).toBe('Anna Renamed'))
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/directory/overview', '/api/v1/directory/members',
    ])
    // The collections the narrow refetch did not touch are still there.
    expect(result.current.teams).toHaveLength(1)
    expect(result.current.gateStatuses).toHaveLength(1)
  })

  it('refetches only the gate statuses', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.endsWith('/gate-status')
        ? respond([{ user_id: 'M1', gate_id: 'G01', status: 'locked' }])
        : respond(overview([STAFF_MEMBER], true)))
    const { result } = renderHook(() => useTeamData(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await result.current.refetchGateStatuses()

    await waitFor(() => expect(result.current.gateStatuses[0].status).toBe('locked'))
    expect(result.current.users).toHaveLength(1)
  })

  it('treats a 403 as no directory, not as an error', async () => {
    // GEX's internal directory is staff-only. A customer's user must see
    // nothing — and must not be shown a failure for a rule working correctly.
    fetchMock.mockImplementation(() => respond({ detail: 'not staff' }, false, 403))
    const { result } = renderHook(() => useTeamData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isError).toBe(false)
    expect(result.current.forbidden).toBe(true)
    expect(result.current.users).toEqual([])
    expect(result.current.teams).toEqual([])
    expect(result.current.gates).toEqual([])
    expect(result.current.gateStatuses).toEqual([])
  })

  it('reports an error and serves empty collections rather than a half-built chart', async () => {
    fetchMock.mockImplementation(() => respond({ detail: 'nope' }, false, 401))
    const { result } = renderHook(() => useTeamData(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.users).toEqual([])
    expect(result.current.teams).toEqual([])
  })
})
