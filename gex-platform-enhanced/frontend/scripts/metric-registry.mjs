// Metric registry (handoff v4, task 6): ONE JSON generated from docs/metrics/<id>.md.
// Each spec carries a front-matter block (id, name, unit, computed_in, probe) and
// the sections: Definition, Formula, Inputs, Timing, Valuation boundary, Access,
// Decision test, Limitations, Where computed. audit-menu.mjs reads the result.
import { readFileSync, readdirSync, existsSync } from 'node:fs'

export const METRICS_DIR = new URL('../../docs/metrics/', import.meta.url)
export const REGISTRY_URL = new URL('registry.json', METRICS_DIR)
const FILES_ROOT = new URL('../../../', import.meta.url)   // files/: both repos live under it
const SECTIONS = { definition: 'Definition', formula: 'Formula', inputs: 'Inputs, units and sources', timing: 'Timing',
  valuation_boundary: 'Valuation boundary', access: 'Access', decision_test: 'Decision test and policy source',
  limitations: 'Limitations' }

export function parseSpec(text, file) {
  const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(text)
  if (!m) throw new Error(`${file}: no front matter`)
  const front = Object.fromEntries(m[1].split('\n').map(l => { const i = l.indexOf(':'); return [l.slice(0, i).trim(), l.slice(i + 1).trim()] }))
  const out = { ...front, spec: `docs/metrics/${file}` }
  for (const [key, label] of Object.entries(SECTIONS)) {
    const s = new RegExp(`\\*\\*${label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.\\*\\* ([^\\n]+)`).exec(m[2])
    if (!s) throw new Error(`${file}: missing section "${label}"`)
    out[key] = s[1].trim()
  }
  return out
}

export function buildRegistry() {
  const files = readdirSync(METRICS_DIR).filter(f => f.endsWith('.md')).sort()
  const metrics = files.map(f => parseSpec(readFileSync(new URL(f, METRICS_DIR), 'utf8'), f))
  return { generated_from: 'docs/metrics/*.md', generator: 'frontend/scripts/metric-registry.mjs', metrics }
}

/** Problems: a spec whose computation is not where it says. */
export function verifyComputedIn(registry) {
  const problems = []
  for (const m of registry.metrics) {
    const url = new URL(m.computed_in, FILES_ROOT)
    if (!existsSync(url)) { problems.push(`${m.id}: ${m.computed_in} not found`); continue }
    if (!readFileSync(url, 'utf8').includes(m.probe)) problems.push(`${m.id}: "${m.probe}" not in ${m.computed_in}`)
  }
  return problems
}
