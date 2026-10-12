#!/usr/bin/env python3
"""Build GEX-Gates-Master_v2_redline.docx: tracked changes (author Claude) against the JML
version of the multi-party review, per decisions D1-D17 (04_decisions_for_JML.md)."""
import copy
import os
import shutil
import subprocess
import sys

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from redline_lib import Part, q, para_text, PARA_ID, TEXT_ID, XML_NS  # noqa: E402

SK = ('/Users/jean-marie.lamay/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/'
      '72e28513-6b87-450e-ba60-005e6d8d10ce/9bc5f50a-d81f-44fe-bbe6-221df5925c7f/skills/docx/scripts')
sys.path.insert(0, SK)
from comment import add_comment  # noqa: E402

SRC = os.path.join(HERE, 'master_unpacked')
BUILD = os.path.join(HERE, 'build_master')
# The delivered redline in docs/master-reconciliation became JML's working copy on 30 Sep 14:38
# (edited in Word). Never rebuild over it: this script writes to the scratch path unless OUT says
# otherwise, and refuses to overwrite anything.
OUT = os.environ.get('OUT', os.path.join(HERE, 'rebuild_check.docx'))
AUTHOR, DATE = 'Claude', '2026-09-30T09:00:00Z'

shutil.rmtree(BUILD, ignore_errors=True)
shutil.copytree(SRC, BUILD)
USED = set()
doc = Part(os.path.join(BUILD, 'word', 'document.xml'), AUTHOR, DATE, 5000, USED)
body = doc.root.find(q('body'))
O = list(body)  # original children; indices as in recon/master_idx.md


def P(i):
    el = O[i]
    assert el.tag == q('p'), (i, el.tag)
    return el


def T(i):
    el = O[i]
    assert el.tag == q('tbl'), (i, el.tag)
    return el


def rows(i):
    return T(i).findall(q('tr'))


def cell(i, r, c, pi=0):
    return rows(i)[r].findall(q('tc'))[c].findall(q('p'))[pi]


def after(ref, *els):
    cur = ref
    for el in els:
        cur.addnext(el)
        cur = el
    return cur


def expect(p, start):
    t = para_text(p)
    assert t.startswith(start), 'expected %r, found %r' % (start, t[:90])
    return p


def append_text(p, add):
    doc.edit(p, para_text(p).rstrip() + add)


# ── templates and builders ─────────────────────────────────────────────────
H1, H2, BODY, BULLET, SUBHEAD = P(51), P(52), P(104), P(69), P(68)
_BM = [900]


def bookmark(p, name):
    _BM[0] += 1
    bid = str(_BM[0])
    ins = p.find(q('ins'))
    bs = etree.Element(q('bookmarkStart'))
    bs.set(q('id'), bid)
    bs.set(q('name'), name)
    be = etree.Element(q('bookmarkEnd'))
    be.set(q('id'), bid)
    ins.addprevious(bs)
    ins.addnext(be)


def h1(text, bm=None, page_break=False):
    p = doc.new_para(text, H1, base_rpr=None, page_break_before=page_break)
    if bm:
        bookmark(p, bm)
    return p


def h2(text, bm=None):
    p = doc.new_para(text, H2, base_rpr=None)
    if bm:
        bookmark(p, bm)
    return p


def para(text):
    return doc.new_para(text, BODY, base_rpr=None)


def bullet(text, like=BULLET):
    return doc.new_para(text, like, base_rpr=None)


def subhead(text):
    return doc.new_para(text, SUBHEAD)


def page_break():
    p = doc.new_para('', BODY, base_rpr=None)
    ins = doc.mark('ins')
    p.append(ins)
    r = etree.SubElement(ins, q('r'))
    etree.SubElement(r, q('br')).set(q('type'), 'page')
    return p


def table(widths, data, **kw):
    kw.setdefault('first_col_bold', True)
    kw.setdefault('first_col_fill', True)
    return doc.new_table(T(197), widths, data, **kw)


NOTES = []


def note(p, text):
    NOTES.append((p, text))


# ── front matter ───────────────────────────────────────────────────────────
p = expect(P(2), 'A multi-stakeholder critique')
doc.edit(p, 'How GEX judges a green-fuel project, and why: the twelve gates as built (evidence rules 4.1.0, '
            '30 September 2026), with the market evidence behind them', whole=True)
note(p, 'D1 (accepted 29 Sep): the master becomes the as-built client reference for evidence rules 4.1.0; '
        'the September critique stays as dated history. New subtitle.')

doc.replace_text(expect(cell(5, 1, 1), 'Evidence: a documented fact'), 'section 10', 'section 11')
p = expect(cell(5, 4, 1), 'My inference')
doc.edit(p, 'GEX inference: analysis drawn from the evidence; test it rather than trust it.')
note(p, 'D2: neutral voice; [I] becomes “GEX inference”. [GEX] now means verified on 30 Sep 2026 '
        '(rules 4.1.0); [GEX 27 Sep] marks history (B7).')
doc.edit(expect(cell(5, 5, 1), 'Verified in the GEX engine'),
         'Verified in the GEX engine on 30 September 2026 (evidence rules 4.1.0). [GEX 27 Sep] marks what the '
         'engine did on 27 September 2026 (rules 3.0.0), kept as history.')

# ── table of contents ──────────────────────────────────────────────────────
TOC_TITLES = {
    7: '1. Why the gates look like this: the September 2026 review',
    8: '1.1 The starting point',
    9: '1.2 Six facts from the engine, 27 September 2026',
    10: '1.3 Three terms not to conflate',
    11: '1.4 The hypothesis tested: correct, incomplete, wrong',
    13: '1.6 What changed: rules 4.0.0 and 4.1.0',
    16: 'G1 · Power, Utilities & Technology Basis',
    29: '3.2 Who bears the risk — and what GEX checks',
    40: '8. The modification: proposed 27 September, built 27–29 September 2026',
    42: '8.2 The changes, and how they were built',
    46: '8.6 What GEX does and does not decide',
    48: '11. Sources',
}
for i, title in TOC_TITLES.items():
    tp = P(i)
    old_title, tail = para_text(tp).rsplit('\t', 1)
    doc.edit(tp, title + '\t' + tail)


def toc_entry(like, title, bm, field_begin=None):
    tp = etree.Element(q('p'))
    tp.set(PARA_ID, doc.new_para_id())
    tp.set(TEXT_ID, '77777777')
    tp.append(copy.deepcopy(like.find(q('pPr'))))
    doc.mark_para(tp, 'ins')
    if field_begin is not None:
        tp.append(field_begin)
    hl = etree.SubElement(tp, q('hyperlink'))
    hl.set(q('anchor'), bm)
    hl.set(q('history'), '1')
    ins = doc.mark('ins')
    hl.append(ins)
    r1 = etree.SubElement(ins, q('r'))
    rp = etree.SubElement(r1, q('rPr'))
    etree.SubElement(rp, q('rStyle')).set(q('val'), 'Hyperlink')
    etree.SubElement(rp, q('noProof'))
    etree.SubElement(r1, q('t')).text = title
    r2 = etree.SubElement(ins, q('r'))
    rp = etree.SubElement(r2, q('rPr'))
    etree.SubElement(rp, q('noProof'))
    etree.SubElement(rp, q('webHidden'))
    etree.SubElement(r2, q('tab'))
    etree.SubElement(r2, q('fldChar')).set(q('fldCharType'), 'begin')
    it = etree.SubElement(r2, q('instrText'))
    it.text = ' PAGEREF %s \\h ' % bm
    it.set('{%s}space' % XML_NS, 'preserve')
    etree.SubElement(r2, q('fldChar')).set(q('fldCharType'), 'separate')
    etree.SubElement(r2, q('t')).text = '–'
    etree.SubElement(r2, q('fldChar')).set(q('fldCharType'), 'end')
    return tp


field_begin = P(7).find(q('r'))
assert field_begin.find(q('fldChar')).get(q('fldCharType')) == 'begin'
field_begin.find(q('fldChar')).set(q('dirty'), 'true')
P(7).remove(field_begin)
toc0 = toc_entry(P(7), 'The twelve gates today (evidence rules 4.1.0)', '_TocGEX001', field_begin)
P(7).addprevious(toc0)
note(toc0, 'TOC: entries edited to match the new headings. Page numbers for new entries fill in when the '
           'table is updated: Word offers to update fields on opening, or right-click the table and choose '
           'Update Field.')
after(P(36), toc_entry(P(37), 'The capital-commitment ladder (concept, not yet computed)', '_TocGEX002'))
after(P(47), toc_entry(P(47), '10. Lessons from the EU Hydrogen Bank', '_TocGEX003'))
after(P(48),
      toc_entry(P(48), 'Annex A · After the gates: how capital is released', '_TocGEX004'),
      toc_entry(P(48), 'Annex B · Illustrative heads-of-terms templates', '_TocGEX005'),
      toc_entry(P(48), 'Annex C · Glossary of GEX terms', '_TocGEX006'))

