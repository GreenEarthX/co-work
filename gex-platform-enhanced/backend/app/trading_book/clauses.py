"""
Typed clauses on the confirmed terms (GreenMesh Phase 2 Step 3, amendment B1; sub-step 1).

Risk, title and payment are three records, each governed by its own clause; none is derived
from another (JML, 12 Nov 2026; ruling R1: the Incoterm governs RISK only).

  delivery clause   attrs.incoterm (Incoterms 2020) + attrs.named_place, and for the C terms
                    attrs.shipment_point (risk passes at shipment, the named place is the
                    destination). Governs risk.
  title clause      attrs.passes: ON_RISK | ON_ACCEPTANCE | ON_PAYMENT_IN_FULL |
                    ON_DOCUMENT_TRANSFER. Governs title. There is no default: no clause, no title.
  payment clause    attrs.trigger: ON_BL | ON_INSPECTOR_CERTIFICATE | ON_ACCEPTANCE | ON_TITLE, and
                    attrs.quantity_basis: BL_QTY | OUTTURN_QTY | ACCEPTED_QTY. Governs payment.

A clause carrying none of its typed fields is free text (the market's `delivery_terms`,
`payment_terms`) and is never read as one of these. A typed field that is present must be
valid: V15 refuses the terms otherwise. A sub-leg's own clause wins over a shared one.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

INCOTERMS = ("EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF")
C_TERMS = ("CPT", "CIP", "CFR", "CIF")
SEA_ONLY = ("FAS", "FOB", "CFR", "CIF")
TITLE_PASSES = ("ON_RISK", "ON_ACCEPTANCE", "ON_PAYMENT_IN_FULL", "ON_DOCUMENT_TRANSFER")
PAYMENT_TRIGGERS = ("ON_BL", "ON_INSPECTOR_CERTIFICATE", "ON_ACCEPTANCE", "ON_TITLE")
PAYMENT_QUANTITY_BASES = ("BL_QTY", "OUTTURN_QTY", "ACCEPTED_QTY")
# The commitment (Phase 2 Step 4): the offtake card's vocabulary (contract_tokens.FORM_STRENGTH).
COMMITMENT_FORMS = ("FRAMEWORK", "TAKE_IF_DELIVERED", "TAKE_AND_PAY", "TAKE_OR_PAY", "TAKE_IF_TENDERED")

_TYPED = {"delivery": ("incoterm", "named_place", "shipment_point"),
          "title": ("passes",),
          "payment": ("trigger", "quantity_basis"),
          "commitment": ("commitment_form", "take_or_pay_pct", "shortfall_price")}


def _text(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def is_typed(clause_type: str, attrs: dict) -> bool:
    if clause_type == "commitment":
        # Typed only when it names its form (Step 4): frame terms written before carry a bare
        # {"take_or_pay_pct": ...} commitment clause, which stays free text, as it was.
        return "commitment_form" in (attrs or {})
    return any(k in (attrs or {}) for k in _TYPED.get(clause_type, ()))


def clause_errors(clause_type: str, attrs: dict) -> list[str]:
    """Why a typed clause is invalid (empty: valid, or not typed at all)."""
    a = attrs or {}
    if not is_typed(clause_type, a):
        return []
    out = []
    if clause_type == "delivery":
        if a.get("incoterm") not in INCOTERMS:
            out.append(f"incoterm must be one of {', '.join(INCOTERMS)}")
        if not _text(a.get("named_place")):
            out.append("an Incoterm needs its named place")
        if "shipment_point" in a and not _text(a.get("shipment_point")):
            out.append("shipment_point, when given, names a place")
    elif clause_type == "title":
        if a.get("passes") not in TITLE_PASSES:
            out.append(f"title passes {' | '.join(TITLE_PASSES)}")
    elif clause_type == "commitment":
        form = a.get("commitment_form")
        if form not in COMMITMENT_FORMS:
            out.append(f"commitment_form is one of {', '.join(COMMITMENT_FORMS)}")
        pct = a.get("take_or_pay_pct")
        if form == "TAKE_OR_PAY" or pct is not None:
            try:
                ok = pct is not None and not isinstance(pct, bool) and 0 < float(str(pct)) <= 100
            except ValueError:
                ok = False
            if not ok:
                out.append("take_or_pay_pct is a percentage above 0 and at most 100, named with TAKE_OR_PAY")
            elif form != "TAKE_OR_PAY":
                out.append("take_or_pay_pct belongs to a TAKE_OR_PAY commitment")
        if a.get("shortfall_price") is not None:
            try:
                if isinstance(a["shortfall_price"], bool) or float(str(a["shortfall_price"])) < 0:
                    out.append("shortfall_price is a non-negative price per tonne")
            except ValueError:
                out.append("shortfall_price is a non-negative price per tonne")
    elif clause_type == "payment":
        if a.get("trigger") not in PAYMENT_TRIGGERS:
            out.append(f"payment trigger is one of {', '.join(PAYMENT_TRIGGERS)}")
        if a.get("quantity_basis") not in PAYMENT_QUANTITY_BASES:
            out.append(f"payment quantity basis is one of {', '.join(PAYMENT_QUANTITY_BASES)}")
    return out


def v15(clauses: Iterable) -> bool:
    """V15: every typed clause valid, and at most one typed clause of a kind per scope
    (shared, or one sub-leg). True = passes."""
    seen = set()
    for c in clauses:
        attrs = c.attrs if hasattr(c, "attrs") else c.get("attrs", {})
        ctype = c.clause_type if hasattr(c, "clause_type") else c.get("clause_type")
        sub = c.sub_leg if hasattr(c, "sub_leg") else c.get("sub_leg")
        if clause_errors(ctype, attrs):
            return False
        if is_typed(ctype, attrs):
            if (ctype, sub) in seen:
                return False
            seen.add((ctype, sub))
    return True


def read(rows: Iterable[dict], sub_leg_id: Optional[str]) -> dict:
    """{risk, title, payment} from tb_clause rows ({sub_leg_id, clause_type, attrs}), each
    {..fields, "source": "sub_leg" | "shared"} or None when the terms carry no such clause."""
    best: dict[str, tuple[int, dict]] = {}
    for r in rows:
        attrs = r["attrs"] if isinstance(r["attrs"], dict) else json.loads(r["attrs"] or "{}")
        own = r["sub_leg_id"] is not None
        if own and str(r["sub_leg_id"]) != str(sub_leg_id):
            continue
        ctype = r["clause_type"]
        if not is_typed(ctype, attrs) or clause_errors(ctype, attrs):
            continue
        rank = 0 if own else 1
        if ctype not in best or rank < best[ctype][0]:
            best[ctype] = (rank, {**{k: attrs.get(k) for k in _TYPED[ctype]},
                                  "source": "sub_leg" if own else "shared"})
    return {"risk": best.get("delivery", (0, None))[1], "title": best.get("title", (0, None))[1],
            "payment": best.get("payment", (0, None))[1], "commitment": best.get("commitment", (0, None))[1]}


def for_terms(conn, terms_id: str, sub_leg_id: Optional[str]) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT sub_leg_id, clause_type, attrs FROM tb_clause WHERE terms_id = ? AND clause_type IN "
        "('delivery', 'title', 'payment', 'commitment') ORDER BY seq", (terms_id,)).fetchall()]
    return read(rows, sub_leg_id)


def bases(c: dict) -> dict:
    """The three records' basis as a reader states it: what governs each, or what is missing."""
    risk, title, payment = c["risk"], c["title"], c["payment"]
    out = {}
    if risk is None:
        out["risk_basis"] = "MISSING: the confirmed terms name no Incoterm and place, so risk cannot pass"
    elif risk["incoterm"] in C_TERMS and not risk.get("shipment_point"):
        out["risk_basis"] = (f"MISSING: {risk['incoterm']} {risk['named_place']} names the destination; the "
                             f"confirmed terms name no shipment point, so risk cannot pass")
    else:
        out["risk_basis"] = f"{risk['incoterm']} {risk['named_place']} (confirmed terms)"
    out["title_basis"] = (f"{title['passes']} (confirmed terms)" if title else
                          "MISSING: the confirmed terms carry no title clause, so title cannot pass")
    out["payment_basis"] = (f"{payment['trigger']}, {payment['quantity_basis']} (confirmed terms)" if payment else
                            "MISSING: the confirmed terms carry no typed payment clause")
    return out
