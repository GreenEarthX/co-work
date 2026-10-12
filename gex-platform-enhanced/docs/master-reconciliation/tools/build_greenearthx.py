#!/usr/bin/env python3
"""GREENEARTHX_redline.docx: tracked changes (author Claude) per decision D9 — vocabulary
alignment with evidence rules 4.1.0, pointers to the client master, illustrations labelled,
version trail fixed, build status moved to docs/CLAUDE_HANDOFF.md §8 item 39.

The June 2026 insertions already pending in the document are left untouched; where one is
wrong, a dated correction paragraph follows it."""
import os
import shutil
import subprocess
import sys

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from redline_lib import Part, q, para_text  # noqa: E402

SK = ('/Users/jean-marie.lamay/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/'
      '72e28513-6b87-450e-ba60-005e6d8d10ce/9bc5f50a-d81f-44fe-bbe6-221df5925c7f/skills/docx/scripts')
sys.path.insert(0, SK)
from comment import add_comment  # noqa: E402

SRC = os.path.join(HERE, 'greenearthx_unpacked')
BUILD = os.path.join(HERE, 'build_greenearthx')
OUT = os.environ.get('OUT', os.path.join(HERE, 'GREENEARTHX_redline_rebuild.docx'))
AUTHOR, DATE = 'Claude', '2026-09-30T15:00:00Z'

shutil.rmtree(BUILD, ignore_errors=True)
shutil.copytree(SRC, BUILD)
doc = Part(os.path.join(BUILD, 'word', 'document.xml'), AUTHOR, DATE, 7000, set())
body = doc.root.find(q('body'))
O = list(body)


def P(i):
    assert O[i].tag == q('p'), (i, O[i].tag)
    return O[i]


def T(i):
    assert O[i].tag == q('tbl'), (i, O[i].tag)
    return O[i]


def cell(i, r, c, pi=0):
    return T(i).findall(q('tr'))[r].findall(q('tc'))[c].findall(q('p'))[pi]


def expect(p, start):
    def norm(s):
        return s.replace('’', "'").replace('\xa0', ' ')
    t = para_text(p)
    assert norm(t).startswith(norm(start)), 'expected %r, found %r' % (start, t[:90])
    return p


def after(ref, *els):
    cur = ref
    for el in els:
        cur.addnext(el)
        cur = el
    return cur


def append_text(p, add):
    doc.edit(p, para_text(p).rstrip() + add)


# A plain body paragraph to copy paragraph formatting from: [154] under the entropy table.
BODY = expect(P(154), 'GEX’s platform fee')


def note_para(text, like=BODY):
    return doc.new_para(text, like, base_rpr=None)


NOTES = []


def note(p, text):
    NOTES.append((p, text))


MASTER = 'the client master (GEX-Gates-Master v2, docs/master-reconciliation)'

# ── version trail (N6) ─────────────────────────────────────────────────────
p = expect(cell(9, 0, 0), 'Reading note (v4.4)')
doc.edit(p, 'Reading note (v4.5, 30 Sep 2026).  This document supersedes GEX Operating Architecture v4.1 (May 12 '
            '2026). v4.5 aligns its gate, state, capital, verification and persona vocabulary with GEX evidence '
            'rules 4.1.0 and points to %s for every definition. It no longer carries build status: the '
            'implementation audit moved to docs/CLAUDE_HANDOFF.md §8 item 39, re-verified on 30 Sep 2026. '
            'Illustrative numbers are labelled as such.' % MASTER, whole=True)
note(p, 'D9 (accepted 29 Sep): vocabulary aligned with rules 4.1.0, pointers to the client master, illustrations '
        'labelled, build status moved to the handoff, one version in the trail (the note said v4.4, the Bottom '
        'Line v4.2). The June 2026 insertions already pending in this document are left untouched; where one '
        'is wrong, a dated correction follows it.')

# ── thought process: two status claims overtaken by rules 4.0.0 ───────────
append_text(expect(P(140), 'GEX does not calculate convergence'),
            '. Since rules 4.0.0 (28 Sep 2026) the coherence checks compute part of this from the commitment cards: '
            'offtake volume against guaranteed capacity × availability (C2), supply against the offtake (C6), '
            'model against contracts (C10). The independent engineer’s assumptions are still not compared with '
            'the model (master §8.4).')
