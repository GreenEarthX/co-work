"""Annotate the input screens that lead to the Returns result (18 Nov 2026).
Same drawing as annotate.py. Run: backend/venv/bin/python docs/screenshots/handoff_v4/annotate_inputs.py"""
from __future__ import annotations

import annotate as a

a.OUT = a.HERE / "inputs"

SHOTS = [
    ("in01_profile_top.jpg", "i1_project_record", "Input 1 — The project record: what the plant is", [
        (1, (425, 344), (640, 344), "Capacity 120 t/day, SUBMITTED by the owner: the source of the 44 kt/yr annual output."),
        (2, (460, 380), (640, 400), "Power, PPAs, electrolyser: UNVERIFIED, not recorded. The TEA needs them; none is entered."),
        (3, (150, 140), (300, 160), "One record per project; every field says whether it is submitted or verified."),
    ], None),
    ("in02_profile_capex.jpg", "i2_project_capex", "Input 2 — CAPEX in the project record becomes the FCI", [
        (1, (425, 332), (640, 332), "CAPEX €250,000,000, SUBMITTED. The Returns screen starts from this as the FCI (€250.0M)."),
        (2, (480, 275), (640, 260), "Cost Basis is linked here as an ESTIMATE — it does not set this CAPEX."),
    ], None),
    ("in03_cost_basis.jpg", "i3_cost_basis", "Input 3 — Cost Basis: equipment build-up to a levelised cost", [
        (1, (300, 262), (300, 360), "Equipment from the catalogue (illustrative: 120 MW PEM + 50 kt/yr methanol reactor): €126.4M installed."),
        (2, (590, 248), (690, 230), "Levelised cost €970/t against a €1,250/t market reference: competitive."),
        (3, (560, 269), (690, 290), "67.5 kt/yr from this equipment — not the 44 kt/yr of the project record. Nothing reconciles the two."),
        (4, (605, 156), (470, 160), "'Save to project (not yet available)': this result goes nowhere — not to the TEA, not to Returns."),
    ], None),
    ("in04_tea_none.jpg", "i4_tea", "Input 4 — The TEA: the reviewed base case Returns should use", [
        (1, (300, 356), (300, 450), "No base case: no TEA has been run or approved for this project. No screen runs one or approves one."),
        (2, (720, 232), (620, 300), "Working currency for TEA runs (EUR); OpenPyTEA computes in USD and GEX converts."),
    ], None),
    ("in05_devex_brief.jpg", "i5_devex", "Input 5 — DEVEX: the owner's pre-FID spend", [
        (1, (60, 212), (250, 300), "€850k pre-FID spend: one package, read from the package register."),
        (2, (110, 546), (330, 470), "The package: Owner's Engineer & Site Diligence, FEL 1, Class 5 estimate, funded by equity."),
        (3, (260, 441), (600, 470), "No spend wave recorded, so the €850k is placed in one year before FID."),
    ], None),
    ("in06_returns_inputs_a.jpg", "i6_returns_inputs", "Input 6 — Returns: the operating and financing inputs", [
        (1, (40, 333), (560, 300), "Starting values are ILLUSTRATIVE: typed here, not taken from the TEA or an agreed term sheet."),
        (2, (150, 418), (230, 448), "FCI €250M: the project record's CAPEX."),
        (3, (440, 418), (520, 448), "Revenue €55M and OPEX €22M in year 1, with growth rates: typed."),
        (4, (150, 545), (260, 575), "Financing at FID: debt €162.5M (65 %), 5.5 %, 15 years: typed."),
    ], None),
    ("in07_returns_inputs_b.jpg", "i7_hurdle_devex", "Input 7 — Hurdle rate build-up and DEVEX", [
        (1, (150, 305), (330, 335), "Hurdle build-up: risk-free 3 %, beta 1.2, ERP 5.5 %, technology premium 3 %, project premium 1 %."),
        (2, (740, 412), (620, 380), "DEVEX €0.85M comes from the DEVEX brief automatically ('the pre-FID package total')."),
        (3, (300, 466), (480, 495), "Construction schedule and COD empty: the engine runs the SCREENING case."),
        (4, (210, 550), (480, 575), "Boundary: full project (pre-FID spend before year 0); scenario BASE."),
    ], None),
    ("in08_returns_calculate.jpg", "i8_calculate", "Input 8 — Calculate: the PF engine computes the result", [
        (1, (400, 492), (560, 465), "Ramp-up empty: full output from year 1 (the screening case)."),
        (2, (100, 530), (260, 570), "Calculate sends these inputs to the PF engine (:8001). The result is the screen you saw."),
    ], None),
]

if __name__ == "__main__":
    for spec in SHOTS:
        print(a.render(*spec).name)
