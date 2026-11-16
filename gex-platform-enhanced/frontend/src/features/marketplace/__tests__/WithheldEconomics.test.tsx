/**
 * A project's input costs are its owner's alone (alembic 112). A company with project
 * access but no ownership receives no input lines, and the screen must not turn that
 * into a cost of zero.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FeedstockPurchasesPanel, type ProjectFeedstockSummary } from '../MarketplacePage'

const summary = (over: Partial<ProjectFeedstockSummary>): ProjectFeedstockSummary => ({
  projectId: 'proj_TEST', project: 'TEST plant', molecule: 'e-Methanol', location: 'Hamburg',
  capacity_mtpd: 28, annualOutput_mt: 10220, outputPrice: 1200, outputPriceState: 'approved',
  totalFeedstockCostPerMt: 0, totalEffectiveCostPerMt: 0, grossMarginPerMt: null, lines: [], status: 'development',
  ...over,
})

describe('Feedstock purchases with no input lines', () => {
  it('shows no cost and says why, instead of a zero cost', () => {
    render(<FeedstockPurchasesPanel feedstockSummaries={[summary({})]} />)
    expect(screen.getByText('Eff. cost: —')).toBeInTheDocument()
    expect(screen.queryByText(/Eff\. cost: 0/)).toBeNull()
    expect(screen.getByText(/not shared with your company/)).toBeInTheDocument()
  })

  it('still shows the cost when the lines are there', () => {
    render(<FeedstockPurchasesPanel feedstockSummaries={[summary({
      totalEffectiveCostPerMt: 2049,
      lines: [{ projectId: 'proj_TEST', project: 'TEST plant', outputMolecule: 'e-Methanol', feedstock: 'CO2',
        supplier: 'TEST', ratio: 1.46, ratioUnit: 'MT/MT', annualVolume_mt: 14921, unitPrice: 105,
        priceUnit: 'EUR/MT', costPerMtOutput: 153.3, effectiveCostPerMtOutput: 153.3, capacityFactor: 0,
        status: 'planned', isUtility: false, verification: 'UNVERIFIED' } as never],
    })]} />)
    expect(screen.getByText('Eff. cost: 2,049 EUR/MT')).toBeInTheDocument()
    expect(screen.queryByText(/not shared with your company/)).toBeNull()
  })
})