append_text(expect(P(146), 'GEX already found the better wedge'),
            ' Since rules 4.0.0 the gates do difference them: O7 and check C10 compare offtake tenor with the '
            'project’s own debt tenor. The rating-engine hardcode remains, a separate code task (decision D15).')

# ── entropy table (C3, C4, C8) ─────────────────────────────────────────────
ENTROPY = {
    (2, 1): 'Technology basis (G1); EPC commitment and independent technical review of FEED (G5); lenders’ '
            'engineer (G6, project finance only)',
    (2, 2): 'Senior debt credit approval (G8, conditional); drawdown only after financial close (G10)',
    (3, 1): 'Offtake terms for at least 60% of output (O2, Commercially plausible); binding with conditions (O4, '
            'G4); effective at Financeable. No Trust Score',
    (3, 2): 'Revenue-backed debt sizing at credit approval (G8)',
    (4, 1): 'Concessional first-loss tranche (DFI / Mezz / Guarantees eligible at G6, project finance)',
    (4, 2): 'Senior Debt Credit Approval (conditional) at G8; drawdown at G10',
}
for (r, c), txt in ENTROPY.items():
    doc.edit(cell(152, r, c), txt)
ent_note = note_para('**Aligned with evidence rules 4.1.0 (v4.5).** Gates, capital decisions and ladders as the '
                     'engine runs them: see %s, “The twelve gates today” and Annex C.' % MASTER)
after(T(152), ent_note)
note(ent_note, 'C3/C4/C8: DFI at G6 (not G10), senior debt credit approval at G8 (conditional), drawdown at G10; '
               'technology examined from G1, independent technical review in G5; no Trust Score (D4).')

# ── §2.1 note (C3) ─────────────────────────────────────────────────────────
doc.replace_text(expect(P(223), 'Note.'),
                 'Senior Debt and ECA are gated behind G10 in Bridge to Capital (§3).',
                 'Capital decisions follow the engine (rules 4.1.0): DFI / Mezz / Guarantees at G6, Senior Debt '
                 'Credit Approval (conditional) at G8 and Debt Drawdown at G10, all for project finance only; ECA is '
                 'not an engine capital type (master, “The twelve gates today”).')

# ── §2.3 participants (C1, C2, C15, N10) ───────────────────────────────────
doc.edit(expect(cell(227, 0, 4), 'ABAC persona'), 'ABAC actor type')
doc.edit(expect(cell(227, 4, 1), 'Reviews G10 pack'),
         'Credit approval at G8 (conditional); reviews the G10 pack, monitors covenants')
doc.edit(expect(cell(227, 7, 1), 'Signs G6 technical'),
         'Signs G6 (lenders’ engineer, project finance only); the independent technical review of FEED is a '
         'G5 item for every project')
p = expect(cell(227, 8, 1), 'Signs HoT at G4')
doc.edit(p, 'Heads of terms (O2) for at least 60% of output by Commercially plausible; binding with conditions '
            '(O4) at G4; effective at Financeable (G10)')
note(p, 'C1/D12: HoT at G4 would let a project reach Buildable on paper no lender in the deal sample accepted. '
        'Evidence: 00_market_evidence_gate_timing.md.')
p = expect(cell(227, 9, 1), 'Binds CAR/EAR/DSU at G7')
doc.edit(p, 'Quotes terms at G7 (insurability); binds CAR/EAR/DSU at G10')
note(p, 'C2: the engine asks for quoted terms at G7 and bound insurance with certificates at G10; lenders place '
        'insurance as a condition to financial close.')
term = note_para('**Terminology (v4.5).** Three axes share the word “persona”. The last column is the '
                 'ABAC actor type: who may act (15 members in ActorType, backend/app/core/abac.py, verified '
                 '30 Sep 2026). The gate view is which gates a party sees (producer, finance, regulator, offtaker, '
                 'executive). The lens is what an evidence item means to a party (producer, offtaker, capital, '
                 'certifier). See the master glossary, Annex C.')
