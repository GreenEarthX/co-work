import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { InputsChip, TeaRunReport } from '../TeaRunReport'

const years = [0, 1, 2, 3].map(i => ({
  year: i, discount_factor: 1 / 1.08 ** (i + 1), production_kg: i < 2 ? 0 : 1_000_000,
  capital: i < 2 ? 50e6 : 0, fixed_opex: i < 2 ? 0 : 4e6, variable_opex: i < 2 ? 0 : 3e6, by_product_revenue: 0,
  cost: i < 2 ? 50e6 : 7e6,
}))

const run = {
  claim_id: 'CLM-MBC-abc', engine: 'openpytea', engine_version: '3.1.0', lcop: 12.5, created_at: '2026-11-20T14:00:00',
  run_by: 'cfo', report: { ref: 'GEX-TEA-abc-1234abcd' },
  inputs_now: { unchanged: false, checks: [{ check: 'engine', result: 'CHANGED', detail: 'Priced on OpenPyTEA 3.0.0; the engine now runs 3.1.0.' }] },
  tea_inputs: {
    request: { quote_plant: {
      equipment: [{ name: 'Electrolyser', installed_cost: 80e6, cost_year: 2024, source: 'Vendor quote Q-17' }],
      variable_opex: { electricity: { consumption: 480, unit: 'MWh/day', price: 60, source: 'PPA term sheet' } },
      loc_factor: 1, loc_factor_basis: 'local quotes', contingency: 0.1, operators_hired: 3, operator_hourly_rate: 40,
    } },
    defaults_used: [
      { name: 'openpytea.osbl_factor', value: 0.3, basis: 'OpenPyTEA default for Fluids plants' },
      { name: 'openpytea.de_factor', value: 0.3, basis: 'OpenPyTEA default for Fluids plants' },
      { name: 'openpytea.maintenance', value: 0.05, basis: 'x ISBL' },
      { name: 'openpytea.working_capital', value: 0.15, basis: 'x fixed capital' },
    ],
    analysis: {
      cost_basis: { cost_year: 2026, cepci_basis: 'CEPCI 2026 (Gabillon forward, row 317b8568)' },
      breakdown: {
        currency: 'EUR', discount_rate: 0.08, plant_utilization: 0.9, project_lifetime: 4, location_factor: 1,
        production_kg_per_year_full: 1_000_000,
        capital_costs: { isbl: 80e6, osbl: 24e6, design_and_engineering: 31.2e6, contingency: 10.4e6, fixed_capital: 145.6e6, working_capital: 21.84e6 },
        equipment: [{ name: 'Electrolyser', category: 'Vendor quote', cost_year: 2024, target_year: 2026, purchased_cost: 83e6, direct_cost: 83e6 }],
        variable_opex: { streams: { electricity: 3e6 }, total: 3e6 },
        fixed_opex: { components: { operating_labor: 0.25e6, maintenance: 4e6 }, total: 4.25e6 },
        per_kg: { capital: 6.0, variable: { electricity: 3.0 }, fixed: { operating_labor: 0.2, maintenance: 3.3 }, by_product_credit: 0, levelized_cost: 12.5, check: 0 },
        years, note: 'Pre-tax, unfinanced. NPV, IRR and payback are not computed here: returns come from the financing case.',
      },
      sensitivity: { tornado: [
        { parameter: 'discount_rate', label: 'Discount rate (no debt in this model)', unit: '%', base_input: 8, low_input: 6, high_input: 10,
          low_lcop: 11.4, high_lcop: 13.7, range_basis: 'CONVENTION (GEX screening range, not a sourced range): +/- 2 percentage points' },
      ] },
      index_band: { applies: true, method: 'Gabillon two-factor P-forward of the CEPCI', years: { 2026: { low: 749.2, value: 834.6, high: 925.8, ref_id: 'fwd2026x' } },
        base: { lcop: 12.5, fixed_capital: 145.6e6 }, index_low: { lcop: 11.9, fixed_capital: 130.7e6 }, index_high: { lcop: 13.1, fixed_capital: 161.5e6 },
        not_covered: ['Electricity and other prices: Gabillon does not apply to power, which cannot be stored.'] },
      market_reference: { applies: true, model: 'Gabillon two-factor (PF engine)', molecule: 'E_METHANOL', calibration_status: 'SEED',
        n_observations: 0, last_calibrated: '2026-03-22', unit: 'EUR/kg', spot: 0.8, long_term_equilibrium: 0.8, capex_floor: 0.6,
        half_life_months: 12.8, levelised_price: 0.716, required_price: 12.5, difference: 11.784,
        basis: 'Real Gabillon price per operating year, levelised over this run.',
        standing: 'SEED: expert priors, no market observations. A model reference, not a market quote or an offtake price.',
        years: [{ year: 2, operating_year: 1, price_nominal: 0.834, price_real: 0.826 }, { year: 3, operating_year: 2, price_nominal: 0.842, price_real: 0.817 }] },
    },
  },
}

