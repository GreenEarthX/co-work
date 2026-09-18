// Engine ↔ frontend parity for the tenor label rule (2026-09-14).
//
// The rule exists twice: tenor_label() in the sibling PF engine
// (gex_pf_engine/backend/pf_engine/core/gabillon.py) labels every curve it
// serves; tenorLabel() here labels fallback/seed curves AND decides whether a
// stored published curve is stale. If the two drift, stored curves are purged
// or kept for the wrong reason. This runs the REAL engine function under the
// engine's own interpreter and compares every tenor from 0 to 600 months.
//
// Skips, does not fail, where the sibling checkout or its venv is absent
// (e.g. the docker build staging copy).

import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it, expect } from 'vitest'
import { tenorLabel } from './tenorLabel'

// src/features/pricing → files/
const SIBLING = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../gex_pf_engine')
const PYTHON = resolve(SIBLING, 'micro_service/bin/python')
const ENGINE_BACKEND = resolve(SIBLING, 'backend')
const MAX_MONTHS = 600

function engineLabels(): string[] {
  const out = execFileSync(PYTHON, [
    '-c',
    'import json; from pf_engine.core.gabillon import tenor_label; '
      + `print(json.dumps([tenor_label(m) for m in range(${MAX_MONTHS + 1})]))`,
  ], { cwd: ENGINE_BACKEND, encoding: 'utf8', timeout: 30_000 })
  return JSON.parse(out.trim().split('\n').pop()!)
}

describe.skipIf(!existsSync(PYTHON))('tenorLabel ↔ engine tenor_label()', () => {
  it('agree for every tenor 0–600 months', () => {
    const engine = engineLabels()
    expect(engine).toHaveLength(MAX_MONTHS + 1)

    const mismatches = engine
      .map((label, months) => ({ months, engine: label, frontend: tenorLabel(months) }))
      .filter(r => r.engine !== r.frontend)
    expect(mismatches).toEqual([])
  }, 30_000)
})
