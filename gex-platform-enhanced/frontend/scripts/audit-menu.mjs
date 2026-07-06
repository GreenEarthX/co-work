// One-shot menu visibility audit. Reads the REAL menuArchitecture.ts (extracts
// the MENU_TABS / CISO_ITEMS array literals and evaluates them with the actual
// visibility constructors) so it cannot drift from source.
//
//   node scripts/audit-menu.mjs
//
// Emits: per-role route lists + counts, and a duplicate-route-per-role check.

import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'

const CHECK = process.argv.includes('--check')  // CI mode: verify docs §9 is current, never write
const src = readFileSync(new URL('../src/config/menuArchitecture.ts', import.meta.url), 'utf8')

function extractArray(name) {
  const start = src.indexOf(`export const ${name}`)
  const eq = src.indexOf('=', start)          // skip the `: MenuTab[]` type annotation
  const open = src.indexOf('[', eq)
  let depth = 0, i = open
  for (; i < src.length; i++) {
    if (src[i] === '[') depth++
    else if (src[i] === ']') { depth--; if (depth === 0) { i++; break } }
  }
  return src.slice(open, i)
}

// Visibility constructors — must mirror menuArchitecture.ts exactly.
const ALL = { company_type: 'ALL', function: 'ALL' }
const PROD = (fn) => ({ company_type: 'PRODUCER', function: fn || 'ALL' })
const OFT = (fn) => ({ company_type: 'OFFTAKER', function: fn || 'ALL' })
const TP = (svc, fn) => ({ company_type: 'THIRD_PARTY', service_type: svc, function: fn || 'ALL' })

const MENU_TABS = eval(extractArray('MENU_TABS'))
const CISO_ITEMS = eval(extractArray('CISO_ITEMS'))

// Resolution logic — mirrors isVisible() + effectiveCompanyTypes().
const CAP_TO_CT = { OFFTAKE: 'OFFTAKER', PRODUCE: 'PRODUCER', SELL: null, TRADE: null, CERTIFY: 'THIRD_PARTY', FINANCE: 'THIRD_PARTY', INSURE: 'THIRD_PARTY' }
function effectiveCompanyTypes(role) {
  const t = new Set([role.company_type])
  for (const c of role.capabilities || []) { const ct = CAP_TO_CT[c]; if (ct) t.add(ct) }
  return [...t]
}
function matchesRule(rules, role) {
  const cts = effectiveCompanyTypes(role)
  return (rules || []).some(r => {
    const ct = r.company_type === 'ALL' || cts.includes(r.company_type)
    const fn = !r.function || r.function === 'ALL' || r.function === role.business_function
    const st = !r.service_type || r.service_type === 'ALL' ||
      (role.company_type === 'THIRD_PARTY' && r.service_type === role.service_type)
    const cap = !r.capability || (role.capabilities || []).includes(r.capability) // MUST mirror app
    return ct && fn && st && cap
  })
}
const isVisible = (item, role) => matchesRule(item.visible_to, role)               // ACCESS
const isConsultOnly = (item, role) => !!item.consult_for && matchesRule(item.consult_for, role)
const isVisibleInNav = (item, role) => isVisible(item, role) && !isConsultOnly(item, role) // PROMINENCE

const allItems = MENU_TABS.flatMap(t => t.items.map(i => ({ ...i, tab: t.label })))

// Producer/Offtaker have multiple business functions; audit each as the org-union
// across its functions (a single user sees a function-scoped subset).
const PROD_FNS = ['ENGINEERING', 'OPERATIONS', 'COMMERCIAL', 'FINANCE_TREASURY', 'COMPLIANCE_LEGAL', 'EXECUTIVE']
const OFT_FNS = ['COMMERCIAL', 'FINANCE_TREASURY', 'OPERATIONS', 'COMPLIANCE_LEGAL', 'EXECUTIVE']

function visibleFor(roles) {
  // union over a list of role objects
  const seen = new Map() // path -> Set(labels)
  for (const it of allItems) {
    if (roles.some(r => isVisible(it, r))) {
      if (!seen.has(it.path)) seen.set(it.path, new Set())
      seen.get(it.path).add(`${it.label} [${it.tab}]`)
    }
  }
  return seen
}

const PERSONAS = {
  'Producer (org union)': PROD_FNS.map(fn => ({ company_type: 'PRODUCER', business_function: fn })),
  'Offtaker (org union)': OFT_FNS.map(fn => ({ company_type: 'OFFTAKER', business_function: fn })),
  'Bank':       [{ company_type: 'THIRD_PARTY', service_type: 'BANK' }],
  'Insurer':    [{ company_type: 'THIRD_PARTY', service_type: 'INSURER' }],
  'Certifier':  [{ company_type: 'THIRD_PARTY', service_type: 'CERTIFIER' }],
  'Engineer':   [{ company_type: 'THIRD_PARTY', service_type: 'ENGINEER' }],
  'Legal':      [{ company_type: 'THIRD_PARTY', service_type: 'LEGAL' }],
  'Logistics':  [{ company_type: 'THIRD_PARTY', service_type: 'LOGISTICS' }],
}

