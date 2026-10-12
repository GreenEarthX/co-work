"""Minimal docx -> markdown-ish text: headings, paragraphs, tables, tracked changes shown
as accepted (w:ins kept, w:del dropped) unless --show-changes. Index prefix = body child idx."""
import sys, zipfile
from lxml import etree
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
def q(t): return '{%s}%s' % (W, t)

def ptext(p, show=False):
    out = []
    for el in p.iter():
        if el.tag == q('t'):
            anc_del = any(a.tag == q('del') for a in el.iterancestors())
            anc_ins = any(a.tag == q('ins') for a in el.iterancestors())
            if anc_del: continue
            out.append(('[+' + (el.text or '') + '+]') if (show and anc_ins) else (el.text or ''))
        elif el.tag == q('delText'):
            if show: out.append('[-' + (el.text or '') + '-]')
        elif el.tag == q('tab'):
            out.append('\t')
        elif el.tag == q('br'):
            out.append('\n')
    return ''.join(out)

def para_deleted(p):
    rpr = p.find(q('pPr') + '/' + q('rPr'))
    return rpr is not None and rpr.find(q('del')) is not None

def style(p):
    s = p.find(q('pPr') + '/' + q('pStyle'))
    return s.get(q('val')) if s is not None else ''

def main(path, show=False, idx=False):
    z = zipfile.ZipFile(path)
    doc = etree.fromstring(z.read('word/document.xml'))
    body = doc.find(q('body'))
    for i, ch in enumerate(body):
        pre = f'[{i}] ' if idx else ''
        if ch.tag == q('p'):
            t = ptext(ch, show)
            if not t.strip(): continue
            if not show and para_deleted(ch) and not t.strip(): continue
            st = style(ch)
            if st.startswith('Heading') or st.startswith('heading'):
                lvl = ''.join(c for c in st if c.isdigit()) or '1'
                print(f'{pre}{"#"*int(lvl)} {t}')
            elif st in ('Title',):
                print(f'{pre}TITLE: {t}')
            else:
                print(f'{pre}{t}' + (f'   <{st}>' if st and st not in ('Normal','BodyText') and idx else ''))
            print()
        elif ch.tag == q('tbl'):
            print(f'{pre}TABLE:')
            for tr in ch.findall(q('tr')):
                trpr = tr.find(q('trPr'))
                mark = ''
                if trpr is not None and trpr.find(q('ins')) is not None: mark = '(+row) '
                if trpr is not None and trpr.find(q('del')) is not None: mark = '(-row) '
                if not show and mark == '(-row) ': continue
                cells = []
                for tc in tr.findall(q('tc')):
                    cells.append(' / '.join(ptext(p, show) for p in tc.iter(q('p')) if ptext(p, show).strip()))
                print('| ' + mark + ' | '.join(cells) + ' |')
            print()
if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], show='--show' in a, idx='--idx' in a)
