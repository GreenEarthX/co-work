/**
 * Equipment equations go through the backend, and the delete names no user.
 *
 * The Supabase version's delete was `.delete().eq("id", id)` — no user
 * scoping, while every sibling query filtered on `user_id`. Under the bundled
 * anon key that removed any row by id, for anybody (CLAUDE_HANDOFF §8.16).
 *
 * The server is the real control; this pins that the client does not even
 * offer an owner to override.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useEquipmentEquations } from '../useEquipmentEquations'

const fetchMock = vi.fn()

const ROW = {
  id: 'row-1',
  equation_id: 'EQ351',
  equation_expression: 'n_H2 = m_H2 / M_H2',
  output_param: 'n_H2',
  variable_bindings: {},
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response)
}

describe('useEquipmentEquations', () => {
  it('reads from the backend, scoped to plant and node', async () => {
    fetchMock.mockImplementation(() => respond([ROW]))
    const { result } = renderHook(() =>
      useEquipmentEquations('rotterdam-rfnbo', 'e-electrolyzer', 'Electrolyzer'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/equipment-equations?plant_slug=rotterdam-rfnbo&node_id=e-electrolyzer')
    expect(result.current.items[0].equation_id).toBe('EQ351')
  })

  it('never sends a user id on any call', async () => {
    localStorage.setItem('gex_auth_session', JSON.stringify({ token: 'tok', email: 'a@b.io' }))
    fetchMock.mockImplementation(() => respond([ROW]))
    const { result } = renderHook(() =>
      useEquipmentEquations('p', 'n', 'Label'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await result.current.upsert({
      equation_id: 'EQ1', equation_expression: 'a = b',
      output_param: 'a', variable_bindings: {},
    })
    await result.current.remove('row-1')

    for (const [url, init] of fetchMock.mock.calls) {
      expect(String(url)).not.toMatch(/user_id|owner/i)
      expect(String((init as RequestInit | undefined)?.body ?? '')).not.toMatch(/user_id|owner/i)
    }
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tok')
  })

  it('deletes by id alone and lets the server decide whose row it is', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      init?.method === 'DELETE' ? respond(null, true, 204) : respond([ROW]))
    const { result } = renderHook(() => useEquipmentEquations('p', 'n', 'L'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    const res = await result.current.remove('row-1')
    expect(res.error).toBeNull()
    const del = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'DELETE')!
    expect(del[0]).toBe('/api/v1/equipment-equations/row-1')
  })

  it('surfaces a refused delete rather than reporting success', async () => {
    // 404 is what someone else's row (or a missing one) answers.
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      init?.method === 'DELETE' ? respond({ detail: 'No such equation' }, false, 404)
        : respond([ROW]))
    const { result } = renderHook(() => useEquipmentEquations('p', 'n', 'L'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    const res = await result.current.remove('someone-elses-row')
    expect(res.error).toBeInstanceOf(Error)
    expect(result.current.items).toHaveLength(1)
  })

  it('upserts with the plant, node and label the hook was given', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      init?.method === 'PUT' ? respond(ROW) : respond([ROW]))
    const { result } = renderHook(() =>
      useEquipmentEquations('rotterdam-rfnbo', 'e-wtu', 'Water Treatment Unit'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await result.current.upsert({
      equation_id: 'EQ8', equation_expression: 'E_year = W_dc_in * H_op_eff',
      output_param: 'E_year', variable_bindings: {},
    })

    const put = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'PUT')!
    const body = JSON.parse(String((put[1] as RequestInit).body))
    expect(body).toMatchObject({
      plant_slug: 'rotterdam-rfnbo',
      equipment_node_id: 'e-wtu',
      equipment_label: 'Water Treatment Unit',
      equation_id: 'EQ8',
    })
  })
})