let totalDupes = 0
console.log('═══ ROLE → ROUTE VISIBILITY AUDIT (main 5 tabs) ═══\n')
for (const [name, roles] of Object.entries(PERSONAS)) {
  const seen = visibleFor(roles)
  const routes = [...seen.keys()].sort()
  console.log(`### ${name} — ${routes.length} routes, ${[...seen.values()].reduce((a, s) => a + s.size, 0)} entries`)
  for (const [path, labels] of [...seen.entries()].sort()) {
    const dup = labels.size > 1
    if (dup) totalDupes++
    console.log(`   ${dup ? '⚠ DUP' : '     '} ${path}  ${[...labels].join('  |  ')}`)
  }
  console.log('')
}

console.log('═══ DUPLICATE-ROUTE-PER-ROLE CHECK ═══')
console.log(totalDupes === 0
  ? '✅ PASS — no role sees the same route under two different names in the main tabs.'
  : `❌ FAIL — ${totalDupes} role/route pairs expose one route under multiple labels.`)

// Global: any route reachable from >1 distinct label anywhere in main tabs?
const globalPath = new Map()
for (const it of allItems) {
  if (!globalPath.has(it.path)) globalPath.set(it.path, new Set())
  globalPath.get(it.path).add(it.label)
}
const globalDupes = [...globalPath.entries()].filter(([, s]) => s.size > 1)
console.log('\n═══ GLOBAL ROUTE→LABEL COLLISIONS (main tabs, role-agnostic) ═══')
console.log(globalDupes.length === 0
  ? '✅ PASS — every route has exactly one label across all main tabs.'
  : globalDupes.map(([p, s]) => `⚠ ${p}: ${[...s].join(' | ')}`).join('\n'))

console.log(`\nCISO admin surface: ${CISO_ITEMS.length} items (separate password-gated surface).`)

// ── Per-USER personas — ACCESS vs NAV PROMINENCE (two-layer model) ──
console.log('\n═══ PER-USER LOAD — ACCESS vs TOP-NAV (consult demoted to project profile) ═══')
console.log('   NAV  ACCESS  Δ   PERSONA')
const userPersonas = [
  ['Producer / ENGINEERING',     { company_type: 'PRODUCER', business_function: 'ENGINEERING' }],
  ['Producer / OPERATIONS',      { company_type: 'PRODUCER', business_function: 'OPERATIONS' }],
  ['Producer / COMMERCIAL',      { company_type: 'PRODUCER', business_function: 'COMMERCIAL' }],
  ['Producer / FINANCE_TREASURY',{ company_type: 'PRODUCER', business_function: 'FINANCE_TREASURY' }],
  ['Producer / COMPLIANCE_LEGAL',{ company_type: 'PRODUCER', business_function: 'COMPLIANCE_LEGAL' }],
  ['Producer / EXECUTIVE',       { company_type: 'PRODUCER', business_function: 'EXECUTIVE' }],
  ['Offtaker / COMMERCIAL',      { company_type: 'OFFTAKER', business_function: 'COMMERCIAL' }],
  ['Offtaker / FINANCE_TREASURY',{ company_type: 'OFFTAKER', business_function: 'FINANCE_TREASURY' }],
  ['Bank',                       { company_type: 'THIRD_PARTY', service_type: 'BANK' }],
  ['Insurer',                    { company_type: 'THIRD_PARTY', service_type: 'INSURER' }],
  ['DFI / public investor',      { company_type: 'THIRD_PARTY', service_type: 'DFI' }],
  ['Engineer',                   { company_type: 'THIRD_PARTY', service_type: 'ENGINEER' }],
  ['Engineer + FINANCE_REVIEW',  { company_type: 'THIRD_PARTY', service_type: 'ENGINEER', capabilities: ['FINANCE_REVIEW'] }],
]
for (const [name, role] of userPersonas) {
  const access = allItems.filter(it => isVisible(it, role)).length
  const nav = allItems.filter(it => isVisibleInNav(it, role)).length
  const delta = nav - access
  console.log(`   ${String(nav).padStart(3)}  ${String(access).padStart(6)}  ${String(delta).padStart(3)}  ${name}`)
}

