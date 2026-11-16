/**
 * The RFQ create call carries an Idempotency-Key (backend F12), and a caller's header is ADDED
 * to the JSON and auth headers — fetchAPI used to let `options` overwrite the merged headers.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { marketAPI } from '@/api'

afterEach(() => vi.unstubAllGlobals())

function capture() {
  const seen: { headers: Record<string, string> }[] = []
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    seen.push({ headers: (init?.headers ?? {}) as Record<string, string> })
    return new Response(JSON.stringify({ id: 'r1' }), { status: 201 })
  }))
  return seen
}

const RFQ = { molecule: 'e-Methanol', volume_mtpd: 10, delivery_start: '2028-01-01', delivery_end: '2028-12-31' }

describe('RFQ create', () => {
  it('sends the Idempotency-Key beside the JSON content type', async () => {
    const seen = capture()
    await marketAPI.createRFQ(RFQ, 'form-key-0001')
    expect(seen[0].headers['Idempotency-Key']).toBe('form-key-0001')
    expect(seen[0].headers['Content-Type']).toBe('application/json')
  })

  it('sends no key when none is given', async () => {
    const seen = capture()
    await marketAPI.createRFQ(RFQ)
    expect(seen[0].headers['Idempotency-Key']).toBeUndefined()
    expect(seen[0].headers['Content-Type']).toBe('application/json')
  })
})
