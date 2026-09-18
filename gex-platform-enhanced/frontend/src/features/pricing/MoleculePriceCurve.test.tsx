// Regression: /pricing-curves rendered NOTHING for any signed-in user (2026-09-14).
//
// The card was written against the `/calibrate` contract (capex_floor_eur,
// n_observations, half-life, seasonality) but fetches `/term-curve`, which the
// PF engine serves in a different shape: capex_floor_eur_t, n_observations
// under governance, and no half-life / seasonality / convenience yield at all.
// The response passed isCurveSane(), so the card rendered it and hit
// `undefined.toLocaleString()`. With no error boundary, one card's TypeError
// unmounted the whole route — all eight cards, the heading, everything.
//
// Signed-out users never saw it: without a token the fetch 401s and the card
// quietly falls back to its seed curve. That is why it looked environmental.

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MoleculePriceCurve } from './MoleculePriceCurve'

// Shape copied from a live `GET :8001/api/v1/pricing/term-curve/E_METHANOL`
// on 2026-09-14. Keys are exact; the numbers are illustrative.
const ENGINE_TERM_CURVE = {
  molecule: 'E_METHANOL',
  spot_price_eur: 800,
  market_structure: 'BACKWARDATION',
  term_curve: [
    { tenor_months: 1, tenor_label: '1M', price_eur: 797.21, implied_forward_eur: 797.21, carry_eur: -2.79, annualised_return_pct: -4.18 },
    { tenor_months: 12, tenor_label: '1Y', price_eur: 772.5, implied_forward_eur: 772.5, carry_eur: -27.5, annualised_return_pct: -3.44 },
    { tenor_months: 60, tenor_label: '5Y', price_eur: 741.0, implied_forward_eur: 741.0, carry_eur: null, annualised_return_pct: -1.47 },
  ],
  capex_floor_eur_t: 560,
  long_term_equilibrium_eur_t: 735.4,
  last_calibrated: '2026-09-14 (seed)',
  governance: { n_observations: 0, calibration_status: 'SEED', run_id: 'r-1' },
}

function engineResponds(body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }))
}

beforeEach(() => {
  localStorage.clear()
  // recharts' ResponsiveContainer needs this; jsdom does not provide it.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => vi.unstubAllGlobals())

describe('MoleculePriceCurve', () => {
  it('renders the engine /term-curve shape instead of blanking the page', async () => {
    engineResponds(ENGINE_TERM_CURVE)
    render(<MoleculePriceCurve molecule="E_METHANOL" showTable />)

    expect(await screen.findByText('e-Methanol Forward Curve')).toBeInTheDocument()
    expect(screen.getByText('800 €/t')).toBeInTheDocument()
    // capex_floor_eur_t is the engine's name for the card's capex_floor_eur.
    expect(screen.getByText('560 €/t')).toBeInTheDocument()
  })

  it('shows a dash for figures the engine does not send, not undefined or NaN', async () => {
    engineResponds(ENGINE_TERM_CURVE)
    render(<MoleculePriceCurve molecule="E_METHANOL" showTable />)
    await screen.findByText('e-Methanol Forward Curve')

    expect(document.body.textContent).not.toMatch(/undefined|NaN/)
    // Half-life and seasonality are absent from /term-curve.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('reads n_observations from the governance stamp, so a seed curve says so', async () => {
    engineResponds(ENGINE_TERM_CURVE)
    render(<MoleculePriceCurve molecule="E_METHANOL" />)
    expect(await screen.findByText('Seed params')).toBeInTheDocument()
  })

  it('still renders a curve published by the Pricing Admin page (the other shape)', async () => {
    engineResponds({})
    localStorage.setItem('gex_forward_curve_SAF', JSON.stringify({
      molecule: 'SAF', spot_price_eur: 1500, convenience_yield: 0.05,
      mean_reversion_half_life_months: 8.3, seasonal_amplitude_pct: 9.4,
      capex_floor_eur: 1050, calibration_error_pct: 0, last_calibrated: '2026-09-01',
      n_observations: 12, published_at: '2026-09-01T10:00:00Z',
      term_curve: [{ tenor_months: 12, tenor_label: '1Y', price_eur: 1576.9 }],
    }))
    render(<MoleculePriceCurve molecule="SAF" />)

    expect(await screen.findByText('Published')).toBeInTheDocument()
    expect(screen.getByText('8.3M')).toBeInTheDocument()
    expect(screen.getByText('1,050 €/t')).toBeInTheDocument()
    // Correctly labelled published curves are kept.
    expect(localStorage.getItem('gex_forward_curve_SAF')).not.toBeNull()
  })

  it('purges a published curve carrying pre-fix tenor labels (18M as "1Y") and uses the engine', async () => {
    engineResponds(ENGINE_TERM_CURVE)
    localStorage.setItem('gex_forward_curve_E_METHANOL', JSON.stringify({
      molecule: 'E_METHANOL', spot_price_eur: 800, capex_floor_eur: 999,
      last_calibrated: '2026-09-01', published_at: '2026-09-01T10:00:00Z',
      term_curve: [
        { tenor_months: 12, tenor_label: '1Y', price_eur: 790 },
        { tenor_months: 18, tenor_label: '1Y', price_eur: 785 },
        { tenor_months: 24, tenor_label: '2Y', price_eur: 780 },
      ],
    }))
    render(<MoleculePriceCurve molecule="E_METHANOL" />)

    expect(await screen.findByText('560 €/t')).toBeInTheDocument()
    expect(localStorage.getItem('gex_forward_curve_E_METHANOL')).toBeNull()
    expect(screen.queryByText('Published')).not.toBeInTheDocument()
  })
})
