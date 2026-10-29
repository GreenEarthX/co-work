/**
 * Build "The GEX Process" as a Word document from the blocks that
 * export_gex_process.py --json writes (the same page as docs/GEX_Process.html,
 * itself generated from the running rules). Nothing is written here by hand
 * except layout: no sentence of the document lives in this file.
 *
 *   NODE_PATH=<dir with node_modules/docx> node scripts/gex_process_docx.cjs blocks.json out.docx
 */
const fs = require('fs')
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, HeadingLevel, AlignmentType, LevelFormat, Footer, Header, PageNumber, PageBreak,
} = require('docx')

const [, , src, dst] = process.argv
const { rules, date, blocks } = JSON.parse(fs.readFileSync(src, 'utf8'))

const INK = '18211D', MUTED = '5A665F', ACCENT = '0D6B57', SOFT = 'E1EFE9', RULE = 'D3DAD4'
const TONE = { deal_killer: 'A3261C', warning: '8A5A00' }
const BODY = 'Georgia', DISPLAY = 'Arial', MONO = 'Consolas'
const TEXT_W = 11906 - 2 * 1134                       // A4, 2 cm margins

function runs(rs, base = {}) {
  return rs.map(r => r.br ? new TextRun({ break: 1 }) : new TextRun({
    text: r.text, bold: r.b || base.bold, italics: r.i,
    font: r.mono ? MONO : base.font, size: r.mono ? (base.size ?? 21) - 2 : base.size,
    color: r.tone ? TONE[r.tone] : (r.muted ? MUTED : base.color),
  }))
}
const plain = rs => rs.map(r => r.text ?? '').join('')

const border = { style: BorderStyle.SINGLE, size: 4, color: RULE }
const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' }

// Column widths by table shape; anything else splits evenly.
function widths(head) {
  const key = head.join('|')
  const presets = {
    'Evidence item|Severity|Maturity|Owner|Applies to|Verified by': [2900, 1050, 1250, 1350, 1450, 1638],
    'Party|Owns|Never owns': [2400, 4238, 3000],
    'State|What must be satisfied|Capital decision made eligible': [2700, 4538, 2400],
    'Check|What is compared|Gate': [900, 7838, 900],
    'Reviewer|Gates': [3400, 6238],
    'Contract|Who confirms|Its confirmation also verifies': [2000, 3400, 4238],
  }
  return presets[key] ?? head.map(() => Math.floor(TEXT_W / head.length))
}

function table(b) {
  const w = widths(b.head)
  const cell = (children, i, header) => new TableCell({
    width: { size: w[i], type: WidthType.DXA },
    borders: { top: none, left: none, right: none, bottom: header ? { ...border, size: 12 } : border },
    shading: header ? { type: ShadingType.CLEAR, color: 'auto', fill: 'F4F6F3' } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children,
  })
  const small = b.head.length >= 5 ? 17 : 19
  return new Table({
    width: { size: w.reduce((a, x) => a + x, 0), type: WidthType.DXA }, columnWidths: w,
    rows: [
      new TableRow({ tableHeader: true, children: b.head.map((t, i) => cell([new Paragraph({ children: [
        new TextRun({ text: t.toUpperCase(), bold: true, font: DISPLAY, size: 15, color: MUTED })] })], i, true)) }),
      ...b.rows.map(r => new TableRow({ cantSplit: true, children: r.map((rs, i) =>
        cell([new Paragraph({ children: runs(rs, { size: small }) })], i, false)) })),
    ],
  })
}

function facts(b) {
  const w = [2800, TEXT_W - 2800]
  return new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: w,
    rows: b.items.map(([label, rs]) => new TableRow({ children: [
      new TableCell({ width: { size: w[0], type: WidthType.DXA }, borders: { top: none, bottom: none, left: none, right: none },
        margins: { top: 30, bottom: 30, left: 0, right: 90 },
        children: [new Paragraph({ children: [new TextRun({ text: label.toUpperCase(), bold: true, font: DISPLAY, size: 15, color: MUTED })] })] }),
      new TableCell({ width: { size: w[1], type: WidthType.DXA }, borders: { top: none, bottom: none, left: none, right: none },
        margins: { top: 30, bottom: 30, left: 90, right: 0 },
        children: [new Paragraph({ children: runs(rs, { size: 19 }) })] }),
    ] })),
  })
}