describe('TeaRunReport', () => {
  it('leads with the reference, the inputs check and the required price, and shows no returns', () => {
    render(<TeaRunReport b={run} />)
    expect(screen.getByTestId('report-ref')).toHaveTextContent('GEX-TEA-abc-1234abcd')
    expect(screen.getByTestId('inputs-chip')).toHaveTextContent('Inputs changed since this run')
    expect(screen.getByText('Required price (LCOP)')).toBeInTheDocument()
    expect(within(screen.getByTestId('cost-per-kg')).getByText('electricity')).toBeInTheDocument()
    expect(screen.queryByText(/^NPV$|^IRR$|Not profitable/)).toBeNull()
  })

  it('names the source of every quote and the basis of every capital factor', () => {
    render(<TeaRunReport b={run} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Capital' }))
    expect(screen.getByText('Vendor quote Q-17')).toBeInTheDocument()
    const build = screen.getByTestId('capital-build-up')
    expect(within(build).getByText(/^30.0% of ISBL$/)).toBeInTheDocument()
    expect(within(build).getAllByText(/OpenPyTEA default for Fluids plants/).length).toBe(2)
    expect(within(build).getByText('STATED on the cost basis')).toBeInTheDocument()
  })

  it('marks the fixed costs that are only a percentage of capital', () => {
    render(<TeaRunReport b={run} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Operating costs' }))
    expect(within(screen.getByTestId('fixed-opex')).getByText('Maintenance †')).toBeInTheDocument()
    expect(screen.getByText(/STATED: 3 operators × 40.00 EUR\/h/)).toBeInTheDocument()
    expect(screen.getByText(/94% of fixed cost/)).toBeInTheDocument()
  })

  it('shows the cost by year and how it divides into the LCOP', () => {
    render(<TeaRunReport b={run} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Cost by year' }))
    expect(screen.getByTestId('cost-by-year').querySelectorAll('tbody tr')).toHaveLength(4)
    expect(screen.getByText(/the LCOP/)).toBeInTheDocument()
  })

  it('moves the rate in points and says the range is a convention', () => {
    render(<TeaRunReport b={run} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Sensitivity' }))
    const t = screen.getByTestId('tornado')
    expect(within(t).getByText('6.00 – 10.00')).toBeInTheDocument()
    expect(within(t).getByText(/^CONVENTION/)).toBeInTheDocument()
  })

  it('shows the Gabillon band and what it does not cover', () => {
    render(<TeaRunReport b={run} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Gabillon' }))
    expect(within(screen.getByTestId('index-band')).getByText('749.2')).toBeInTheDocument()
    expect(screen.getByText(/does not apply to power/)).toBeInTheDocument()
  })

  it('sets the Gabillon price beside the required price, labelled as a model on SEED priors', () => {
    render(<TeaRunReport b={run} />)
    const mr = screen.getByTestId('market-reference')
    expect(within(mr).getByText('0.716')).toBeInTheDocument()
    expect(within(mr).getByText('11.784')).toBeInTheDocument()
    expect(within(mr).getAllByText('MODEL · SEED').length).toBeGreaterThan(0)
    expect(within(mr).getByText(/not a market quote/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Gabillon' }))
    expect(screen.getByTestId('gabillon-deck').querySelectorAll('tbody tr')).toHaveLength(2)
  })

  it('a product Gabillon cannot compare says why, with no figure', () => {
    const r = structuredClone(run)
    r.tea_inputs.analysis.market_reference = { applies: false, reason: 'Gabillon prices E_METHANE in €/MWh; no energy content is stated.' }
    render(<TeaRunReport b={r} />)
    expect(screen.getByTestId('market-reference-none')).toHaveTextContent('€/MWh')
    expect(screen.queryByTestId('market-reference')).toBeNull()
  })

  it('states the run as SUBMITTED until an independent review confirms it', () => {
    const { unmount } = render(<TeaRunReport b={run} />)
    expect(screen.getByTestId('state-chip')).toHaveTextContent('SUBMITTED')
    unmount()
    render(<TeaRunReport b={{ ...run, state: 'verified', review_basis: 'OWNER_INTERNAL' }} />)
    expect(screen.getByTestId('state-chip')).toHaveTextContent('SUBMITTED')
  })

  it('an independent review shows CONFIRMED', () => {
    render(<TeaRunReport b={{ ...run, state: 'verified', review_basis: 'INDEPENDENT', reviewed_by_company: 'Foxwell' }} />)
    expect(screen.getByTestId('state-chip')).toHaveTextContent('CONFIRMED')
  })

  it('draws the three graphs from the record: cost per kg, cost by year, Gabillon against the required price', () => {
    render(<TeaRunReport b={run} />)
    const kg = screen.getByTestId('chart-cost-per-kg')
    expect(kg.querySelectorAll('rect[height="28"]')).toHaveLength(3)       // capital, electricity, fixed
    expect(kg).toHaveTextContent('Capital 48%')                            // 6.0 of 12.5
    fireEvent.click(screen.getByRole('tab', { name: 'Cost by year' }))
    const yr = screen.getByTestId('chart-cost-by-year')
    expect(yr.querySelectorAll('rect[width]').length).toBeGreaterThanOrEqual(4)
    fireEvent.click(screen.getByRole('tab', { name: 'Gabillon' }))
    const g = screen.getByTestId('chart-gabillon')
    expect(g).toHaveTextContent('Required 12.500')
    expect(g).toHaveTextContent('Levelised 0.716')
    expect(g).toHaveTextContent('not a market quote')
  })

  it('says plainly when a run predates recorded results', () => {
    render(<TeaRunReport b={{ ...run, tea_inputs: { request: {} } }} />)
    expect(screen.getByTestId('report-not-recorded')).toHaveTextContent('only its headline figures exist')
  })

  it('opens the inputs check to show what changed', () => {
    render(<InputsChip status={run.inputs_now} />)
    fireEvent.click(screen.getByTestId('inputs-chip'))
    expect(screen.getByText(/the engine now runs 3.1.0/)).toBeInTheDocument()
  })
})

describe('TeaRunReport, defensive', () => {
  it('says the band is zero when no line is priced before the cost-base year', () => {
    const flat = structuredClone(run)
    const ib = flat.tea_inputs.analysis.index_band
    ib.index_low = { ...ib.base }; ib.index_high = { ...ib.base }
    flat.tea_inputs.defaults_used.push({ name: 'quote.cost_year', value: 2026, basis: 'price year not stated for 3 line(s); taken as the cost base year, no escalation' })
    render(<TeaRunReport b={flat} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Gabillon' }))
    expect(screen.getByTestId('index-band-flat')).toHaveTextContent('price year not stated for 3 line(s)')
  })

  it('a broken record shows an error in place, never a blank page', () => {
    const broken = structuredClone(run)
    broken.tea_inputs.analysis.index_band = { applies: true, years: {}, base: { lcop: 1, fixed_capital: 1 } }
    render(<TeaRunReport b={broken} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Gabillon' }))
    expect(screen.getByTestId('report-error')).toBeInTheDocument()
  })
})
