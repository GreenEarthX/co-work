"""Annotate the repaired calculation chain (v2), 18 Nov 2026. Same drawing as annotate.py.
Run: backend/venv/bin/python docs/screenshots/handoff_v4/annotate_chain_v2.py"""
from __future__ import annotations

import annotate as a

a.RAW = a.HERE / "chain_v2" / "raw"
a.OUT = a.HERE / "chain_v2"

SHOTS = [
    ("r01_tea_form.jpg", "v01_tea_form", "Repair 1 — The TEA is run from the plant's own lines; the engineer states what they don't hold", [
        (1, (230, 240), (735, 238), "What the saved plant makes: 17,520 t/yr hydrogen and 50,000 t/yr methanol."),
        (2, (380, 262), (735, 270), "Stated with a basis: process type (it sets OpenPyTEA's capital factors) and location factor."),
        (3, (330, 311), (735, 308), "Each feedstock: made on site (with its basis) and/or bought (price, unit, source)."),
        (4, (220, 336), (735, 345), "Run: every other input comes from cost basis v1."),
        (5, (200, 509), (735, 500), "v1's TEA now FAILS here: it priced a generic train, not these lines."),
    ], None),
    ("r02_tea_v2_run.jpg", "v02_first_v2_run", "Repair 2 — The first v2 run finds a CO2 shortfall", [
        (1, (250, 258), (735, 250), "v1's run is marked: it cannot feed a financing case."),
        (2, (190, 288), (735, 288), "First v2 run: CAPEX €351.0M, OPEX €87.6M/yr, levelised cost €3.08/kg."),
        (3, (200, 329), (735, 323), "All 9 cost basis lines priced at their installed cost."),
        (4, (165, 349), (735, 356), "CO2 FAILS: capture 50 kt/yr against 61,875 t needed."),
        (5, (240, 359), (735, 392), "+€138.9M over the cost basis: OpenPyTEA's OSBL and D&E defaults."),
    ], None),
    ("r03_three_tea_runs.jpg", "v03_v2_all_checks_pass", "Repair 3 — HamburgOne buys the shortfall at the approved €208/t: every check passes", [
        (1, (180, 205), (735, 200), "First v2 run: CO2 short 11,875 t/yr, so it fails."),
        (2, (200, 277), (735, 278), "Current run CLM-MBC-61f3a1083e: the shortfall bought at the registry's approved €208/t."),
        (3, (180, 350), (735, 338), "Every check passes: lines, hydrogen and CO2 balances."),
        (4, (230, 370), (735, 372), "OPEX €90.3M/yr (+€2.7M); CAPEX unchanged at €351.0M."),
        (5, (240, 414), (735, 412), "Lisa could review it only as the owner, labelled not independent; that cannot publish."),
    ], None),
    ("r04_defaults_listed.jpg", "v04_defaults_listed", "Repair 4 — Every OpenPyTEA default still used is listed, with its value", [
        (1, (200, 101), (735, 105), "OSBL 30 % and D&E 30 %: defaults that likely double-count the site, building and grid lines."),
        (2, (230, 170), (735, 170), "Fixed operating cost factors on labour and capital: defaults, listed."),
        (3, (240, 228), (735, 225), "Timing and tax: defaults here; for returns the PF engine is the authority."),
        (4, (250, 252), (735, 258), "The catalogue prices state no price year: taken as 2024, and said."),
        (5, (230, 402), (735, 402), "Financing waits for a TEA reviewed by the appointed independent engineer."),
    ], None),
    ("r05_v1_withdrawn.jpg", "v05_v1_withdrawn", "Repair 5 — v1 is withdrawn from reliance; its contents are kept as the record", [
        (1, (690, 162), (765, 150), "Marked withdrawn."),
        (2, (400, 213), (765, 215), "Reason, date and who withdrew it; ABN AMRO's access revoked."),
        (3, (300, 252), (765, 260), "Needs review: its TEA has since been replaced."),
        (4, (110, 284), (40, 330), "The figures are kept unchanged, as the record. Not to be relied on."),
        (5, (400, 400), (765, 400), "Its chain shows why: an owner's review of a generic-train TEA."),
    ], None),
    ("r06_reviewer_not_yet_appointed.jpg", "v06_reviewer_waiting", "Next — The independent engineer waits for his appointment", [
        (1, (170, 112), (400, 260), "Ewan Stewart (TEST Foxwell Survey UK) signs in, but the chain is refused: GEX staff have not yet appointed him on ABN AMRO's instruction."),
        (2, (90, 18), (300, 30), "Signed in as the test independent engineer."),
    ], None),
]

if __name__ == "__main__":
    for spec in SHOTS:
        print(a.render(*spec).name)
