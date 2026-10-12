"""Tracked-change (redline) editing of WordprocessingML with lxml.

Every text change is written as <w:ins>/<w:del> by one author, so the reader can
accept or reject each edit in Word. Nothing here reformats untouched XML.
"""
import copy
import difflib
import random
import re

from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W14 = 'http://schemas.microsoft.com/office/word/2010/wordml'
XML_NS = 'http://www.w3.org/XML/1998/namespace'


def q(tag):
    return '{%s}%s' % (W, tag)


PARA_ID = '{%s}paraId' % W14
TEXT_ID = '{%s}textId' % W14

LABEL_ONE = r'\[(?:E|P|O|I|GEX)(?: [^\]\[]*)?\]'
LABEL_RE = re.compile(LABEL_ONE)
LABEL_COLORS = {'E': '245E42', 'P': '0D5754', 'O': '8A5F06', 'I': 'A8341A', 'GEX': '3A4A46'}
TOKEN_RE = re.compile(LABEL_ONE + r"|\w+(?:[’'\-]\w+)*|\s+|[^\w\s]", re.U)
TEXT_CHILDREN = {q('t'), q('tab'), q('br'), q('cr'), q('lastRenderedPageBreak'), q('rPr')}

# CT_PPr child order (subset that matters here).
PPR_ORDER = ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl',
             'numPr', 'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens',
             'kinsoku', 'wordWrap', 'overflowPunct', 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN',
             'bidi', 'adjustRightInd', 'snapToGrid', 'spacing', 'ind', 'contextualSpacing',
             'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection', 'textAlignment',
             'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange']


def run_text(r):
    out = []
    for ch in r:
        if ch.tag == q('t'):
            out.append(ch.text or '')
        elif ch.tag == q('tab'):
            out.append('\t')
        elif ch.tag in (q('br'), q('cr')):
            out.append('\n')
    return ''.join(out)


def in_deleted(el):
    return any(a.tag in (q('del'), q('moveFrom')) for a in el.iterancestors())


def live_runs(p):
    return [r for r in p.iter(q('r')) if not in_deleted(r)]


def para_text(p):
    return ''.join(run_text(r) for r in live_runs(p))


def is_label_run(r):
    t = run_text(r).strip()
    return bool(t) and re.fullmatch(r'(?:%s)+' % LABEL_ONE, t) is not None


