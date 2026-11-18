/**
 * JML, 2026-11-18:
 *  B — the package register's write controls show for the project's owner only
 *      (server-decided `viewer_is_owner`); everyone else reads.
 *  C — one "DEVEX Brief" page: the owner and an authorised bank reach the same
 *      route; the former bank screen redirects to it.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { MENU_TABS, isVisible, type UserRole } from '@/config/menuArchitecture'
import appSrc from '@/App.tsx?raw'

const state = vi.hoisted(() => ({ owner: false }))

vi.mock('@/hooks/useVisibleProjects', () => ({
  useVisibleProjects: () => ({
    projects: [{ id: 'P1', name: 'North Sea', viewer_is_owner: state.owner }],
    isLoading: false, isError: false, isStaticFallback: false, isFetching: false,
  }),
}))
vi.mock('@/contexts/ProjectContext', () => ({
  useSelectedProject: () => ({ selectedProjectId: 'P1', setSelectedProjectId: vi.fn() }),
}))
vi.mock('@/contexts/UserRoleContext', () => ({
  useUserRole: () => ({ role: { company_type: 'THIRD_PARTY', company_name: 'NORD/LB', user_name: 'Bank' },
    authSession: { email: 'bank@example.com' } }),
}))
vi.mock('@/api', () => ({
  packagesAPI: {
    listForProject: vi.fn(async () => [{ package_id: 'k1', package_name: 'EPC wrap package', package_type: 'EPC',
      phase_required: 'CONSTRUCTION', cost_amount: 1, workflow_state: 'identified', estimate_class: 'CLASS_3', risk_removed: [], capital_eligible: [] }]),
    summary: vi.fn(async () => ({ total_packages: 1, total_capex_p50_eur: 1, fid_readiness_pct: 0, by_state: {} })),
  },
}))

async function renderRegister() {
  const { PackageRegister } = await import('../PackageRegister')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter><PackageRegister /></MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(screen.getByText('EPC wrap package')).toBeTruthy())
}

describe('package register: write controls for the owner only (B)', () => {
  it('a bank sees the register and no "New package"', async () => {
    state.owner = false
    await renderRegister()
    expect(screen.queryByText(/New package/)).toBeNull()
  })

  it('the owner sees "New package"', async () => {
    state.owner = true
    await renderRegister()
    expect(screen.getByText(/New package/)).toBeTruthy()
  })
})

describe('one DEVEX Brief page (C)', () => {
  const items = MENU_TABS.flatMap(t => t.items)
  const role = (company_type: string, f: string, service_type: string | null = null) =>
    ({ company_type, business_function: f, service_type, company_name: 'X', user_name: 'Y' }) as unknown as UserRole

  it('has one entry, named "DEVEX Brief", open to the owner functions and to banks and DFIs', () => {
    const briefs = items.filter(i => /devex/i.test(i.id))
    expect(briefs.map(i => [i.id, i.label, i.path])).toEqual([['devex-brief', 'DEVEX Brief', '/finance/devex-brief']])
    const brief = briefs[0]
    expect(isVisible(brief, role('PRODUCER', 'FINANCE_TREASURY'))).toBe(true)
    expect(isVisible(brief, role('PRODUCER', 'EXECUTIVE'))).toBe(true)
    expect(isVisible(brief, role('THIRD_PARTY', 'EXECUTIVE', 'BANK'))).toBe(true)
    expect(isVisible(brief, role('THIRD_PARTY', 'EXECUTIVE', 'DFI'))).toBe(true)
  })

  it('the former bank screen redirects to the one page', () => {
    expect(appSrc).toMatch(/path="devex-shared"\s+element=\{<Navigate to="\/finance\/devex-brief" replace \/>\}/)
  })
})
