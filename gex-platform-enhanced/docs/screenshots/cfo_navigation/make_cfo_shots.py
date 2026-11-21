"""Capture the CFO navigation screens on localhost and annotate them (numbered callouts + arrows).
Signs in with the login page's own demo 'fill' button (HamburgOne CEO/CFO, a demo seed account)."""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
APP = "http://localhost:3000"
DPR = 2
RED = (200, 40, 30)
try:
    F = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
    FS = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
except Exception:
    F = FS = ImageFont.load_default()


PAGE = {"pg": None}


def box(loc):
    """Page coordinates (viewport box + scroll), to match full-page clips."""
    b = loc.bounding_box()
    if b is None:
        return None
    sy = PAGE["pg"].evaluate("window.scrollY") if PAGE["pg"] else 0
    return (b["x"], b["y"] + sy, b["x"] + b["width"], b["y"] + sy + b["height"])


def annotate(src, dst, clip, marks, margin=520):
    """marks: [(n, (x0,y0,x1,y1) page px, label)]. A red box round each element, a numbered disc
    beside it with a short arrow into it, and the numbered explanations in a right-hand margin."""
    import math
    im = Image.open(src).convert("RGB")
    W, H = im.size
    d0 = ImageDraw.Draw(im)
    wrapped = []
    for m in marks:
        label = m[2]
        words, line, lines = label.split(), "", []
        for w in words:
            if d0.textlength((line + " " + w).strip(), font=FS) > margin - 90:
                lines.append(line); line = w
            else:
                line = (line + " " + w).strip()
        lines.append(line)
        wrapped.append(lines)
    need = 40 + sum(len(l) * 30 + 34 for l in wrapped)
    CH = max(H, need)
    canvas = Image.new("RGB", (W + margin, CH), "white")
    canvas.paste(im, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W - 1, H - 1], outline=(190, 190, 190), width=2)
    cx0, cy0 = clip[0], clip[1]
    R = 20
    for m in marks:
        n, b, label = m[0], m[1], m[2]
        side = m[3] if len(m) > 3 else "left"
        x0, y0, x1, y1 = [(v - o) * DPR for v, o in zip(b, (cx0, cy0, cx0, cy0))]
        d.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 5], outline=RED, width=4)
        if side == "right":
            dx, dy = x1 + 5 + 70, (y0 + y1) / 2
            tx, ty = x1 + 9, dy
        elif side == "above":
            dx, dy = (x0 + x1) / 2, max(y0 - 5 - 60, R + 4)
            tx, ty = dx, y0 - 9
        elif x0 - 5 - 90 > 0:
            dx, dy = x0 - 5 - 70, (y0 + y1) / 2
            tx, ty = x0 - 9, dy
        else:
            dx, dy = (x0 + x1) / 2, max(y0 - 5 - 60, R + 4)
            tx, ty = dx, y0 - 9
        a = math.atan2(ty - dy, tx - dx)
        sx, sy = dx + R * math.cos(a), dy + R * math.sin(a)
        d.line([sx, sy, tx, ty], fill=RED, width=4)
        for s_ in (0.5, -0.5):
            d.line([tx, ty, tx - 16 * math.cos(a + s_), ty - 16 * math.sin(a + s_)], fill=RED, width=4)
        d.ellipse([dx - R, dy - R, dx + R, dy + R], fill=RED)
        d.text((dx, dy), str(n), fill="white", font=F, anchor="mm")
    y = 40
    for m, lines in zip(marks, wrapped):
        n = m[0]
        lx = W + 28
        d.ellipse([lx, y - R + 12, lx + 2 * R, y + R + 12], fill=RED)
        d.text((lx + R, y + 12), str(n), fill="white", font=F, anchor="mm")
        for k, t in enumerate(lines):
            d.text((lx + 2 * R + 14, y + k * 30), t, fill=(25, 25, 25), font=FS)
        y += len(lines) * 30 + 34
    canvas.save(dst)


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=DPR)
    PAGE["pg"] = pg
    pg.goto(f"{APP}/login"); pg.wait_for_timeout(1500)
    pg.get_by_text("fill →").first.click()
    pg.get_by_role("button", name="Sign in").click()
    pg.wait_for_url("**/projects**", timeout=15000)
    pg.evaluate("localStorage.setItem('gex_selected_project','proj_north_sea_e_methanol_203b51')")

    # 1 — Projects menu → Current Projects
    pg.goto(f"{APP}/projects"); pg.wait_for_timeout(2500)
    proj_tab = pg.locator("[data-topbar] button", has_text="Projects").first
    proj_tab.hover(); pg.wait_for_timeout(600)
    cur = pg.get_by_text("Current Projects", exact=True).first
    clip = (0, 0, 1440, 400)
    pg.screenshot(full_page=True, path=str(OUT / "raw1.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 400})
    annotate(OUT / "raw1.png", OUT / "01_projects_menu.png", clip, [
        (1, box(proj_tab), "Projects menu in the top bar", "above"),
        (2, box(cur), "Current Projects: your company's projects", "right")])
    pg.mouse.move(1000, 700); pg.wait_for_timeout(400)
    pg.goto(f"{APP}/projects"); pg.wait_for_timeout(2500)
    ns = pg.get_by_text("North Sea e-Methanol").first
    ns.scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    nb = box(ns)
    top = max(nb[1] - 300, 0)
    pg.screenshot(full_page=True, path=str(OUT / "raw1b.png"), clip={"x": 0, "y": top, "width": 1440, "height": 560})
    marks = [(1, nb, "Click the project: it becomes the selected project for every screen")]
    sel = pg.get_by_text("North Sea e-Methanol").first.locator("xpath=ancestor::*[self::a or self::button or @role='button'][1]")
    annotate(OUT / "raw1b.png", OUT / "01b_choose_project.png", (0, top), marks)

    # 2 — Finance menu → Deal Structuring → Calculation Chain
    pg.goto(f"{APP}/finance/calculation-chain"); pg.wait_for_timeout(3000)
    fin = pg.locator("[data-topbar] button", has_text="Finance").first
    fin.hover(); pg.wait_for_timeout(700)
    cc = pg.get_by_text("Calculation Chain", exact=True).first
    ccb = box(cc)
    h = int(min(900, (ccb[3] if ccb else 700) + 60))
    pg.screenshot(full_page=True, path=str(OUT / "raw2.png"), clip={"x": 0, "y": 0, "width": 1440, "height": h})
    marks = [(1, box(fin), "Finance menu in the top bar", "above"),
             (2, box(pg.get_by_text("DEAL STRUCTURING").first) or box(pg.get_by_text("Deal Structuring").first), "Deal Structuring section"),
             (3, ccb, "Calculation Chain: cost basis, TEA, financing, returns")]
    annotate(OUT / "raw2.png", OUT / "02_finance_menu.png", (0, 0), [m for m in marks if m[1]])
    pg.mouse.move(700, 600); pg.wait_for_timeout(500)

    # 3 — the Calculation Chain page, step 2: the current run only
    run = pg.get_by_text("CLM-MBC-6c2bc77c3e · from cost basis", exact=False).first
    run.scroll_into_view_if_needed(); pg.wait_for_timeout(400)
    results_btn = pg.get_by_role("button", name="Results").last
    wb_btn = pg.get_by_role("button", name="Download TEA workbook").last
    ref = pg.get_by_text("GEX-TEA-6c2bc77c3e-ac422fb2", exact=False).last
    chip = pg.get_by_test_id("inputs-chip").last
    rnb, rb, wb, refb, chb = box(run), box(results_btn), box(wb_btn), box(ref), box(chip)
    top, bottom = rnb[1] - 16, max(rb[3], wb[3]) + 12
    clip = (0, top, 1440, bottom)
    pg.screenshot(full_page=True, path=str(OUT / "raw3.png"), clip={"x": 0, "y": top, "width": 1440, "height": bottom - top})
    annotate(OUT / "raw3.png", OUT / "03_chain_step2.png", clip, [
        (1, rnb, "The run: its id, the cost basis it priced and its state (SUBMITTED until reviewed)"),
        (2, (refb[0], refb[1], chb[2], chb[3]), "Report reference and inputs check", "above"),
        (3, rb, "Results: opens the results view under the run"),
        (4, wb, "Download TEA workbook: the same report in Excel, with the graphs"),
    ])

    # 4 — results view, Overview
    results_btn.click(); pg.wait_for_timeout(1200)
    rep = pg.locator('[data-testid="tea-run-report"]').first
    rep.scroll_into_view_if_needed()
    pg.evaluate("document.querySelector('[data-testid=\"tea-run-report\"]').scrollIntoView({block:'start'}); window.scrollBy(0,-150)")
    pg.wait_for_timeout(500)
    rb_ = box(rep)
    kg = box(rep.locator('[data-testid="chart-cost-per-kg"]'))
    top, bottom = rb_[1] - 8, min(kg[3] + 12, rb_[1] + 880)
    clip = (0, top, 1440, bottom)
    pg.screenshot(full_page=True, path=str(OUT / "raw4.png"), clip={"x": 0, "y": top, "width": 1440, "height": bottom - top})
    annotate(OUT / "raw4.png", OUT / "04_results_overview.png", clip, [
        (1, box(rep.locator('[data-testid="report-ref"]')), "Report reference: the same reference reprints the same figures"),
        (2, (box(rep.locator('[data-testid="state-chip"]'))[0], box(rep.locator('[data-testid="state-chip"]'))[1],
             box(rep.locator('[data-testid="inputs-chip"]'))[2], box(rep.locator('[data-testid="inputs-chip"]'))[3]),
         "State (SUBMITTED until an independent reviewer confirms) and inputs check (click: the five checks)", "right"),
        (3, box(rep.get_by_role("tablist")), "Six tabs: Overview, Capital, Operating costs, Cost by year, Sensitivity, Gabillon"),
        (4, box(rep.get_by_text("Required price (LCOP)", exact=True).first), "Required price: the headline, with unit, standing and basis"),
        (5, kg, "Graph: where the required price comes from, part by part"),
    ])

    # 5–7 — the graph tabs
    for n, (tab, tid, fname, labels) in enumerate([
        ("Cost by year", "chart-cost-by-year", "05_cost_by_year.png",
         [("Cost by year tab", None), ("Stacked columns: capital while building, then fixed and variable cost, M EUR", "chart")]),
        ("Sensitivity", "tornado", "06_sensitivity.png",
         [("Sensitivity tab", None), ("Each lever moved alone: the LCOP at each end and the range's basis", "chart")]),
        ("Gabillon", "chart-gabillon", "07_gabillon.png",
         [("Gabillon tab", None), ("Gabillon price by year against the required price (red line)", "chart")]),
    ], start=5):
        t = rep.get_by_role("tab", name=tab)
        t.click(); pg.wait_for_timeout(700)
        el = rep.locator(f'[data-testid="{tid}"]')
        pg.evaluate(f"document.querySelector('[data-testid=\"tea-run-report\"]').scrollIntoView({{block:'start'}}); window.scrollBy(0,-150)")
        pg.wait_for_timeout(300)
        tb, eb = box(t), box(el)
        if eb[3] - tb[1] > 820:
            el.scroll_into_view_if_needed(); pg.wait_for_timeout(300); tb, eb = box(t), box(el)
        top = min(tb[1], eb[1]) - 8
        bottom = min(eb[3] + 16, top + 860)
        clip = (0, top, 1440, bottom)
        pg.screenshot(full_page=True, path=str(OUT / f"raw{n}.png"), clip={"x": 0, "y": top, "width": 1440, "height": bottom - top})
        marks = [(1, box(rep.get_by_role("tablist")), labels[0][0] + " (selected, underlined)", "right"), (2, eb, labels[1][0])]
        annotate(OUT / f"raw{n}.png", OUT / fname, clip, [m for m in marks if m[1]])

    # 8 — the GEX administrator buttons are only for administrators: not captured with this account.
    br.close()
for f in OUT.glob("raw*.png"):
    f.unlink()
print(json.dumps(sorted(x.name for x in OUT.glob("*.png"))))
