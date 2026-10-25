// Dev helper (2026-10-25): delete named top-level const / function statements
// from a .tsx file, by AST position. Usage: node remove_ts_consts.cjs <file> NAME [NAME...]
const ts = require(require.resolve('typescript', { paths: [process.cwd()] }))
const fs = require('fs')
const [file, ...names] = process.argv.slice(2)
const text = fs.readFileSync(file, 'utf8')
const sf = ts.createSourceFile(file, text, ts.ScriptTarget.ES2020, true, ts.ScriptKind.TSX)
const cut = []
for (const st of sf.statements) {
  const n = ts.isVariableStatement(st) ? st.declarationList.declarations[0].name.getText(sf)
    : ts.isFunctionDeclaration(st) && st.name ? st.name.getText(sf) : null
  if (n && names.includes(n)) cut.push([st.getFullStart(), st.getEnd(), n])
}
const missing = names.filter(n => !cut.some(c => c[2] === n))
if (missing.length) { console.error('not found:', missing.join(', ')); process.exit(1) }
let out = text
for (const [a, b] of cut.sort((x, y) => y[0] - x[0])) out = out.slice(0, a) + out.slice(b)
fs.writeFileSync(file, out)
console.log('removed', cut.map(c => c[2]).join(', '))
