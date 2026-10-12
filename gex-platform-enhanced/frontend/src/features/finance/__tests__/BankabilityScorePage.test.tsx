/**
 * T2 — State & Blockers tells the engine's story and nothing else.
 *
 * The visible project is the REAL customerProjects.ts record for HamburgOne,
 * whose hand-written block says 52 % complete, G0 done, "Technology Vendor
 * Locked" at 75 % and €8M of grants drawn. The screen used to turn that into
 * "BB 63.2". None of it may appear: only the engine readout does.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BankabilityScorePage from '../BankabilityScorePage'
import { CUSTOMER_PROJECTS, type CustomerProject } from '@/data/customerProjects'
import { engineRoutes, speculativeReadout, stubFetch } from '@/test/engineReadoutFixture'

const visible = vi.hoisted(() => ({ projects: [] as CustomerProject[] }))

vi.mock('@/contexts/ProjectContext', () => ({
  useSelectedProject: () => ({ selectedProjectId: 'proj_hamburgone_emethanol', setSelectedProjectId: vi.fn() }),
}))
vi.mock('@/hooks/useVisibleProjects', () => ({
  useVisibleProjects: () => ({
    projects: visible.projects, isLoading: false, isError: false, isStaticFallback: false, isFetching: false,
  }),
}))

const HAMBURG = CUSTOMER_PROJECTS.find(p => p.id === 'proj_hamburgone_emethanol')!

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BankabilityScorePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const FIXTURE_ONLY = [
  'Site Rights Secured', 'Technology Vendor Locked', 'Power, Water & Critical Utility Access',
  'Insurance Bound', 'Bankable Offtake', 'FEED / Financial Structuring', '€8M', 'NordLB',
]

beforeEach(() => { visible.projects = [HAMBURG] })
afterEach(() => vi.unstubAllGlobals())

describe('State & Blockers', () => {
  it('shows the engine state, blockers, levels and capital decisions', async () => {
    stubFetch(engineRoutes({ proj_hamburgone_emethanol: speculativeReadout() }))
    renderPage()

    const line = await screen.findByTestId('declared-vs-evidenced')
    await waitFor(() => expect(line).toHaveTextContent('Declared phase Development'))
    expect(line).toHaveTextContent('Evidenced state Speculative')
    expect(line).toHaveTextContent('0 of 89 applicable evidence items verified')

    expect(screen.getByText('G0 Site Rights & Social License')).toBeInTheDocument()
    expect(screen.getByText('G1 Power, Utilities & Technology Basis')).toBeInTheDocument()
    expect(screen.getByText(/Deal-killer items open: Land Option or Lease Executed/)).toBeInTheDocument()
    expect(screen.getByText('O0')).toBeInTheDocument()
    expect(screen.getByText('E0')).toBeInTheDocument()
    expect(screen.getByText('0 of 8')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/GEX does not commit, release or draw capital/)).toBeInTheDocument())
    expect(screen.getByText('Waiting on G8 Audit-Grade Financial Model')).toBeInTheDocument()
  })

  it('shows no rating, score or fixture figure', async () => {
    stubFetch(engineRoutes({ proj_hamburgone_emethanol: speculativeReadout() }))
    renderPage()
    await screen.findByTestId('declared-vs-evidenced')

    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/\b(AAA|AA|BBB|BB|CCC|CC)\b/)
    expect(text).not.toMatch(/rating|score|63\.2|52\s?%|pts/i)
    for (const s of FIXTURE_ONLY) expect(text).not.toContain(s)
  })

  it('says the engine did not answer instead of falling back to the fixture', async () => {
    stubFetch(engineRoutes({
      proj_hamburgone_emethanol: { status: 503, body: { detail: 'Bankability engine unavailable (port 8001)' } },
    }))
    renderPage()

    expect(await screen.findByText('The gate engine did not answer, so no state is shown.')).toBeInTheDocument()
    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/port 8001/i)
    for (const s of FIXTURE_ONLY) expect(text).not.toContain(s)
  })

  it('shows a refusal reason, which is the user\'s to read', async () => {
    stubFetch(engineRoutes({
      proj_hamburgone_emethanol: { status: 403, body: { detail: 'Access to this project is not granted.' } },
    }))
    renderPage()
    expect(await screen.findByText('Access to this project is not granted.')).toBeInTheDocument()
  })

  it('says so when there is no project to show', () => {
    visible.projects = []
    stubFetch(engineRoutes({}))
    renderPage()
    expect(screen.getByText('No project selected.')).toBeInTheDocument()
  })
})
