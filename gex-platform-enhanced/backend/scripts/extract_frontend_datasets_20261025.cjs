// One-off (2026-10-25): extract the per-project dictionaries the frontend held as
// literals, verbatim, for move_frontend_datasets_20261025.py. Evaluates ONLY the
// initializer of each named const (object/array literals); fails if one is not
// a pure literal. Run from frontend/:  node ../backend/scripts/extract_frontend_datasets_20261025.cjs
// The screens no longer hold these constants (that was the point), so a re-run
// must read a copy from before the move: SRC_ROOT=<that copy's frontend/src>.
// The committed data file was produced from co-work at 5da95a7; its last entry,
// plant_builder_preset, was added by hand (loadPecosI set state, it held no literal).
const ts = require(require.resolve('typescript', { paths: [process.cwd()] }))
const fs = require('fs')
const path = require('path')

const SOURCES = [
  ['bankers_snapshot', 'features/finance/BankersSnapshot.tsx', 'SNAPSHOT_DATA'],
  ['capital_stack', 'features/finance/CapitalStack.tsx', 'CAPITAL_DATA'],
  ['cert_readiness', 'features/finance/CertReadiness.tsx', 'CERT_DATA'],
  ['cert_45v', 'features/finance/CertReadiness.tsx', 'V45_DATA'],
  ['offtake_quality', 'features/finance/OfftakeQuality.tsx', 'OFFTAKE_DATA'],
  ['insurance_schedule', 'features/finance/InsuranceSchedule.tsx', 'SCHEDULE_DATA'],
  ['transfer_readiness', 'features/finance/TransferReadiness.tsx', 'TRANSFER_DATA'],
  ['ic_pack_config', 'features/finance/ICPackBuilder.tsx', 'PROJECT_CONFIGS'],
  ['ic_pack_readiness', 'features/finance/ICPackBuilder.tsx', 'READINESS_OVERRIDES'],
  ['demand_buyers', 'features/finance/DemandPipeline.tsx', 'PROJECT_BUYERS'],
  ['dfi_institutions', 'features/finance/DFIDashboard.tsx', 'MOCK_DFI'],
  ['spend_wave', 'features/finance/SpendWaveView.tsx', 'MOCK_SPEND'],
  ['drawdown_tranches', 'features/finance/DrawdownTimeline.tsx', 'MOCK_TRANCHES'],
  // An un-keyed constant that belonged to one project (its comment says so):
  // the 4th element names that project.
  ['drawdown_milestones', 'features/finance/DrawdownTimeline.tsx', 'MOCK_MILESTONES', 'proj_etf_pecos1'],
]

// Per-project BRANCHES of a builder function: called once per project the
// function names explicitly. Its fallback branch (every other project) is not
// extracted — a default is not a project's data.
const CALLS = [
  ['term_sheet', 'features/finance/TermSheetTracker.tsx', 'buildTerms', ['proj_lehavre_eng', 'proj_bremen_h2']],
  ['project_timeline', 'features/finance/ProjectTimeline.tsx', 'generateTimelineData',
    ['proj_le_havre_eng', 'proj_bremen_h2', 'proj_rotterdam_nh3']],
]

const out = []
for (const [kind, file, name, onlyProject] of SOURCES) {
  const text = fs.readFileSync(path.join(process.env.SRC_ROOT || 'src', file), 'utf8')
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX)
  let init = null
  sf.forEachChild(function visit(n) {
    if (ts.isVariableDeclaration(n) && n.name.getText(sf) === name) init = n.initializer
    ts.forEachChild(n, visit)
  })
  if (!init) throw new Error(`${name} not found in ${file}`)
  let expr = init
  while (ts.isAsExpression(expr) || ts.isSatisfiesExpression?.(expr)) expr = expr.expression
  // Helpers the literal calls (e.g. makeGate): the file's top-level function
  // declarations, which run only if called. Imports are not available, so a
  // helper that needs one throws — and the extraction stops.
  const helpers = sf.statements.filter(st => ts.isFunctionDeclaration(st)).map(st => st.getText(sf)).join('\n')
  const js = ts.transpileModule(`${helpers}\nmodule.exports = (${expr.getText(sf)})`,
    { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } }).outputText
  const m = { exports: {} }
  new Function('module', 'exports', js)(m, m.exports)   // throws on any free identifier
  out.push({ kind, from: `${file} ${name}`, data: onlyProject ? { [onlyProject]: m.exports } : m.exports })
}
for (const [kind, file, fn, ids] of CALLS) {
  const text = fs.readFileSync(path.join(process.env.SRC_ROOT || 'src', file), 'utf8')
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX)
  const helpers = sf.statements.filter(st => ts.isFunctionDeclaration(st)).map(st => st.getText(sf)).join('\n')
  const js = ts.transpileModule(`${helpers}\nmodule.exports = ${fn}`,
    { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } }).outputText
  const m = { exports: {} }
  new Function('module', 'exports', js)(m, m.exports)
  out.push({ kind, from: `${file} ${fn}()`, data: Object.fromEntries(ids.map(id => [id, m.exports(id)])) })
}
process.stdout.write(JSON.stringify(out, null, 1))
