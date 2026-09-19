/**
 * One definition of "finance-like", now with two consumers.
 *
 * `canEnterRoute` uses it to admit viewers to finance-guarded routes; the
 * project row uses it to decide whether to offer the Economics (TEA) link.
 * A second copy of the rule would drift, and the drift would show as a button
 * that leads to "no access" — or, worse, a hidden door for someone entitled.
 * The server gate (require_finance_entitlement) remains the real control.
 */
import { describe, expect, it } from 'vitest'

import { isFinanceLike } from '../evidenceCatalog'

describe('isFinanceLike', () => {
  it('admits the finance functions', () => {
    expect(isFinanceLike({ business_function: 'FINANCE_TREASURY' })).toBe(true)
    expect(isFinanceLike({ business_function: 'EXECUTIVE' })).toBe(true)
  })

  it('admits the lender and insurer service types whatever their function', () => {
    for (const service_type of ['BANK', 'DFI', 'INSURER']) {
      expect(isFinanceLike({ business_function: 'ENGINEERING', service_type })).toBe(true)
    }
  })

  it('does not admit the other functions', () => {
    for (const business_function of ['ENGINEERING', 'COMMERCIAL', 'OPERATIONS', 'COMPLIANCE_LEGAL']) {
      expect(isFinanceLike({ business_function })).toBe(false)
    }
  })

  it('does not admit an unrelated service type, or a missing one', () => {
    expect(isFinanceLike({ business_function: 'OPERATIONS', service_type: 'LOGISTICS' })).toBe(false)
    expect(isFinanceLike({ business_function: 'OPERATIONS', service_type: null })).toBe(false)
    expect(isFinanceLike({ business_function: 'OPERATIONS' })).toBe(false)
  })
})
