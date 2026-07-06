// Causal-ways map + linter. Generated, never hand-maintained — so the diagram
// cannot drift from the routing it depicts (the same doctrine as
// audit-menu.mjs, which generates the menu map from menuArchitecture.ts).
//
//   node scripts/audit-causal-ways.mjs            # generate + audit
//   node scripts/audit-causal-ways.mjs --check    # audit only (CI; no write)
//
// Reads the REAL sources of every causal "way" (claim → consequence → screen):
//   1. App.tsx                       — registered routes + which are guarded
//   2. data/evidenceCatalog.ts       — STATIC_EVIDENCE_CATALOG, FINANCE_GUARDED_ROUTES
//   3. features/projects/ProjectsPage.tsx — risk/next-action/gate way-helpers
//   4. gex_pf_engine .../bankability_engine.py — PERSONA_GATES (the deep-link funnel)
//
// Emits docs/causal-ways-map.md (mermaid) and lints every way-target:
//   • EXISTENCE  — target resolves to a registered route (catches F1/F2 typos)
//   • REACHABLE  — target is not a finance-guarded screen unless the way is
//                  rendered guard-aware (the F4 class)
// Exits nonzero if any way-target route does not exist.

import { readFileSync, writeFileSync } from 'node:fs'

const HERE = (p) => new URL(p, import.meta.url)
const CHECK_ONLY = process.argv.includes('--check')

const appSrc      = readFileSync(HERE('../src/App.tsx'), 'utf8')
const catalogSrc  = readFileSync(HERE('../src/data/evidenceCatalog.ts'), 'utf8')
const projectsSrc = readFileSync(HERE('../src/features/projects/ProjectsPage.tsx'), 'utf8')
const pbvSrc      = readFileSync(HERE('../src/features/producer/ProducerBankabilityView.tsx'), 'utf8')
const engineSrc   = readFileSync(HERE('../../../gex_pf_engine/backend/app/core/bankability_engine.py'), 'utf8')

// Strangler migration tracker: which call-sites delegate to resolveActionRoute.
// A guarded route reached THROUGH the resolver is handled (allowed/fallback/
// forbidden), not a defect. A guarded route hit RAW still warns.
const RESOLVER = 'resolveActionRoute'
const evidenceResolved = pbvSrc.includes(RESOLVER)

// ── helpers ──────────────────────────────────────────────────────────────────
function braceSlice(src, anchor, open, close) {
  const start = src.indexOf(anchor)
  if (start < 0) throw new Error(`anchor not found: ${anchor}`)
  const o = src.indexOf(open, start)
  let depth = 0, i = o
  for (; i < src.length; i++) {
    if (src[i] === open) depth++
    else if (src[i] === close) { depth--; if (depth === 0) { i++; break } }
  }
  return src.slice(o, i)
}
/** Normalise a route for comparison: drop query, collapse :param / {param} to *. */
function normRoute(r) {
  let s = r.split('?')[0].replace(/\/$/, '')
  s = s.replace(/\{[^}]+\}/g, '*').replace(/:[^/]+/g, '*')
  return s.startsWith('/') ? s : '/' + s
}

// ── 1 · registered routes + guards (App.tsx) ──────────────────────────────────
// Tracks the nearest enclosing parent path (e.g. <Route path="finance"> …) so a
// child "dscr-sensitivity" registers as both /dscr-sensitivity and /finance/….
const registered = new Set()
const guarded = { finance: new Set(), gatelock: new Set() }
{
  const lines = appSrc.split('\n')
  let parent = ''
  for (const line of lines) {
    const m = line.match(/path="([^"]+)"/)
    if (!m) continue
    const raw = m[1]
    const isParentOnly = /path="[^"]+">\s*$/.test(line) && !line.includes('element=')
    const abs = raw.startsWith('/') ? raw : '/' + (parent ? parent + '/' : '') + raw
    registered.add(normRoute(abs))
    registered.add(normRoute('/' + raw)) // also the bare leaf
    if (/FinanceRouteGuard/.test(line)) guarded.finance.add(normRoute('/' + raw))
    if (/GatedRoute|GateLock/.test(line)) guarded.gatelock.add(normRoute('/' + raw))
    if (isParentOnly) parent = raw
  }
}

// ── 2 · evidence catalog (eval the literal, like audit-menu evals MENU_TABS) ──
const G0 = 'G0', G1 = 'G1' // mirror the consts the literal references
const STATIC_EVIDENCE_CATALOG = eval('(' + braceSlice(catalogSrc, 'STATIC_EVIDENCE_CATALOG', '{', '}') + ')')
const FINANCE_GUARDED_ROUTES = new Set(
  eval(braceSlice(catalogSrc, 'FINANCE_GUARDED_ROUTES = new Set(', '[', ']'))
)