after(expect(P(228), 'Persona reconciliation (v4.3)'), term)
note(term, 'C15: the June insertion above calls actor types “personas”; this separates the three axes.')

# ── §2.4 verification (C7) ─────────────────────────────────────────────────
mapping = note_para('**Mapping to the gates (v4.5).** The gates keep three separate facts, not one state: '
                    'evidence status (… SUBMITTED, UNDER_REVIEW, VERIFIED), maturity (INTENT → EFFECTIVE) '
                    'and coherence (PASS, FAIL, NOT_EVALUABLE, NOT_APPLICABLE). UNVERIFIED ≈ not started or in '
                    'progress; SUBMITTED ≈ submitted or under review; CONFIRMED ≈ verified and at the '
                    'required maturity; AUDITED has no gate equivalent (independent re-verification, required by no '
                    'gate). Canonical terms: master, Annex C.')
after(expect(P(231), 'Every artefact GEX creates'), mapping)
note(mapping, 'C7: one mapping between this taxonomy and the gates’ status, maturity and coherence.')

# ── §3 phases (C1, C5, C11, C12) ───────────────────────────────────────────
doc.replace_text(expect(P(234), 'The project lifecycle table'),
                 'Applying DSCR before Financial Close distorts the picture; the pre-COD metrics in §4.6 '
                 'replace it.',
                 'DSCR is a lender metric at credit approval (G8 requires an audited base-case model, and check C10 '
                 'compares it with the contracts), not a development-stage dashboard; before then the pre-COD '
                 'metrics in §5.10 apply.')
corr = note_para('**Correction (v4.5).** The coarse mapping above leaves G4 and G7–G9 out. Use: Gate 1 → '
                 'G0–G1 (Technically plausible); Gate 2 → G2–G3 (Commercially plausible); Gate 3 '
                 '→ G4–G8 (Buildable to Credit approved); Gate 4 → G9–G11 (Financeable to '
                 'Operational). The single phase map is the master’s §6.')
after(expect(P(235), 'Gate vocabulary (v4.3)'), corr)
note(corr, 'C5: the June insertion’s mapping (Gate 3 → G5–G6, Gate 4 → G10–G11) omits four '
           'gates.')
doc.edit(expect(cell(237, 2, 3), 'G0–G3'), 'G0–G3; offtake terms for at least 60% of output (O2)')
doc.edit(expect(cell(237, 3, 3), 'G2, G3, G5, G6'),
         'G4, G5 (binding offtake with conditions, O4; EPC agreed form, E4)')
doc.edit(expect(cell(237, 4, 3), 'G4, G7, G8, G10'), 'G6, G7, G8; then G9, G10 at financial close')
doc.edit(expect(cell(237, 4, 4), 'Senior debt (post-CP)'),
         'Senior debt credit approval (conditional, G8); DFI / Mezz / Guarantees (G6); drawdown only after G10; '
         'equity first-loss')
doc.edit(expect(cell(237, 5, 3), 'G5, G9, G11'), 'G11 in progress; post-FID triggers T1–T3 live')
phase_note = note_para('**Aligned (v4.5).** Gates and capital follow evidence rules 4.1.0; the canonical phase '
                       'map is the master’s §6. The pre-COD metric thresholds in this table (ECR, FMR, RAS, '
                       'TIE) are internal and not canonical (decision D11). “RAS ≥ 75” is not a gate '
                       'requirement: Financeable needs an effective offtake at O7 (project finance) or O5 (balance '
                       'sheet).')
after(T(237), phase_note)
note(phase_note, 'C1/C12/D11/D12: G4 moves from FID readiness to FEED (binding with conditions); heads of terms '
                 'for 60% of output come at pre-FEED; metric thresholds flagged as non-canonical.')

# ── §3.1 adjacency: illustration and status (C13, C14) ─────────────────────
append_text(expect(P(253), 'This is how Development Finance Institutions'),
            ' (Illustrative: no such cohort exists yet; the figures are placeholders.)')
