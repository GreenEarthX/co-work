import { describe, expect, it } from 'vitest'
import { judge, policyLine, approvedThreshold, type DecisionTest } from './decisionPolicy'

const base: DecisionTest = { label: 'DSCR P50', metric: 'dscr_p50', policy_key: 'dscr_floor_p50', comparator: '>=',
  capital_decisions: ['SENIOR_DEBT_COMMITMENT'], approved: null,
  proposed: [{ value: 1.3, status: 'GEX proposed', policy_party: 'GEX', effective_date: null }] }
const approved: DecisionTest = { ...base, approved: { value: 1.3, status: 'GEX default (approved by JML)', policy_party: 'GEX', effective_date: '2026-12-01' } }

describe('decision tests on screen', () => {
  it('a proposed value never judges', () => {
    expect(approvedThreshold(base)).toBeNull()
    expect(judge(1.05, base)).toBe('NO_APPROVED_THRESHOLD')
    expect(policyLine(base)).toBe('no approved threshold — no pass/fail (GEX proposed >= 1.3x, not in force)')
  })
  it('a missing metric is not assessable, never a breach', () => {
    expect(judge(null, approved)).toBe('NOT_ASSESSABLE')
  })
  it('an approved value judges and names its party, status and date', () => {
    expect(judge(1.29, approved)).toBe('FAIL')
    expect(judge(1.3, approved)).toBe('PASS')
    expect(policyLine(approved)).toBe('>= 1.3x — GEX, GEX default (approved by JML), effective 2026-12-01')
  })
  it('without the registry nothing is judged', () => {
    expect(judge(2, undefined)).toBe('NO_APPROVED_THRESHOLD')
    expect(policyLine(undefined)).toMatch(/no pass\/fail/)
  })
})