// ── 3 · ProjectsPage way-helpers (scan route literals → topology + existence) ─
function scanRoutes(fnName) {
  // Slice from this function declaration to the next one — avoids the
  // braceSlice trap of capturing the `: { route; label }` RETURN-TYPE brace
  // instead of the body. These helpers are small and consecutive.
  // Match the exact name boundary with the open paren — `function roleNextAction(`
  // must not prefix-match `function roleNextActionText(`.
  const start = projectsSrc.indexOf(`function ${fnName}(`)
  if (start < 0) return []
  const next = projectsSrc.indexOf('\nfunction ', start + 1)
  const span = projectsSrc.slice(start, next < 0 ? undefined : next)
  const out = []
  const re = /route:\s*(`[^`]*`|'[^']*'|"[^"]*")/g
  let m
  while ((m = re.exec(span))) {
    out.push(m[1].slice(1, -1).replace(/\$\{[^}]*\}/g, '')) // drop template exprs
  }
  return [...new Set(out)]
}
// Convention: a helper named *Action produces a RouteAction for the resolver
// (migrated); *Way / *Route helpers still decide the route themselves (raw).
// All four risk/next-action/blocker helpers now produce RouteActions for the
// resolver (*Action suffix = resolver-mediated).
const wayHelpers = {
  roleNextAction: scanRoutes('roleNextAction'),
  blockerAction: scanRoutes('blockerAction'),
  riskFlagAction: scanRoutes('riskFlagAction'),
  riskAlertAction: scanRoutes('riskAlertAction'),
}
const projectsResolved = projectsSrc.includes(RESOLVER)
const helperMediated = (fn) => projectsResolved && fn.endsWith('Action')

// ── 4 · engine PERSONA_GATES (the deep-link funnel) ───────────────────────────
const personaGates = {}
{
  const block = braceSlice(engineSrc, 'PERSONA_GATES', '{', '}')
  const re = /"([A-Z_]+)":\s*(\[[^\]]*\]|list\([^)]*\))/g
  let m
  while ((m = re.exec(block))) {
    if (m[2].startsWith('list(')) personaGates[m[1]] = 'ALL'
    else personaGates[m[1]] = [...m[2].matchAll(/"([^"]+)"/g)].map(x => x[1])
  }
}

// ════════════════ AUDIT ════════════════
const findings = []
const evidenceRoutes = [...new Set(Object.values(STATIC_EVIDENCE_CATALOG).map(e => e.route).filter(Boolean))]
const allWayTargets = [
  // Evidence WORK IT ways are resolver-mediated once PBV delegates to resolveActionRoute.
  ...evidenceRoutes.map(r => ({ src: 'evidenceCatalog', route: r, mediated: evidenceResolved })),
  ...Object.entries(wayHelpers).flatMap(([fn, rs]) => rs.map(r => ({ src: fn, route: r, mediated: helperMediated(fn) }))),
]
let missing = 0, rawGuarded = 0, rawLocked = 0
for (const { src, route, mediated } of allWayTargets) {
  const n = normRoute(route)
  const exists = registered.has(n) || registered.has(normRoute('/finance' + n))
  if (!exists) { findings.push(`❌ MISSING ROUTE  ${src} → ${route}  (no registered <Route>)`); missing++ }
  else if (FINANCE_GUARDED_ROUTES.has(n)) {
    if (mediated) findings.push(`✅ resolver-handled  ${src} → ${route}  (resolveActionRoute → allowed | fallback | forbidden)`)
    else { findings.push(`⚠️  FINANCE-GUARDED (raw)  ${src} → ${route}  (not yet migrated to resolveActionRoute)`); rawGuarded++ }
  }
  else if (guarded.gatelock.has(n)) {
    if (mediated) findings.push(`✅ resolver-handled  ${src} → ${route}  (owner-surface; resolver routes non-owners to fallback)`)
    else { findings.push(`ℹ️  WORKFLOW-LOCKED (raw)  ${src} → ${route}  (GateLock degrades gracefully; migrate to resolveActionRoute)`); rawLocked++ }
  }
}

// ════════════════ MERMAID ════════════════
function mermaid() {
  const L = []
  L.push('flowchart TD')
  L.push('    M1[Projects menu] --> PP["/projects<br/>claims: next action · blockers · risk flags"]')
  L.push('    M2[Finance / Producer menu] --> PB["/producer-bankability<br/>persona-scoped gate evidence"]')
  L.push('')
  L.push('    %% Deep-link funnel — engine persona decides which gates are visible')
  for (const [persona, gates] of Object.entries(personaGates)) {
    const g = gates === 'ALL' ? 'all gates' : gates.map(x => x.split('_')[0]).join(' ')
    L.push(`    PP -- "blocker deep-link<br/>persona=${persona}" --> PB`)
    L.push(`    PB -. "${persona} sees: ${g}" .-> PBG${persona}([${g}])`)
  }
  L.push('')
  const seen = new Set()
  const edges = new Set()
  const label = (r) => r.split('?')[0]                       // drop query for display
  const klassOf = (n, mediated) =>
    FINANCE_GUARDED_ROUTES.has(n) ? (mediated ? ':::resolved' : ':::guarded')
    : guarded.gatelock.has(n) ? ':::locked' : ':::open'
  const node = (r, mediated = false) => {
    const n = normRoute(r), id = 'R' + n.replace(/[^a-zA-Z0-9]/g, '_')
    if (!seen.has(id)) { L.push(`    ${id}["${label(r)}"]${klassOf(n, mediated)}`); seen.add(id) }
    return id
  }
  const edge = (from, lbl, to) => { const e = `    ${from} -- "${lbl}" --> ${to}`; if (!edges.has(e)) { L.push(e); edges.add(e) } }

  L.push('    %% Evidence-item ways (generated from STATIC_EVIDENCE_CATALOG.route)')
  if (evidenceResolved) {
    // Migrated: edges flow THROUGH the resolver, which decides allowed/fallback/forbidden.
    L.push('    PB --> RR{{"resolveActionRoute()<br/>allowed · fallback · forbidden"}}')
    for (const r of evidenceRoutes) edge('RR', 'WORK IT', node(r, true))
  } else {
    for (const r of evidenceRoutes) edge('PB', 'WORK IT', node(r, false))
  }
  L.push('    PB -- "Upload ✓ / Eye→docs ✓" --> DOC[("evidence_documents<br/>sha256 + append-only audit")]')
  L.push('')
  L.push('    %% Risk-flag & next-action ways (scanned from ProjectsPage helpers)')
  if (projectsResolved) L.push('    PP --> RR')   // shared resolver node
  for (const [fn, rs] of Object.entries(wayHelpers)) {
    const mediated = helperMediated(fn)
    for (const r of rs) {
      if (mediated) edge('RR', 'risk flag', node(r, true))
      else edge('PP', 'risk / next action', node(r, false))
    }
  }
  L.push('')
  L.push('    classDef guarded stroke:#e11d48,stroke-width:2px;')
  L.push('    classDef resolved stroke:#2563eb,stroke-width:2px;')
  L.push('    classDef locked stroke:#f59e0b,stroke-width:2px,stroke-dasharray:4 3;')
  L.push('    classDef open stroke:#10b981,stroke-width:1.5px;')
  return L.join('\n')
}

function doc() {
  const date = new Date().toISOString().slice(0, 10)
  return `# GEX Causal-Ways Map — GENERATED (do not hand-edit)

> Source of truth: \`App.tsx\` (routes+guards) · \`data/evidenceCatalog.ts\`
> (evidence ways + finance-guarded set) · \`features/projects/ProjectsPage.tsx\`
> (risk / next-action helpers) · engine \`bankability_engine.py\` (PERSONA_GATES).
> Regenerate: \`node frontend/scripts/audit-causal-ways.mjs\` · generated ${date}.
>
> **Doctrine (Hidalgo/Sung):** every claim traces claim → consequence → a *way*
> to the screen where it is worked, and a way only targets a screen the viewer
> can enter. **Blue** = routed through \`resolveActionRoute()\` (the way is
> decided centrally, not by the screen). **Red** = finance-guarded, hit raw
> (not yet migrated). **Amber-dashed** = workflow GateLock. **Green** = open.
>
> Migration is strangler-pattern: each call-site delegates to the resolver one
> at a time; a red edge turning blue is the proof a migration landed.

\`\`\`mermaid
${mermaid()}
\`\`\`

## Lint result (${findings.filter(f=>f.startsWith('❌')).length} blocking)

${findings.length ? findings.map(f => '- ' + f).join('\n') : '- ✅ clean — every way-target resolves to a registered, reachable route.'}

## Persona deep-link funnel (engine PERSONA_GATES)

A blocker deep-link to \`/producer-bankability?gate=Gx\` resolves only if Gx is in
the viewer's persona view — otherwise the screen shows an explicit "not in your
persona" notice (no silent miss).

${Object.entries(personaGates).map(([p, g]) => `- **${p}** → ${g === 'ALL' ? 'all gates' : g.join(', ')}`).join('\n')}
`
}

