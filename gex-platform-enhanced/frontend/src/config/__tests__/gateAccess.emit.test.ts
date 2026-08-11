/**
 * Gate-the-verb-not-the-view invariants.
 *
 * The change these protect: a lender used to be locked out of diagnostic
 * screens by the SPONSOR's gate progress — their own workspace gated on the
 * borrower's actions. Diagnostic screens are now readable by a readiness
 * assessor with a banner stating the gate position.
 *
 * The risk that creates, and what these tests exist to prevent: the same
 * bypass leaking onto routes that EMIT an artefact or a commitment. A lender
 * positively wants a system that refuses to export an IC pack over an open
 * gate — that control must survive every future edit.
 */

import { describe, expect, it } from 'vitest'
import {
  EMIT_ROUTES,
  isEmitRoute,
  isReadinessAssessor,
  shouldViewLockedScreen,
} from '../gateAccess'
import type { UserRole } from '@/contexts/UserRoleContext'

const bank: UserRole = {
  company_type: 'THIRD_PARTY',
  service_type: 'BANK',
  business_function: 'FINANCE_TREASURY',
} as UserRole

const producer: UserRole = {
  company_type: 'PRODUCER',
  service_type: null,
  business_function: 'ENGINEERING',
} as UserRole

const insurer: UserRole = {
  company_type: 'THIRD_PARTY',
  service_type: 'INSURER',
  business_function: 'COMPLIANCE_LEGAL',
} as UserRole

// Diagnostic screens a lender must be able to read ahead of the gate.
const DIAGNOSTIC_ROUTES = [
  '/bankability-snapshot',
  '/capital-stack',
  '/offtake-quality',
  '/term-sheet',
  '/finance-gaps',
  '/insurance-schedule',
  '/insurance-coverage',
  '/data-room',
  '/finance/drawdown-timeline',
]

describe('emit gates hold for everyone', () => {
  it.each([...EMIT_ROUTES])('%s is never bypassed by a bank', (route) => {
    expect(isEmitRoute(route)).toBe(true)
    expect(shouldViewLockedScreen(bank, route)).toBe(false)
  })

  it('covers the three commitment-forming routes', () => {
    // If a route is added that signs, approves or exports, it belongs here.
    expect(EMIT_ROUTES).toContain('/ic-pack')
    expect(EMIT_ROUTES).toContain('/approval-queue')
    expect(EMIT_ROUTES).toContain('/commitment-signing')
  })
})

describe('diagnostic screens open for readiness assessors', () => {
  it.each(DIAGNOSTIC_ROUTES)('%s is readable by a bank', (route) => {
    expect(isEmitRoute(route)).toBe(false)
    expect(shouldViewLockedScreen(bank, route)).toBe(true)
  })
})

describe('the change is deliberately narrow', () => {
  it('does not alter the producer experience', () => {
    expect(isReadinessAssessor(producer)).toBe(false)
    for (const route of [...DIAGNOSTIC_ROUTES, ...EMIT_ROUTES]) {
      expect(shouldViewLockedScreen(producer, route)).toBe(false)
    }
  })

  it('does not silently extend to insurers or other third parties', () => {
    // Extending is a deliberate decision per actor, using the same test:
    // does this actor ASSESS readiness, or does it DECLARE it?
    expect(isReadinessAssessor(insurer)).toBe(false)
    expect(shouldViewLockedScreen(insurer, '/capital-stack')).toBe(false)
  })

  it('identifies a lender by service type, not company type', () => {
    expect(isReadinessAssessor(bank)).toBe(true)
  })
})
