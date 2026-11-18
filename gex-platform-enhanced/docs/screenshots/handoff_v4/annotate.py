"""Annotate the handoff v4 screenshots: numbered markers, arrows to the element, and a
legend strip under each image. Run with the backend venv (Pillow):

    backend/venv/bin/python docs/screenshots/handoff_v4/annotate.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
RAW, OUT = HERE / "raw", HERE
RED, WHITE, INK, PAPER = (220, 38, 38), (255, 255, 255), (15, 23, 42), (248, 250, 252)


def font(size: int, bold: bool = False):
    for name in (("Arial Bold.ttf" if bold else "Arial.ttf"), "Helvetica.ttc", "DejaVuSans.ttf"):
        for base in ("/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/", "/Library/Fonts/"):
            try:
                return ImageFont.truetype(base + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


F_NUM, F_TXT, F_TITLE = font(15, True), font(14), font(17, True)

# (raw file, output name, title, [(n, target_xy, marker_xy, legend text)], box)
# box: optional (x0, y0, x1, y1) outlined in red around the key region.
SHOTS = [
    ("83njmh.jpg", "01_owner_returns_start", "Owner (HamburgOne finance/executive) opens Returns — North Sea e-Methanol", [
        (1, (225, 25), (330, 30), "Signed in as the project OWNER: Lisa Friedrich, Executive, HamburgOne."),
        (2, (150, 212), (330, 212), "Published returns cases: what others may be shown. Nothing is shown until the owner publishes."),
        (3, (230, 271), (470, 300), "Starting values are ILLUSTRATIVE: the owner replaces them before reading any result."),
    ], None),
    ("wvkcrv.jpg", "02_screening_case", "Step 1 — Calculate the SCREENING case (FCI in full at year 0)", [
        (1, (60, 144), (230, 120), "The engine labels the method: screening case, full-project boundary, scenario BASE."),
        (2, (70, 320), (70, 245), "Unlevered (project) IRR 10.9 % against the project hurdle 8.1 % — shown WITH NPV."),
        (3, (420, 320), (420, 245), "Levered (equity) IRR 18.2 %, kept separate from the project return."),
        (4, (100, 515), (230, 560), "DSCR covenant test: GEX proposed 1.25x is NOT in force → 'no approved threshold — no pass/fail'."),
        (5, (545, 500), (690, 540), "LLCR computed by the engine (validated); no decision test is wired to an LLCR floor yet."),
    ], (20, 445, 780, 555)),
    ("o8xhct.jpg", "03_screening_downside", "Step 2 — Downside sensitivities are shown with every result", [
        (1, (90, 357), (300, 345), "Ten shocks (CAPEX, COD delay, revenue, OPEX, interest rate): each re-runs the whole model."),
        (2, (85, 545), (280, 560), "Revenue −20 %: unlevered IRR 6.3 %, project NPV negative — the downside a lender reads."),
        (3, (700, 410), (740, 330), "Each row carries its DSCR minimum and LLCR."),
    ], (20, 340, 780, 600)),
    ("ghk8dm.jpg", "04_scheduled_inputs", "Step 3 — SCHEDULED case: construction years, a part-year COD and ramp-up", [
        (1, (700, 153), (560, 130), "COD 30 months after FID → the first operating year is a half year."),
        (2, (730, 261), (560, 235), "Ramp-up: 60 % then 85 % of full output in the first operating years."),
        (3, (70, 300), (200, 300), "Calculate (the construction schedule 90 / 100 / 60 €M reconciles to the FCI)."),
        (4, (60, 353), (300, 372), "The engine names the method: SCHEDULED case."),
        (5, (60, 543), (230, 525), "Unlevered IRR falls to 8.2 % (screening said 10.9 %): timing matters."),
    ], None),
    ("ismwtz.jpg", "05_screening_vs_scheduled", "Step 4 — Both methods side by side, with both cash-flow timelines", [
        (1, (440, 294), (440, 240), "Screening 10.91 % vs scheduled 8.22 %: the difference is stated, not hidden."),
        (2, (680, 448), (690, 400), "Equity invested rises by the €10.2M interest during construction."),
        (3, (110, 480), (300, 470), "Year-by-year cash flows of both cases (year 0 = FID; DEVEX before it)."),
    ], None),
    ("uewiyj.jpg", "06_scheduled_debt_and_downside", "Step 5 — Debt metrics and downside of the scheduled case", [
        (1, (55, 185), (230, 175), "DSCR minimum 0.68x in the half first year — shown, but not judged: no approved floor."),
        (2, (150, 205), (360, 230), "The policy line names the status: GEX proposed, not in force."),
        (3, (90, 277), (300, 280), "Downside table recomputed on the scheduled case."),
    ], None),
    ("whdfat.jpg", "07_provenance", "Step 6 — Calculation provenance travels with the figures", [
        (1, (290, 242), (470, 225), "Model and version: gex_pf_engine, core.returns v1.3.0."),
        (2, (300, 261), (560, 262), "TEA case NOT_SUPPLIED: the inputs are the caller's own — said plainly."),
        (3, (240, 296), (560, 300), "Inputs fingerprint (sha256) and computation time."),
        (4, (250, 365), (560, 370), "Validation checks run, each with its outcome (all PASS)."),
        (5, (270, 444), (560, 440), "Validity: a verified case is not an assured outcome."),
    ], (20, 205, 780, 465)),
    ("5e12mt.jpg", "08_published_cases", "Step 7 — The owner PUBLISHES cases (immutable, versioned, hashed)", [
        (1, (147, 229), (420, 205), "A FROM-FID case: pre-FID spend treated as sunk, labelled as such."),
        (2, (130, 286), (420, 265), "The FULL-PROJECT case: pre-FID spend before year 0."),
        (3, (600, 300), (660, 320), "Identity: boundary, model, rules 4.9.0, evidence fingerprint, TEA, date, sha256."),
        (4, (640, 350), (520, 390), "Publish a new version from the calculator's inputs (earlier versions stay unchanged)."),
        (5, (80, 451), (230, 430), "Share panel: per user, read-only, expirable, revocable."),
    ], None),
    ("fd0gtp.jpg", "09_audience_suggestions", "Step 8 — Audience suggestions: PROPOSED, they grant nothing", [
        (1, (220, 378), (470, 350), "Suggestions are PROPOSED until JML approves; they never grant access."),
        (2, (90, 397), (300, 430), "What a senior lender would typically need: IRR, NPV, DSCR, LLCR, downside."),
    ], (20, 370, 780, 490)),
    ("48uv81.jpg", "10_share_returns_case", "Step 9 — The owner shares ONE case with the bank (NORD/LB)", [
        (1, (330, 299), (330, 265), "Chosen: 'this case and later versions' (or one version only)."),
        (2, (615, 299), (680, 265), "Share — read-only."),
        (3, (718, 353), (718, 400), "Active share, with Revoke on the same line."),
        (4, (660, 374), (500, 410), "An earlier share, already revoked, stays listed (audit)."),
    ], None),
    ("audt6z.jpg", "11_share_devex_summary", "Step 10 — The owner shares the DEVEX SUMMARY section only", [
        (1, (60, 343), (230, 300), "Shared with the bank: SUMMARY (totals) — no breakdown, funding or packages."),
        (2, (745, 343), (745, 300), "Revoke closes every path at once."),
        (3, (60, 452), (230, 500), "Each section opens only itself: none other is ticked."),
    ], None),
    ("v64k74.jpg", "12_bank_sees_shared_case", "Step 11 — The BANK signs in: the shared case is listed", [
        (1, (140, 25), (330, 30), "Signed in as the bank: Henrik Vost, NORD/LB."),
        (2, (130, 231), (420, 210), "The owner's published case — the only one shared."),
        (3, (215, 302), (420, 330), "The calculator is labelled 'your own inputs, not the owner's case'."),
    ], None),
    ("3yi3e5.jpg", "13_bank_reads_owner_case", "Step 12 — The bank reads the OWNER's figures, not a recalculation", [
        (1, (50, 327), (230, 300), "11.0 % / €44.0M: identical to the owner's published version."),
        (2, (160, 391), (420, 380), "What is withheld is stated: dated pre-FID figures (FUNDING not shared)."),
        (3, (150, 465), (420, 470), "The covenant test reads the same for the bank: no approved threshold."),
    ], None),
    ("2kt6t4.jpg", "14_bank_devex_summary", "Step 13 — The bank's DEVEX brief: SUMMARY only, no return generated", [
        (1, (350, 195), (350, 290), "'Shared with you by the project's owner, read-only … summary'. Each read is recorded."),
        (2, (130, 243), (330, 380), "This project records no pre-FID spend — said, not shown as a figure."),
    ], None),
    ("8xm4kr.jpg", "15_bank_spend_wave_refused", "Step 14 — FUNDING was not shared: the spend wave is refused", [
        (1, (400, 168), (400, 260), "Refused with the reason — never an empty table that looks like 'nothing recorded'."),
    ], None),
    ("ka7a9e.jpg", "16_bank_package_register", "Step 15 — Package register (no packages on this project)", [
        (1, (400, 260), (400, 420), "No packages on this project — true for the owner too."),
        (2, (733, 172), (640, 250), "DEFECT (for JML): 'New package' is offered to a bank; the server refuses the write."),
    ], None),
    ("666dtu.png", "17_owner_revokes", "Step 16 — The owner REVOKES the returns share", [
        (1, (720, 63), (560, 63), "Status now 'revoked'."),
    ], None),
    ("b2m52n.jpg", "18_bank_after_revoke_returns", "Step 17 — After revocation: the bank's Returns view is closed", [
        (1, (330, 223), (330, 300), "'No returns case of this project has been shared with you' — at the next request."),
    ], None),
    ("mek2a8.jpg", "19_bank_after_revoke_brief", "Step 18 — After revocation: the DEVEX brief is closed too", [
        (1, (400, 186), (400, 300), "Refused, and it says that Returns access does not include pre-FID data."),
    ], None),
    ("s4seiy.jpg", "20_gap_analysis_not_recorded", "Gap Analysis: a project with no structuring inputs of its own", [
        (1, (400, 233), (400, 320), "No inputs recorded → no gaps computed. Never a borrowed case (Breizh quarantined)."),
        (2, (650, 170), (560, 240), "Counters read zero rather than invent gaps."),
    ], None),
    ("irhhvz.jpg", "21_finding_brief_screen_role", "Finding: the owner's DEVEX brief screen is role-gated for a bank", [
        (1, (400, 230), (400, 380), "The bank uses its own screen, 'Shared DEVEX Brief' (step 13). Listed for JML."),
    ], None),
]


def arrow(d: ImageDraw.ImageDraw, start, end, color=RED, width=3):
    d.line([start, end], fill=color, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 11
    pts = [end,
           (end[0] - size * math.cos(ang - math.pi / 7), end[1] - size * math.sin(ang - math.pi / 7)),
           (end[0] - size * math.cos(ang + math.pi / 7), end[1] - size * math.sin(ang + math.pi / 7))]
    d.polygon(pts, fill=color)


def wrap(text: str, width_px: int, f) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if f.getlength(trial) <= width_px:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def render(raw: str, name: str, title: str, marks, box) -> Path:
    img = Image.open(RAW / raw).convert("RGB")
    if img.width != 800:
        img = img.resize((800, round(img.height * 800 / img.width)))
    d = ImageDraw.Draw(img)
    if box:
        d.rectangle(box, outline=RED, width=2)
    for n, target, marker, _ in marks:
        # stop the arrow at the target, start it at the marker's edge
        dx, dy = target[0] - marker[0], target[1] - marker[1]
        dist = math.hypot(dx, dy) or 1
        start = (marker[0] + dx / dist * 15, marker[1] + dy / dist * 15)
        if dist > 20:
            arrow(d, start, target)
        r = 14
        d.ellipse([marker[0] - r, marker[1] - r, marker[0] + r, marker[1] + r], fill=RED, outline=WHITE, width=2)
        d.text(marker, str(n), font=F_NUM, fill=WHITE, anchor="mm")
    # title bar + legend strip
    legend = []
    for n, _, _, text in marks:
        legend.append((n, wrap(text, 740, F_TXT)))
    legend_h = 16 + sum(len(lines) * 20 + 8 for _, lines in legend)
    out = Image.new("RGB", (800, 40 + img.height + legend_h), PAPER)
    od = ImageDraw.Draw(out)
    od.rectangle([0, 0, 800, 40], fill=INK)
    od.text((14, 20), title, font=F_TITLE, fill=WHITE, anchor="lm")
    out.paste(img, (0, 40))
    y = 40 + img.height + 10
    for n, lines in legend:
        od.ellipse([14, y, 38, y + 24], fill=RED)
        od.text((26, y + 12), str(n), font=F_NUM, fill=WHITE, anchor="mm")
        for i, line in enumerate(lines):
            od.text((48, y + 3 + i * 20), line, font=F_TXT, fill=INK)
        y += len(lines) * 20 + 8
    path = OUT / f"{name}.png"
    out.save(path, optimize=True)
    return path


if __name__ == "__main__":
    for spec in SHOTS:
        print(render(*spec).name)
