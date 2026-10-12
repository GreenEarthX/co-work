/**
 * T1 — the declared phase is read against the evidenced state, both from the
 * engine readout, with the platform vocabulary's labels.
 */
import type { ReactNode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DeclaredVsEvidenced } from '../DeclaredVsEvidenced'
import { engineRoutes, speculativeReadout, stubFetch } from '@/test/engineReadoutFixture'

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

afterEach(() => vi.unstubAllGlobals())

describe('DeclaredVsEvidenced', () => {
  it('reads the declared phase against the evidenced state and the verified count', async () => {
    stubFetch(engineRoutes({}))
    wrap(<DeclaredVsEvidenced readout={speculativeReadout()} />)
    const line = screen.getByTestId('declared-vs-evidenced')
    await waitFor(() => expect(line).toHaveTextContent('Declared phase Development'))
    expect(line).toHaveTextContent('Evidenced state Speculative')
    expect(line).toHaveTextContent('Idea stage — nothing can be committed yet')
    expect(line).toHaveTextContent('0 of 89 applicable evidence items verified')
  })

  it('says the phase is not recorded when the engine was told none', () => {
    stubFetch(engineRoutes({}))
    wrap(<DeclaredVsEvidenced readout={speculativeReadout({ project_phase: null })} />)
    expect(screen.getByTestId('declared-vs-evidenced')).toHaveTextContent('Declared phase not recorded')
  })

  it('stays readable when the vocabulary does not answer', () => {
    stubFetch([])
    wrap(<DeclaredVsEvidenced readout={speculativeReadout({ current_state: 'TECHNICALLY_PLAUSIBLE' })} />)
    expect(screen.getByTestId('declared-vs-evidenced')).toHaveTextContent('Evidenced state Technically plausible')
  })
})
