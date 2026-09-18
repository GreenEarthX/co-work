/**
 * The TEA screen must say which of five things is true, and never imply a sixth.
 *
 * The refusals carry the meaning here: an unapproved base case must render as a
 * refusal with no figures, and a forbidden project must not be distinguishable
 * from a missing one. The backend enforces both; these tests stop the screen
 * from undoing that by rendering something reassuring instead.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import EconomicsSnapshotPage from '../EconomicsSnapshotPage'

const APPROVED = {
  project_id: 'proj_x',
  claim: {
    claim_id: 'CLM-MBC-abc123', pathway_id: 'pw_1', state: 'verified',
    approved_by: 'ie@example.com', approval_decision_id: 'DEC-1',
    valid_from: '2026-09-18T10:00:00Z', created_at: '2026-09-18T10:00:00Z',
    supersedes_claim_id: null, run_evidence_id: 'EV-1',
  },
  basis: {
    engine: 'openpytea', cost_basis_hash: 'hash_abc123',
    nameplate_capacity: 40000, nameplate_unit: 't_per_year',
  },
  economics: {
    capex_eur: 201000000, opex_eur_per_year: 131000000, lcop: 4617,
    lcop_basis: 'levelised cost per nameplate unit of primary product (t_per_year)',
  },
  lca: {
    g_co2e_per_mj: {
      claim_id: 'CLM-1', state: 'verified', approved: true,
      method: 'Annex VI', approved_by: 'ie@example.com', value: 9.9, unit: 'gCO2e/MJ',
    },
    ghg_saving: null,
  },
  integrity: { ascertained: false, note: 'Provisional cost basis. Inputs are not verifier-signed.' },
  not_available: {
    cost_stack: 'not persisted: the compute path stores the run’s hash',
    regime: 'not persisted',
    sensitivity_tornado: 'not persisted: /sensitivity is compute-only',
    why: 'Serving these would mean recomputing.',
  },
}

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }))
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/economics/proj_x']}>
      <Routes>
        <Route path="/economics/:projectId" element={<EconomicsSnapshotPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('approved base case', () => {
  it('shows the figures with the claim and hash that produced them', async () => {
    mockFetch(200, APPROVED)
    renderPage()
    await waitFor(() => expect(screen.getByText(/4617/)).toBeInTheDocument())
    expect(screen.getByText('CLM-MBC-abc123')).toBeInTheDocument()
    expect(screen.getByText('hash_abc123')).toBeInTheDocument()
    expect(screen.getByText('ie@example.com')).toBeInTheDocument()
  })

  it('always carries the provisional disclaimer', async () => {
    mockFetch(200, APPROVED)
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/ascertained: false/i)).toBeInTheDocument())
    expect(screen.getByText(/not verifier-signed/i)).toBeInTheDocument()
  })

  it('names what is not shown instead of leaving a gap', async () => {
    mockFetch(200, APPROVED)
    renderPage()
    await waitFor(() => expect(screen.getByText('cost_stack')).toBeInTheDocument())
    expect(screen.getByText('sensitivity_tornado')).toBeInTheDocument()
    expect(screen.getByText(/recomputing/i)).toBeInTheDocument()
  })

  it('shows an unapproved GHG claim as awaiting approval, without its value', async () => {
    mockFetch(200, {
      ...APPROVED,
      lca: {
        g_co2e_per_mj: {
          claim_id: 'CLM-2', state: 'submitted', approved: false,
          method: 'Annex VI', approved_by: null, value: undefined,
        },
        ghg_saving: null,
      },
    })
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument())
    expect(screen.queryByText(/9\.9/)).not.toBeInTheDocument()
  })

  it('shows a missing GHG claim as not computed, never as zero', async () => {
    mockFetch(200, { ...APPROVED, lca: { g_co2e_per_mj: null, ghg_saving: null } })
    renderPage()
    await waitFor(() =>
      expect(screen.getAllByText(/not computed/i).length).toBeGreaterThan(0))
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument()
  })
})

describe('the refusals', () => {
  it('renders an unapproved base case as a refusal with no figures', async () => {
    mockFetch(409, {
      detail: {
        error: 'BASE_CASE_NOT_APPROVED', claim_id: 'CLM-MBC-zzz', state: 'submitted',
        message: 'The live base case has not been approved.',
      },
    })
    renderPage()
    await waitFor(() => expect(screen.getByText(/Not approved/i)).toBeInTheDocument())
    expect(screen.getByText(/state submitted/i)).toBeInTheDocument()
    // The whole point: no numbers on a provisional run.
    expect(screen.queryByText(/4617/)).not.toBeInTheDocument()
    expect(screen.queryByText(/201,000,000|€201/)).not.toBeInTheDocument()
  })

  it('says nothing has been computed on 404', async () => {
    mockFetch(404, { detail: 'no base case' })
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/Nothing computed/i)).toBeInTheDocument())
  })

  it('says no access on 403, revealing nothing about the project', async () => {
    mockFetch(403, { detail: 'forbidden' })
    renderPage()
    await waitFor(() => expect(screen.getByText(/No access/i)).toBeInTheDocument())
    expect(screen.queryByText(/Nothing computed/i)).not.toBeInTheDocument()
  })

  it('surfaces a transport failure rather than rendering an empty shell', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    renderPage()
    await waitFor(() => expect(screen.getByText(/network down/i)).toBeInTheDocument())
  })
})
