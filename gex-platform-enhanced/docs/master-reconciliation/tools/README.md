# Redline tools (30 Sep 2026)

These scripts produced `GEX-Gates-Master_v2_redline.docx` and `GREENEARTHX_redline.docx`. Every
text change they make is a tracked `<w:ins>`/`<w:del>` by one author, so the reader accepts or
rejects each one in Word.

**Do not rebuild over a delivered redline.** JML edited the master redline in Word on 30 Sep. That
file is now JML's working copy. Both build scripts write to this folder by default (`OUT`
overrides) and refuse to overwrite. Apply later changes as tracked edits on top of JML's latest save.

| File | What it does |
|---|---|
| `redline_lib.py` | Tracked word-level edits, paragraph/row/table insert and delete, labels, bookmarks |
| `build_master.py` | Every master edit, with 26 comments (expects `master_unpacked/`) |
| `build_greenearthx.py` | The GREENEARTHX edits, with 12 comments (expects `greenearthx_unpacked/`) |
| `accepted_view.py` | Accepted-view text of a redline, bold marked, for review |
| `docx2md.py` | Text export of a .docx with body-child indices (the indices the build scripts use) |

Preparing an input (the docx skill's `merge_runs.py` must run first, or phrases are split across runs):

```bash
mkdir master_unpacked && (cd master_unpacked && unzip -q "../../../GEX-Gates-Multi-Party-Review_JML modified.docx")
python3 "<docx skill>/scripts/merge_runs.py" master_unpacked/
python3 build_master.py
python3 "<docx skill>/scripts/office/validate.py" rebuild_check.docx --original "<original>.docx" --author Claude
```

The indices in the build scripts (`P(51)`, `T(197)` …) are body-child positions in the original
document. Every edit checks the paragraph's opening text before changing it, so a mismatch stops
the build instead of editing the wrong paragraph. The skill path is set in each script (`SK`).