# ── new front section: the gates as built ──────────────────────────────────
glance = table([1700, 2900, 2900, 1860], [
    ['State', 'What it makes possible', 'Required', 'Capital decision made eligible'],
    ['Speculative', 'Idea stage — nothing can be committed yet', '—', '—'],
    ['Technically plausible', 'Site and technology basis confirmed', 'G0, G1',
     'Grants & TA (G0); Seed / VC / Angel (G1)'],
    ['Commercially plausible', 'Commercially defined — offtake term sheets cover most of the output',
     'G2, G3; offtake O2 or better for at least 60% of planned output', 'Strategic Equity (G3)'],
    ['Buildable', 'Commitment-ready — producer and offtaker can sign binding-with-conditions',
     'G4 with offtake O4; G5 with EPC E4', 'Project Equity (G4)'],
    ['Structurally bankable', 'Independently validated', 'G6, G7; under project finance, offtake O6',
     'DFI / Mezz / Guarantees (G6, project finance)'],
    ['Credit approved', 'Credit approved — conditional until financial close', 'G8',
     'Senior Debt Credit Approval (conditional) (G8, project finance)'],
    ['Financeable', 'Committed — investment decision taken',
     'G9, G10; offtake effective at O7 (project finance) or O5 (balance sheet); EPC E6',
     'Debt Drawdown (G10, project finance)'],
    ['Operational', 'Delivering — certified product accepted by the buyer', 'G11',
     'Refinance / Bonds / Infra (G11)'],
    ['Refinancing eligible', 'Proven — refinancing possible',
     'Not yet computed: the highest state the engine assigns is Operational', '—'],
])
front = [
    h1('The twelve gates today (evidence rules 4.1.0)', '_TocGEX001'),
    para('This is GEX’s reference for anyone approaching the platform: producer, offtaker, lender, equity '
         'investor, development-finance institution, EPC contractor, certifier or insurer. This section states '
         'the rules as they run on 30 September 2026. Sections 1 to 9 keep the multi-party review of '
         '27 September 2026 that produced them, as the reasoning behind each rule; where the software differs '
         'from what the review proposed, an “As built” note says so. [GEX]'),
    bullet('**Twelve gates, nine states.** A project moves through the states in strict order, and each state '
           'requires its gates: G0–G1 for Technically plausible, G2–G3 for Commercially plausible, G4–G5 for '
           'Buildable, G6–G7 for Structurally bankable, G8 for Credit approved, G9–G10 for Financeable and G11 '
           'for Operational. Evidence can be gathered in any order; states cannot be skipped. [GEX]'),
    bullet('**One determination per gate.** Each gate is SATISFIED, BLOCKED, INCOMPLETE or WAIVED. It is '
           'satisfied when every applicable item is verified at its required maturity, its commitment level is '
           'met, no coherence check fails and no trigger is active. [GEX]'),
    bullet('**Verified is not mature.** Verification says a document is authentic; maturity says how far it '
           'has progressed: intent, indicative, agreed, executed, effective. Thirty-one instruments carry a '
           'required maturity, and an undeclared maturity fails closed. The submitter declares maturity; a '
           'reviewer may confirm or lower it, never raise it. [GEX]'),
    bullet('**Scope follows the financing and the power model.** There are 93 evidence items. Twenty-three '
           'protect an external lender and are asked only of project-financed projects; G6 and G8 consist only '
           'of such items and are waived whole for balance-sheet projects. A waived gate counts towards the '
           'state but is never shown as satisfied by evidence. Grid and behind-the-meter items apply according '
           'to the project’s power model. [GEX]'),
    bullet('**Two commitment ladders, derived, never entered.** The offtake is graded O0–O7 and the EPC E0–E6 '
           'from verified evidence and the commitment cards (sections 4.1 and 5). [GEX]'),
    bullet('**Ten coherence checks and three triggers.** The checks compare the commitments recorded on five '
           'cards (offtake, EPC, schedule, supply, model); a failed check blocks its gate, and missing data is '
           'shown but never counts as a pass (section 8.4). Three triggers keep gates live after the investment '
           'decision: power contract or public support revoked, certification suspended, EPC contractor or key '
           'OEM insolvent. [GEX]'),
    bullet('**Four lenses, one evidence base.** Every item is tagged for the Producer, Offtaker, Capital and '
           'Certifier lenses. Lenses are views, never separate scores. Gate views exist for producers, finance, '
           'regulators, offtakers and executives. [GEX]'),
    bullet('**Capital: eligibility, not money.** A satisfied gate makes a project eligible for the named capital '
           'provider’s decision. GEX does not commit, release or draw capital. [GEX]'),
    bullet('**GEX enforces the evidence standard; capital providers make every funding decision.** A gate whose '
           'evidence falls short is blocked, and the platform refuses evidence that breaks the rules. Whether '
           'to fund, and on what terms, each capital provider decides under its own credit criteria '
           '(section 8.6). [GEX]'),
    bullet('**No scores.** GEX publishes no composite, quality or trust score. It shows gate determinations, '
           'offtake and EPC levels, offtake coverage and coherence results. [GEX]'),
    para('The states, the commitment each makes possible, what it requires and the capital decisions it makes '
         'eligible: [GEX]'),
    glance,
    para('A credit approval at G8 stays conditional until financial close; debt becomes available to draw only '
         'when G10’s conditions are satisfied. [GEX]'),
    page_break(),
]
after(P(49), *front)
note(front[0], 'D1, D3, D4: new front section stating the rules as they run on 30 Sep 2026, from the engine '
               'export (re-verified today against gex_pf_engine rules 4.1.0). Enforcement sentence per D3; no '
               'scores per D4. The table quotes the engine’s state and capital labels verbatim.')

# ── 1. Why the gates look like this ────────────────────────────────────────
p = expect(P(51), '1. Executive Summary')
doc.edit(p, '1. Why the gates look like this: the September 2026 review')
note(p, 'D1: section 1 is kept as the dated reasoning behind the rules: the review of rules 3.0.0 on '
        '27 Sep 2026.')
after(P(51), para('This section keeps the review of 27 September 2026 that led to rules 4.0.0. It describes '
                  'the engine as it was then, under rules 3.0.0; section 1.6 and the “As built” rows in section '
                  '2 say what changed. [GEX]'))

doc.edit(expect(P(52), '1.1 GEX Current view'), '1.1 The starting point')
p = expect(P(53), 'The GEX perspective')
doc.edit(p, 'In September 2026, the GEX perspective was slanted towards financing, and more precisely towards '
            'debt. The technology aspect was addressed late, and it was weak from the off-taker view '
            'perspective. [I]')
p = expect(P(54), 'Gathered current evidence')
t = para_text(p)
t = (t.replace('evidence support “', 'evidence supports “').replace('solely   on', 'solely on')
      .replace('The Current twelve gates process must', 'The twelve gates must'))
doc.edit(p, t)
p = expect(P(55), 'Test one')
doc.edit(p, 'Test one is whether each party is mature enough for the commitment asked of it.')
note(p, 'B2: JML’s rewrite put both tests in “Test one” and made “Test two” a restatement. This restores '
        'the two tests of the original, in JML’s words; test two now says what the engine computes since '
        '4.0.0. The rest of JML’s 1.1 is kept, with tense and grammar fixes only.')
doc.edit(expect(P(56), 'Test two'),
         'Test two is whether the conditions, dates and quantities in each party’s commitment line up with the '
         'evidence held in the other gates. This is exactly the convergence the GEX mantra promises. The engine '
         'did not compute it in September 2026; since rules 4.0.0 it computes it for the commitments recorded '
         'on the commitment cards (section 8.4). [GEX]')

p = expect(P(57), '1.2 Six facts')
doc.edit(p, '1.2 Six facts from the engine, 27 September 2026')
note(p, 'B7/A1: the [GEX] labels removed in the JML edit are restored and dated 27 Sep; each fact now ends '
        'with what changed in rules 4.0.0 and 4.1.0.')
after(P(57), para('Each fact was checked in the running engine on 27 September 2026, under rules 3.0.0, and '
                  'is followed by what has changed since. [GEX 27 Sep]'))
FACTS = {
    58: ('The ladder is a capital ladder.',
         ' [GEX 27 Sep] Since rules 4.0.0 each state also names the commitment it makes possible, and since '
         '4.1.0 the decision G8 makes eligible reads “Senior Debt Credit Approval (conditional)”. [GEX]'),
    59: ('The offtake gate is coded',
         ' [GEX 27 Sep] Since rules 4.0.0 financing scope is set per item: 23 lender-protection items are not '
         'asked of balance-sheet projects, only G6 and G8 are waived whole, and G4, G7 and G10 apply to every '
         'project. [GEX]'),
    60: ('G4 describes the offtake',
         ' [GEX 27 Sep] Since rules 4.0.0 G4 also asks for the seller-side terms, and the offtake is graded '
         'O0–O7 from its verified maturity and an offtake card; G4 needs O4. [GEX]'),
    61: ('The technology is never asked',
         ' [GEX 27 Sep] Since rules 4.0.0 G1 asks for a technology maturity dossier, a licensor term sheet and a '
         'mass and energy balance, and G5 asks for FEED at AACE Class 3, the licence and process guarantee, '
         'long-lead items, EPC security and an independent technical review of FEED for every project. [GEX]'),
    62: ('GEX misses the offtaker view.',
         ' [GEX 27 Sep] Since rules 4.0.0 offtakers have their own gate view (G2, G4, G5, G9, G10, G11) and an '
         'Offtaker lens on every item. [GEX]'),
    63: ('Nothing requires a product certificate',
         ' [GEX 27 Sep] Since rules 4.0.0 G11 requires the certification audit passed with first certificates '
         'issued, and first on-specification deliveries accepted by the offtaker. [GEX]'),
}
for i, (start, add) in FACTS.items():
    append_text(expect(P(i), start), add)

p = expect(P(64), '1.3')
doc.edit(p, '1.3 Three terms not to conflate')
note(p, 'B3: JML’s definitions kept in substance; grammar fixed (“because it has across four dimensions”, '
        'stray quote mark) and labels added. The four “financed but not ready” cases stay in section 7.')
doc.edit(expect(cell(65, 0, 1), 'Making a project financeable'),
         'Making a project financeable is not eliminating risk; it means transferring each exposure to a '
         'counterparty strong enough to bear it, so that a capital provider can underwrite the risk '
         'allocation. [I]')