// ── Access-preservation guarantee: every consult-demoted item is still ACCESSIBLE ──
console.log('\n═══ ACCESS PRESERVATION (consult demotion must not remove access) ═══')
let leak = 0
for (const [name, role] of userPersonas) {
  for (const it of allItems) {
    if (isConsultOnly(it, role) && !isVisible(it, role)) {
      leak++; console.log(`   ❌ ${name}: ${it.path} consult-only but NOT accessible`)
    }
  }
}
console.log(leak === 0
  ? '✅ PASS — every consult-demoted screen remains accessible (reachable via Project profile).'
  : `❌ FAIL — ${leak} screens demoted out of nav AND out of access.`)

// ── PERSONA-MINIMUM GUARANTEE ────────────────────────────────────────────────
// Each role's SIGNATURE tasks — the screens that define its job. The audit FAILS
// LOUDLY if any future visibility change ever strips one. This turns "a user
// always has access to its role-specific tasks" from a promise into an invariant.
// Routes are matched by path (stable). Edit this list when a role's mandate
// genuinely changes — never to paper over an accidental removal.
const SIGNATURE = [
  ['Producer / Engineering',     { company_type: 'PRODUCER', business_function: 'ENGINEERING' },
    ['/finance-plant-builder', '/producer-bankability', '/plant-data']],
  ['Producer / Operations',      { company_type: 'PRODUCER', business_function: 'OPERATIONS' },
    ['/plant-data', '/producer-bankability', '/capacity', '/ciso-gateways']],
  ['Producer / Commercial',      { company_type: 'PRODUCER', business_function: 'COMMERCIAL' },
    ['/marketplace', '/matching', '/contracts', '/offtake-quality', '/finance-demand']],
  ['Producer / Compliance-Legal',{ company_type: 'PRODUCER', business_function: 'COMPLIANCE_LEGAL' },
    ['/cert-readiness', '/stage-gates', '/regulator-dashboard', '/data-room']],
  ['Producer / Finance-Treasury',{ company_type: 'PRODUCER', business_function: 'FINANCE_TREASURY' },
    ['/finance/bankability', '/capital-stack', '/covenants', '/ic-pack']],
  ['Producer / Executive',       { company_type: 'PRODUCER', business_function: 'EXECUTIVE' },
    ['/finance/bankability', '/cfo-report']],
  ['Offtaker / Commercial',      { company_type: 'OFFTAKER', business_function: 'COMMERCIAL' },
    ['/marketplace', '/offtaker-supply', '/matching', '/contracts', '/offtake-quality']],
  ['Bank',     { company_type: 'THIRD_PARTY', service_type: 'BANK' },
    ['/finance/bankability', '/capital-stack', '/covenants', '/ic-pack', '/data-room']],
  ['Insurer',  { company_type: 'THIRD_PARTY', service_type: 'INSURER' },
    ['/insurance-schedule', '/insurance-coverage', '/insurance-assets']],
  ['Certifier',{ company_type: 'THIRD_PARTY', service_type: 'CERTIFIER' },
    ['/cert-readiness', '/stage-gates']],
  ['Engineer', { company_type: 'THIRD_PARTY', service_type: 'ENGINEER' },
    ['/finance-plant-builder', '/producer-bankability', '/plant-data']],
  ['Legal',    { company_type: 'THIRD_PARTY', service_type: 'LEGAL' },
    ['/contracts', '/regulator-dashboard', '/data-room']],
  ['Logistics',{ company_type: 'THIRD_PARTY', service_type: 'LOGISTICS' },
    ['/capacity']],
]

console.log('\n═══ PERSONA-MINIMUM GUARANTEE (role keeps its signature tasks) ═══')
let sigFail = 0
for (const [name, role, must] of SIGNATURE) {
  const missing = must.filter(p => {
    const it = allItems.find(i => i.path === p)
    return !it || !isVisible(it, role)
  })
  if (missing.length) {
    sigFail += missing.length
    console.log(`   ❌ ${name} — MISSING role-specific: ${missing.join(', ')}`)
  } else {
    console.log(`   ✅ ${name} — all ${must.length} signature tasks retained`)
  }
}
console.log(sigFail === 0
  ? '✅ PASS — every role retains all of its signature tasks.'
  : `❌ FAIL — ${sigFail} role-specific task(s) stripped. Fix visible_to before shipping.`)

// ═══════════════════════════════════════════════════════════════════════════
// COHERENCE LINT (advisory) — a door must name what is behind it (Hidalgo),
// and a "trading" workspace must be honest about which CTRM functions exist.
// These are QUALITY signals, not access regressions, so they report but do not
// fail the build (the access checks above remain the hard gate).
// ═══════════════════════════════════════════════════════════════════════════

const STOP = new Set(['the','and','of','a','for','to','&','page','screen','view','my','your'])
const toks = (s) => [...new Set((s || '').toLowerCase().match(/[a-z0-9]+/g) || [])].filter(t => !STOP.has(t) && t.length > 1)
const overlap = (a, b) => a.some(t => b.includes(t))
const lastSeg = (p) => (p || '').split('?')[0].replace(/\/$/, '').split('/').filter(Boolean).pop() || ''

