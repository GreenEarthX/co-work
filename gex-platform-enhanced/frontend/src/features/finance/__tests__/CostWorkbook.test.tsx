import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { CostWorkbook, FundingSummary } from '../CostWorkbook'

const empty = { provided: false, report: [], summary: { ACCEPTED: 0, CONVERTED: 0, MISSING: 0, CONFLICTING: 0, UNSUPPORTED: 0, blocking: 0 }, can_commit: false }
const sum = (blocking = 0) => ({ ACCEPTED: 5, CONVERTED: 1, MISSING: 0, CONFLICTING: blocking, UNSUPPORTED: 0, blocking })
const preview = (over: Record<string, unknown> = {}) => ({
  file_sha256: 'f'.repeat(64),
  tabs: {
    cost_basis: { provided: true, can_commit: false, summary: sum(1),
      report: [{ status: 'CONFLICTING', field: 'boundary.hydrogen', where: 'Cost Basis', detail: 'hydrogen is made on site, yet the CAPEX excludes electrolysis.', blocking: true }],
      versus_current: { current_version: 2, changes: [{ field: 'power_price_eur_mwh' }], unchanged: false },
      external: [{ metric: 'LCOP_EUR_PER_KG', value: 1.9, author: 'Consultant Ltd', model_and_date: 'TEA model 12 Nov' }] },
    financing: { provided: true, can_commit: true, summary: sum(), report: [], tea_claim_id: 'CLM-1', would_save_as: 'DRAFT',
      limitations: [{ code: 'TEA_NOT_INDEPENDENTLY_REVIEWED', detail: 'TEA run CLM-1 is submitted, review none.' }],
      case_preview: { fci_eur: 3e8, debt_eur: 1.8e8, interest_rate: 0.06, debt_tenor_years: 15, grant_eur: 2e7 },
      capital_sources: [{ name: 'Senior bank debt', amount_eur: 1.2e8, status: 'TERM_SHEET' }] },
    offtake: empty,
  },
  ...over,
})

afterEach(() => vi.unstubAllGlobals())

function uploadFile() {
  fireEvent.change(screen.getByLabelText('Upload workbook'), { target: { files: [new File(['x'], 'cfo.xlsx')] } })
}

describe('CostWorkbook', () => {
  it('previews every tab without saving, and refuses a tab that has a blocking entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => preview() })
    vi.stubGlobal('fetch', fetchMock)
    render(<CostWorkbook projectId="p1" onSaved={() => {}} />)
    uploadFile()
    await screen.findByTestId('workbook-preview')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/workbook/preview')
    expect(screen.getAllByText(/CAPEX excludes electrolysis/).length).toBeGreaterThan(0)
    expect(screen.getByText(/attributed assessments/)).toBeInTheDocument()
    expect(screen.getByText(/kept as declared, beside the case/)).toBeInTheDocument()
    expect(screen.getByText(/Offtake: left empty/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Cost Basis + TEA inputs' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save Financing' })).toBeEnabled()
    expect(screen.getByText(/feeds no returns until promoted/)).toBeInTheDocument()
    expect(screen.getByText('TEA run CLM-1 is submitted, review none.')).toBeInTheDocument()
  })

  it('saves one tab from exactly the previewed file', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => preview() })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ version_number: 3 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => preview() })
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()
    render(<CostWorkbook projectId="p1" onSaved={onSaved} />)
    uploadFile()
    fireEvent.click(await screen.findByRole('button', { name: 'Save Financing' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Financing case v3 saved from the workbook.'))
    const body = fetchMock.mock.calls[1][1].body as FormData
    expect(fetchMock.mock.calls[1][0]).toContain('/workbook/commit')
    expect(body.get('expected_file_sha256')).toBe('f'.repeat(64))
    expect(body.get('tab')).toBe('financing')
  })
})

describe('FundingSummary', () => {
  it('shows uses, the remaining need, what is not counted and attributed gearing', () => {
    const f = {
      uses: [{ kind: 'CONSTRUCTION', amount_eur: 300e6, origin: 'CALCULATED' }, { kind: 'FINANCING_COSTS', component: 'IDC', amount_eur: 15e6, origin: 'STATED' }],
      unknown_uses: ['RESERVES'], total_uses_eur: 315e6, total_is_floor: true, openpytea_working_capital_eur: 45e6,
      received_eur: 10e6, binding_available_eur: 80e6, remaining_need_eur: 225e6,
      conditional: [{ name: 'DFI loan', amount_eur: 60e6, conditions: 'credit committee approval' }],
      uncommitted: [], pipeline: [{ name: 'Green bond', amount_eur: 50e6 }], pipeline_total_eur: 50e6,
      gearing: [{ by: 'Senior bank debt', ratio: 0.57, threshold: 0.5, result: 'ABOVE', basis: 'debt / total defined uses', standing: "this lender's own limit, as declared" }],
      notes: [],
    }
    render(<FundingSummary f={f} />)
    expect(screen.getByText(/Total project cost at least €315M/)).toBeInTheDocument()
    expect(screen.getByText(/remaining funding need at least €225M/)).toBeInTheDocument()
    expect(screen.getByText(/Conditional, not counted: DFI loan/)).toBeInTheDocument()
    expect(screen.getByText(/Pipeline, outside this plan/)).toBeInTheDocument()
    expect(screen.getByText(/set by Senior bank debt/)).toBeInTheDocument()
  })
})
