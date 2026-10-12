"""Accepted view of a redline: ins kept, del dropped; **bold** marked; tables as rows; headings as #."""
import re, sys, zipfile
from lxml import etree
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
q=lambda t:'{%s}%s'%(W,t)
def deleted(el): return any(a.tag in (q('del'),) for a in el.iterancestors())
def para(p, bold=True):
    out=[]; cur=None
    for r in p.iter(q('r')):
        if deleted(r): continue
        rpr=r.find(q('rPr')); b = rpr is not None and rpr.find(q('b')) is not None and rpr.find(q('b')).get(q('val')) not in ('0','false')
        txt=''.join((c.text or '') if c.tag==q('t') else '\t' if c.tag==q('tab') else '\n' if c.tag==q('br') else '' for c in r)
        if not txt: continue
        if bold and b and not re.fullmatch(r'\s*(\[[^\]]*\]\s*)+', txt): txt='**'+txt+'**'
        out.append(txt)
    s=''.join(out); s=s.replace('****','')
    return s
def mark_deleted(p):
    rpr=p.find(q('pPr')+'/'+q('rPr')); return rpr is not None and rpr.find(q('del')) is not None
def style(p):
    s=p.find(q('pPr')+'/'+q('pStyle')); return s.get(q('val')) if s is not None else ''
z=zipfile.ZipFile(sys.argv[1]); d=etree.fromstring(z.read('word/document.xml')); body=d.find(q('body'))
bold='--nobold' not in sys.argv
for ch in body:
    if ch.tag==q('p'):
        t=para(ch,bold)
        if not t.strip(): continue
        st=style(ch)
        if st.startswith('Heading'): print('#'*int(st[-1]), t)
        elif st.startswith('TOC'): print('  TOC|', t.replace('\t',' … '))
        else: print(t)
        print()
    elif ch.tag==q('tbl'):
        for tr in ch.findall(q('tr')):
            trpr=tr.find(q('trPr'))
            if trpr is not None and trpr.find(q('del')) is not None: continue
            cells=[' / '.join(para(p,bold) for p in tc.findall(q('p')) if para(p,bold).strip()) for tc in tr.findall(q('tc'))]
            print('| '+' | '.join(cells)+' |')
        print()
