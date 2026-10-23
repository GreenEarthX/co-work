#!/usr/bin/env python3
"""Accept every tracked change in a .docx's document.xml (no LibreOffice on this machine).

Word's semantics: inserted content stays, deleted content goes; a row or paragraph whose
mark is deleted goes (an emptied paragraph with a deleted mark is removed); insertion
markers and property-change records are dropped, keeping the current properties."""
import shutil
import sys
import zipfile

from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def q(t):
    return '{%s}%s' % (W, t)


def unwrap(el):
    parent, i = el.getparent(), el.getparent().index(el)
    for k, child in enumerate(list(el)):
        parent.insert(i + k, child)
    tail = el.tail
    parent.remove(el)
    return tail


def accept(root):
    n = {'del': 0, 'ins': 0, 'rows_del': 0, 'paras_del': 0, 'prop_changes': 0, 'tables_del': 0}
    for tag in ('pPrChange', 'rPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange', 'sectPrChange', 'tblGridChange'):
        for el in list(root.iter(q(tag))):
            el.getparent().remove(el)
            n['prop_changes'] += 1
    for tr in list(root.iter(q('tr'))):            # rows: deleted go, inserted lose the marker
        trpr = tr.find(q('trPr'))
        if trpr is None:
            continue
        if trpr.find(q('del')) is not None:
            tr.getparent().remove(tr)
            n['rows_del'] += 1
            continue
        for m in trpr.findall(q('ins')):
            trpr.remove(m)
    for tbl in list(root.iter(q('tbl'))):          # a table with no rows left goes too
        if tbl.find(q('tr')) is None:
            tbl.getparent().remove(tbl)
            n['tables_del'] += 1
    for el in list(root.iter(q('del'), q('moveFrom'))):   # run-level deletions
        if el.getparent() is not None and el.getparent().tag != q('rPr'):
            el.getparent().remove(el)
            n['del'] += 1
    for el in list(root.iter(q('ins'), q('moveTo'))):      # run-level insertions: keep content
        if el.getparent() is not None and el.getparent().tag != q('rPr'):
            unwrap(el)
            n['ins'] += 1
    for p in list(root.iter(q('p'))):              # paragraph marks
        rpr = p.find(q('pPr') + '/' + q('rPr'))
        if rpr is None:
            continue
        for m in rpr.findall(q('ins')):
            rpr.remove(m)
        dm = rpr.find(q('del'))
        if dm is not None:
            rpr.remove(dm)
            has_content = any(r.find(q('t')) is not None or r.find(q('tab')) is not None
                              for r in p.iter(q('r')))
            if has_content:   # merge into the next paragraph, as Word does
                nxt = p.getnext()
                assert nxt is not None and nxt.tag == q('p'), 'deleted mark with content and no next paragraph'
                for child in [c for c in p if c.tag != q('pPr')]:
                    nxt.insert(1 if nxt.find(q('pPr')) is not None else 0, child)
            p.getparent().remove(p)
            n['paras_del'] += 1
    left = [el.tag for el in root.iter(q('ins'), q('del'), q('moveFrom'), q('moveTo'))]
    assert not left, f'tracked markup left: {left[:5]}'
    return n


def main(src, dst):
    shutil.copyfile(src, dst + '.tmp')
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                root = etree.fromstring(data)
                print(accept(root))
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            zout.writestr(item, data)
    import os
    os.remove(dst + '.tmp')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
