/**
 * F15: availability is derived from the project's tokens (rate × days of window in the period, by
 * state), never from the sales record's stored "available / tokenised / in market" figures.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { TokenAvailabilityLine, periodTonnes } from '../MarketplacePage'

const W = [
  { start: '2028-01-01', end: '2028-01-10', rate_mtpd: 10, state: 'MINTED' },      // 10 days
  { start: '2028-01-05', end: '2028-02-28', rate_mtpd: 2, state: 'RESERVED' },
  { start: '2028-01-01', end: '2028-12-31', rate_mtpd: 1, state: 'SETTLED' },
  { start: '2028-01-01', end: '2028-12-31', rate_mtpd: 99, state: 'UNKNOWN' },    // not a live bucket
]
const d = (s: string) => new Date(`${s}T00:00:00Z`)

describe('tonnes from tokens', () => {
  it('counts each window\'s overlap with the period, the end day included', () => {
    expect(periodTonnes(W, d('2028-01-01'), d('2028-01-11'))).toEqual({ available: 100, listed: 12, contracted: 10 })
    expect(periodTonnes(W, d('2028-03-01'), d('2028-03-11'))).toEqual({ available: 0, listed: 0, contracted: 10 })
    expect(periodTonnes([], d('2028-01-01'), d('2029-01-01'))).toEqual({ available: 0, listed: 0, contracted: 0 })
  })

  it('shows nothing for a project the caller does not own', () => {
    const { container } = render(<TokenAvailabilityLine windows={undefined} capacityMtpd={100} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('says zero, from tokens, when there are no tokens, whatever the record claimed', () => {
    render(<TokenAvailabilityLine windows={[]} capacityMtpd={100} />)
    expect(screen.getByTestId('token-availability')).toHaveTextContent('tokenised, not listed 0 t')
    expect(screen.getByText('Tokenised: 0% of capacity')).toBeInTheDocument()
  })
})