append_text(expect(P(254), 'Note.'),
            ' Status (30 Sep 2026): the platform endpoint exists but reads PostgreSQL-owned tables from SQLite and '
            'fails on the live stack (docs/CLAUDE_HANDOFF.md §8 item 39).')
doc.replace_text(expect(cell(257, 0, 0), 'gex_pf_engine/core/adjacency.py'),
                 'gex_pf_engine/core/adjacency.py  [NEW — Phase B2]',
                 'gex_pf_engine/backend/pf_engine/core/adjacency.py  (built)')

# ── §4 chain of investment promises (D5) ───────────────────────────────────
chain = note_para('**Aligned (v4.5).** This chain is the capital-side analogue of the offtake and EPC ladders. The '
                  'master states it as the capital-commitment ladder, a concept not yet computed: interest → '
                  'conditional offer → credit approval → signed with conditions → financial close '
                  '→ drawdown, with this module’s funding and tranche states mapped to it (master §6).')
after(T(265), chain)

# ── §5.1 Gantt (D12) and Capital State Gates (C6) ──────────────────────────
doc.replace_text(expect(P(436), '    Offtake Bankability Matrix'),
                 'Offtake Bankability Matrix Volume / Tenor / Price / Credit',
                 'Offtake Heads of Terms for 60 percent of Output (O2) + Bankability Matrix')
doc.replace_text(expect(P(448), '    Executable Offtake Term Sheets'),
                 'Executable Offtake Term Sheets',
                 'Binding Offtake with Conditions and Longstop (O4, G4)')
csg = note_para('**Mapping (v4.5).** Capital State Gates are internal milestones, not engine gates. CSG1 ≈ '
                'Technically plausible; CSG2 ≈ Commercially plausible (indicative term sheets; offtake terms for at '
                'least 60% of output); CSG3 ≈ Buildable to Structurally bankable (the credit process can start); '
                'CSG4 ≈ Credit approved (G8, conditional); CSG5 ≈ signed with conditions (stage 4 of the '
                'master’s capital-commitment ladder); CSG6 ≈ Financeable (G10, financial close); CSG7 '
                '≈ construction and first production (no engine state); CSG8 ≈ Operational (G11).')
after(expect(P(512), '    Capital State Gate 8'), csg)
note(csg, 'C6: each internal ladder gets a mapping to the engine’s states, or it goes (D5, D9).')

# ── §5.8 and §5.11 illustrative constants (C14) ────────────────────────────
illus = note_para('**Illustrative (v4.5).** The rates, tenors and grace periods above, and the target returns in '
                  '§5.11, are placeholders from the reference model, not sourced market data. Do not present '
                  'them as data.')
after(T(538), illus)
note(illus, 'C14: unsourced constants read as data; labelled rather than removed, since this is an internal spec.')

# ── §5.10 pre-COD metrics (C12, D4, D11) ───────────────────────────────────
pcm = note_para('**Status (v4.5).** Two metric sets exist, this one and the retired Bridge v6’s, with '
                'conflicting thresholds and a mis-defined ECR; none is canonical, so they stay out of client material '
                '(decision D11). “RAS ≥ 75 for G10” is not an engine rule: Financeable needs an '
                'effective offtake at O7 (project finance) or O5 (balance sheet). Any score here must be derived, '
                'never typed (D4).')
after(T(549), pcm)

# ── §6 verification taxonomy (C7) ──────────────────────────────────────────
after(T(563), note_para('**Mapping (v4.5):** see §2.4. “Required for G10 close” is not an engine '
                        'rule: no gate requires AUDITED; G8 requires the model audit opinion issued (executed).'))

# ── §8 integration map: status and namespace ───────────────────────────────
after(expect(P(641), '8   Software Integration Map'),
      note_para('**Status (v4.5).** Status columns in this section are superseded by docs/CLAUDE_HANDOFF.md §8 '
                'item 39, re-verified on 30 Sep 2026. Engine paths below use the pre-9-September namespace: the '
                'project-finance engine is the sibling repo gex_pf_engine, package pf_engine '
                '(backend/pf_engine/core/…); deal_engine is a different service.'))