// ════════════════ EMIT ════════════════
console.log('\n═══ CAUSAL-WAYS AUDIT ═══')
console.log(`routes registered: ${registered.size} · evidence ways: ${evidenceRoutes.length} · `
  + `helper ways: ${Object.values(wayHelpers).flat().length} · personas: ${Object.keys(personaGates).length}`)
console.log('resolver migration:'
  + ` evidence WORK IT ${evidenceResolved ? '✅' : '⛔'} ·`
  + ` blockers ${helperMediated('blockerAction') ? '✅' : '⛔'} ·`
  + ` risk flags ${helperMediated('riskFlagAction') ? '✅' : '⛔'} ·`
  + ` next-action ${helperMediated('roleNextAction') ? '✅' : '⛔'} ·`
  + ` legacy-alerts ${helperMediated('riskAlertAction') ? '✅' : '⛔'}`)
for (const f of findings) console.log('  ' + f)
console.log(`\nraw guarded remaining: ${rawGuarded} · raw workflow-locked remaining: ${rawLocked}  (migrate these next)`)
console.log(missing ? `❌ FAIL — ${missing} way-target(s) point at a non-existent route.`
  : '✅ PASS — all way-targets resolve to registered routes.')

if (!CHECK_ONLY) {
  const out = HERE('../../docs/causal-ways-map.md')
  writeFileSync(out, doc())
  console.log(`📝 wrote ${out.pathname}`)
}
process.exit(missing ? 1 : 0)