// path → component name, from App.tsx <Route> elements.
const appSrc = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
const pathToComp = {}
for (const m of appSrc.matchAll(/path="([^"]+)"[^>]*element=\{(?:<GatedRoute[^>]*>|<FinanceRouteGuard[^>]*>)?\s*<([A-Za-z0-9_]+)/g)) {
  pathToComp['/' + m[1].replace(/^\//, '')] = m[2]
}
// component → source file, from import lines.
const compToFile = {}
for (const m of appSrc.matchAll(/import\s*\{?\s*([A-Za-z0-9_]+)\s*\}?\s*from\s*'(@\/[^']+)'/g)) {
  compToFile[m[1]] = m[2]
}
const SRC = new URL('../src/', import.meta.url)
function screenTokens(path) {
  const comp = pathToComp[path]
  if (!comp) return { comp: null, tokens: [] }
  let header = comp
  const rel = compToFile[comp]
  if (rel) {
    try {
      const f = readFileSync(new URL(rel.replace('@/', '') + '.tsx', SRC), 'utf8')
      // Header = leading // comments + first JSDoc title line.
      const head = f.split('\n').slice(0, 14)
      header += ' ' + head.filter(l => /^\s*(\/\/|\*)/.test(l)).join(' ')
    } catch { /* placeholder/missing — component name only */ }
  }
  return { comp, tokens: toks(header) }
}

const mainItems = MENU_TABS.flatMap(t => t.items.map(i => ({ ...i, tab: t.label })))
const drift = [], mislabel = []
for (const it of mainItems) {
  const L = toks(it.label), P = toks(lastSeg(it.path)), I = toks(it.id)
  // Name-drift: the URL the user reaches shares no word with the door label.
  if (P.length && L.length && !overlap(L, P))
    drift.push(`${it.tab} · "${it.label}"  ⇄  ${it.path}  (id '${it.id}')`)
  // Label↔screen: the door label shares no word with the screen it opens.
  const { comp, tokens } = screenTokens(it.path)
  if (comp && tokens.length && L.length && !overlap(L, tokens))
    mislabel.push(`${it.tab} · "${it.label}"  →  ${it.path}  (${comp})`)
}

console.log('\n═══ DOOR↔SCREEN COHERENCE (Hidalgo: one thing, one name) ═══')
console.log(mislabel.length === 0
  ? '✅ every door label shares vocabulary with the screen it opens.'
  : `⚠ ${mislabel.length} door(s) open a screen that names a different function:`)
for (const m of mislabel) console.log('   ⚠ ' + m)
console.log(`\n   route-name drift (URL ≠ label — advisory, URL rename deferred): ${drift.length}`)
for (const d of drift) console.log('   · ' + d)

// ── CTRM completeness manifest ─────────────────────────────────────────────
// A function "exists" if a SCREEN names it — its filename, its `// Screen:`
// identity line, or a menu label. We deliberately do NOT match arbitrary body
// text: a "P&L MTD" KPI label or a "counterparty exposure" sentence inside an
// offtake screen is not a position/credit MODULE. A false ✅ would hide the
// very gap this manifest exists to surface.
function identitySurface() {
  let id = mainItems.map(i => i.label).join('\n')
  const walk = (url) => {
    for (const name of readdirSync(url)) {
      const child = new URL(name + (statSync(new URL(name, url)).isDirectory() ? '/' : ''), url)
      if (statSync(child).isDirectory()) walk(child)
      else if (name.endsWith('.tsx') || name.endsWith('.ts')) {
        id += '\n' + name
        const first = readFileSync(child, 'utf8').split('\n').slice(0, 3).find(l => /\/\/\s*Screen:/i.test(l))
        if (first) id += '\n' + first
      }
    }
  }
  try { walk(new URL('features/', SRC)) } catch { /* noop */ }
  return id
}
const FEAT = identitySurface()
// PROPOSED disposition (point 5) — strategic posture: GEX is an offtake/
// bankability OS for developers & prosumers, NOT a merchant trading desk, so
// the risk-book half is mostly "integrate with an external CTRM", not "build".
// EDIT THIS MAP to change the product posture; §9 regenerates from it.
//   v1       = required for a credible CTRM-lite v1
//   later    = optional, post-v1
//   integrate= not intended for GEX; consume from an external CTRM
const CTRM = [
  ['Deal capture / blotter',         /blotter|deal.?ticket|trade.?capture/i,                       'later'],
  ['Position book / net exposure',   /net.?position|position.?book|net.?exposure|long.*short.*position/i, 'integrate'],
  ['Mark-to-market / P&L',           /mark.?to.?market|\bmtm\b|\bp&l\b|\bpnl\b/i,                  'integrate'],
  ['Credit risk / exposure limits',  /credit.?limit|credit.?exposure|counterparty.?exposure|exposure.?limit/i, 'v1'],
  ['Risk limits / VaR (commercial)', /value.?at.?risk|\bvar\b.{0,12}limit|trading.?limit/i,        'integrate'],
  ['Trade confirmations',            /trade.?confirmation|deal.?confirmation|confirmation.?workflow/i, 'later'],
]
const DISPO = { v1: 'Required for CTRM-lite v1', later: 'Optional (post-v1)', integrate: 'Not intended — integrate external CTRM' }
const ctrmRows = CTRM.map(([fn, re, d]) => ({ fn, present: re.test(FEAT), dispo: d }))
const ctrmGaps = ctrmRows.filter(r => !r.present).length

