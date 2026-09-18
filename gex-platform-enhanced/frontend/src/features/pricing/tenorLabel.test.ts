import { describe, it, expect } from 'vitest'
import { tenorLabel } from './tenorLabel'

describe('tenorLabel', () => {
  it('labels whole years as Y and everything else in months', () => {
    const tenors = [1, 3, 6, 9, 12, 18, 24, 30, 36, 48, 60]
    const labels = tenors.map(tenorLabel)
    expect(labels).toEqual(['1M', '3M', '6M', '9M', '1Y', '18M', '2Y', '30M', '3Y', '4Y', '5Y'])
    expect(new Set(labels).size).toBe(labels.length)
  })
})
