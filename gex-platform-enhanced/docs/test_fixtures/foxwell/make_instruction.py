"""Build the TEST instruction letter: ABN AMRO (test account) instructs Foxwell Survey UK
(test independent engineer) on North Sea e-Methanol. JML, 18 Nov 2026.

Synthetic. Not issued by ABN AMRO Bank N.V.; no legal effect. The PDF is built with
reportlab's invariant mode so the same text always gives the same bytes and sha256.

    backend/venv/bin/python docs/test_fixtures/foxwell/make_instruction.py
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
OUT = HERE / "GEX-TEST-IE-NSEM-001_instruction_Foxwell.pdf"

ss = getSampleStyleSheet()
body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=14)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, spaceAfter=6)
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4)
banner = ParagraphStyle("ban", parent=body, textColor=HexColor("#991b1b"), fontName="Helvetica-Bold")


def p(t, s=body):
    return Paragraph(t, s)


def build() -> str:
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm, invariant=1,
                            title="TEST - Instruction to act as Independent Engineer",
                            author="GEX demonstration (test document)")
    s = []
    s.append(Table([[p("TEST DOCUMENT — SYNTHETIC. Prepared for the GreenEarthX platform demonstration. "
                       "Not issued by ABN AMRO Bank N.V. or any real institution, not addressed to any real "
                       "firm or person, and of no legal effect.", banner)]],
                   colWidths=[170 * mm],
                   style=TableStyle([("BOX", (0, 0), (-1, -1), 1.2, HexColor("#991b1b")),
                                     ("BACKGROUND", (0, 0), (-1, -1), HexColor("#fef2f2")),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 6)])))
    s.append(Spacer(1, 8))
    s.append(p("Instruction to act as Independent Engineer", h1))
    meta = [["Reference", "GEX-TEST-IE-NSEM-001"],
            ["Date", "18 November 2026"],
            ["Instructing party", "ABN AMRO — Structured Lending (GEX test account: Sander de Vries, "
                                  "sander_devries_abnamro_com)"],
            ["Independent Engineer", "TEST — Foxwell Survey UK (GEX tenant foxwell_survey_uk); attention "
                                     "Ewan Stewart, Senior Engineer (ewan_stewart_foxwellsurvey_com)"],
            ["Project", "North Sea e-Methanol (proj_north_sea_e_methanol_203b51), owner HamburgOne.com"],
            ["Platform role", "INDEPENDENT_ENGINEER — gates G0, G1, G3, G5, G6, G11"]]
    s.append(Table([[p(f"<b>{k}</b>"), p(v)] for k, v in meta], colWidths=[42 * mm, 128 * mm],
                   style=TableStyle([("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cbd5e1")),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP")])))

    s.append(p("1. Why we instruct you", h2))
    s.append(p("The instructing party is assessing debt for the project. It will rely on the project's "
               "techno-economic base case (TEA) only after an engineer independent of the owner has reviewed "
               "it. A returns case published on 18 November 2026 (version v1) has been withdrawn from reliance "
               "because its TEA did not price the plant on the owner's saved Cost Basis. This instruction "
               "concerns the replacement base case."))
    s.append(p("2. Scope of the review", h2))
    for t in [
        "The TEA base case for the project that is priced from the owner's saved Cost Basis on the GEX "
        "calculation chain, as recorded there with its exact OpenPyTEA inputs.",
        "Plant boundary: that the TEA prices the same equipment as the saved Cost Basis, and that no "
        "feedstock is both built on site and bought.",
        "Feedstock balance: hydrogen and CO<sub>2</sub> required against on-site supply and stated purchases, "
        "at the stated run time.",
        "Every value the TEA did not receive from the owner and took from OpenPyTEA's defaults (outside "
        "battery limits, design and engineering, working capital, fixed operating cost factors, construction "
        "timing), and whether each is acceptable for this project.",
        "Location, contingency, labour and units of every stream, as stated.",
    ]:
        s.append(p("• " + t))
    s.append(p("Out of scope: returns, debt sizing and financial covenants, which the instructing party "
               "assesses itself; certification of the product.", body))
    s.append(p("3. Deliverable", h2))
    s.append(p("Your review recorded on the GEX platform against the base case: approve, approve with stated "
               "conditions, or reject, with your reasons. The platform will label it an independent review "
               "only because you are appointed by GEX staff on this instruction and your company is not the "
               "owner."))
    s.append(p("4. Independence", h2))
    s.append(p("Please confirm in writing, before you start, any relationship with HamburgOne.com or its "
               "project that could affect your independence. This instruction states none, because none is "
               "known to the instructing party; it is not a confirmation on your behalf."))
    s.append(p("5. Not stated in this test document", h2))
    s.append(p("Fees, timetable, liability, confidentiality and governing law. A real instruction would state "
               "each of them."))
    s.append(Spacer(1, 14))
    s.append(Table([[p("<b>For the instructing party</b><br/><br/>Not signed (test document)"),
                     p("<b>Accepted by the Independent Engineer</b><br/><br/>Not signed (test document)")]],
                   colWidths=[85 * mm, 85 * mm],
                   style=TableStyle([("BOX", (0, 0), (-1, -1), 0.4, HexColor("#cbd5e1")),
                                     ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor("#cbd5e1")),
                                     ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 18)])))
    doc.build(s)
    return hashlib.sha256(OUT.read_bytes()).hexdigest()


if __name__ == "__main__":
    print(OUT.name, "sha256", build())
