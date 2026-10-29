/**
 * The screen's gate line: engine figures for the gates the screen feeds, never a lock.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { GateFeedLine } from '../ScreenGateLine'
import type { CustomerProject } from '@/data/customerProjects'

const gate = (over: Partial<CustomerProject['bankability']['gates'][number]>) => ({
  id: 'G4_OFFTAKE_BANKABLE', name: 'Offtake bankable', completion_pct: 42, total_evidence: 7,
  verified_count: 3, is_complete: false, blocking_items: [], description: '', ...over,
})
const evaluated = (gates: CustomerProject['bankability']['gates']) =>
  ({ evaluated: true, source: 'engine', overall_completion: 10, gates, capital_status: [],
     next_milestone: '' }) as unknown as CustomerProject['bankability']

function wrap(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('GateFeedLine', () => {
  it('names the gate, the verified count and the engine determination, with a link to open items', () => {
    wrap(<GateFeedLine gateIds={['G4_OFFTAKE_BANKABLE']}
      bankability={evaluated([gate({ determination: 'BLOCKED', blocked_reasons: ['OFFTAKE O2 below O4'] })])} />)
    const line = screen.getByTestId('screen-gate-line')
    expect(line).toHaveTextContent('Feeds G4 Offtake bankable — 3 of 7 items verified')
    expect(line).toHaveTextContent('blocked: OFFTAKE O2 below O4')
    expect(screen.getByRole('link', { name: 'Open items' })).toHaveAttribute('href', '/project-report')
  })

  it('shows nothing for a gate outside the viewer\'s persona', () => {
    wrap(<GateFeedLine gateIds={['G8_AUDIT_GRADE_MODEL']} bankability={evaluated([gate({})])} />)
    expect(screen.queryByTestId('screen-gate-line')).toBeNull()
  })

  it('says "not yet evaluated" instead of a figure', () => {
    wrap(<GateFeedLine gateIds={['G4_OFFTAKE_BANKABLE']}
      bankability={{ evaluated: false } as unknown as CustomerProject['bankability']} />)
    expect(screen.getByTestId('screen-gate-line')).toHaveTextContent('feeds G4 — not yet evaluated')
  })
})