const out = []
let gatesStarted = false
for (const b of blocks) {
  switch (b.t) {
    case 'h1':
      out.push(new Paragraph({ heading: HeadingLevel.TITLE, children: runs(b.runs) })); break
    case 'h2':
      if (plain(b.runs) === 'The twelve gates') { gatesStarted = true; out.push(new Paragraph({ children: [new PageBreak()] })) }
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: runs(b.runs) })); break
    case 'h3':
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, children: runs(b.runs) })); break
    case 'p': {
      const s = b.style
      if (s === 'mantra') out.push(new Paragraph({ spacing: { before: 200, after: 200 }, indent: { left: 200 },
        shading: { type: ShadingType.CLEAR, color: 'auto', fill: SOFT },
        border: { left: { style: BorderStyle.SINGLE, size: 24, color: ACCENT, space: 8 } },
        children: runs(b.runs, { bold: true, size: 25 }) }))
      else if (s === 'lede') out.push(new Paragraph({ children: runs(b.runs, { size: 25, color: MUTED }) }))
      else if (s === 'stamp') out.push(new Paragraph({ children: runs(b.runs, { font: MONO, size: 16, color: MUTED }) }))
      else if (s === 'note') out.push(new Paragraph({ children: runs(b.runs, { size: 19, color: MUTED }) }))
      else out.push(new Paragraph({ children: runs(b.runs) }))
      break
    }
    case 'ol': case 'ul':
      b.items.forEach(rs => out.push(new Paragraph({ numbering: { reference: b.t === 'ol' ? 'steps' : 'bullets', level: 0 },
        children: runs(rs) })))
      break
    case 'det':
      b.items.forEach(rs => out.push(new Paragraph({ indent: { left: 200 }, spacing: { after: 100 },
        border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 8 } }, children: runs(rs) })))
      break
    case 'facts':
      out.push(facts(b)); out.push(new Paragraph({ spacing: { after: 60 }, children: [] })); break
    case 'table':
      out.push(table(b)); out.push(new Paragraph({ spacing: { after: gatesStarted ? 240 : 120 }, children: [] })); break
  }
}

const doc = new Document({
  creator: 'GreenEarthX', title: 'The GEX Process',
  description: `Generated from evidence rules ${rules} on ${date}`,
  styles: {
    default: { document: { run: { font: BODY, size: 21, color: INK }, paragraph: { spacing: { after: 120, line: 290 } } } },
    paragraphStyles: [
      { id: 'Title', name: 'Title', basedOn: 'Normal', next: 'Normal',
        run: { font: DISPLAY, size: 52, bold: true, color: INK }, paragraph: { spacing: { after: 160 } } },
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: DISPLAY, size: 30, bold: true, color: INK },
        paragraph: { spacing: { before: 420, after: 140 }, keepNext: true, outlineLevel: 0,
          border: { top: { style: BorderStyle.SINGLE, size: 12, color: INK, space: 8 } } } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: DISPLAY, size: 24, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 320, after: 100 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: 'steps', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 300 } }, run: { font: DISPLAY, bold: true, color: ACCENT } } }] },
    { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: 'The GEX Process', font: DISPLAY, size: 15, color: MUTED })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: `Evidence rules ${rules} · ${date} · page `, font: DISPLAY, size: 15, color: MUTED }),
      new TextRun({ children: [PageNumber.CURRENT], font: DISPLAY, size: 15, color: MUTED })] })] }) },
    children: out,
  }],
})

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(dst, buf); console.log(`wrote ${dst} (${Math.round(buf.length / 1024)} KB)`) })
