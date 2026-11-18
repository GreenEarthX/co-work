import { describe, expect, it } from 'vitest'
import { createQueryClient, failureStatus, isSensitive } from './sensitiveQueries'

const refusal = (status: number) => Object.assign(new Error('refused'), { status })

describe('pre-FID queries are never shown from cache (handoff v4 task 9)', () => {
  it('names the sensitive roots only', () => {
    expect(isSensitive(['packages', 'P1'])).toBe(true)
    expect(isSensitive(['devex-brief', 'P1'])).toBe(true)
    expect(isSensitive(['gates', 'P1'])).toBe(false)
  })

  it('reads the status from the error or its message', () => {
    expect(failureStatus(refusal(403))).toBe(403)
    expect(failureStatus(new Error('HTTP 503'))).toBe(503)
    expect(failureStatus(new Error('boom'))).toBeUndefined()
  })

  it('a 403 after a success clears the figures the query held', async () => {
    const client = createQueryClient()
    client.setQueryData(['packages', 'P1'], [{ package_id: 'dev' }])
    await client.fetchQuery({ queryKey: ['packages', 'P1'], queryFn: () => Promise.reject(refusal(403)), retry: false }).catch(() => {})
    const state = client.getQueryState(['packages', 'P1'])
    expect(state?.status).toBe('error')
    expect(state?.data).toBeUndefined()
  })

  it('a 503 clears too; a non-sensitive query keeps its last data', async () => {
    const client = createQueryClient()
    client.setQueryData(['devex-brief', 'P1'], { data: { total: 1 } })
    client.setQueryData(['gates', 'P1'], { g: 1 })
    for (const key of [['devex-brief', 'P1'], ['gates', 'P1']]) {
      await client.fetchQuery({ queryKey: key, queryFn: () => Promise.reject(refusal(503)), retry: false }).catch(() => {})
    }
    expect(client.getQueryData(['devex-brief', 'P1'])).toBeUndefined()
    expect(client.getQueryData(['gates', 'P1'])).toEqual({ g: 1 })
  })

  it('sensitive queries are kept for nobody and refetched on every mount', () => {
    const d = createQueryClient().getQueryDefaults(['packages', 'P1'])
    expect(d.gcTime).toBe(0)
    expect(d.refetchOnMount).toBe('always')
    expect(d.staleTime).toBe(0)
  })
})