ns = note_para('**Correction (v4.5).** The namespace note above describes deal_engine (formerly gex_pf_engine, '
               'renamed 9 Sep 2026), a different service. The project-finance engine is the sibling repo '
               'gex_pf_engine (package pf_engine): waterfall.py, cfads.py, adjacency.py and debt/sculpting.py exist '
               'there under backend/pf_engine/core/ (verified 30 Sep 2026).')
after(expect(P(649), 'Namespace correction (v4.3)'), ns)
note(ns, 'The June insertion above says these modules are not present; they are, in the sibling repo.')

# ── §9 doctrines (C8, C11) ─────────────────────────────────────────────────
doc.replace_text(expect(cell(657, 1, 0), 'Pre-COD finance is a package-definition'),
                 'DSCR is not shown before G10.',
                 'DSCR is a lender metric at credit approval (G8), not a development-stage dashboard.')
append_text(expect(cell(657, 6, 0), 'A project’s bankability state is a stack'),
    ' The gates’ canonical readout is one determination per gate, O- and E-levels, offtake coverage and '
    'coherence results; any certainty bar must be derived from them, never typed (D4).')

# ── Appendix B state machines (C6, D5, D8) ─────────────────────────────────
after(T(668), note_para('**Note (v4.5).** Package states are internal workflow states, not gates; unlock_condition '
                        'links a package to gate evidence. Bridge v6’s eight-state variant is retired with that '
                        'document (decision D8).'))
after(T(670), note_para('**Mapping (v4.5).** Tranche states map onto the master’s capital-commitment ladder: '
                        'proposed and due_diligence → 1; conditional_offer → 2; mandated → 3; signed '
                        '→ 4; committed → 5; partially_drawn and fully_drawn → 6.'))

# ── Appendix E primitives (C8, C14) ────────────────────────────────────────
after(T(710), note_para('**Aligned (v4.5).** Built in the platform registry engine and derived from gate results '
                        '(docs/CLAUDE_HANDOFF.md §8 item 39). It is an internal view: client material shows gate '
                        'determinations, O- and E-levels, offtake coverage and coherence results, never an aggregate '
                        'score (D4).'))
after(T(713), note_para('**Illustrative (v4.5):** the numbers in this specification (71%, N = 14, 86%, 18%) are '
                        'examples; no cohort exists yet.'))

# ── build status: moved to the handoff (C13, D9) ───────────────────────────
heading = expect(P(727), 'The Future and where')
doc.edit(heading, 'Implementation status (moved)')
moved = note_para('**Moved (v4.5).** The implementation-status audit that stood here (status as of v4.2, 14 May '
                  '2026) contradicted itself and the tree: rows marked IMPLEMENTED with the note “Not '
                  'built”, and “PostgreSQL migrations DEFERRED” while the schema is at head 059. It '
                  'was re-verified on 30 Sep 2026 and now lives in docs/CLAUDE_HANDOFF.md §8 item 39.')
after(heading, moved)
note(heading, 'C13/D9: build status moved to the handoff after re-verification; the Bottom Line (v4.2) goes with '
              'it, which also ends the three-version trail.')
for i in range(728, 772):
    el = O[i]
    if el.tag == q('tbl'):
        doc.delete_table(el)
    elif el.tag == q('p'):
        assert el.find('.//' + q('sectPr')) is None, i
        doc.delete_para(el)

# TOC: retitle the moved section, drop its sub-entries.
toc = expect(P(91), 'The Future and where')
tt, tail = para_text(toc).rsplit('\t', 1)
doc.edit(toc, 'Implementation status (moved)\t' + tail)
for i in range(92, 101):
    doc.delete_para(P(i))

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
        w = doc.mark('ins')
        w.append(ref)
        p.append(w)
    else:
        p.append(ref)

doc.save()
if os.path.exists(OUT):
    raise SystemExit('refusing to overwrite %s' % OUT)
subprocess.run(['zip', '-q', '-X', '-r', OUT, '.'], cwd=BUILD, check=True)
print('wrote', OUT, os.path.getsize(OUT), 'bytes;', len(NOTES), 'comments')