console.log('\n═══ DOOR↔SCREEN COHERENCE & CTRM (advisory) ═══')
console.log(mislabel.length === 0 ? '✅ door↔screen coherent' : `⚠ ${mislabel.length} door↔screen mismatch · ${drift.length} route-name drift`)
console.log(`   CTRM: ${ctrmGaps}/${CTRM.length} risk/position functions absent (see docs §9)`)

// ── Generate docs §9 (zero-drift; the doc never hand-tracks these findings) ──
const mapURL = new URL('../../docs/menu-architecture-map.md', import.meta.url)
const START = '<!-- §9:AUTO:START -->', END = '<!-- §9:AUTO:END -->'

function section9() {
  const COMM = mainItems.filter(i => i.tab === 'Commercial')
  const klass = (it) => {
    const { tokens } = screenTokens(it.path)
    const L = toks(it.label)
    return (tokens.length && L.length && !overlap(L, tokens)) ? 'warn' : 'ok'
  }
  const nodes = COMM.map((it, n) => `  COM --> D${n}["${it.label} → ${it.path}"]:::${klass(it)}`).join('\n')
  const gaps = ctrmRows.filter(r => !r.present)
    .map((r, n) => `  COM -.->|${DISPO[r.dispo]}| GP${n}[[${r.fn} — ABSENT]]:::gap`).join('\n')
  const mislabelLines = mislabel.length
    ? mislabel.map(m => `- ⚠ ${m}`).join('\n')
    : '- ✅ every door opens a screen that shares its name.'
  const ctrmLines = ctrmRows.map(r =>
    `| ${r.fn} | ${r.present ? '✅ present' : '⛔ absent'} | ${DISPO[r.dispo]} |`).join('\n')

  return `${START}
## 9 · Door↔screen coherence & CTRM completeness  *(GENERATED by \`audit-menu.mjs\` — do not hand-edit)*

> Regenerate: \`npm run audit:menu\`. Build runs \`--check\` and fails if this
> block is stale. §1–§8 verify **access**; §9 verifies **honesty** — does a
> door open the screen it names (Hidalgo), and is "Commercial" honest about
> which CTRM functions exist? Advisory (does not gate access), but it answers
> the buy-side / CTRM diligence question the access audit cannot.

### Commercial workspace (${COMM.length} doors)

\`\`\`mermaid
flowchart TD
  COM[Commercial · ${COMM.length} doors]
${nodes}
${gaps}
  classDef ok stroke:#10b981,stroke-width:1.5px;
  classDef warn stroke:#f59e0b,stroke-width:2px,stroke-dasharray:4 3;
  classDef gap stroke:#64748b,stroke-width:1.5px,stroke-dasharray:2 3,color:#64748b;
\`\`\`

### Door↔screen coherence — ${mislabel.length} mismatch(es), ${drift.length} route-name drift

${mislabelLines}

- **Fixed:** the "Counterparties" door previously opened a screen inconsistent
  with its label (the screen is *Delivery & Settlement*; no counterparty/credit
  module exists). Now corrected — the door is **Delivery & Settlement**, and
  counterparty/credit is tracked below as a CTRM gap rather than implied by a door.
- **Route-name drift (${drift.length}):** URL ≠ label on legacy paths. Deferred —
  URL renames break deep links; do via a canonical-route alias registry (ticket).

### CTRM completeness — what GEX Commercial *is*

Present: **origination → matching → RFQ → contracts → term-sheet →
offtake-quality → settlement → capacity**. The risk-book half is **${ctrmGaps}/${CTRM.length} absent**.
Disposition reflects the posture *GEX is an offtake/bankability OS, not a
merchant trading desk* — edit \`CTRM\` in \`audit-menu.mjs\` to change it.

| CTRM function | Status | Disposition |
|---|---|---|
${ctrmLines}

GEX Commercial is a credible **deal desk**; it is **not a CTRM** until the
\`v1\`-dispositioned functions exist. Trading-desk vocabulary (e.g. the former
"Trader Dashboard" with fabricated position/P&L tiles) was removed so the menu,
docs, and investor narrative state this precisely.
${END}`
}