doc.edit(expect(cell(65, 1, 0), 'Producer can credibly'), 'The producer can credibly commit commercially')
doc.edit(expect(cell(65, 1, 1), 'because every outbound'),
         'when every outbound obligation (volume, specification and timing) is backed back-to-back by an '
         'inbound guarantee (EPC, licensor, feedstock, power) or absorbed by its own balance sheet. [I]')
doc.edit(expect(cell(65, 2, 0), 'Offtaker Long-Term'), 'The offtaker’s long-term commitment is credible')
doc.edit(expect(cell(65, 2, 1), 'Because it has'),
         'when it holds on four dimensions: durable demand (downstream customers or regulatory obligations), '
         'physical deliverability (logistics and use of the product), regulatory value (eligibility for '
         'compliance certificates) and financial capability (creditworthiness, capacity to pass the price '
         'through, and board approval). [I]')

p = expect(P(67), '1.4')
doc.edit(p, '1.4 The hypothesis tested: correct, incomplete, wrong')
note(p, 'B1/D2: neutral voice (“your proposition” becomes “the hypothesis”); the question put to the review is '
        'restored as context; past tense marks what was true of rules 3.0.0.')
after(P(67), para('The hypothesis put to the review: the framework is too finance-centric, and every gate should '
                  'be read through the producer’s and the offtaker’s eyes as well as the financier’s. Each '
                  'finding marked “correct” led to a change in rules 4.0.0 (section 1.6).'))
doc.edit(expect(P(69), 'GEX’s framework measures'),
         'GEX’s framework measured maturity mainly as capital eligibility (facts 1 and 2).')
doc.edit(expect(P(70), 'The producer’s own readiness'),
         'The producer’s own readiness questions (technology, licensor, FEED, EPC strategy, long-lead, '
         'specification, ramp-up, operations) were absent, or handed to the lenders’ engineer late (fact 4).')
doc.edit(expect(P(71), 'The offtake is one binary'),
         'The offtake was one binary milestone seen from the lender’s side, and the offtaker had no lens '
         '(facts 3 & 5).')
p = expect(P(72), 'Commitments requested before')
doc.edit(p, 'Commitments requested before the maturity that makes them credible cause attrition. Of the 15 '
            'winners of the EU Hydrogen Bank’s second auction, 7 withdrew in 2025 (1.88 GW of 2.33 GW; €755m of '
            '€993m). The European Commission said they “chose not to proceed with the grant agreement procedure '
            'or were unable to provide the signed completion guarantee” (a bank guarantee of 8% of the maximum '
            'grant); the companies cited policy and infrastructure delays and uncertainty. By January 2026, six '
            'projects had signed grant agreements, for €270.6m in total. [E]')
note(p, 'B4, verified: the completion guarantee is 8% of the maximum grant (IF24 terms and conditions, up from '
        '4% in IF23), not 8–10%. The quote is the European Commission’s (Argus, 18 Sep 2025), and the Commission '
        'gave no reasons; the reasons are those the companies cited (Balkan Green Energy News, 23 Sep 2025). '
        '“Unviable PPA pricing” could not be sourced. Outcome from the Commission’s IF24 page (20 Jan 2026).')
append_text(expect(P(76), 'Debt vs. Equity Lens'), ' [O]')
doc.edit(expect(P(77), 'The GEX Mismatch'),
         'The GEX Mismatch: under rules 3.0.0, GEX’s early screening gates unlocked early equity, VC, and public '
         'grants, yet failed to test the fundamental technical criteria that technology-equity investors '
         'actually require. Since rules 4.0.0, G1 tests the technology basis. [I]')
doc.replace_text(expect(P(83), '“A sophisticated buyer'), 'Your proposition is right', 'The hypothesis is right')
p = expect(cell(94, 0, 0, 1), 'The decisive question')
doc.replace_text(p, 'GEX can compute that.',
                 'GEX computes that, since rules 4.0.0, for the commitments recorded on its cards (section 8.4).')
append_text(p, '[GEX]')

p = expect(P(95), '1.6')
doc.edit(p, '1.6 What changed: rules 4.0.0 and 4.1.0')
note(p, 'D1/A3: the proposal of 27 Sep was built as rules 4.0.0 (27–28 Sep) and extended in 4.1.0 (29 Sep, '
        'D12/D13). The list now records what was built.')
SIXTEEN = {
    96: 'Twelve gates, nine states and one determination per gate were kept. No gate was added. [GEX]',
    97: 'Every item was split into commercial substance, asked of every project, and lender protection, asked '
        'only under project finance (23 items). G4, G7 and G10 now apply to every project; only G6 and G8, made '
        'entirely of lender items, are waived for balance-sheet projects. [GEX]',
    98: 'The two commitments that are misread most often, the offtake and the EPC, are graded on ladders (O0–O7 '
        'and E0–E6) derived from structured evidence, with minimum levels by gate and state (section 8.3). [GEX]',
    99: 'Sixteen evidence items were added, from 77 to 93, where the producer’s and offtaker’s questions were '
        'missing: technology basis and licensor, FEED and estimate class, licence and process guarantee, '
        'long-lead items, EPC security, independent technical review, product qualification, seller-side offtake '
        'terms, certificates issued, deliveries accepted. [GEX]',
    100: 'Every item is tagged with the lenses it serves (Producer, Offtaker, Capital, Certifier), and offtakers '
         'have their own gate view. Lenses are views over one evidence base, not separate scores. [GEX]',
    101: 'Ten commitment coherence checks are computed across the commitment cards, and a failed check blocks '
         'its gate. This is GEX’s first real convergence test; it compares what the cards record, not the '
         'documents themselves. [GEX]',
    102: 'Gates stay live after FID: three triggers (power contract or public support revoked, certification '
         'suspended, EPC contractor or key OEM insolvent) block the gates they undermine, and a schedule '
         'forecast past the offtake longstop fails check C5 while the offtake is still conditional. [GEX]',
}
for i, txt in SIXTEEN.items():
    doc.edit(P(i), txt)
after(P(102), bullet('Rules 4.1.0 (29 September 2026) added the EU Hydrogen Bank’s own bar: to be Commercially '
                     'plausible, a project needs offtake terms (O2 or better) for at least 60% of its planned '
                     'output. It also relabelled the decision G8 makes eligible “Senior Debt Credit Approval '
                     '(conditional)” and the Credit approved state “conditional until financial close”, because '
                     'every financing sampled ran credit approval, financial close and drawdown as separate '
                     'stages, months apart. [GEX][E]', like=P(102)))

# ── 2. Gate by gate ────────────────────────────────────────────────────────
p = expect(P(104), 'For each gate')
doc.edit(p, 'For each gate: the lens it was written in under rules 3.0.0 (27 September 2026), what each party '
            'needs from it, what was missing, what the review proposed, and what was built (“As built”, rules '
            '4.1.0). [GEX]')
note(p, 'A2/D10: an “As built (4.1.0)” row per gate, from the engine export. Deviations recorded: G6 (the '
        'review for every project was built in G5) and G10 (item scope plus state requirements, not a split '
        'gate). G1 heading renamed; gate subtitles corrected for per-item scope.')
doc.edit(expect(P(108), 'G1 · Power, Water'), 'G1 · Power, Utilities & Technology Basis')
SUBTITLES = {
    118: 'achievement · project equity · never waived; lender-protection items for project finance only',
    124: 'achievement · DFI / Mezz / Guarantees · project finance only (waived for balance-sheet projects)',
    127: 'readiness · no capital · every project; the lenders’ deductible item for project finance only',
    130: 'achievement · Senior Debt Credit Approval (conditional) · project finance only (waived for '
         'balance-sheet projects)',
    136: 'achievement · debt drawdown (project finance) · every project; lender items for project finance only',
}
for i, txt in SUBTITLES.items():
    doc.edit(P(i), txt)
AS_BUILT = {
    107: 'Built as proposed: Site Technical Suitability (major-hazard siting, geotechnics, logistics access) '
         'added; four items. [GEX]',
    110: 'Renamed “Power, Utilities & Technology Basis”. Added: Technology Maturity Dossier; Technology Licensor '
         'Identified — Term Sheet (indicative); Integrated Mass & Energy Balance at design basis, including '
         'hydrogen buffer and turndown against the power profile. Nineteen items; grid and behind-the-meter '
         'items apply by power model. Trigger T1 (power contract or public support revoked) blocks G1. [GEX]',
    113: 'Added: Product Qualification Pathway (specification standard and annex status). Certificate issuance '
         'moved to G11. The compliance-regime match is recorded on the offtake card and tested by checks C7 and '
         'C8 at G4. Trigger T2 (certification suspended) blocks G2. Offtakers see this gate. [GEX]',
    116: 'Added: Feedstock Specification & Eligibility matched to design basis and certification scheme. Supply '
         'against the offtake is tested by check C6 at G4. Since rules 4.1.0, Commercially plausible also needs '
         'offtake terms (O2 or better) for at least 60% of planned output. [GEX]',
    119: 'Never waived. The lender protections (credit support, take-or-pay floor, termination payment, '
         'assignment, step-in, hedgeable pricing index) are asked only under project finance. Added: Seller-Side '
         'Offtake Terms Reviewed. The offtake is graded O0–O7 from the contract’s verified maturity and the '
         'offtake card, and G4 needs O4. Checks C1–C3 and C5–C8 belong to G4; a failed check blocks it. '
         'Offtakers see this gate. [GEX]',
    122: 'Added: FEED complete (AACE Class 3 or better); Technology Licence & Process Performance Guarantee '
         '(agreed); Long-Lead Items Reserved (agreed); EPC Security Package & Damage Caps (agreed); Independent '
         'Technical Review of FEED for every project. The EPC is graded E0–E6, and G5 needs E4. Check C4 belongs '
         'to G5; trigger T3 (contractor or key OEM insolvent) blocks it. [GEX]',
    125: 'Built differently: the independent technical review for every project is an item in G5, before '
         'Buildable. G6 remains the lenders’ independent engineer and applies only under project finance. [GEX]',
    128: 'Every project: insurers’ quoted programme terms, broker market report, exclusions register, '
         'first-of-a-kind exclusions and OEM-warranty backstop. Project finance only: deductibles accepted by '
         'lenders. Insurance is bound at G10, not here. [GEX]',
    131: 'Project finance only. Check C10 compares model inputs with contract terms, and offtake tenor with debt '
         'tenor; a failed check blocks G8. Since rules 4.1.0 the decision it makes eligible is labelled “Senior '
         'Debt Credit Approval (conditional)”. [GEX]',
    134: 'Items unchanged. The proposed longstop test is check C5, which belongs to G4, where the longstop is '
         'agreed. Offtakers see this gate. [GEX]',
    137: 'Built differently: not split into two gates. Every project: all major contracts executed, funding '
         'committed, insurance bound with certificates delivered, O&M contract or organisation in place. Project '
         'finance only: conditions precedent satisfied, debt service reserve funded, security perfected, legal '
         'opinions issued. Financeable also requires the offtake effective at O7 (project finance) or O5 '
         '(balance sheet), and the EPC at E6. Check C9 (force majeure aligned) belongs to G10. [GEX]',
    140: 'Added: Certification Audit Passed & First Certificates Issued (executed); First On-Specification '
         'Deliveries Accepted by the Offtaker (executed). Trigger T2 blocks G11. [GEX]',
}
for ti, txt in AS_BUILT.items():
    rs = rows(ti)
    first = rs[0].findall(q('tc'))[0].find(q('p'))
    assert para_text(first) == 'Current lens', (ti, para_text(first))
    doc.edit(first, 'Lens in 3.0.0')
    last_first = rs[-1].findall(q('tc'))[0].find(q('p'))
    assert para_text(last_first) == 'Proposed', (ti, para_text(last_first))
    doc.insert_row_after(rs[-1], ['As built (4.1.0)', txt], default_sz=18)

