/**
 * Decision tests on screen (handoff v4, task 6).
 *
 * A metric is always shown; it is judged only against an APPROVED policy value
 * (a GEX default approved by JML, or an institution's established policy with a
 * reference). With none, the screen says "no approved threshold — no pass/fail"
 * and shows any proposed value as GEX proposed. With the metric missing, it is
 * "not assessable — required inputs missing". No floor is typed in a screen.
 * Values come from GET /api/v1/decision-tests (the reference data registry).
 */
import { useQuery } from '@tanstack/react-query'
import { getAuthHeader } from '@/lib/authToken'

export interface PolicyValue {
  value: number | null; status: string | null; policy_party: string; effective_date: string | null
  source?: string | null; policy_reference?: string | null; context?: Record<string, unknown> | null
}
export interface DecisionTest {
  label: string; metric: string; policy_key: string; comparator: '>=' | '<='
  capital_decisions: string[]; approved: PolicyValue | null; proposed: PolicyValue[]
}
export type TestId = 'DSCR_P50' | 'DSCR_P90' | 'DSCR_DEFAULT' | 'DSCR_COVENANT' | 'WACC' | 'OFFTAKE_COVERAGE' | 'DFI_IRR' | 'DFI_CATALYTIC' | 'REGULATORY_PREMIUM'
export type Outcome = 'PASS' | 'FAIL' | 'NO_APPROVED_THRESHOLD' | 'NOT_ASSESSABLE'

export const MESSAGES: Record<Outcome, string> = {
  PASS: 'meets the approved threshold',
  FAIL: 'does not meet the approved threshold',
  NO_APPROVED_THRESHOLD: 'no approved threshold — no pass/fail',
  NOT_ASSESSABLE: 'not assessable — required inputs missing',
}

export function useDecisionTests() {
  return useQuery<{ tests: Record<TestId, DecisionTest> }>({
    queryKey: ['decision-tests'],
    staleTime: 60_000,
    queryFn: async () => {
      const res = await fetch('/api/v1/decision-tests', { headers: getAuthHeader() })
      if (!res.ok) throw Object.assign(new Error(`The policy registry answered ${res.status}.`), { status: res.status })
      return res.json()
    },
  })
}

/** The approved threshold, or null. A proposed value never judges. */
export function approvedThreshold(test: DecisionTest | undefined): number | null {
  const v = test?.approved?.value
  return typeof v === 'number' ? v : null
}

export function judge(value: number | null | undefined, test: DecisionTest | undefined): Outcome {
  if (value == null || Number.isNaN(value)) return 'NOT_ASSESSABLE'
  const t = approvedThreshold(test)
  if (t == null) return 'NO_APPROVED_THRESHOLD'
  return (test!.comparator === '>=' ? value >= t : value <= t) ? 'PASS' : 'FAIL'
}

/** Text tone for an outcome: green and red only for a real judgement. */
export function outcomeTone(o: Outcome): string {
  return o === 'PASS' ? 'text-green-700' : o === 'FAIL' ? 'text-red-700' : 'text-slate-700'
}

/** One line naming the policy: whose, which status, effective when; or why there is none. */
export function policyLine(test: DecisionTest | undefined, unit = 'x'): string {
  if (!test) return 'Policy registry not read — no pass/fail'
  const a = test.approved
  if (a && a.value != null) {
    return `${test.comparator} ${a.value}${unit} — ${a.policy_party}, ${a.status}${a.effective_date ? `, effective ${a.effective_date}` : ''}`
  }
  const p = test.proposed?.[0]
  return `${MESSAGES.NO_APPROVED_THRESHOLD}${p?.value != null ? ` (${p.status} ${test.comparator} ${p.value}${unit}, not in force)` : ''}`
}