class Part:
    """One XML part (document.xml or a footer) edited with tracked changes."""

    def __init__(self, path, author, date, id_start, used_para_ids):
        self.path = path
        self.tree = etree.parse(path)
        self.root = self.tree.getroot()
        self.author, self.date = author, date
        self._id = id_start
        self.used = used_para_ids
        for el in self.root.iter():
            v = el.get(PARA_ID)
            if v:
                self.used.add(v)

    # ── bookkeeping ────────────────────────────────────────────────────────
    def nid(self):
        self._id += 1
        return str(self._id)

    def mark(self, kind):
        el = etree.Element(q(kind))
        el.set(q('id'), self.nid())
        el.set(q('author'), self.author)
        el.set(q('date'), self.date)
        return el

    def new_para_id(self):
        while True:
            v = '%08X' % random.randint(0x10000000, 0x7FFFFFFE)
            if v not in self.used:
                self.used.add(v)
                return v

    def fresh_ids(self, el):
        for x in el.iter():
            if x.get(PARA_ID) is not None:
                x.set(PARA_ID, self.new_para_id())
                x.set(TEXT_ID, '77777777')

    def save(self):
        self.tree.write(self.path, xml_declaration=True, encoding='UTF-8', standalone=True)

    # ── runs ───────────────────────────────────────────────────────────────
    def segments(self, p):
        segs, pos = [], 0
        for r in live_runs(p):
            t = run_text(r)
            segs.append((r, pos, pos + len(t)))
            pos += len(t)
        return segs

    def split_run(self, r, k):
        """Split run r so its first k characters stay in r; returns the new right-hand run."""
        for ch in r:
            if ch.tag not in TEXT_CHILDREN:
                raise ValueError('cannot split run containing %s: %r' % (ch.tag, run_text(r)))
        right = etree.Element(q('r'))
        rpr = r.find(q('rPr'))
        if rpr is not None:
            right.append(copy.deepcopy(rpr))
        pos = 0
        moving = False
        for ch in [c for c in r if c.tag != q('rPr')]:
            if moving:
                right.append(ch)
                continue
            if ch.tag == q('t'):
                txt = ch.text or ''
                if pos + len(txt) <= k:
                    pos += len(txt)
                    if pos == k:
                        moving = True
                    continue
                cut = k - pos
                left_txt, right_txt = txt[:cut], txt[cut:]
                ch.text = left_txt
                if left_txt != left_txt.strip():
                    ch.set('{%s}space' % XML_NS, 'preserve')
                nt = etree.SubElement(right, q('t'))
                nt.text = right_txt
                if right_txt != right_txt.strip():
                    nt.set('{%s}space' % XML_NS, 'preserve')
                if not left_txt:
                    r.remove(ch)
                moving = True
                pos = k
            elif ch.tag in (q('tab'), q('br'), q('cr')):
                pos += 1
                if pos == k:
                    moving = True
            # lastRenderedPageBreak stays left
        r.addnext(right)
        return right

    def split_at(self, p, k):
        for r, a, b in self.segments(p):
            if a < k < b:
                self.split_run(r, k - a)
                return

    def isolate(self, p, s, e):
        self.split_at(p, s)
        self.split_at(p, e)
        return [r for r, a, b in self.segments(p) if a >= s and b <= e and b > a]

    def pick_rpr(self, p, runs, prefer_before=True):
        """Formatting for inserted text: first non-label run among `runs`, else nearest neighbour."""
        for r in runs:
            if not is_label_run(r) and run_text(r).strip():
                return r.find(q('rPr'))
        allr = [r for r in live_runs(p) if run_text(r)]
        if runs:
            idx = allr.index(runs[0]) if runs[0] in allr else 0
        else:
            idx = 0
        order = list(reversed(allr[:idx])) + allr[idx:] if prefer_before else allr[idx:] + list(reversed(allr[:idx]))
        for r in order:
            if not is_label_run(r) and run_text(r).strip():
                return r.find(q('rPr'))
        return None

    # ── making runs ────────────────────────────────────────────────────────
    @staticmethod
    def _sz(rpr, default=21):
        if rpr is not None:
            s = rpr.find(q('sz'))
            if s is not None:
                return int(s.get(q('val')))
        return default

    def label_rpr(self, label, base_rpr, default_sz=21):
        key = re.match(r'\[(GEX|E|P|O|I)', label).group(1)
        size = max(self._sz(base_rpr, default_sz) - 3, 10)
        rpr = etree.Element(q('rPr'))
        fonts = base_rpr.find(q('rFonts')) if base_rpr is not None else None
        if fonts is not None:
            rpr.append(copy.deepcopy(fonts))
        etree.SubElement(rpr, q('b'))
        etree.SubElement(rpr, q('bCs'))
        etree.SubElement(rpr, q('color')).set(q('val'), LABEL_COLORS[key])
        etree.SubElement(rpr, q('sz')).set(q('val'), str(size))
        etree.SubElement(rpr, q('szCs')).set(q('val'), str(size))
        return rpr

    @staticmethod
    def _set_bold(rpr, bold):
        for tag in ('b', 'bCs'):
            el = rpr.find(q(tag))
            if el is not None:
                rpr.remove(el)
        if bold:
            # b/bCs come after rStyle, rFonts in CT_RPr
            pos = 0
            for i, ch in enumerate(rpr):
                if ch.tag in (q('rStyle'), q('rFonts')):
                    pos = i + 1
            rpr.insert(pos, etree.Element(q('bCs')))
            rpr.insert(pos, etree.Element(q('b')))

    @staticmethod
    def _set_italic(rpr, italic):
        for tag in ('i', 'iCs'):
            el = rpr.find(q(tag))
            if el is not None:
                rpr.remove(el)
        if italic:
            pos = 0
            for i, ch in enumerate(rpr):
                if ch.tag in (q('rStyle'), q('rFonts'), q('b'), q('bCs')):
                    pos = i + 1
            rpr.insert(pos, etree.Element(q('iCs')))
            rpr.insert(pos, etree.Element(q('i')))

    def text_run(self, text, rpr):
        r = etree.Element(q('r'))
        if rpr is not None and len(rpr):
            r.append(rpr)
        parts = re.split(r'(\t|\n)', text)
        for part in parts:
            if part == '':
                continue
            if part == '\t':
                etree.SubElement(r, q('tab'))
            elif part == '\n':
                etree.SubElement(r, q('br'))
            else:
                t = etree.SubElement(r, q('t'))
                t.text = part
                if part != part.strip() or '  ' in part:
                    t.set('{%s}space' % XML_NS, 'preserve')
        return r

    def make_runs(self, text, base_rpr, default_sz=21, markup=True):
        """Runs for `text`: **bold** (markup) and evidence labels get their own formatting."""
        base = copy.deepcopy(base_rpr) if base_rpr is not None else etree.Element(q('rPr'))
        for el in list(base):
            if el.tag in (q('ins'), q('del'), q('rPrChange')):
                base.remove(el)
            if el.tag == q('rStyle') and el.get(q('val')) in ('apple-converted-space', 'CommentReference'):
                base.remove(el)
        runs = []
        chunks = re.split(r'(\*\*.+?\*\*)', text) if markup else [text]
        base_bold = base.find(q('b')) is not None
        for chunk in chunks:
            if not chunk:
                continue
            bold, italic = base_bold, base.find(q('i')) is not None
            if markup and chunk.startswith('**') and chunk.endswith('**') and len(chunk) > 4:
                chunk, bold = chunk[2:-2], True
            for piece in re.split('(%s)' % LABEL_ONE, chunk):
                if not piece:
                    continue
                if LABEL_RE.fullmatch(piece):
                    runs.append(self.text_run(piece, self.label_rpr(piece, base, default_sz)))
                else:
                    rpr = copy.deepcopy(base)
                    self._set_bold(rpr, bold)
                    self._set_italic(rpr, italic)
                    runs.append(self.text_run(piece, rpr))
        return runs

    @staticmethod
    def _is_bold(r):
        rpr = r.find(q('rPr'))
        b = rpr.find(q('b')) if rpr is not None else None
        return b is not None and b.get(q('val')) not in ('0', 'false')

    def _format_split(self, runs, new):
        """When a replaced range starts with a bold lead-in sentence and continues in plain text,
        give the new text the same shape: its first sentence bold, the rest plain."""
        content = [r for r in runs if run_text(r).strip() and not is_label_run(r)]
        if len(content) < 2:
            return None
        first = self._is_bold(content[0])
        lead, k = '', 0
        for r in runs:
            if run_text(r).strip() and not is_label_run(r) and self._is_bold(r) != first:
                break
            lead += run_text(r)
            k += 1
        if k >= len(runs) or not lead.rstrip().endswith(('.', ':')):
            return None
        m = re.search(r'[.:](?=\s|$)', new)
        if not m:
            return None
        rest = [r for r in runs[k:] if run_text(r).strip() and not is_label_run(r)]
        if not rest:
            return None
        return new[:m.end()], new[m.end():], content[0].find(q('rPr')), rest[0].find(q('rPr'))

    # ── tracked text edits ─────────────────────────────────────────────────
    def wrap_del(self, runs):
        groups = []
        for r in runs:
            if groups and groups[-1][-1].getparent() is r.getparent() and groups[-1][-1].getnext() is r:
                groups[-1].append(r)
            else:
                groups.append([r])
        dels = []
        for g in groups:
            d = self.mark('del')
            g[0].addprevious(d)
            for r in g:
                for t in r.findall(q('t')):
                    t.tag = q('delText')
                for it in r.findall(q('instrText')):
                    it.tag = q('delInstrText')
                d.append(r)
            dels.append(d)
        return dels

    def replace_range(self, p, s, e, new, default_sz=21):
        if e > s:
            runs = self.isolate(p, s, e)
            if not runs:
                raise ValueError('nothing to delete at %d..%d in %r' % (s, e, para_text(p)[:60]))
            only_space = all(not run_text(r).strip() for r in runs)
            # Replacing bare whitespace with text that starts a new word: format it like the word
            # that follows, not like a bold lead-in that precedes it.
            base = self.pick_rpr(p, runs, prefer_before=not (only_space and new[:1].isspace()))
            split = self._format_split(runs, new) if new else None
            dels = self.wrap_del(runs)
            if new:
                ins = self.mark('ins')
                dels[-1].addnext(ins)
                if split:
                    head, tail, rpr_head, rpr_tail = split
                    made = self.make_runs(head, rpr_head, default_sz) + self.make_runs(tail, rpr_tail, default_sz)
                else:
                    made = self.make_runs(new, base, default_sz)
                for r in made:
                    ins.append(r)
            return
        if not new:
            return
        # Slide an insertion that starts with the same whitespace as the text after it, so the
        # inserted words start after the space and take the format of the word they precede.
        full = para_text(p)
        while new and new[0].isspace() and s < len(full) and full[s] == new[0]:
            s, new = s + 1, new[1:] + new[0]
        self.split_at(p, s)
        segs = [(r, a, b) for r, a, b in self.segments(p) if b > a]
        prev = [r for r, a, b in segs if b == s]
        nxt = [r for r, a, b in segs if a == s]
        ins = self.mark('ins')
        full = para_text(p)
        word_start = s > 0 and full[s - 1].isspace() and not new[:1].isspace()
        if prev and nxt and word_start:
            ref = nxt[0]
            base = self.pick_rpr(p, [ref], prefer_before=False)
            ref.addprevious(ins)
        elif prev:
            ref = prev[-1]
            base = self.pick_rpr(p, [ref])
            ref.addnext(ins)
        elif nxt:
            ref = nxt[0]
            base = self.pick_rpr(p, [ref], prefer_before=False)
            ref.addprevious(ins)
        else:
            base = None
            p.append(ins)
        for r in self.make_runs(new, base, default_sz):
            ins.append(r)

    @staticmethod
    def _coalesce(ops, a, b):
        def short(i1, i2):
            toks = a[i1:i2]
            if any(t in ('.', ':', ';', '!', '?', '\n', '\t') for t in toks):
                return False  # never merge across a sentence or line boundary
            words = [t for t in toks if t.strip() and re.match(r'\w', t)]
            return len(words) <= 2 and sum(len(t) for t in toks) <= 14

        changed = True
        ops = [list(o) for o in ops]
        while changed:
            changed = False
            for k in range(1, len(ops) - 1):
                if ops[k][0] == 'equal' and ops[k - 1][0] != 'equal' and ops[k + 1][0] != 'equal' \
                        and short(ops[k][1], ops[k][2]):
                    merged = ['replace', ops[k - 1][1], ops[k + 1][2], ops[k - 1][3], ops[k + 1][4]]
                    ops[k - 1:k + 2] = [merged]
                    changed = True
                    break
        return ops

    def edit(self, p, new_text, default_sz=21, whole=False):
        """Tracked word-level edit of paragraph p to read `new_text` (plain text + labels)."""
        old = para_text(p)
        if old == new_text:
            return
        if whole:
            self.replace_range(p, 0, len(old), new_text, default_sz)
            return
        a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new_text)
        assert ''.join(a) == old, 'tokenise old'
        assert ''.join(b) == new_text, 'tokenise new'
        ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        ops = self._coalesce(ops, a, b)
        for tag, i1, i2, j1, j2 in reversed(ops):
            if tag == 'equal':
                continue
            s = sum(len(x) for x in a[:i1])
            e = s + sum(len(x) for x in a[i1:i2])
            self.replace_range(p, s, e, ''.join(b[j1:j2]), default_sz)
        got = para_text(p)
        if got != new_text:
            raise AssertionError('edit mismatch:\n want %r\n got  %r' % (new_text, got))

    def replace_text(self, p, old, new, default_sz=21):
        """Tracked replacement of the unique substring `old` in paragraph p."""
        t = para_text(p)
        i = t.find(old)
        if i < 0 or t.find(old, i + 1) >= 0:
            raise ValueError('substring not unique/absent: %r in %r' % (old, t[:80]))
        self.replace_range(p, i, i + len(old), new, default_sz)

    # ── paragraphs ─────────────────────────────────────────────────────────
    @staticmethod
    def ppr_set(ppr, tag, el=None):
        """Insert or replace child `tag` of pPr at its schema position."""
        old = ppr.find(q(tag))
        if old is not None:
            ppr.remove(old)
        el = el if el is not None else etree.Element(q(tag))
        rank = PPR_ORDER.index(tag)
        pos = len(ppr)
        for i, ch in enumerate(ppr):
            name = etree.QName(ch).localname
            if name in PPR_ORDER and PPR_ORDER.index(name) > rank:
                pos = i
                break
        ppr.insert(pos, el)
        return el

    def mark_para(self, p, kind):
        ppr = p.find(q('pPr'))
        if ppr is None:
            ppr = etree.Element(q('pPr'))
            p.insert(0, ppr)
        rpr = ppr.find(q('rPr'))
        if rpr is None:
            rpr = self.ppr_set(ppr, 'rPr')
        for x in rpr.findall(q('ins')) + rpr.findall(q('del')):
            rpr.remove(x)
        rpr.insert(0, self.mark(kind))

    def new_para(self, text, like, base_rpr='auto', default_sz=21, style=None, page_break_before=False,
                 numbered_like=None, strip_numbering=False, markup=True, keep_next=None, spacing=None):
        p = etree.Element(q('p'))
        p.set(PARA_ID, self.new_para_id())
        p.set(TEXT_ID, '77777777')
        src = like.find(q('pPr')) if like is not None else None
        ppr = copy.deepcopy(src) if src is not None else etree.Element(q('pPr'))
        for bad in ppr.findall(q('sectPr')) + ppr.findall(q('pPrChange')):
            ppr.remove(bad)
        if strip_numbering and ppr.find(q('numPr')) is not None:
            ppr.remove(ppr.find(q('numPr')))
        if numbered_like is not None:
            np_ = numbered_like.find(q('pPr') + '/' + q('numPr'))
            self.ppr_set(ppr, 'numPr', copy.deepcopy(np_))
        if style is not None:
            ps = etree.Element(q('pStyle'))
            ps.set(q('val'), style)
            self.ppr_set(ppr, 'pStyle', ps)
        if page_break_before:
            self.ppr_set(ppr, 'pageBreakBefore')
        if keep_next is True:
            self.ppr_set(ppr, 'keepNext')
        elif keep_next is False and ppr.find(q('keepNext')) is not None:
            ppr.remove(ppr.find(q('keepNext')))
        if spacing is not None:
            sp = etree.Element(q('spacing'))
            for k, v in spacing.items():
                sp.set(q(k), str(v))
            self.ppr_set(ppr, 'spacing', sp)
        p.append(ppr)
        self.mark_para(p, 'ins')
        if base_rpr == 'auto':
            base_rpr = None
            if like is not None:
                cands = [r for r in live_runs(like) if run_text(r).strip() and not is_label_run(r)]
                if cands:
                    base_rpr = cands[0].find(q('rPr'))
        if text:
            ins = self.mark('ins')
            p.append(ins)
            for r in self.make_runs(text, base_rpr, default_sz, markup=markup):
                ins.append(r)
        return p

    def delete_para(self, p):
        runs = [r for r in live_runs(p)]
        # runs already inside my own insertions must not be deleted this way
        if runs:
            self.wrap_del(runs)
        self.mark_para(p, 'del')

    # ── tables ─────────────────────────────────────────────────────────────
    def _cell_para_fill(self, p, text, default_sz, markup=True):
        base = None
        cands = [r for r in live_runs(p) if run_text(r).strip() and not is_label_run(r)]
        if cands:
            base = copy.deepcopy(cands[0].find(q('rPr')))
        for ch in list(p):
            if ch.tag != q('pPr'):
                p.remove(ch)
        self.mark_para(p, 'ins')
        ins = self.mark('ins')
        p.append(ins)
        for r in self.make_runs(text, base, default_sz, markup=markup):
            ins.append(r)

    def insert_row_after(self, tr_ref, texts, like_tr=None, default_sz=18, bold_first=None):
        like = like_tr if like_tr is not None else tr_ref
        tr = copy.deepcopy(like)
        self.fresh_ids(tr)
        trpr = tr.find(q('trPr'))
        if trpr is None:
            trpr = etree.Element(q('trPr'))
            pos = 1 if tr.find(q('tblPrEx')) is not None else 0
            tr.insert(pos, trpr)
        for x in trpr.findall(q('tblHeader')) + trpr.findall(q('ins')) + trpr.findall(q('del')):
            trpr.remove(x)
        trpr.append(self.mark('ins'))
        cells = tr.findall(q('tc'))
        assert len(cells) == len(texts), 'cell count %d != %d' % (len(cells), len(texts))
        for tc, text in zip(cells, texts):
            ps = tc.findall(q('p'))
            for extra in ps[1:]:
                tc.remove(extra)
            paras = text.split('\n\n')
            self._cell_para_fill(ps[0], paras[0], default_sz)
            prev = ps[0]
            for more in paras[1:]:
                np_ = copy.deepcopy(ps[0])
                self.fresh_ids(np_)
                prev.addnext(np_)
                for ch in list(np_):
                    if ch.tag != q('pPr'):
                        np_.remove(ch)
                ins = self.mark('ins')
                np_.append(ins)
                base = ps[0].find('.//' + q('r') + '/' + q('rPr'))
                for r in self.make_runs(more, base, default_sz):
                    ins.append(r)
                prev = np_
        tr_ref.addnext(tr)
        return tr

    def delete_row(self, tr):
        trpr = tr.find(q('trPr'))
        if trpr is None:
            trpr = etree.Element(q('trPr'))
            pos = 1 if tr.find(q('tblPrEx')) is not None else 0
            tr.insert(pos, trpr)
        trpr.append(self.mark('del'))
        for p in tr.iter(q('p')):
            runs = live_runs(p)
            if runs:
                self.wrap_del(runs)

    def delete_table(self, tbl):
        for tr in tbl.findall(q('tr')):
            self.delete_row(tr)

    def new_table(self, like_tbl, widths, rows, header=True, sz=16, head_sz=16, first_col_bold=False,
                  first_col_fill=False, fills=None):
        tbl = etree.Element(q('tbl'))
        tblpr = copy.deepcopy(like_tbl.find(q('tblPr')))
        tblpr.find(q('tblW')).set(q('w'), str(sum(widths)))
        tbl.append(tblpr)
        grid = etree.SubElement(tbl, q('tblGrid'))
        for w in widths:
            etree.SubElement(grid, q('gridCol')).set(q('w'), str(w))
        border = 'D6DFDB'
        for ri, cells in enumerate(rows):
            head = header and ri == 0
            tr = etree.SubElement(tbl, q('tr'))
            tr.set(PARA_ID, self.new_para_id())
            tr.set(TEXT_ID, '77777777')
            ex = etree.SubElement(tr, q('tblPrEx'))
            mar = etree.SubElement(ex, q('tblCellMar'))
            for side in ('top', 'bottom'):
                m = etree.SubElement(mar, q(side))
                m.set(q('w'), '0')
                m.set(q('type'), 'dxa')
            trpr = etree.SubElement(tr, q('trPr'))
            etree.SubElement(trpr, q('cantSplit'))
            if head:
                etree.SubElement(trpr, q('tblHeader'))
            trpr.append(self.mark('ins'))
            assert len(cells) == len(widths), 'row %d has %d cells, want %d' % (ri, len(cells), len(widths))
            for ci, text in enumerate(cells):
                tc = etree.SubElement(tr, q('tc'))
                tcpr = etree.SubElement(tc, q('tcPr'))
                tw = etree.SubElement(tcpr, q('tcW'))
                tw.set(q('w'), str(widths[ci]))
                tw.set(q('type'), 'dxa')
                bds = etree.SubElement(tcpr, q('tcBorders'))
                for side in ('top', 'left', 'bottom', 'right'):
                    b = etree.SubElement(bds, q(side))
                    for k, v in (('val', 'single'), ('sz', '4'), ('space', '0'), ('color', border)):
                        b.set(q(k), v)
                fill = None
                if head or (first_col_fill and ci == 0):
                    fill = 'EEF3F1'
                if fills and (ri, ci) in fills:
                    fill = fills[(ri, ci)]
                if fill:
                    shd = etree.SubElement(tcpr, q('shd'))
                    shd.set(q('val'), 'clear')
                    shd.set(q('color'), 'auto')
                    shd.set(q('fill'), fill)
                tm = etree.SubElement(tcpr, q('tcMar'))
                for side, w in (('top', 70), ('left', 100), ('bottom', 70), ('right', 100)):
                    m = etree.SubElement(tm, q(side))
                    m.set(q('w'), str(w))
                    m.set(q('type'), 'dxa')
                size = head_sz if head else sz
                for ptxt in text.split('\n\n'):
                    p = etree.SubElement(tc, q('p'))
                    p.set(PARA_ID, self.new_para_id())
                    p.set(TEXT_ID, '77777777')
                    ppr = etree.SubElement(p, q('pPr'))
                    sp = etree.SubElement(ppr, q('spacing'))
                    sp.set(q('after'), '40')
                    self.mark_para(p, 'ins')
                    rpr = etree.Element(q('rPr'))
                    if head or (first_col_bold and ci == 0):
                        etree.SubElement(rpr, q('b'))
                        etree.SubElement(rpr, q('bCs'))
                    if head:
                        etree.SubElement(rpr, q('color')).set(q('val'), '0D5754')
                    etree.SubElement(rpr, q('sz')).set(q('val'), str(size))
                    etree.SubElement(rpr, q('szCs')).set(q('val'), str(size))
                    ins = self.mark('ins')
                    p.append(ins)
                    for r in self.make_runs(ptxt, rpr, size):
                        ins.append(r)
        return tbl