# ── 3. Producer readiness ──────────────────────────────────────────────────
doc.edit(expect(P(142), 'Nine criteria'),
         'Nine criteria that sit alongside the financing criteria. The last two columns state what must be true '
         'before the producer can responsibly sign a binding-with-conditions offtake, and what before it gives '
         'unconditional commitments. The thresholds are GEX’s proposal, anchored in the practice cited. [I] '
         'Since rules 4.0.0 most criteria have evidence items in the gates (technology, licensor, FEED, EPC, '
         'inputs, permits, product qualification and certificates, O&M), and row 9 is computed by the coherence '
         'checks (section 8.4). [GEX]')
p = expect(P(146), '3.2')
doc.edit(p, '3.2 Who bears the risk — and what GEX checks')
note(p, 'D10: the last column now states what the engine computes; parts not built are said to be not built.')
doc.edit(expect(cell(147, 0, 2), 'What GEX should check'), 'What GEX checks (rules 4.1.0)')
CHECKS32 = {
    1: 'Contracted volume within guaranteed capacity × availability (C2); a ramp-up factor is not yet applied',
    3: 'Offtake delay exposure backed by EPC damages, contingency and sponsor support (C4); longstop covers '
       'permits, investment decision, construction at P80 and commissioning (C5)',
    4: 'First-of-a-kind exclusions and OEM-warranty backstop reviewed (G7); service agreements are not yet an '
       'item',
    5: 'Change in law allocated in the offtake (needed for O7); producer certifies under the scheme the offtake '
       'requires (C8)',
    7: 'Trigger T1 blocks G1 when the power contract or public support terms are revoked',
    8: 'EPC security package (G5); trigger T3 blocks G5 when the contractor or a key OEM is insolvent',
}
for r, txt in CHECKS32.items():
    doc.edit(cell(147, r, 2), txt)

# ── 4. Offtaker readiness ──────────────────────────────────────────────────
p = expect(P(150), '4.1')
note(p, 'D10/A4: O-level definitions quoted verbatim from the engine; market ranges kept as context. '
        'D12/D13/N8: the 60% heads-of-terms bar at Commercially plausible. D14: a captive project records an '
        'intra-group offtake card (the Hydrogen Bank treats integrated projects the same way).')
doc.edit(expect(cell(151, 0, 1), 'Instrument'), 'Definition (GEX engine)')
O_DEFS = {
    1: 'No verified offtake document with a declared maturity.',
    2: 'MoU or letter of intent: a buyer exists; nothing binds.',
    3: 'Term sheet, heads of agreement or agreed form: commercial fit, not binding.',
    4: 'Signed, but not a binding commitment: a framework, volume or price not firm, or conditions with no '
       'longstop.',
    5: 'Binding, subject to conditions precedent with a longstop date.',
    6: 'Binding and effective: conditions satisfied; obligations run from COD.',
    7: 'Firm take-or-pay or take-if-tendered from an investment-grade or credit-supported buyer.',
    8: 'Project-finance grade: O6 plus tenor covering debt, assignment, step-in, a termination payment and '
       'allocated change in law.',
}
for r, txt in O_DEFS.items():
    doc.edit(cell(151, r, 1), txt)
append_text(expect(cell(151, 3, 3), 'Commercial fit'),
            ' Since rules 4.1.0, needed for at least 60% of planned output to reach Commercially plausible.')
append_text(expect(cell(151, 5, 3), 'The buyer has done'), ' G4 requires O4.')
doc.edit(expect(cell(151, 6, 2), 'Obligations run from COD'),
         'Obligations run from COD; the seller carries volume risk unless the commitment is firm')
append_text(expect(P(153), 'Market calibration'),
            ' GEX’s firmness threshold for O6 is the bottom of that range: take-or-pay for at least 60% of '
            'contract quantity, or take-if-tendered. [GEX]')
after(P(153),
      para('**How GEX derives the level.** The level is derived, never entered: from the verified maturity of '
           'the offtake contract (intent gives O1; indicative or agreed gives O2; executed or effective gives O3 '
           'or higher) and from the offtake card: a binding commitment form, a longstop date, conditions '
           'satisfied, the take-or-pay share, the buyer’s credit, tenor against the debt tenor and allocated '
           'change in law. O7 also needs the lender protections (assignment, step-in, termination payment) '
           'verified in G4. Effectiveness is tracked separately: a firm O6 or O7 offtake can still be '
           'conditional, and Financeable requires it to be effective. [GEX]'),
      para('**What each stage requires.** Commercially plausible: O2 or better for at least 60% of planned '
           'output. G4: O4. Structurally bankable, under project finance: O6. Financeable: an effective offtake '
           'at O7 under project finance, or at O5 on a balance sheet. [GEX]'),
      para('**Coverage.** Coverage is contracted tonnes per year divided by the planned output recorded on the '
           'offtake card, or by the EPC’s guaranteed capacity when no planned output is recorded; a coverage '
           'that cannot be computed fails closed. The 60% bar is the EU Hydrogen Bank’s own application '
           'requirement (section 10). A project that consumes its own output records an intra-group offtake '
           'card; there is no captive exemption, just as the Hydrogen Bank asks integrated projects for a '
           'director’s letter reserving 60% of output. [GEX][E]'))

p = expect(P(154), '4.2')
note(p, 'A5/D10: the table is the card the review proposed; the card as built and the roadmap follow it.')
doc.edit(expect(P(155), 'Instead of one yes/no'),
         'Instead of one yes/no document, GEX records the offtake’s terms on a card and derives the O-level from '
         'them. The table lists the full card the review proposed; what is built is listed below it. Every field '
         'is something a buyer, seller or lender negotiates anyway. [I]')
after(T(156),
      para('**Built (rules 4.1.0).** The offtake card records: counterparty name and role; planned output '
           '(tonnes per year); buyer investment grade; credit support; commitment form (take-or-pay, '
           'take-if-tendered, take-and-pay, take-if-delivered or framework); take-or-pay percentage; contracted '
           'tonnes per year; tenor; price mechanism; conditions satisfied; conditions precedent; longstop date; '
           'first delivery date; delay-damages cap; product specification standard; certification scheme; '
           'compliance regime; force-majeure definition; change in law allocated. The lender protections are '
           'evidence items in G4, not card fields. Four more cards hold the EPC, schedule, supply and model terms '
           'that the coherence checks compare. [GEX]'),
      para('**Roadmap.** Not yet recorded: ramp-up profile, tolerance band, make-up and carry-forward rights, '
           'floors and caps, price-review windows, replacement cost, seller performance security, acceptance '
           'testing, delivery point and Incoterm, logistics responsibility, termination rights. [GEX]'))
doc.edit(expect(P(166), 'In GEX: the OFFTAKER'),
         'In GEX: since rules 4.0.0, offtaker accounts have their own gate view (G2, G4, G5, G9, G10, G11) and an '
         'Offtaker lens on every item. The offtaker’s own readiness (section 4.3) is not yet recorded. [GEX]')

# ── 5. EPC maturity ────────────────────────────────────────────────────────
p = expect(P(167), '5.')
note(p, 'D10/A4: E-level definitions quoted verbatim from the engine, with practice kept after them; how the '
        'level is derived is added below the table.')
