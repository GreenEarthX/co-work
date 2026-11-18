/**
 * D-A (alembic 120): a record whose confirmation was withdrawn for want of a source is shown as
 * "Claimed · source not recorded", with the reason, never as CONFIRMED or plain UNVERIFIED.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FeedstockPurchasesPanel, type ProjectFeedstockSummary } from '../MarketplacePage'

const REASON = 'Source not recorded: moved from a frontend constant and confirmed without evidence.'
const line = (over: object) => ({ projectId: 'proj_TEST', project: 'TEST plant', outputMolecule: 'e-Methanol',
  feedstock: 'CO2', supplier: 'TEST supplier', ratio: 1.46, ratioUnit: 'MT/MT', annualVolume_mt: 14921, unitPrice: 105,
  priceUnit: 'EUR/MT', costPerMtOutput: 153.3, effectiveCostPerMtOutput: 153.3, capacityFactor: 0, status: 'contracted',
  isUtility: false, verification: 'UNVERIFIED', ...over } as never)
const summary = (lines: never[]): ProjectFeedstockSummary => ({
  projectId: 'proj_TEST', project: 'TEST plant', molecule: 'e-Methanol', location: 'Hamburg', capacity_mtpd: 28,
  annualOutput_mt: 10220, outputPrice: 1200, outputPriceState: 'approved', totalFeedstockCostPerMt: 153.3,
  totalEffectiveCostPerMt: 153.3, grossMarginPerMt: null, lines, status: 'development' })

describe('quarantined Marketplace records', () => {
  it('say the source is not recorded, with the reason', () => {
    render(<FeedstockPurchasesPanel feedstockSummaries={[summary([line({ quarantine: REASON })])]} />)
    const badges = screen.getAllByText('Claimed · source not recorded')
    expect(badges.length).toBeGreaterThan(0)
    expect(badges[0]).toHaveAttribute('title', REASON)
    expect(screen.queryByText('CONFIRMED')).toBeNull()
  })

  it('leave an ordinary unverified record as it was', () => {
    render(<FeedstockPurchasesPanel feedstockSummaries={[summary([line({})])]} />)
    expect(screen.queryByText('Claimed · source not recorded')).toBeNull()
    expect(within(document.body).getAllByText('UNVERIFIED').length).toBeGreaterThan(0)
  })
})
