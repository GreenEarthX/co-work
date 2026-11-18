import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChainTrace, reviewLabel, type Chain } from '../ChainTrace'

const chain: Chain = {
  source_versions: {
    cost_basis: { version_number: 1, content_sha256: 'a'.repeat(64), saved_by: 'eng', saved_at: '2026-11-18T12:05:00', catalogue_sha256: 'c'.repeat(64) },
    tea_base_case: { claim_id: 'CLM-MBC-1', cost_basis_hash: 'h'.repeat(64), engine: 'openpytea', result_status: 'SCREENING',
      run_by: 'eng', reviewed_by: 'cfo', review_basis: 'OWNER_INTERNAL', review_conditions: ['Re-base CAPEX on FEED'] },
    financing_case: { version_number: 1, content_sha256: 'f'.repeat(64), saved_by: 'cfo' },
  },
  checks: [
    { check: 'FCI = reviewed TEA CAPEX', result: 'PASS', detail: 'EUR 175,255,929' },
    { check: 'Project record CAPEX vs reviewed TEA CAPEX', result: 'REPORTED', difference: -74744071, difference_pct: -0.299 },
  ],
  remaining_assumptions: [{ name: 'product_price_eur_t', value: 1200, source: 'registry', verification_status: 'ASSUMPTION' }],
}

describe('ChainTrace', () => {
  it('shows the source versions, the review standing, every check and every assumption', () => {
    render(<ChainTrace chain={chain} />)
    expect(screen.getByText('1 · Cost Basis v1')).toBeInTheDocument()
    expect(screen.getByText("Owner's internal review — not independent")).toBeInTheDocument()
    expect(screen.getByText(/Re-base CAPEX on FEED/)).toBeInTheDocument()
    expect(screen.getByText('PASS')).toBeInTheDocument()
    expect(screen.getByText('REPORTED')).toBeInTheDocument()
    expect(screen.getByText('product_price_eur_t')).toBeInTheDocument()
  })

  it('says plainly when a version is not traced to a saved chain', () => {
    render(<ChainTrace chain={null} />)
    expect(screen.getByTestId('chain-untraced')).toHaveTextContent('Not traced to a saved calculation chain')
  })

  it('never calls an owner review independent', () => {
    expect(reviewLabel('OWNER_INTERNAL')).toMatch(/not independent/)
    expect(reviewLabel('INDEPENDENT')).toBe('Independent review')
    expect(reviewLabel(undefined)).toBe('not reviewed on the chain')
  })
})

describe('ChainTrace against the version it replaces', () => {
  it('shows that the previous version was withdrawn and what changed', () => {
    render(<ChainTrace chain={{ ...chain, reconciliation_vs_previous: {
      previous_version_number: 1, previous_content_sha256: 'c5de', previous_withdrawn: true,
      previous_withdrawal_reason: 'TEA priced another plant boundary',
      previous_results: { unlevered_irr: -0.0996 },
      inputs_changed: [{ item: 'fci_eur', previous: 175255929, this: 351000000 }] } }} />)
    const box = screen.getByTestId('vs-previous')
    expect(box).toHaveTextContent('v1 was withdrawn from reliance: TEA priced another plant boundary')
    expect(box).toHaveTextContent('fci_eur')
    expect(box).toHaveTextContent('-10.0 %')
  })
})
