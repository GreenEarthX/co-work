"""
A buyer's requirements on an RFQ (Phase 1; alembic 117) — validated here, nowhere else.

Every key is optional; a key that is present must be valid, or the RFQ is refused with the
reason. `mandatory` names the requirements that must hold for a candidate to be eligible; the
rest are preferences that rank (the compatibility step reads both). The vocabulary is shared with
the product record (core/product_record.PARAMETERS, CI bases) and the typed delivery clause
(trading_book/clauses.INCOTERMS), so a requirement and an offer always speak the same words.
"""
from __future__ import annotations

from typing import Any

from app.core.product_record import CI_BASES, PARAMETERS
from app.trading_book.clauses import INCOTERMS

EVIDENCE_LEVELS = ("submitted", "verified")
PHYSICAL_FORMS = ("gas", "compressed_gas", "liquid", "liquefied_gas")
KEYS = ("max_ci_gco2e_mj", "ci_min_basis", "regimes", "accepted_schemes", "min_evidence_state", "physical_form",
        "quality_limits", "incoterms", "named_place", "delivery_country", "mandatory")
CHECKABLE = ("max_ci_gco2e_mj", "ci_min_basis", "regimes", "accepted_schemes", "min_evidence_state", "physical_form",
             "quality_limits", "incoterms", "delivery_country")


def _strings(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def errors(req: dict) -> list[str]:
    """Why these requirements are invalid (empty list: valid)."""
    if not isinstance(req, dict):
        return ["requirements are an object"]
    out = [f"unknown requirement {k!r}" for k in req if k not in KEYS]
    if "max_ci_gco2e_mj" in req and not (isinstance(req["max_ci_gco2e_mj"], (int, float))
                                         and req["max_ci_gco2e_mj"] >= 0):
        out.append("max_ci_gco2e_mj is a non-negative number (gCO2e/MJ)")
    if "ci_min_basis" in req and req["ci_min_basis"] not in CI_BASES:
        out.append(f"ci_min_basis is one of {', '.join(CI_BASES)}")
    for k in ("regimes", "accepted_schemes"):
        if k in req and not _strings(req[k]):
            out.append(f"{k} is a list of names")
    if "min_evidence_state" in req and req["min_evidence_state"] not in EVIDENCE_LEVELS:
        out.append(f"min_evidence_state is one of {', '.join(EVIDENCE_LEVELS)}")
    if "physical_form" in req and req["physical_form"] not in PHYSICAL_FORMS:
        out.append(f"physical_form is one of {', '.join(PHYSICAL_FORMS)}")
    if "quality_limits" in req:
        q = req["quality_limits"]
        if not isinstance(q, dict):
            out.append("quality_limits maps a parameter to {min, max}")
        else:
            for p, lim in q.items():
                if p not in PARAMETERS:
                    out.append(f"unknown quality parameter {p!r}")
                elif not isinstance(lim, dict) or not lim or any(k not in ("min", "max") or not isinstance(v, (int, float))
                                                                 for k, v in lim.items()):
                    out.append(f"{p}: give a numeric min and/or max")
    if "incoterms" in req and not (_strings(req["incoterms"]) and all(i in INCOTERMS for i in req["incoterms"])):
        out.append(f"incoterms are among {', '.join(INCOTERMS)}")
    for k in ("named_place", "delivery_country"):
        if k in req and not (isinstance(req[k], str) and req[k].strip()):
            out.append(f"{k} names a place")
    if "delivery_country" in req and isinstance(req["delivery_country"], str) and len(req["delivery_country"].strip()) != 2:
        out.append("delivery_country is an ISO 3166 two-letter code")
    if "mandatory" in req:
        m = req["mandatory"]
        if not (_strings(m) and all(k in CHECKABLE and k in req for k in m)):
            out.append("mandatory lists requirements stated above that can be checked")
    return out