p = expect(P(168), '“EPC approved”')
doc.replace_text(p, 'separate facts. [I]', 'separate facts. [GEX]')
doc.edit(expect(cell(169, 0, 2), 'What must be true'), 'Definition (GEX engine), then practice')
E_DEFS = {
    1: 'No contracting strategy and no verified EPC document.',
    2: 'Strategy defined: contracting model chosen, contractor candidates identified. In practice also: '
       'lump-sum turnkey, EPCM, split contracts or FEED-to-EPC conversion; who wraps process performance; the '
       'licensor’s role.',
    3: 'FEED complete (AACE Class 3 or better). In practice: FEED by a credible contractor, the licensor’s '
       'process design package, a long-lead list and hazard studies. IPA: design competitions for FEED '
       '“typically produce better defined FEED packages” than other routes. [P]',
    4: 'Priced proposal: a verified quotation or term sheet on the FEED basis, such as a binding priced bid or '
       'an agreed FEED-to-EPC conversion price.',
    5: 'Agreed form: price, schedule, guarantees, damages and caps, security and licence guarantee all agreed. '
       'This is the G5 bar.',
    6: 'Executed; long-lead items ordered.',
    7: 'Effective and bankable: notice to proceed issued, security posted. In practice also: interfaces '
       'wrapped, and construction insurance, which GEX requires bound at G10.',
}
for r, txt in E_DEFS.items():
    doc.edit(cell(169, r, 2), txt)
after(T(169), para('**How GEX derives the level.** From the verified maturity of the EPC contract and of the '
                   'licence guarantee, security package, damages schedule and long-lead orders, with the '
                   'contracting model on the EPC card. G5 requires E4; Financeable requires E6. If the contractor '
                   'or a key OEM is reported insolvent, an EPC at E4 or above falls back to E3 (trigger T3). '
                   '[GEX]'))
p = expect(cell(173, 0, 0, 1), 'The technology’s commercial readiness')
doc.replace_text(p, 'A ladder that promises a “senior debt commitment” at G8 regardless of technology tells a '
                    'first-of-a-kind producer something the market will not deliver.',
                 'A ladder that promised a “senior debt commitment” at G8 regardless of technology told a '
                 'first-of-a-kind producer something the market will not deliver. Since rules 4.1.0, G8 makes a '
                 'project eligible for a lender’s credit decision, labelled “Senior Debt Credit Approval '
                 '(conditional)”; whether a lender approves still depends on the technology’s commercial '
                 'readiness.')
append_text(p, '[GEX]')

# ── 6. Dependency map and the capital-commitment ladder ────────────────────
append_text(expect(P(176), 'How the commitments'),
            ' This is the single phase map GEX uses; the engine’s requirements by state are in the table at the '
            'front of this document and in section 8.3. [GEX]')
doc.edit(expect(cell(177, 2, 5), 'O2'), 'O2 for at least 60% of planned output')
doc.edit(expect(cell(177, 4, 6), 'Credit approval (PF)'),
         'Credit approval, conditional until financial close (PF), or board approval; development finance and '
         'export credit')
doc.edit(expect(cell(177, 5, 5), 'O5–O7'), 'O5–O7, effective: conditions satisfied')
cap = doc.new_table(T(177), [1700, 2600, 2700, 3000, 3680], [
    ['Stage', 'Typical document', 'What it means', 'Where it sits in GEX', 'Market evidence'],
    ['1 Interest', 'Non-disclosure agreement, teaser, expression of interest, letter of intent',
     'No funding obligation', 'Before any capital decision', '—'],
    ['2 Conditional offer', 'Term sheet; equity support letter', 'Terms known; still conditional',
     'Development and support-scheme applications',
     'EU Hydrogen Bank IF25: equity support letters for at least 60% of projected equity at application [E]'],
    ['3 Credit approval', 'Credit-committee or board approval; mandate or commitment letter',
     'Serious, but subject to documentation and conditions precedent; it can lapse',
     'G8 makes a project eligible (project finance): Senior Debt Credit Approval (conditional)',
     'IDB Invest approved US$200m for Atome, 19 Nov 2025; Gevo withdrew from its DOE conditional commitment, '
     '15 Apr 2026 [E]'],
    ['4 Signed with conditions', 'Facility, grant or subscription agreement',
     'A legal obligation once the conditions precedent are met', 'Between G8 and G10',
     'Atome signed US$420m of definitive debt, 12–13 Mar 2026, its availability conditional on equity '
     'documents [E]'],
    ['5 Financial close', 'Conditions precedent satisfied', 'Money available to draw',
     'G10, and the state Financeable', 'Atome: equity agreements and FID, 23 Apr 2026 [E]'],
    ['6 Drawdown', 'Utilisation request, withdrawal application or capital call; payment certificate',
     'Cash moves against certified progress; a breach can stop further draws',
     'After G10: Debt Drawdown (project finance)',
     'Atome: first disbursement expected end May 2026. Plug Power: DOE loan guarantee closed Jan 2025; '
     'activities under it suspended Nov 2025 [E]'],
], header=True, sz=15, head_sz=15, first_col_bold=True, first_col_fill=True)
ladder_h = h2('The capital-commitment ladder (concept, not yet computed)', '_TocGEX002')
after(P(178),
      ladder_h,
      para('The offtake and the EPC have ladders; capital needs one too. Every financing sampled ran credit '
           'approval, signing, financial close and drawdown as separate stages, often months apart, and '
           'conditional commitments lapse. GEX does not compute this ladder yet; it is shown so that every party '
           'uses one vocabulary. A satisfied gate makes a project eligible for a capital provider’s decision, '
           'never a commitment. [I]'),
      cap,
      para('GEX’s capital module records funding states that map onto these stages: announced and indicative to '
           'stage 1; term-sheeted to 2; credit-approved to 3; legally committed to 4; conditions satisfied and '
           'available to draw to 5; drawn, spent and verified as eligible use to 6. Its tranche states map the '
           'same way: proposed and in due diligence to 1; conditional offer to 2; mandated to 3; signed to 4; '
           'committed to 5; partly or fully drawn to 6. Annex A describes stage 6 from the CFO’s side. [I]'))
note(ladder_h, 'D5: the capital-commitment ladder as a concept, not computed, with the internal funding and '
               'tranche states mapped to it. Evidence: 00_market_evidence_gate_timing.md (debt staging).')

# ── 7. Market evidence ─────────────────────────────────────────────────────
doc.edit(expect(P(182), 'Transaction-level cases'),
         para_text(P(182)).replace('Transaction-level cases, 2023–2026, selected',
                                   'Transaction-level cases, 2023–2026, as known on 27 September 2026, selected'))
ehb = [r for r in rows(183) if para_text(r.findall(q('tc'))[0].find(q('p'))).startswith('EU Hydrogen Bank')]
assert len(ehb) == 1
append_text(ehb[0].findall(q('tc'))[1].find(q('p')),
            ' By 20 January 2026, six projects had signed grant agreements, for €270.6m.')

# ── 8. The modification ────────────────────────────────────────────────────
p = expect(P(188), '8. Proposed modification')
doc.edit(p, '8. The modification: proposed 27 September, built 27–29 September 2026')
note(p, 'A3/A6: section 8 records the proposal and how it was built; 8.2 and 8.3 gain the as-built facts and '
        'the two 4.1.0 changes; 8.6 is replaced (D3, D4, D16).')
after(P(188), para('The review proposed the changes below on 27 September 2026. Rules 4.0.0 (27–28 September) '
                   'built them with two deviations, on G6 and G10 (section 2), and rules 4.1.0 (29 September) '
                   'added the offtake-coverage bar and the capital labels. [GEX]'))
doc.edit(expect(P(194), '8.2'), '8.2 The changes, and how they were built')
BUILT82 = {
    1: ' Built: 23 lender-protection items; G6 and G8 are waived whole.',
    2: ' Built, with O4 required at G4 itself and the offtake effective at Financeable; rules 4.1.0 add O2 for '
       '60% of output at Commercially plausible.',
    3: ' Built: E4 at G5, E6 at Financeable.',
    4: ' Built: 16 items, from 77 to 93; the independent technical review sits in G5, not G6.',
    5: ' Built; OFFTAKER is both a gate view and a lens.',
    6: ' Built; the engine’s labels are in the table at the front of this document.',
    7: ' Built differently: each check belongs to one gate (C1–C3 and C5–C8 to G4, C4 to G5, C10 to G8, C9 to '
       'G10) and a failure blocks that gate; missing data never blocks and never passes; the checks compare '
       'the cards, not the documents.',
    8: ' Built: triggers T1–T3; a schedule forecast past the longstop fails check C5.',
}
for r, add in BUILT82.items():
    append_text(cell(195, r, 2), add)
doc.replace_text(expect(cell(195, 1, 3), 'G4 offtake, G6'), 'today all are waived', 'under rules 3.0.0 all were '
                 'waived')
last82 = rows(195)[-1]
r9 = doc.insert_row_after(last82, [
    '9', 'Offtake coverage bar (4.1.0)',
    'Commercially plausible needs offtake terms (O2 or better) for at least 60% of planned output; a coverage '
    'that cannot be computed fails closed.',
    'The EU Hydrogen Bank asks for exactly this at application (IF24, IF25); only about 13% of contracted '
    'clean-hydrogen volumes are fully binding. [E]'], default_sz=16)
doc.insert_row_after(r9, [
    '10', 'Capital labels (4.1.0)',
    'G8’s decision reads “Senior Debt Credit Approval (conditional)”; Credit approved reads “conditional until '
    'financial close”. Identifiers unchanged.',
    'Credit approval, financial close and drawdown ran months apart in every financing sampled, and '
    'conditional commitments lapse (Gevo, 2026). [E]'], like_tr=last82, default_sz=16)

doc.edit(expect(cell(197, 0, 1), 'Today'), 'Rules 3.0.0 (27 September)')
doc.edit(expect(cell(197, 0, 2), 'Proposed'), 'As built (rules 4.1.0)')
append_text(expect(cell(197, 2, 2), 'Plus product qualification'), ' for at least 60% of planned output (4.1.0)')
doc.edit(expect(cell(197, 3, 2), 'Offtake O4'),
         'Offtake O4 (binding with conditions, realistic longstop) + EPC E4 (includes FEED Class 3, licence '
         'guarantee, security) + independent technical review (G5) + no failed check among C1–C8')
