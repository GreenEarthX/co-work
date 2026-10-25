/**
 * Attack A (2026-09-30): a producer verified its own claims from this page.
 * Review, Verify and Reject are now offered only where the server says the
 * caller may review (can_review — the rule it enforces on the write). Verify
 * names the document on file; the page never sends who acted; and a
 * submission uploads its document to the server before anything else.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { StageGatesPage } from '../StageGatesPage'
import { ENGINE_RULES, speculativeReadout, stubFetch } from '@/test/engineReadoutFixture'

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

const SHA = 'a'.repeat(64)

// The readout fixture, plus what /evaluate adds per gate and the page reads.
function snapshot(items: Array<Record<string, unknown>>) {
  const readout = speculativeReadout() as unknown as { gate_evaluations: Array<Record<string, unknown>> }
  readout.gate_evaluations = readout.gate_evaluations.map(g => ({ ...g, owners: ['PROJECT'], unlocks_capital: [] }))
  readout.gate_evaluations[0].evidence_detail = items
  return readout
}

const submitted = (canReview: boolean) => ({
  key: 'land_option_or_lease_executed', label: 'Land Option or Lease Executed', status: 'SUBMITTED',
  severity: 'deal_killer', can_review: canReview, document_hash: SHA,
})
const underReview = (canReview: boolean, documentHash: string | null = SHA) => ({
  key: 'zoning_compatibility_memo', label: 'Zoning Compatibility Memo', status: 'UNDER_REVIEW',
  severity: 'critical', can_review: canReview, document_hash: documentHash,
})

function serve(items: Array<Record<string, unknown>>) {
  const body = snapshot(items)
  return stubFetch([
    ['/bankability/evidence/documents', { status: 200, body: { documents: [] } }],
    ['/bankability/evidence/document', { status: 200, body: { sha256: SHA, status: 'SUBMITTED' } }],
    ['/bankability/evidence', { status: 200, body }],
    ['/bankability/evaluate', { status: 200, body }],
    ['/bankability/rules', { status: 200, body: ENGINE_RULES }],
    ['/bankability/terms', { status: 200, body: { cards: {}, can_edit: false, card_fields: {}, card_gates: {} } }],
  ])
}

async function openG0() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <StageGatesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  // The gate name also appears outside its card; the card's title is the h3.
  const names = await screen.findAllByText('Site Rights & Social License')
  fireEvent.click(names.find(el => el.tagName === 'H3')!)
}

function posts(mock: ReturnType<typeof vi.fn>, fragment: string) {
  return mock.mock.calls
    .filter(([url, init]) => String(url).includes(fragment) && (init as RequestInit | undefined)?.method === 'POST')
    .map(([, init]) => init as RequestInit)
}

afterEach(() => vi.unstubAllGlobals())

describe('evidence review controls', () => {
  it('offers no Review, Verify or Reject to a caller who may not review', async () => {
    serve([submitted(false), underReview(false)])
    await openG0()
    expect(await screen.findByText('Awaiting independent review')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Document/ })).toBeInTheDocument()   // anyone may look
    for (const name of ['Review', 'Verify', 'Reject']) {
      expect(screen.queryByRole('button', { name: new RegExp(`^${name}$`) })).toBeNull()
    }
  })

  it('offers them to a reviewer, and Verify names the document on file — never a person', async () => {
    const mock = serve([submitted(true), underReview(true)])
    await openG0()
    expect(await screen.findByRole('button', { name: /Review/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Reject$/ })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: /^Verify$/ }))
    await waitFor(() => expect(posts(mock, '/bankability/evidence')).toHaveLength(1))
    const body = JSON.parse(String(posts(mock, '/bankability/evidence')[0].body))
    expect(body).toMatchObject({ evidence_key: 'zoning_compatibility_memo', new_status: 'VERIFIED', document_sha256: SHA })
    expect(body).not.toHaveProperty('submitted_by')
  })

  it('will not offer Verify without a document on file, but still offers Reject', async () => {
    serve([underReview(true, null)])
    await openG0()
    expect(await screen.findByText('No document on file — it can be rejected, not verified.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Verify$/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^Reject$/ })).toBeEnabled()
  })

  it('uploads the document to the server before submitting, and sends no name', async () => {
    const mock = serve([{ key: 'stakeholder_map_v1', label: 'Stakeholder Map V1', status: 'IN_PROGRESS', severity: 'critical' }])
    await openG0()
    fireEvent.click(await screen.findByRole('button', { name: 'Define submit' }))
    const file = new File(['TEST map'], 'map.pdf', { type: 'application/pdf' })
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit evidence' }))

    await waitFor(() => expect(posts(mock, '/bankability/evidence')).toHaveLength(2))
    const [upload, submit] = posts(mock, '/bankability/evidence')
    expect(upload.body).toBeInstanceOf(FormData)
    expect((upload.body as FormData).get('file')).toBe(file)
    expect(upload.headers).not.toHaveProperty('Content-Type')
    const body = JSON.parse(String(submit.body))
    expect(body).toMatchObject({ evidence_key: 'stakeholder_map_v1', new_status: 'SUBMITTED' })
    expect(body).not.toHaveProperty('submitted_by')
  })
})
