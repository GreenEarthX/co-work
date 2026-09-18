// The per-card error boundary, pinned.
//
// Before it existed, one TypeError in any of the eight cards on /pricing-curves
// unmounted the whole route (2026-09-14). The data fix removed that TypeError;
// this boundary is what stops the NEXT shape drift from blanking the page again.
//
// The chart is forced to throw. The fallback text and the surviving sibling can
// only both be present if the boundary caught it — without the boundary, the
// render error escapes and neither assertion can hold.

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>()
  return {
    ...actual,
    ResponsiveContainer: () => { throw new Error('chart exploded') },
  }
})

import { MoleculePriceCurve } from './MoleculePriceCurve'

const SANE_ENGINE_CURVE = {
  molecule: 'SAF',
  spot_price_eur: 1500,
  term_curve: [{ tenor_months: 12, tenor_label: '1Y', price_eur: 1576.9 }],
  capex_floor_eur_t: 1050,
  governance: { n_observations: 0 },
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => SANE_ENGINE_CURVE }))
  // React logs caught render errors; the log is expected, not a failure.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('MoleculePriceCurve error boundary', () => {
  it('contains a render failure to its own card and leaves the page standing', async () => {
    render(
      <div>
        <MoleculePriceCurve molecule="SAF" />
        <p>SIBLING_STILL_HERE</p>
      </div>,
    )

    expect(await screen.findByText('SAF curve could not be displayed')).toBeInTheDocument()
    expect(screen.getByText('SIBLING_STILL_HERE')).toBeInTheDocument()
  })
})
