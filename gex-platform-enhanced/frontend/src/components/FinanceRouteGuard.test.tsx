// Frontend route-guard tests (Ticket 1a, item 7).
// Proves direct navigation to a sensitive screen renders the right state:
//   no project → "Project required" · allowed → children · denied → "Access denied"
//   backend error → "Access denied" (FAIL CLOSED — no client heuristic).

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { FinanceRouteGuard } from './FinanceRouteGuard'

// Controllable mocks.
let selectedProjectId: string | null = 'proj_etf_pecos1'
vi.mock('@/contexts/ProjectContext', () => ({
  useSelectedProject: () => ({ selectedProjectId, setSelectedProjectId: () => {} }),
}))

const checkFinanceEntitlement = vi.fn()
vi.mock('@/lib/api/entitlements', () => ({
  checkFinanceEntitlement: (...args: unknown[]) => checkFinanceEntitlement(...args),
}))

function renderGuard() {
  return render(
    <FinanceRouteGuard routeLabel="DSCR Sensitivity Analysis">
      <div>SENSITIVE_CONTENT</div>
    </FinanceRouteGuard>,
  )
}

describe('FinanceRouteGuard', () => {
  beforeEach(() => {
    selectedProjectId = 'proj_etf_pecos1'
    checkFinanceEntitlement.mockReset()
  })

  it('renders children when authorized', async () => {
    checkFinanceEntitlement.mockResolvedValue({ allowed: true, basis: 'role+relationship', reason: 'ok', project_id: 'proj_etf_pecos1' })
    renderGuard()
    expect(await screen.findByText('SENSITIVE_CONTENT')).toBeInTheDocument()
  })

  it('blocks with Access denied when unauthorized', async () => {
    checkFinanceEntitlement.mockResolvedValue({ allowed: false, basis: 'none', reason: 'no relationship', project_id: 'proj_etf_pecos1' })
    renderGuard()
    expect(await screen.findByText(/access denied/i)).toBeInTheDocument()
    expect(screen.queryByText('SENSITIVE_CONTENT')).not.toBeInTheDocument()
  })

  it('shows Project required when no project is selected', async () => {
    selectedProjectId = null
    renderGuard()
    expect(await screen.findByText(/project required/i)).toBeInTheDocument()
    expect(screen.queryByText('SENSITIVE_CONTENT')).not.toBeInTheDocument()
  })

  it('FAILS CLOSED: backend error → Access denied, never renders content', async () => {
    checkFinanceEntitlement.mockRejectedValue(new Error('backend unreachable'))
    renderGuard()
    await waitFor(() => expect(screen.getByText(/access denied/i)).toBeInTheDocument())
    expect(screen.queryByText('SENSITIVE_CONTENT')).not.toBeInTheDocument()
  })
})