append_text(expect(cell(197, 5, 2), 'Plus model-to-contract'), '; the approval stays conditional until financial '
            'close')
doc.edit(expect(cell(197, 6, 2), 'Permits + FID lock'),
         'Permits + FID lock (all projects): offtake effective at O5 (balance sheet) or O7 (project finance), '
         'EPC E6, O&M in place, force majeure aligned (C9); lender conditions for project finance only')

doc.edit(expect(P(199), 'Each compares two documents'),
         'Each check compares two commitments recorded on GEX’s commitment cards: the producer’s statement of its '
         'contracts, not the documents themselves. None needs a new party to act. PASS and FAIL decide, and a '
         'FAIL blocks the gate the check belongs to; NOT_EVALUABLE (data missing) and NOT_APPLICABLE never block '
         'and never count as a pass. [GEX]')
doc.edit(expect(cell(200, 0, 1), 'Test'), 'Test (GEX engine) and gate')
C_TITLES = {
    1: 'First delivery after guaranteed completion plus commissioning allowance (G4)',
    2: 'Contracted volume within guaranteed capacity × availability (G4)',
    3: 'Offtake specification guaranteed by the EPC or licensor (G4)',
    4: 'Offtake delay exposure backed by EPC damages, contingency and sponsor support (G5)',
    5: 'Longstop covers permits, investment decision, construction and commissioning (G4)',
    6: 'Feedstock and power contracted for the offtake’s volume and tenor (G4)',
    7: 'Power and CO2 sourcing meet the certification the offtake requires (G4)',
    8: 'Producer certifies under the scheme the offtake requires (G4)',
    9: 'Force majeure aligned across offtake, EPC and supply contracts (G10)',
    10: 'Model inputs equal contract terms; offtake tenor covers debt (G8)',
}
for r, txt in C_TITLES.items():
    doc.edit(cell(200, r, 1), txt)
after(T(200), para('**Post-FID triggers.** T1: power contract or public support terms revoked (blocks G1). T2: '
                   'certification suspended (blocks G2 and G11). T3: EPC contractor or key OEM insolvent (blocks '
                   'G5). Each is recorded on the supply or EPC card. [GEX]'))
after(P(206),
      bullet('Do not publish a composite, quality or trust score. GEX shows gate determinations, O- and E-levels, '
             'offtake coverage and coherence results; any internal score must be derived from them, never typed. '
             '[GEX]', like=P(206)),
      bullet('Do not let each capital provider configure its own thresholds. There is one GEX standard, and each '
             'provider applies its own credit criteria to the evidence GEX shows. [GEX]', like=P(206)))
p = expect(P(207), '8.6')
doc.edit(p, '8.6 What GEX does and does not decide')
note(p, 'D3/D4/D16/D17: replaces “What it would take in GEX”, which was built as rules 4.0.0. Enforcement '
        'sentence per D3; no scores (D4); one standard, no provider-configurable thresholds (D16); fees stay out '
        'of the master (D17).')
doc.edit(expect(P(208), 'A rules 4.0.0 change'),
         'GEX enforces the evidence standard; capital providers make every funding decision. GEX decides whether '
         'each item’s evidence is verified at the required maturity, each gate’s determination, the project’s '
         'state, the O- and E-levels and the coherence results; a gate that falls short is blocked, and the '
         'platform refuses evidence that breaks the rules. GEX does not decide whether to fund. A satisfied gate '
         'makes a project eligible for the named capital provider’s decision, and each provider applies its own '
         'credit criteria to the evidence GEX shows. [GEX]', whole=True)
after(P(208),
      para('Funders enforce their own hard conditions, and GEX’s blocking mirrors that practice for evidence: the '
           'EU Hydrogen Bank calls the completion guarantee and terminates the grant when financial close or '
           'entry into operation comes too late; the UK SAF mechanism’s milestone requirements let the government '
           'counterparty withdraw support if progress stalls; lenders’ conditions precedent govern every '
           'drawdown. [E][P]'),
      para('The developer produces the evidence, the capital provider evaluates it, and after the investment '
           'decision the same evidence base supports monitoring through the triggers and each funder’s own '
           'conditions. [I]'))

# ── 9. Limits ──────────────────────────────────────────────────────────────
doc.replace_text(expect(P(212), 'Some statistics'), 'I use them', 'GEX uses them')
doc.edit(expect(P(214), 'Thresholds are proposals'),
         'Thresholds are calibrated on public cases, not yet on client files. Since rules 4.0.0 the Class 3 '
         'threshold, the O- and E-level requirements, the 60% firmness and coverage thresholds and the coherence '
         'checks block gates; they should be recalibrated as client files accumulate.')
p = expect(P(215), 'Nothing in GEX was changed')
doc.edit(p, 'The review changed GEX. Rules 4.0.0 (27–28 September 2026) and 4.1.0 (29 September 2026) implement '
            'it, with the deviations recorded in section 2; section 1.2 describes the engine as it was on '
            '27 September. The coherence checks compare what the commitment cards record, which is the producer’s '
            'statement of its contracts, not the documents themselves.')
note(p, 'A6: “Nothing in GEX was changed” is no longer true.')

# ── 10. Lessons from the EU Hydrogen Bank (new; replaces JML's §11 narrative) ──
table10 = table([2300, 3300, 3760], [
    ['Requirement', 'Auction threshold', 'Where GEX tests it'],
    ['Offtake heads of terms',
     'At least 60% of hydrogen volume (IF24, IF25); integrated projects give a director’s letter reserving 60% '
     'for self-consumption',
     'Commercially plausible: offtake O2 or better for at least 60% of planned output (rules 4.1.0); a captive '
     'project records an intra-group offtake card'],
    ['Electricity heads of terms', 'At least 60% of required electricity; no more than one year old (IF25)',
     'G1: Signed PPA / Term Sheet / LOI Evidence (indicative) and PPA Volume vs Plant Load Coverage Analysis'],
    ['Grid connection', 'Permit application submitted, with a realistic timeline (IF25)',
     'G1: Grid Interconnection Study; Grid Queue Position / Capacity Reservation'],
    ['Environmental permit', 'Application submitted, with a credible approval timeline (IF25)',
     'No application-stage item; G9 requires the permit granted'],
    ['Electrolyser procurement', 'Memorandum or letter of intent with the manufacturer, stating origin',
     'G5: EPC and OEM warranty items in agreed form; origin is not tested'],
    ['Electrolyser origin',
     'At least 75% of electrolysers, stacks included, from outside China (IF25); Chinese stacks at most 25% of '
     'capacity (IF24)', 'Not tested by GEX'],
    ['Equity support', 'Letters for at least 60% of projected equity (IF25)',
     'No item before G10 (Funding Committed); see the capital-commitment ladder, section 6'],
    ['Completion guarantee', '8% of the maximum grant (IF24, IF25; 4% in IF23)',
     'A funder’s instrument, not project evidence'],
    ['Financial close', 'Within 2.5 years of grant signature; binding contracts expected then',
     'G10 and Financeable, with the offtake effective'],
    ['Entry into operation', 'Within 5 years of grant signature', 'G11'],
    ['Maritime topic',
     'Signed contracts with maritime offtakers for 60% of volume at financial close, or termination',
     'Offtake O4 or better at G4; effective at Financeable'],
])
lessons_h = h1('10. Lessons from the EU Hydrogen Bank', '_TocGEX003')
after(P(215),
      bullet('**Market facts are dated.** They are as of 27–30 September 2026. The EU Hydrogen Bank requirements '
             'come from the IF24 terms and conditions and the IF25 draft terms with CINEA’s questions and answers '
             '(3 February 2026); check the final IF25 terms before relying on them.', like=P(215)),
      lessons_h,
      para('The European Hydrogen Bank’s auctions are the clearest public test of what happens when a funder asks '
           'for commitments before, or after, the maturity that makes them credible. [I]'),
      para('**What happened.** The second auction (IF24) selected 15 projects on 20 May 2025. By September 2025 '
           'seven had withdrawn, taking 1.88 GW of the 2.33 GW and €755m of the funding. The European Commission '
           'said they “chose not to proceed with the grant agreement procedure or were unable to provide the '
           'signed completion guarantee”; the companies cited policy and infrastructure delays and uncertainty. '
           'Ten projects from the reserve list, 774 MW between them, were invited to take their place. On '
           '20 January 2026 six projects signed grant agreements, for €270.6m in total. [E]'),
      para('**Why, according to those involved.** An EU official said the completion guarantee was “working as '
           'expected in weeding out companies that have bid too low, or were forced to reassess their project '
           'maturity or financial viability”. [O] One analyst pointed to the 8% guarantee, the difficulty of '
           'securing bankable offtake and the gap between auction timelines and project-finance timelines '
           '(T. Harper, May 2026). [O] Clean Air Task Force found that the binding constraints often sit after '
           'selection, when projects must still firm up capital-cost estimates and grid connections (July 2026). '
           '[O] National hydrogen associations blamed ultra-low bids that proved economically unviable, weak '
           'demand and the late transposition of RED III (June 2026). [O] The shared lesson, in Harper’s words: '
           'the question is not “how low can bids go?” but “how many of the projects that win actually get '
           'built?” [O]'),
      para('**What the auction asks for, and when.** Both IF24 and the IF25 draft ask, at application, for heads '
           'of terms or other signed pre-contractual term sheets covering at least 60% of the hydrogen volume and '
           'at least 60% of the electricity, with an electrolyser procurement strategy backed by a memorandum or '
           'letter of intent with the manufacturer; binding contracts with offtakers and electrolyser makers are '
           'expected at financial close (CINEA). IF24 raised the completion guarantee from 4% to 8% of the '
           'maximum grant and set the deadlines: financial close within 2.5 years of grant signature and entry '
           'into operation within 5 years, or the guarantee is called and the grant terminated. IF25 tightens '
           'the entry ticket: heads of terms no more than one year old, permit applications already submitted, '
           'equity support letters for at least 60% of projected equity, and at least 75% of electrolysers, '
           'stacks included, from outside China, where IF24 capped Chinese stacks at 25% of capacity. [E]'),
      para('**What it means for a project in GEX.** The auction’s sequence is GEX’s: terms for 60% of output '
           'early, binding contracts by financial close. Since rules 4.1.0 a project reaches Commercially '
           'plausible only with offtake terms (O2 or better) for at least 60% of planned output; G4 needs a '
           'binding offtake with conditions and a longstop (O4); Financeable needs the offtake effective. The '
           'withdrawals show the cost of a hard, callable commitment demanded before permits, grid and offtake '
           'are mature, which is the conditional-convergence argument of section 1.5. [I][GEX]'),
      para('The auction’s requirements, mapped to GEX: [E][GEX]'),
      table10)
