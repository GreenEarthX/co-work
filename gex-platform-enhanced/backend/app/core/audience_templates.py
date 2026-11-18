"""
Audience templates — suggestions for what an owner might share (handoff v4, task 10).
=====================================================================================
A template lists, per type of party, the DEVEX sections and returns metrics an
owner MIGHT choose to share. It GRANTS NOTHING. Access comes only from the
owner's per-user shares (DEVEX_SHARE:<SECTION>, RETURNS_SHARE:<case version>);
a recipient whose party type matches a template, without a share, sees nothing.

Status: PROPOSED. JML approves templates as GEX defaults; until then they are
offered to the owner as suggestions, labelled as such, and never pre-ticked.
"""
from __future__ import annotations

STATUS = "PROPOSED — not a GEX default until approved by JML; grants nothing"

TEMPLATES: dict[str, dict] = {
    "SENIOR_LENDER": {
        "label": "Senior lender (credit decision)",
        "devex_sections": ["SUMMARY"],
        "returns": True,
        "metrics": ["unlevered_irr", "npv_unlevered", "dscr_min", "dscr_avg", "llcr", "payback_years",
                    "downside_sensitivities"],
        "why": "A lender sizes debt on cash flow cover; it needs the case's debt metrics and downside, "
               "not the development budget.",
    },
    "DFI": {
        "label": "Development finance institution (additionality and mobilisation)",
        "devex_sections": ["SUMMARY", "FUNDING"],
        "returns": True,
        "metrics": ["unlevered_irr", "levered_irr", "npv_unlevered", "dscr_min", "downside_sensitivities"],
        "why": "A DFI assesses whether its terms are needed and what they mobilise; funding by layer shows that.",
    },
    "EQUITY_INVESTOR": {
        "label": "Equity investor",
        "devex_sections": ["SUMMARY", "BREAKDOWN"],
        "returns": True,
        "metrics": ["levered_irr", "npv_levered", "roe_avg_annual", "equity_payback_years",
                    "downside_sensitivities"],
        "why": "An equity investor prices its return and what has already been spent before it enters.",
    },
    "INSURER": {
        "label": "Insurer",
        "devex_sections": [],
        "returns": False,
        "metrics": [],
        "why": "An insurer underwrites risks evidenced at the gates; no financial case is suggested.",
    },
    "ADVISER": {
        "label": "Lenders' adviser / independent engineer",
        "devex_sections": ["SUMMARY", "PACKAGES"],
        "returns": True,
        "metrics": ["unlevered_irr", "dscr_min", "llcr", "provenance"],
        "why": "An adviser reviews the case's provenance and the development package basis.",
    },
}


def suggestions() -> dict:
    """What the owner is shown when choosing what to share. Nothing is applied."""
    return {"status": STATUS, "grants_access": False, "templates": TEMPLATES}
