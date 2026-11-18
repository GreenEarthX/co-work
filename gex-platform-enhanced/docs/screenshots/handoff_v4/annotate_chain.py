"""Annotate the calculation-chain acceptance demonstration (18 Nov 2026).
Same drawing as annotate.py. Run: backend/venv/bin/python docs/screenshots/handoff_v4/annotate_chain.py"""
from __future__ import annotations

import annotate as a

a.RAW = a.HERE / "chain" / "raw"
a.OUT = a.HERE / "chain"

SHOTS = [
    ("c01_cost_basis_computed.jpg", "k01_cost_basis_compute", "Step 1 — Engineering builds the plant on Cost Basis (Mark Puntz, HamburgOne)", [
        (1, (250, 137), (380, 420), "Nine catalogue lines: 120 MW PEM, 50 kt/yr methanol reactor, CO2 capture, water, storage, site, building, metering, DCS — €192.9M installed."),
        (2, (750, 110), (560, 440), "Compute: run time 90 %, power €55/MWh, Germany, WACC 8 %, 25 years. Nothing is stored yet."),
        (3, (630, 190), (480, 490), "'67.5k t/yr' adds the electrolyser's hydrogen (17.5 kt) to the methanol (50 kt). The chain counts methanol only."),
    ], None),
    ("c02_cost_basis_saved.jpg", "k02_cost_basis_saved", "Step 1 — Save as cost basis version v1", [
        (1, (594, 110), (430, 430), "Saved as v1: the server recomputes from the configuration and hashes configuration + result (sha256 5a0a40fb…)."),
        (2, (680, 110), (520, 480), "Next: the Calculation Chain, where every later step cites this saved version."),
        (3, (155, 18), (330, 22), "Saved by the owner's engineer. A bank cannot save a cost basis (403)."),
    ], None),
    ("c03_tea_run_awaiting_review.jpg", "k03_tea_run", "Step 2 — The TEA is run FROM cost basis v1 (Mark Puntz)", [
        (1, (622, 227), (735, 262), "Run TEA from v1: nameplate, run time, power price, contingency, WACC and life are derived from v1. Nothing typed."),
        (2, (200, 327), (735, 318), "Base case CLM-MBC-0fa58f34bd, SUBMITTED. OpenPyTEA 3.0.0, SCREENING: CAPEX €175.3M, OPEX €52.4M/yr."),
        (3, (190, 350), (735, 352), "PASS: priced from this saved cost basis; nameplate carried forward."),
        (4, (260, 371), (735, 385), "REPORTED, not judged: the TEA is 17 % below the catalogue on CAPEX and OPEX. No tolerance has been agreed."),
        (5, (300, 410), (735, 420), "Mark ran it, so Mark cannot review it: no review controls are offered to him."),
    ], None),
    ("c04_review_before.jpg", "k04_review", "Step 3 — Review by someone other than who ran it (Lisa Friedrich, Executive)", [
        (1, (160, 14), (330, 22), "Signed in as Lisa Friedrich, the owner's executive."),
        (2, (300, 300), (735, 290), "She reviews with the reconciliation in front of her."),
        (3, (245, 355), (735, 335), "Three conditions: screening-grade (re-base on FEED); explain the 17 % gap; owner review only."),
        (4, (428, 358), (735, 380), "Approve with conditions."),
    ], None),
    ("c05_reviewed_and_financing_form.jpg", "k05_reviewed", "Step 3 → 4 — Reviewed, and labelled for what it is", [
        (1, (330, 186), (735, 180), "VERIFIED, 'Owner's internal review — not independent'. Only an appointed independent engineer reviews as INDEPENDENT."),
        (2, (330, 206), (735, 218), "The conditions are stored on the base case and travel with every version that cites it."),
        (3, (200, 346), (735, 330), "The financing case is built on this reviewed TEA only: its FCI is the reviewed CAPEX, €175.3M."),
        (4, (480, 363), (735, 380), "Each term needs a source. None is verified until a lender confirms it."),
    ], None),
    ("c06_financing_saved_returns_form.jpg", "k06_financing_and_returns", "Step 4 → 5 — Financing case saved; Returns states only what the chain lacks", [
        (1, (290, 237), (735, 232), "Financing v1 hashed: debt €113.9M (65 % = approved OIES reference × reviewed CAPEX), 6 %, 15 yr, no grant."),
        (2, (250, 441), (735, 420), "Stated by the owner, each with a source: price, tax, depreciation, cost of equity."),
        (3, (480, 441), (735, 470), "Price €1,200/t: the approved reference value (its provenance is not recorded); no offtake contract."),
        (4, (190, 511), (430, 535), "Publish. FCI, OPEX, life and debt are set by the server from the chain; a typed FCI is refused."),
    ], None),
    ("c07_published_sources.jpg", "k07_published_sources", "Step 5 — The published version stores its source versions", [
        (1, (190, 312), (735, 300), "Base case (chain) v1, sha256 c5de242046c1…: immutable, like every published case."),
        (2, (200, 355), (60, 360), "Cost Basis v1 (hash)."),
        (3, (400, 392), (735, 420), "TEA: run by Mark, reviewed by Lisa — owner's internal review, with its conditions."),
        (4, (560, 362), (735, 360), "Financing case v1 (hash)."),
        (5, (180, 470), (60, 470), "Identity checks PASS: each step cites the one before."),
    ], None),
    ("c08_published_checks_assumptions.jpg", "k08_checks_assumptions", "Step 5 — Reconciliation checks and remaining assumptions, stored with the version", [
        (1, (170, 205), (60, 205), "Seven identity checks PASS."),
        (2, (240, 251), (735, 230), "Revenue volume: 50,000 t/yr × 0.9 = 45,000 t/yr sold."),
        (3, (240, 264), (735, 270), "Project record €250M vs reviewed TEA €175.3M: −€74.7M (−29.9 %). Reported."),
        (4, (190, 400), (60, 400), "13 remaining assumptions with sources: ASSUMPTION (stated) or DECLARED (cost basis). None verified."),
    ], None),
    ("c09_share_form.jpg", "k09_share", "Step 6 — The owner shares exactly this version with one bank user", [
        (1, (150, 278), (735, 270), "One named user: Sander de Vries, ABN AMRO."),
        (2, (300, 278), (735, 310), "'v1 only': later versions are not opened unless the owner chooses 'this case and later versions'."),
        (3, (690, 110), (735, 160), "The other versions say 'inputs typed, not traced': a reader can tell them apart."),
    ], None),
    ("c10_shared.jpg", "k10_shared", "Step 6 — Shared: read-only, revocable, audited", [
        (1, (130, 314), (735, 290), "Active share on version eaf52a55 for sander_devries_abnamro_com."),
        (2, (673, 314), (735, 345), "Revoke closes every path on the next request."),
    ], None),
    ("c11_bank_projects.jpg", "k11_bank_projects", "Step 7 — The bank's project list (Sander de Vries, ABN AMRO)", [
        (1, (110, 18), (330, 22), "Signed in as the bank."),
        (2, (100, 183), (300, 300), "North Sea e-Methanol appears because the owner shared a returns case: 'Shared with you, read-only'."),
        (3, (325, 182), (520, 260), "No molecule: the share does not disclose one (it wrongly said H2; fixed today)."),
    ], None),
    ("c12_bank_version.jpg", "k12_bank_version", "Step 7 — The bank reads the SAME version", [
        (1, (650, 172), (755, 140), "Same sha256 c5de242046c1, 'traced to a saved chain'."),
        (2, (110, 212), (40, 160), "The owner's figures, not recomputed: project IRR −10.0 %, equity IRR −20.1 %."),
        (3, (270, 242), (40, 290), "DEVEX and dated pre-FID figures are withheld: only RETURNS was shared."),
        (4, (400, 330), (755, 330), "Where the figures came from: cost basis, TEA with its review standing, financing."),
        (5, (300, 450), (40, 450), "Every reconciliation check."),
    ], None),
    ("c13_bank_assumptions.jpg", "k13_bank_assumptions", "Step 7 — The bank sees every remaining assumption and what it means", [
        (1, (200, 330), (40, 330), "All 13 remaining assumptions, with their sources."),
        (2, (300, 250), (755, 250), "The €74.7M gap between the project record and the reviewed TEA is disclosed too."),
        (3, (110, 520), (300, 540), "DSCR 0.13x: at €1,200/t the plant does not service this debt. The chain shows it; it does not hide it."),
    ], None),
    ("c14_bank_refused_chain.jpg", "k14_bank_refused", "Step 7 — The chain itself stays the owner's", [
        (1, (400, 160), (400, 320), "The bank cannot open the Calculation Chain: the screen refuses, and the server answers 403 OWNER_ONLY."),
    ], None),
]

if __name__ == "__main__":
    for spec in SHOTS:
        print(a.render(*spec).name)
