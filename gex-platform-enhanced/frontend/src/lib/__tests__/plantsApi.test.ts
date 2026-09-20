/**
 * The plants client must never name an owner.
 *
 * The Supabase version passed `user_id` from the browser and PostgREST
 * honoured it, so naming somebody else's id read or overwrote their
 * portfolio — and the live ids were `admin-001`, `demo-user`, `user-003`.
 * The server now takes the owner from the bearer token, and this file pins
 * that the client never sends one anyway: two layers, not one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  deletePlant, getPlant, listPlants, replacePortfolio, touchPlant, upsertPlant,
} from '../plantsApi'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

function respond(body: unknown, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response)
}

const ROW = { slug: 'rotterdam', data: { id: 'rotterdam' }, updated_at: 'T1', created_at: 'T0' }

describe('plantsApi', () => {
  it('sends no user id on any call', async () => {
    fetchMock.mockImplementation(() => respond([ROW]))
    await listPlants()
    await upsertPlant('rotterdam', { id: 'rotterdam' })
    await deletePlant('rotterdam')
    await touchPlant('rotterdam')
    await replacePortfolio([{ slug: 'a', data: {} }], { confirmDelete: 0 })

    for (const [url, init] of fetchMock.mock.calls) {
      expect(String(url)).not.toMatch(/user_id|owner/i)
      const body = String((init as RequestInit | undefined)?.body ?? '')
      expect(body).not.toMatch(/user_id|owner_user_id/i)
    }
  })

  it('attaches the session bearer', async () => {
    localStorage.setItem('gex_auth_session', JSON.stringify({ token: 'tok', email: 'a@b.io' }))
    fetchMock.mockImplementation(() => respond([]))
    await listPlants()
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer tok')
  })

  it('reads the portfolio', async () => {
    fetchMock.mockImplementation(() => respond([ROW]))
    const rows = await listPlants<{ id: string }>()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/plants')
    expect(rows[0].data.id).toBe('rotterdam')
  })

  it('treats a missing plant as absent, not as a failure', async () => {
    fetchMock.mockImplementation(() => respond({ detail: 'no' }, false, 404))
    await expect(getPlant('ghost')).resolves.toBeNull()
    await expect(touchPlant('ghost')).resolves.toBeNull()
    // Deleting what is already gone is success.
    await expect(deletePlant('ghost')).resolves.toBeUndefined()
  })

  it('states the expected deletion count on a bulk replace', async () => {
    fetchMock.mockImplementation(() => respond([]))
    await replacePortfolio([{ slug: 'a', data: {} }], { confirmDelete: 2 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/plants?confirm_delete=2')
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT')
  })

  it('surfaces the refusal when the deletion guard trips', async () => {
    // The server refuses and changes nothing; the caller must not read that
    // as "saved".
    fetchMock.mockImplementation(() =>
      respond({ detail: 'would delete 2 plants (a, b), caller expected 0' }, false, 409))
    await expect(replacePortfolio([], { confirmDelete: 0 }))
      .rejects.toThrow(/would delete 2 plants/)
  })

  it('does not swallow a real error', async () => {
    fetchMock.mockImplementation(() => respond({ detail: 'boom' }, false, 500))
    await expect(listPlants()).rejects.toThrow(/boom/)
  })
})