note(lessons_h, 'D6: JML’s §11 rewritten from primary sources and placed before the sources. Corrections: the '
                '60% heads-of-terms rules already applied in IF24, the auction whose winners withdrew, so they were '
                'not introduced afterwards; equity letters cover 60% of projected equity, not of total financing; '
                'the electrolyser rule is non-China, not non-EU (N3); the guarantee is 8% (B4). Removed as '
                'unverifiable: the three reasons attributed to S&P, the “free options” commentary, the '
                'EY/Hyvolution claim (its report predates the withdrawals) and the “common rejection reason” column '
                '(N5). Each is logged in 03_conflict_register.md.')

# ── 11. Sources ────────────────────────────────────────────────────────────
p = expect(P(216), '10. Sources')
doc.edit(p, '11. Sources')
note(p, 'N13: sources for section 10, the capital ladder and Annex A added with dates; GEX sources restated '
        'without code paths (list E).')
SRC_LIKE = P(233)
after(expect(P(233), 'Project Finance Law'),
      bullet('European Commission, Innovation Fund IF24 auction: terms and conditions, 25 September 2024, and '
             'results (selection 20 May 2025; reserve list 16 September 2025; six grant agreements, '
             '20 January 2026) — climate.ec.europa.eu', like=SRC_LIKE),
      bullet('European Commission, Innovation Fund IF25 hydrogen auction: draft terms and conditions — '
             'climate.ec.europa.eu; CINEA, IF25 questions and answers v0.2, 3 February 2026 — cinea.ec.europa.eu',
             like=SRC_LIKE),
      bullet('Argus, “Seven projects drop out of EU H2 bank negotiations”, 18 September 2025 — argusmedia.com',
             like=SRC_LIKE),
      bullet('Balkan Green Energy News, “Half of EU auction-backed hydrogen projects pull out”, 23 September 2025 '
             '— balkangreenenergynews.com', like=SRC_LIKE),
      bullet('T. Harper, “IF25 European Hydrogen Auction Explained”, 7 May 2026 — timharper.net', like=SRC_LIKE),
      bullet('Clean Air Task Force, Designing a €100bn Industrial Decarbonisation Bank to Deliver Operating '
             'Projects, July 2026 — catf.us', like=SRC_LIKE),
      bullet('pv magazine, “Only a quarter of funds from the second European hydrogen auction is turning into '
             'investment”, 10 June 2026 — pv-magazine.com', like=SRC_LIKE),
      bullet('APMG, PPP Certification Guide, “Financial close” — ppp-certification.com', like=SRC_LIKE),
      bullet('World Bank, Disbursement Guidelines for Investment Project Financing, February 2017 — worldbank.org',
             like=SRC_LIKE))
append_text(expect(P(243), 'Atome:'),
            '; IDB Invest approval, 19 November 2025 — worldfertilizer.com; definitive debt agreements, '
            '13 March 2026, and equity agreements and FID, 23 April 2026 — investegate.co.uk')
after(expect(P(250), 'Montana Renewables'),
      bullet('Plug Power: DOE loan guarantee closed, 16 January 2025 — ir.plugpower.com; activities under the '
             'guarantee suspended, Form 10-Q for the third quarter of 2025 — sec.gov', like=P(250)))
doc.edit(expect(P(254), 'gex_pf_engine'),
         'GEX evidence rules 3.0.0, as read in the engine on 27 September 2026: gates, lender-gate waiver, gate '
         'views, capital types', whole=True)
doc.edit(expect(P(255), 'Engine export'),
         'GEX evidence rules 4.1.0, engine export of 29 September 2026, re-verified 30 September 2026: 93 '
         'evidence items with maturity requirements and financing scope, commitment ladders, coherence checks, '
         'triggers, state and capital labels; account company types (OFFTAKER present)', whole=True)

# ── old §11: verified content moved to section 10; templates become Annex B ──
old11 = expect(P(258), '11. Reflection')
note(old11, 'Moved: the verified content is now section 10; the templates are Annex B.')
for i in range(258, 292):
    el = O[i]
    if el.tag == q('tbl'):
        doc.delete_table(el)
    elif el.tag == q('p'):
        doc.delete_para(el)
doc.delete_para(expect(P(293), 'Head of Terms'))

tA1 = table([3200, 6160], [
    ['Task', 'Why it matters'],
    ['Maintain sources and uses', 'Prevents funding gaps'],
    ['Track committed, available and drawn capital separately', 'Avoids counting promises as liquidity'],
    ['Manage account permissions', 'Prevents unauthorised cash leakage'],
    ['Prepare draw requests', 'Unlocks debt and grant money'],
    ['Certify eligible costs', 'Keeps development-finance and grant money valid'],
    ['Maintain the cost-to-complete model', 'Protects lenders from overrun risk'],
    ['Manage equity calls', 'Ensures sponsor money arrives before debt exposure grows'],
    ['Monitor conditions precedent and covenants', 'Prevents a drawstop'],
    ['Control the cash waterfall', 'Determines who is paid, and when'],
    ['Manage reserves', 'Debt service, maintenance, tax, decommissioning'],
    ['Handle waivers', 'Needed when the project diverges from the financing documents'],
    ['Preserve the audit trail', 'Required by lenders, development-finance institutions, grant agencies, tax '
                                 'authorities and certifiers'],
])
tA2 = table([4200, 5160], [
    ['Evidence', 'Who validates'],
    ['EPC invoice', 'EPC contractor'],
    ['Payment certificate', 'Owner’s engineer or project controller'],
    ['Independent engineer’s report', 'Lenders’ technical adviser'],
    ['Updated cost to complete', 'CFO, project controls, independent engineer'],
    ['Updated schedule', 'EPC contractor and owner’s team'],
    ['Permits still valid', 'Legal and compliance'],
    ['No-default certificate', 'Borrower'],
    ['Equity contribution confirmation', 'Account bank or facility agent'],
    ['Use-of-proceeds certificate', 'CFO'],
    ['Insurance confirmation', 'Insurance adviser'],
    ['Environmental and social compliance report', 'E&S adviser or development-finance agent'],
    ['Updated financial model, where required', 'Model auditor and lenders'],
])
tA3 = table([3200, 6160], [
    ['Funder', 'What it usually gets'],
    ['Senior lenders', 'Security over the project accounts, draw approval, cash-sweep rights, covenant control'],
    ['Development-finance institutions and export-credit agencies',
     'Eligible-cost controls, environmental and social conditions, procurement rules, monitoring rights'],
    ['Grant agencies', 'A designated account where required, claims documentation, milestone verification'],
    ['Sponsors (equity)', 'An equity commitment, a capital-call process, a shareholder-loan or equity ledger'],
    ['Mezzanine lenders', 'Subordinated payment rights, an intercreditor agreement, restricted-payment tests'],
    ['Equipment lessors', 'A lease payment account or direct payment'],
    ['EPC contractor', 'Payment certificates, direct payment from the construction account, retention'],
    ['Offtaker', 'Sometimes payment into the collection account, credit support, step-in or assignment rights'],
])
tA4 = table([2600, 6760], [
    ['Funder', 'Typical conditions for releasing money'],
    ['Senior banks', 'Financial close; conditions precedent satisfied; base-case model locked; budget approved; '
                     'EPC contract signed; permits materially in place; independent engineer’s report delivered; '
                     'no default; sponsor equity funded first or pro rata; use of proceeds certified; '
                     'cost-to-complete test passed'],
    ['Development-finance institutions and export-credit agencies',
     'The banks’ conditions, plus environmental and social action plans, procurement compliance, anti-corruption '
     'and sanctions checks, host-country permits, community, land and biodiversity matters, reporting and '
     'disbursement documentation; often paid in stages'],
    ['Grant agencies', 'Reimbursement after eligible spend, an advance into a designated account, direct payment '
                       'to suppliers or release on milestone evidence; restricted to set cost categories; '
                       'clawback if conditions are breached'],
    ['Sponsors', 'Shareholders’ agreement, equity commitment or subscription agreement, sponsor support, parent '
                 'guarantee or letter of credit, capital calls; banks want equity in before debt, or pro rata'],
    ['Mezzanine lenders', 'Subordinated loan or notes, intercreditor agreement, payment blockage and standstill; '
                          'paid only after senior debt, prior reserves and lock-up tests'],
])
annexA_h = h1('Annex A · After the gates: how capital is released', '_TocGEX004', page_break=True)
annexB_h = h1('Annex B · Illustrative heads-of-terms templates', '_TocGEX005', page_break=True)
after(expect(P(292), ''),
      annexA_h,
      para('A note for chief financial officers and funders. The gates decide when a project is eligible for a '
           'capital decision; this annex describes what follows the decision, as committed money becomes cash. '
           'It summarises common practice; each project’s financing documents govern. GEX does not hold, release '
           'or draw money. [I]'),
      subhead('Announced is not available'),
      para('Capital passes through distinct states, and none should be counted as the next: announced, '
           'indicative, term-sheeted, credit-approved, legally committed, conditions satisfied, available to '
           'draw, drawn, spent, verified as eligible use. The first four are promises. Money is available only '
           'once a signed agreement’s conditions precedent are satisfied: “financial close means not only that '
           'the financing documents have been signed, but also that the prior conditions for the availability of '
           'financing have been fulfilled” (APMG). It counts for grant and development-finance purposes only once '
           'its use is verified as eligible. [P]'),
      subhead('What the CFO controls'),
      tA1,
      subhead('What a construction drawdown needs'),
      para('Construction disbursements follow verified spend and certified progress, not dates. A typical draw '
           'package: [I]'),
      tA2,
      para('Green-fuel projects add: RFNBO or RED III evidence status; power-sourcing evidence, including '
           'additionality and temporal correlation; CO2 feedstock contract status; water permits; grid '
           'milestones; offtake conditions precedent; the technology guarantee package; electrolyser and '
           'synthesis-unit delivery evidence; certification-body engagement; and mass-balance, '
           'guarantee-of-origin and proof-of-sustainability readiness. Much of this is evidence the gates already '
           'hold. [I]'),
      subhead('Accounts: one structure, many funders'),
      para('Money flows through a secured project account structure, with a ledger per funding source, not one '
           'account per investor. During development a few accounts suffice: sponsor operating, development '
           'budget, grant or subsidy, tax, escrow. After financial close the structure enforces the cash '
           'waterfall, in which operating costs are paid first, then debt service and reserves, and '
           'distributions last. Typical accounts then include equity proceeds, debt proceeds and construction, '
           'project disbursement, operating, revenue collection, debt service reserve, major maintenance reserve, '
           'tax, insurance proceeds, damages received, distribution and lock-up, decommissioning reserve, a '
           'designated grant account and hedging collateral. [I]'),
      tA3,
      subhead('Release conditions by funder'),
      tA4,
      para('Public funders use a small set of disbursement methods; the World Bank’s, for instance, are '
           'reimbursement, advance, direct payment and special commitment, each against a withdrawal application '
           'with supporting documents. [P]'),
      annexB_h,
      para('These templates are GEX-drafted illustrations of the documents the EU Hydrogen Bank asks for at '
           'application (section 10): heads of terms for power and for offtake, and a grid-connection status '
           'declaration. They are not legal advice and not the auction’s official forms; use counsel and the '
           'auction’s current terms and templates. [I]'))