let section9Stale = false
try {
  const doc = readFileSync(mapURL, 'utf8')
  const block = section9()
  const re = new RegExp(`${START}[\\s\\S]*?${END}`)
  let next
  if (re.test(doc)) next = doc.replace(re, block)
  else next = doc.replace(/\n\*Reproduce the audit any time:/, `\n${block}\n\n*Reproduce the audit any time:`)
  if (next !== doc) {
    if (CHECK) { section9Stale = true; console.log('   ❌ docs §9 is STALE — run `npm run audit:menu` to regenerate.') }
    else { writeFileSync(mapURL, next); console.log('   📝 wrote docs §9 (menu-architecture-map.md).') }
  } else {
    console.log('   ✅ docs §9 current.')
  }
} catch (e) { console.log('   ⚠ could not update docs §9:', e.message) }

// ═══════════════════════════════════════════════════════════════════════════
// §10 · PROJECT-FINANCE COMPLETENESS (advisory) — the Finance analog of §9's
// CTRM manifest. Finance is GEX's strongest workspace (0 stubs, 0 mislabels)
// but it is UNDER-HARVESTED: the engine computes debt mechanics the UI never
// shows. Each function is classified ui-visible / engine-only / absent — the
// "engine-only" rows are value left on the floor. A surfaced metric is only
// lender-grade if it carries model-governance provenance (SEED vs MARKET);
// "governed?" tracks that — a naked DSCR/LLCR tile is the Finance version of
// the fabricated "P&L MTD" we removed from Commercial.
// ═══════════════════════════════════════════════════════════════════════════

// Best-effort read of the COMPUTE surface: the sibling PF engine AND the
// platform's pre-COD intelligence engine. (v1.0 of this probe missed
// pre_cod_metrics.py — which computes LLCR + Sources & Uses — and wrongly
// reported both "absent". Coverage ratios for a pre-COD greenfield project
// live in the platform pre-COD engine, not gex_pf_engine core.)
let ENGINE = '', engineReadable = false
try {
  const eb = new URL('../../../gex_pf_engine/backend/app/', import.meta.url)
  for (const rel of ['core/waterfall.py', 'core/cfads.py', 'core/debt/sculpting.py', 'core/debt/tranche.py', 'api/routes_model.py']) {
    try { ENGINE += '\n' + readFileSync(new URL(rel, eb), 'utf8') } catch { /* file absent */ }
  }
  // Platform pre-COD engine (LLCR, SUC/Sources & Uses, CEC, FRI, RMR, CBM).
  try { ENGINE += '\n' + readFileSync(new URL('../../backend/app/api/v1/pre_cod_metrics.py', import.meta.url), 'utf8') } catch { /* absent */ }
  engineReadable = ENGINE.length > 0
} catch { /* repos not present */ }

