/**
 * T3 — Capital Eligibility: engine counts under engine words, no fixture
 * capital, no pre-COD panel (D11), and no write on page view.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FinanceBankabilityView } from '../FinanceBankabilityView'
import { CUSTOMER_PROJECTS } from '@/test/fixtures/customerProjects'
import { engineRoutes, speculativeReadout, stubFetch } from '@/test/engineReadoutFixture'

vi.mock('@/contexts/ProjectContext', () => ({
  useSelectedProject: () => ({ selectedProjectId: 'proj_hamburgone_emethanol', setSelectedProjectId: vi.fn() }),
}))
vi.mock('@/hooks/useVisibleProjects', async () => {
  const { CUSTOMER_PROJECTS: all } = await vi.importActual<typeof import('@/test/fixtures/customerProjects')>('@/test/fixtures/customerProjects')
  const hamburg = all.find(p => p.id === 'proj_hamburgone_emethanol')!
  return {
    useVisibleProjects: () => ({
      projects: [hamburg], isLoading: false, isError: false, isStaticFallback: false, isFetching: false,
    }),
  }
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FinanceBankabilityView />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function card(label: string) {
  return screen.getByText(label).parentElement as HTMLElement
}

afterEach(() => vi.unstubAllGlobals())

describe('Capital Eligibility', () => {
  it('labels the engine counts for what they count', async () => {
    stubFetch(engineRoutes({ proj_hamburgone_emethanol: speculativeReadout() }))
    renderPage()
    await screen.findByTestId('declared-vs-evidenced')

    expect(card('Gates satisfied')).toHaveTextContent('0 of 12')
    expect(card('Evidence verified')).toHaveTextContent('0 of 89')
    expect(card('Eligible for a capital decision')).toHaveTextContent('0 of 8')
    expect(screen.getByText(/Technically plausible \(Site and technology basis confirmed\) — waiting on G0 Site Rights & Social License, G1 Power, Utilities & Technology Basis/)).toBeInTheDocument()
    expect(screen.getByText('Senior Debt Credit Approval (conditional)')).toBeInTheDocument()
    expect(screen.getByText('Waiting on G0 Site Rights & Social License')).toBeInTheDocument()
  })

  it('lists the engine FINANCE persona gates under Financial gates', async () => {
    stubFetch(engineRoutes({ proj_hamburgone_emethanol: speculativeReadout() }))
    renderPage()
    const heading = await screen.findByText('Financial gates')
    const section = heading.closest('.rounded-2xl') as HTMLElement
    await waitFor(() => expect(within(section).queryByText('G0 Site Rights & Social License')).toBeNull())
    for (const name of [
      'G4 Binding Offtake', 'G6 Independent Engineer Sign-off', 'G7 Insurability Confirmed',
      'G8 Audit-Grade Financial Model', 'G10 Financial Close',
    ]) expect(within(section).getByText(name)).toBeInTheDocument()
  })

  it('shows no fixture capital, no "unlocked", no pre-COD metrics and no developer message', async () => {
    const fetchMock = stubFetch(engineRoutes({ proj_hamburgone_emethanol: speculativeReadout() }))
    renderPage()
    await screen.findByTestId('declared-vs-evidenced')

    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/unlock/i)
    expect(text).not.toMatch(/proxy mode|start backend|port 8001/i)
    expect(text).not.toMatch(/\b(CEC|FRI|RMR|CBM|LLCR)\b|FID READY/)
    expect(text).not.toMatch(/€\s?\d|NordLB|drawn/i)
    // Viewing the page writes nothing: no request reaches the pre-COD route.
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('pre-cod-metrics'))).toBe(false)
  })

  it('says the engine did not answer instead of falling back to the fixture', async () => {
    stubFetch(engineRoutes({
      proj_hamburgone_emethanol: { status: 503, body: { detail: 'Bankability engine unavailable (port 8001)' } },
    }))
    renderPage()
    expect(await screen.findByText('The gate engine did not answer, so no determination is shown.')).toBeInTheDocument()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/port 8001/i)
    // The fixture's gate names never stand in for the engine's.
    const fixtureGates = CUSTOMER_PROJECTS.find(p => p.id === 'proj_hamburgone_emethanol')!.bankability.gates
    for (const g of fixtureGates) expect(text).not.toContain(g.name)
  })
})
