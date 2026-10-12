/**
 * T5 — source guard for the gate screens (docs/master-reconciliation/06).
 *
 * These four screens tell the gate engine's story. They must not read the
 * customerProjects.ts `bankability` block (hand-written gates, completion and
 * capital), invent figures with Math.random, or show developer messages.
 * Matched on the source text, comments included: a comment that quotes a
 * forbidden pattern is rewritten rather than exempted.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SCREENS = [
  'features/projects/ProjectsPage.tsx',
  'features/finance/BankabilityScorePage.tsx',
  'features/finance/FinanceBankabilityView.tsx',
  'features/finance/StageGatesPage.tsx',
]

const FORBIDDEN: Array<[string, RegExp]> = [
  ['a read of the fixture bankability block', /\.bankability\b/],
  ['a random number', /Math\.random/],
  ['the "proxy mode" developer message', /proxy mode/i],
  ['a port number in client text', /port 8001/i],
]

describe('gate screens source guard', () => {
  it('each pattern catches what it names (negative check)', () => {
    expect(FORBIDDEN[0][1].test('project.bankability.gates')).toBe(true)
    expect(FORBIDDEN[0][1].test('canonicalProject?.bankability?.gates')).toBe(true)
    expect(FORBIDDEN[0][1].test('bankabilityAPI.readout(id)')).toBe(false)
    expect(FORBIDDEN[0][1].test("fetch('/api/v1/bankability/rules')")).toBe(false)
    expect(FORBIDDEN[1][1].test('0.3 + Math.random() * 0.1')).toBe(true)
    expect(FORBIDDEN[2][1].test('⚠ proxy mode (start backend)')).toBe(true)
    expect(FORBIDDEN[3][1].test('engine (port 8001) is reachable')).toBe(true)
  })

  for (const file of SCREENS) {
    it(`${file} carries none of the forbidden patterns`, () => {
      const src = readFileSync(resolve(__dirname, '..', file), 'utf8')
      const found = FORBIDDEN.filter(([, re]) => re.test(src)).map(([what]) => what)
      expect(found, `${file}: ${found.join('; ')}`).toEqual([])
    })
  }
})