const PFDISPO = {
  surface: 'v1 — surface existing engine output (UI wiring; MUST carry governance stamp)',
  engine:  'v1 — compute in engine (CFADS + debt service available), then surface',
  build:   'v1 — build (no engine primitive yet)',
  later:   'Optional (post-v1)',
  have:    'present',
}
// [name, UI-identity probe, engine COMPUTATION probe, disposition]
// engine probe targets real computation, not incidental mentions (e.g. LLCR
// must be a coverage calc, not the `llcr_lock_up` threshold default).
const PF = [
  ['CFADS (cash available for debt service)', /cfads/i,                       /cfads/i,                                   'surface'],
  ['Cash-flow waterfall',                     /waterfall/i,                   /class\s+\w*[Ww]aterfall|def\s+\w*waterfall|waterfall\/execute/i, 'surface'],
  ['DSRA (debt service reserve)',             /dsra|debt.?service.?reserve/i, /dsra/i,                                    'surface'],
  ['Cash sweep / lock-up',                    /cash.?sweep/i,                 /class\s+CashSweep|cash.?sweep/i,            'surface'],
  ['Debt sculpting / repayment profile',      /sculpt|repayment.?profile/i,   /sculpt/i,                                  'surface'],
  ['DSCR (min / average)',                    /dscr/i,                        /dscr/i,                                    'have'],
  ['LLCR (loan-life coverage)',               /llcr/i,                        /loan.?life.?coverage|def\s+\w*llcr|llcr\s*=\s*npv/i, 'engine'],
  ['PLCR (project-life coverage)',            /plcr/i,                        /project.?life.?coverage|def\s+\w*plcr|plcr\s*=\s*npv/i, 'engine'],
  // SUC ratio ≠ S&U statement. The COVERAGE RATIO exists (pre-COD engine);
  // the ITEMIZED STATEMENT (EPC/IDC/contingency … equity/senior/DFI rows) does not.
  ['Sources & Uses coverage (SUC ratio)',     /suc|sources.{0,4}uses.{0,16}coverage/i, /def _compute_suc|class SUCInput|sources.{0,4}uses.{0,16}coverage/i, 'have'],
  ['Sources & Uses statement (itemized)',     /sources.{0,4}and.{0,4}uses.?statement|itemi[sz]ed.{0,10}sources/i, /total_uses|total_sources|sources_uses_line/i, 'build'],
  ['Covenant package',                        /covenant/i,                    /covenant/i,                                'have'],
  ['Hedging (rate / FX / power)',             /hedg/i,                        /hedg/i,                                    'later'],
  ['Refinancing / mini-perm',                 /refinanc|mini.?perm/i,         /refinanc|mini.?perm/i,                     'later'],
]
// UI-surfacing is probed only over the FINANCE METRIC SURFACE — files that
// actually CONSUME PF engine output (call /finance-model/, or are the canonical
// metric screens). This excludes incidental mentions (a passing "hedge" comment
// in an unrelated file is not a surfaced metric — the CTRM false-positive
// lesson). Gated on engine-computation FIRST: a function the engine does NOT
// compute is `absent` regardless of on-screen text, so an honest "LLCR — NOT
// COMPUTED" gap card never falsely flips LLCR to ui-visible.
const METRIC_SCREENS = /DSCRHeatmap|CovenantsPage|DebtCashflowWaterfall|FinanceBankabilityView/
// A screen is GOVERNED if it carries an assumption/governance stamp (basis,
// reliance, rules_version). A ui-visible metric on an ungoverned screen is a
// naked forward number — WARN (not fail; flip to fail once the scaffold lands).
const GOV_MARKER = /governance|ILLUSTRATIVE|PreCODGovernanceBanner|not credit-approved|data_basis|reliance/i
function financeSurface() {
  let blob = '', governed = ''
  const walk = (url) => {
    for (const name of readdirSync(url)) {
      const child = new URL(name + (statSync(new URL(name, url)).isDirectory() ? '/' : ''), url)
      if (statSync(child).isDirectory()) walk(child)
      else if (name.endsWith('.tsx') || name.endsWith('.ts')) {
        const body = readFileSync(child, 'utf8')
        if (body.includes('/finance-model/') || METRIC_SCREENS.test(name)) {
          blob += '\n' + body
          if (GOV_MARKER.test(body)) governed += '\n' + body
        }
      }
    }
  }
  try { walk(new URL('features/', SRC)) } catch { /* noop */ }
  return { blob, governed }
}
const { blob: FIN_SURFACE, governed: GOV_SURFACE } = financeSurface()
const pfRows = PF.map(([fn, uiRe, enRe, dispo]) => {
  const eng = engineReadable ? enRe.test(ENGINE) : false
  const ui = uiRe.test(FIN_SURFACE)
  const status = !engineReadable ? 'unknown'
    : !eng ? 'absent'              // not computed → absent, whatever the UI says
    : ui ? 'ui-visible' : 'engine-only'
  // governed only meaningful when surfaced; true if it appears on a stamped screen.
  const governed = status === 'ui-visible' ? uiRe.test(GOV_SURFACE) : null
  return { fn, status, dispo, governed }
})
const engineOnly = pfRows.filter(r => r.status === 'engine-only').length
const pfAbsent = pfRows.filter(r => r.status === 'absent').length

const ungoverned = pfRows.filter(r => r.governed === false)
console.log('\n═══ §10 · PROJECT-FINANCE COMPLETENESS (advisory) ═══')
console.log(`   ui-visible ${pfRows.filter(r=>r.status==='ui-visible').length} · engine-only ${engineOnly} (value on the floor) · absent ${pfAbsent}`)
console.log(`   governed: ${pfRows.filter(r=>r.governed===true).length} / ${pfRows.filter(r=>r.governed!==null).length} surfaced`
  + (ungoverned.length ? `  ⚠ UNGOVERNED (naked) — fix before flipping to a hard gate: ${ungoverned.map(r=>r.fn.split(' ')[0]).join(', ')}` : ''))

