/**
 * T4 — /projects reads Phase and State from the engine readout, formats an
 * absent COD as "—", and shows no BNK composite or fixture capital.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProjectsPage, fmtCod } from '../ProjectsPage'
import type { CustomerProject } from '@/data/customerProjects'
import { CUSTOMER_PROJECTS } from '@/test/fixtures/customerProjects'
import { engineRoutes, speculativeReadout, stubFetch } from '@/test/engineReadoutFixture'

const HAMBURG = CUSTOMER_PROJECTS.find(p => p.id === 'proj_hamburgone_emethanol')!
// A project created at runtime: the server shell, no completion date.
const NORTH_SEA: CustomerProject = {
  ...HAMBURG,
  id: 'proj_north_sea_e_methanol_203b51',
  name: 'North Sea e-Methanol',
  completion_date: '',
  bankability: { overall_completion: 0, gates: [], capital_status: [], next_milestone: '', unlocked_capital: [], risk_alerts: [] },
}

vi.mock('@/hooks/useVisibleProjects', () => ({
  useVisibleProjects: () => ({
    projects: [HAMBURG, NORTH_SEA], isLoading: false, isError: false, isStaticFallback: false, isFetching: false,
  }),
}))
vi.mock('@/contexts/ProjectContext', () => ({
  useSelectedProject: () => ({ selectedProjectId: 'proj_hamburgone_emethanol', setSelectedProjectId: vi.fn() }),
}))
vi.mock('@/contexts/UserRoleContext', () => ({
  useUserRole: () => ({
    role: {
      company_type: 'PRODUCER', service_type: null, business_function: 'EXECUTIVE',
      company_name: 'HamburgOne.com', user_name: 'Lisa Friedrich',
    },
  }),
}))
vi.mock('@/hooks/useRiskFlags', () => ({ useRiskFlags: () => ({ flags: [] }) }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function row(name: string) {
  return screen.getByText(name).closest('button') as HTMLElement
}

afterEach(() => vi.unstubAllGlobals())

describe('fmtCod', () => {
  it('formats a date, shows "—" for none, and keeps a non-date as entered', () => {
    expect(fmtCod('2028-02-01')).toBe('FEB-28')
    expect(fmtCod('')).toBe('—')
    expect(fmtCod(null)).toBe('—')
    expect(fmtCod(undefined)).toBe('—')
    expect(fmtCod('2027-Q3')).toBe('2027-Q3')
  })
})

describe('/projects', () => {
  function stubBoth() {
    return stubFetch(engineRoutes({
      proj_hamburgone_emethanol: speculativeReadout(),
      proj_north_sea_e_methanol_203b51: speculativeReadout({
        project_id: 'proj_north_sea_e_methanol_203b51', project_phase: null, total_evidence: 93,
      }),
    }))
  }

  it('reads each row as declared phase against evidenced state, from the engine', async () => {
    stubBoth()
    renderPage()
    await waitFor(() => expect(within(row('HamburgOne e-Methanol Plant')).getByText('0/89 verified')).toBeInTheDocument())

    const hamburg = row('HamburgOne e-Methanol Plant')
    expect(within(hamburg).getByText('DEV')).toBeInTheDocument()
    expect(within(hamburg).getByText('Speculative')).toBeInTheDocument()
    expect(within(hamburg).getByText(
      'Reach Technically plausible: G0 Site Rights & Social License, G1 Power, Utilities & Technology Basis',
    )).toBeInTheDocument()

    // Runtime project: no phase recorded, no completion date.
    const northSea = row('North Sea e-Methanol')
    await waitFor(() => expect(within(northSea).getByText('0/93 verified')).toBeInTheDocument())
    expect(within(northSea).getByTitle('No phase recorded in the project context')).toHaveTextContent('—')
  })

  it('shows no BNK composite, no fixture capital and no invalid date', async () => {
    stubBoth()
    renderPage()
    await waitFor(() => expect(screen.getAllByText('Speculative')).toHaveLength(2))

    const text = document.body.textContent ?? ''
    expect(text).not.toMatch(/BNK|E·G·C·B|Cpx|INVALID DATE|aN\b/)
    expect(text).not.toContain('52%')
    expect(text).not.toMatch(/behind|on track|needs action/i)
  })

  it('says the engine is unavailable rather than showing fixture figures', async () => {
    stubFetch(engineRoutes({
      proj_hamburgone_emethanol: { status: 503, body: { detail: 'Bankability engine unavailable (port 8001)' } },
      proj_north_sea_e_methanol_203b51: { status: 503, body: { detail: 'Bankability engine unavailable (port 8001)' } },
    }))
    renderPage()
    await waitFor(() => expect(screen.getAllByText('Gate engine unavailable')).toHaveLength(2))
    expect(document.body.textContent).not.toContain('52%')
  })
})