note(annexA_h, 'D7: CFO annex drawn from GREENEARTHX §4.0–4.2, without code; unsourced constants (such as '
               'account counts) left out.')
note(annexB_h, 'D6/B5: templates marked illustrative, not legal advice. Checked: RFNBO ≥70% GHG saving and '
               'Delegated Regulation 2023/1184 (correct); ISO 14687 Grade D at 99.97% (correct). Corrected: entry '
               'into operation is due 5 years after grant-agreement signature, not after the award. The '
               'heads-of-terms lines now state the 60% total.')
doc.replace_text(expect(P(303), '   - Contracted Volume'), 'of total electrolyser power demand)',
                 'of total electrolyser power demand; heads of terms must cover at least 60% in total)')
doc.replace_text(expect(P(333), '   - Contracted Annual Volume'), 'of total planned production)',
                 'of total planned production; heads of terms must cover at least 60% in total)')
doc.replace_text(expect(P(343), '   - First Gas Date'), '(Not later than 5 years post-Auction Award)',
                 '(no later than 5 years after signature of the grant agreement)')

# ── Annex C: glossary ──────────────────────────────────────────────────────
tC = table([2300, 7060], [
    ['Term', 'Meaning in GEX'],
    ['Gate', 'One of twelve evidence checkpoints, G0 to G11, each with one determination.'],
    ['Determination', 'SATISFIED, BLOCKED, INCOMPLETE or WAIVED. A gate waived by financing model counts towards '
                      'the state but is never shown as satisfied by evidence.'],
    ['State', 'One of nine stages, from Speculative to Refinancing eligible, reached in strict order; each names '
              'the commitment it makes possible.'],
    ['Capital decision', 'The capital provider’s decision that a satisfied gate makes a project eligible for '
                         '(eight types). GEX does not commit, release or draw capital.'],
    ['Financing model', 'Project finance or balance sheet. Twenty-three lender-protection items, and gates G6 and '
                        'G8 in full, apply only under project finance.'],
    ['Power model', 'Grid-connected, behind-the-meter or hybrid; it decides which power items apply.'],
    ['Evidence status', 'Not started, in progress, submitted, under review, verified, rejected, expired or not '
                        'applicable. Only verified evidence counts.'],
    ['Verified', 'The document is authentic. Verification says nothing about maturity or coherence.'],
    ['Maturity', 'How far an instrument has progressed: intent (plan, letter of intent, MoU), indicative (term '
                 'sheet, quotation, application submitted), agreed (agreed form, not yet signed or granted), '
                 'executed (signed, bound, granted, issued or passed), effective (in force: conditions precedent '
                 'satisfied, policy incepted, appeal period expired).'],
    ['Required maturity', 'The maturity at which a verified instrument counts; 31 items carry one, and an '
                          'undeclared maturity fails closed.'],
    ['Offtake level (O0–O7)', 'The offtake’s commitment, derived from its verified maturity and the offtake card '
                              '(section 4.1).'],
    ['Effective', 'Conditions precedent satisfied, so obligations run. Financeable requires an effective '
                  'offtake.'],
    ['Offtake coverage', 'Contracted tonnes per year as a share of planned output, or of the EPC’s guaranteed '
                         'capacity. Commercially plausible needs at least 60% under terms.'],
    ['EPC level (E0–E6)', 'The EPC’s commitment, derived from verified evidence and the EPC card (section 5).'],
    ['Commitment card', 'A structured record of a commitment’s terms: offtake, EPC, schedule, supply or model.'],
    ['Coherence check', 'A computed comparison of two commitments (C1–C10). PASS or FAIL decide, and a FAIL blocks '
                        'the check’s gate; NOT_EVALUABLE and NOT_APPLICABLE never block and never pass.'],
    ['Trigger', 'An event after the investment decision that blocks the gates it undermines (T1–T3).'],
    ['Lens', 'What an item means to a party: Producer, Offtaker, Capital or Certifier. A view, never a score.'],
    ['Gate view', 'The gates a party sees: producer, finance, regulator, offtaker or executive.'],
])
annexC_h = h1('Annex C · Glossary of GEX terms', '_TocGEX006', page_break=True)
after(expect(P(370), '2. Technical layout'),
      annexC_h,
      para('Terms as the GEX engine uses them, evidence rules 4.1.0. [GEX]'),
      tC)
note(annexC_h, 'Suggested by the reconciliation method: a glossary annex generated from the engine '
               '(02_glossary.md).')

# ── comments ───────────────────────────────────────────────────────────────
for p, text in NOTES:
    cid, _, _ = add_comment(BUILD, text, author=AUTHOR, initials='C')
    s = etree.Element(q('commentRangeStart'))
    s.set(q('id'), str(cid))
    e = etree.Element(q('commentRangeEnd'))
    e.set(q('id'), str(cid))
    ref = etree.Element(q('r'))
    etree.SubElement(ref, q('commentReference')).set(q('id'), str(cid))
    ppr = p.find(q('pPr'))
    p.insert(1 if ppr is not None else 0, s)
    p.append(e)
    prpr = ppr.find(q('rPr')) if ppr is not None else None
    if prpr is not None and prpr.find(q('ins')) is not None:
        wrap = doc.mark('ins')
        wrap.append(ref)
        p.append(wrap)
    else:
        p.append(ref)

doc.save()

# ── footers: date ──────────────────────────────────────────────────────────
for n in (1, 2, 3):
    f = Part(os.path.join(BUILD, 'word', 'footer%d.xml' % n), AUTHOR, DATE, 9000 + 100 * n, USED)
    hits = [fp for fp in f.root.iter(q('p')) if '27 Sept 2026' in para_text(fp)]
    assert len(hits) == 1, n
    f.replace_text(hits[0], '27 Sept 2026', '30 Sept 2026')
    f.save()

# ── settings: offer to update fields (TOC page numbers) on opening ─────────
st = Part(os.path.join(BUILD, 'word', 'settings.xml'), AUTHOR, DATE, 9900, USED)
if st.root.find(q('updateFields')) is None:
    uf = etree.Element(q('updateFields'))
    uf.set(q('val'), 'true')
    later = ['hdrShapeDefaults', 'footnotePr', 'endnotePr', 'compat', 'docVars', 'rsids', 'mathPr',
             'attachedSchema', 'themeFontLang', 'clrSchemeMapping', 'doNotIncludeSubdocsInStats',
             'doNotAutoCompressPictures', 'forceUpgrade', 'captions', 'readModeInkLockDown', 'smartTagType',
             'schemaLibrary', 'shapeDefaults', 'doNotEmbedSmartTags', 'decimalSymbol', 'listSeparator']
    anchor = next((ch for ch in st.root if etree.QName(ch).localname in later), None)
    if anchor is not None:
        anchor.addprevious(uf)
    else:
        st.root.append(uf)
    st.save()

# ── package ────────────────────────────────────────────────────────────────
if os.path.exists(OUT):
    raise SystemExit('refusing to overwrite %s' % OUT)
subprocess.run(['zip', '-q', '-X', '-r', OUT, '.'], cwd=BUILD, check=True)
print('wrote', OUT, os.path.getsize(OUT), 'bytes;', len(NOTES), 'comments')