const START10 = '<!-- §10:AUTO:START -->', END10 = '<!-- §10:AUTO:END -->'
function section10() {
  const ICON = { 'ui-visible': '✅ UI', 'engine-only': '🟠 engine-only', 'absent': '⛔ absent', 'unknown': '❔ unknown' }
  const govCell = (r) => r.governed === null ? '—' : r.governed ? '🟢 governed' : '🔴 NAKED'
  const rows = pfRows.map(r => `| ${r.fn} | ${ICON[r.status]} | ${govCell(r)} | ${r.status === 'ui-visible' ? (r.governed ? 'present + stamped' : 'present — NEEDS STAMP') : PFDISPO[r.dispo]} |`).join('\n')
  const eo = pfRows.filter(r => r.status === 'engine-only')
    .map((r, n) => `  ENG -.->|surface to UI| U${n}[[${r.fn}]]:::eng`).join('\n')
  return `${START10}
## 10 · Project-finance completeness  *(GENERATED by \`audit-menu.mjs\` — do not hand-edit)*

> The Finance analog of §9. Finance is GEX's strongest workspace by coherence
> (0 stubs, 0 door↔screen mismatches) but **under-harvested**: the engine
> computes debt mechanics the UI never surfaces. Status:
> **🟠 engine-only = value on the floor** (computed, not shown). A surfaced
> metric is lender-grade *only if it carries model-governance provenance*
> (SEED vs MARKET, \`rules_version\`, challenger) — a naked DSCR/LLCR tile is
> the Finance equivalent of the fabricated "P&L MTD" removed from Commercial.

\`\`\`mermaid
flowchart TD
  ENG[("PF engine<br/>cfads · waterfall · sculpting · tranche")]
  FINUI[Finance UI]
  ENG -->|surfaced today| FINUI
  FINUI --> V1[DSCR Sensitivity]:::ok
  FINUI --> V2[Covenants]:::ok
  FINUI --> V3[Drawdown Timeline]:::ok
${eo}
  AB[[LLCR · PLCR · Sources&Uses — not computed]]:::gap
  classDef ok stroke:#10b981,stroke-width:1.5px;
  classDef eng stroke:#f59e0b,stroke-width:2px;
  classDef gap stroke:#64748b,stroke-width:1.5px,stroke-dasharray:2 3,color:#64748b;
\`\`\`

**${engineOnly} engine-only function(s)** = the highest-ROI fixes: the maths
already exists (\`/cfads/calculate\`, \`/waterfall/execute\` incl. DSRA + cash
sweep, \`debt/sculpting.py\`), it is simply not wired into a Finance screen.
**${pfAbsent} absent**: LLCR/PLCR are only consumed as lock-up *thresholds*,
never computed; Sources & Uses and refinancing have no primitive.

**Governance (provenance before completeness):** a ui-visible ratio is lender-grade
only if its screen carries an assumption stamp (basis · scenario · rules_version ·
reliance). 🔴 NAKED = surfaced without a stamp — currently **WARN** (advisory);
flip to a hard build gate once every surfaced ratio is stamped.
*Heuristic limit (honest):* "governed" here means surfaced on **≥1** stamped
screen (Debt Cashflow & Waterfall, Finance Bankability pre-COD panel). The
**standalone DSCR Sensitivity (DSCRHeatmap) and Covenants screens are NOT yet
stamped** — a banker viewing those directly sees a naked number. Per-screen
stamping is the next tightening before the gate can fail the build.

| Project-finance function | Status | Governed? | Disposition |
|---|---|---|---|
${rows}

**Sequence (do not reorder):** ① this manifest (recurring control) → ② one
lender-grade *Debt Sizing & Waterfall* view surfacing CFADS/waterfall/DSRA/
sweep/sculpting **with the governance stamp** → ③ compute LLCR/PLCR in the
engine → ④ Sources & Uses → ⑤ only then compress Deal Structuring's 13 doors
into ~4 workflows. Menu compression is last; the lender-grade spine comes first.

> **Conditions Precedent scope:** the CP section currently contains insurance
> only. Real PF CPs (legal opinions, security package, account-bank/direct
> agreements, permits, model audit, TA sign-off) are out of scope — expand the
> section, do not rename it down. Tracked as a CP-coverage gap.
${END10}`
}

let section10Stale = false
try {
  const doc = readFileSync(mapURL, 'utf8')
  const block = section10()
  const re = new RegExp(`${START10}[\\s\\S]*?${END10}`)
  let next
  if (re.test(doc)) next = doc.replace(re, block)
  else if (doc.includes(END)) next = doc.replace(END, `${END}\n\n${block}`)
  else next = doc.replace(/\n\*Reproduce the audit any time:/, `\n${block}\n\n*Reproduce the audit any time:`)
  if (next !== doc) {
    if (CHECK) { section10Stale = true; console.log('   ❌ docs §10 is STALE — run `npm run audit:menu`.') }
    else { writeFileSync(mapURL, next); console.log('   📝 wrote docs §10 (menu-architecture-map.md).') }
  } else console.log('   ✅ docs §10 current.')
} catch (e) { console.log('   ⚠ could not update docs §10:', e.message) }

// Non-zero exit on any ACCESS failure (hard gate) OR a stale generated §9/§10
// in --check mode (drift gate). Coherence/CTRM/PF findings stay advisory.
const anyFail = totalDupes > 0 || globalDupes.length > 0 || leak > 0 || sigFail > 0
process.exitCode = (anyFail || section9Stale || section10Stale) ? 1 : 0
