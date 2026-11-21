"""The Financing and Offtake tabs of the CFO's workbook (19 Nov 2026). Same template as
core/cost_workbook.py: rows read by the grey key in column A, a blank is unknown, every
term carries its source, `parse_*` writes nothing.

Financing -> GEX's financing case (calculation_chain.financing_record): the reviewed TEA run
  it rests on, debt, all-in rate, tenor and grants, each with source, date and standing.
  Behind it the CFO may list the CAPITAL STACK being raised (grants, DFI loan, senior debt,
  bond, mezzanine, equity; amount, cost, tenor, status). GEX's case holds one debt figure;
  the stack is DECLARED beside it (workbook_import, 126), reconciled, never summed into it
  by guess: grants must agree (unambiguous), the debt and rate differences are reported.

Offtake -> the offtake commitment card (commitment_terms.validate_card, the same rules as
  the screen). One buyer without a company id is a single-counterparty card; several
  buyers, or any company id, make a frame with one sub-leg per buyer. Saved terms reach
  the gate engine only once each counterparty confirms its own: the workbook does not
  change that. Each row's source and date are declared beside the card (126).
"""
from __future__ import annotations

from typing import Optional

from app.core import cost_workbook as cw
from app.core.bankability_engine import COMMITMENT_CARD_FIELDS
from app.core.commitment_terms import OFFTAKE_BUYER_FIELDS, OFFTAKE_SHARED_FIELDS

Field = cw.Field

CAPITAL_TYPES = ("GRANT", "SENIOR_DEBT", "DFI_LOAN", "GREEN_BOND", "MEZZANINE", "SPONSOR_EQUITY",
                 "THIRD_PARTY_EQUITY", "OTHER")
DEBT_TYPES = ("SENIOR_DEBT", "DFI_LOAN", "GREEN_BOND", "MEZZANINE")
CAPITAL_STATUS = ("INDICATIVE", "APPLIED", "MANDATE", "TERM_SHEET", "COMMITTED", "SIGNED")
YES_NO = ("Yes", "No")

FIN_FIELDS = (
    Field("financing.case_id", "Financing case id (GEX fills it)", "text", "", False,
          "Blank: a new case. Kept: the next version of THAT case. Never edit it."),
    Field("financing.tea_claim_id", "TEA run this case rests on", "text", "claim id", False,
          "Blank in a draft. Promotion needs an independently reviewed TEA run (Calculation chain, step 2)."),
    Field("financing.debt_eur", "Debt", "number", "EUR", True, "The debt the case is sized on."),
    Field("financing.interest_rate", "All-in interest rate", "fraction", "0-1", True),
    Field("financing.debt_tenor_years", "Debt tenor", "int", "years", True),
    Field("financing.grant_eur", "Grants", "number", "EUR", False, "Blank: no grant stated."),
)
CAP_COLUMNS = ("source_id", "name", "type", "amount_eur", "rate", "tenor_years", "status", "obligation", "conditions",
               "received_eur", "available_eur", "in_plan", "lender_max_gearing", "source", "as_of")
CAP_HEADERS = ("Id (GEX fills it)", "Source of capital", "Type", "Amount (EUR)", "Cost (rate, 0-1)", "Tenor (years)",
               "Document stage", "Obligation (substance)", "Open conditions", "Cash received (EUR)",
               "Binding and available to draw (EUR)", "In this plan? (No = pipeline)", "This lender's max gearing (0-1)",
               "Document / source", "As of")
USE_COLUMNS = ("use_id", "kind", "component", "amount_eur", "standing", "reason", "source", "as_of")
USE_HEADERS = ("Id (GEX fills it)", "Use", "Financing cost component", "Amount (EUR)", "Standing",
               "Reason (required: a stated financing cost, a zero working capital)", "Document / source", "As of")

SPEC = COMMITMENT_CARD_FIELDS["offtake"]
_LABELS = {
    "planned_output_tonnes_per_year": ("Planned output", "t/yr"),
    "product_spec_standard": ("Product specification standard", ""),
    "certification_scheme": ("Certification scheme", ""),
    "compliance_regime": ("Compliance regimes", "separate with ;"),
    "fm_definition_ref": ("Force majeure definition (reference)", ""),
    "change_in_law_allocated": ("Change in law allocated", "Yes / No"),
}
OFF_SHARED = tuple(Field(f"offtake.{f}", _LABELS.get(f, (f, ""))[0], SPEC[f], _LABELS.get(f, (f, ""))[1])
                   for f in OFFTAKE_SHARED_FIELDS)
BUYER_COLUMNS = ("company_id",) + OFFTAKE_BUYER_FIELDS + ("source", "as_of")
BUYER_HEADERS = ("GEX company id (if a party)",) + tuple(
    f.replace("_", " ") + (" (%)" if f == "take_or_pay_pct" else "") for f in OFFTAKE_BUYER_FIELDS) + (
    "Document / source", "As of")


def extra_lists() -> dict:
    from app.core import funding as fd
    enums = {f"enum_{f}": tuple(SPEC[f][5:].split("|")) for f in SPEC if SPEC[f].startswith("enum:")}
    return {"capital_types": CAPITAL_TYPES, "capital_status": CAPITAL_STATUS, "yes_no": YES_NO,
            "obligations": fd.OBLIGATIONS, "use_kinds": fd.USE_KINDS, "financing_components": fd.FINANCING_COMPONENTS,
            **enums}


def _list_for(kind: str, field: str) -> Optional[str]:
    if kind == "bool":
        return "yes_no"
    if kind.startswith("enum:"):
        return f"enum_{field}"
    return None


# ── sheets ─────────────────────────────────────────────────────────────────────

def financing_sheet(wb, lists: dict, filled: Optional[dict]):
    s = cw._styles()
    ws = wb.create_sheet("Financing")
    f = filled or {}
    ws.cell(1, 2, "FINANCING").font = s["title"]
    ws.cell(2, 2, "The case GEX sizes returns on rests on ONE independently reviewed TEA run. "
                  "List the capital you are raising below it; it is kept as declared, beside the case.")
    ws.cell(4, 2, "1. Financing case").font = s["h"]
    dv: dict = {}
    r = cw._field_rows(ws, 5, FIN_FIELDS, f.get("fields", {}), lists, dv)
    ws.cell(r + 1, 2, "2. Sources: classify each by the substance of the obligation and its open conditions, "
                      "not by the document's title. 'No' in the plan column = a pipeline opportunity, shown "
                      "apart and never counted.").font = s["h"]
    r = cw._table(ws, r + 2, "capital.header", CAP_HEADERS, CAP_COLUMNS, f.get("capital", []), 10, lists, dv,
                  {"type": "capital_types", "status": "capital_status", "obligation": "obligations",
                   "in_plan": "yes_no"})
    ws.cell(r + 1, 2, "3. Uses of this case. Construction is the TEA run's fixed capital (GEX fills it when a "
                      "TEA run is named). A use left out is unknown: the total is then a floor.").font = s["h"]
    cw._table(ws, r + 2, "uses.header", USE_HEADERS, USE_COLUMNS, f.get("uses", []), 8, lists, dv,
              {"kind": "use_kinds", "component": "financing_components", "standing": "standings"})
    for col, w in zip("ABCDEFGHI", (16, 34, 18, 14, 14, 14, 30, 16, 30)):
        ws.column_dimensions[col].width = w


def offtake_sheet(wb, lists: dict, filled: Optional[dict]):
    from openpyxl.utils import get_column_letter
    s = cw._styles()
    ws = wb.create_sheet("Offtake")
    f = filled or {}
    ws.cell(1, 2, "OFFTAKE").font = s["title"]
    ws.cell(2, 2, "The offtake card. Saved terms reach the gate engine only once each buyer confirms its own "
                  "on GEX. One buyer without a company id is a single card; several buyers make a frame.")
    ws.cell(4, 2, "1. Terms shared by every buyer").font = s["h"]
    dv: dict = {}
    r = 5
    for col, h in enumerate(("key", "Field", "Value", "Unit", "Source", "As of"), 1):
        c = ws.cell(r, col, h)
        c.font, c.fill = s["head"], s["headfill"]
    for fld in OFF_SHARED:
        r += 1
        v = f.get("shared", {}).get(fld.key) or {}
        ws.cell(r, 1, fld.key).font = s["key"]
        ws.cell(r, 2, fld.label)
        ws.cell(r, 3, v.get("value")).fill = s["input"]
        ws.cell(r, 4, fld.unit)
        ws.cell(r, 5, v.get("source")).fill = s["input"]
        ws.cell(r, 6, v.get("as_of")).fill = s["input"]
        name = _list_for(fld.kind, fld.key.split(".", 1)[1])
        if name:
            cw._validate(ws, dv, name, lists, f"C{r}")
    ws.cell(r + 2, 2, "2. Buyers: one row per buyer").font = s["h"]
    lists_for = {c: _list_for(SPEC[c], c) for c in OFFTAKE_BUYER_FIELDS if _list_for(SPEC[c], c)}
    cw._table(ws, r + 3, "buyers.header", BUYER_HEADERS, BUYER_COLUMNS, f.get("buyers", []), 8, lists, dv,
              lists_for)
    for i in range(1, len(BUYER_COLUMNS) + 2):
        ws.column_dimensions[get_column_letter(i)].width = 16 if i > 2 else 22


# ── fill (the inverse of parse) ────────────────────────────────────────────────

def fill_financing(version: Optional[dict], declared: Optional[dict], default_claim: Optional[str]) -> dict:
    fields = {}
    if version:
        if version.get("case_id"):
            fields["financing.case_id"] = {"value": version["case_id"], "source": "GEX"}
        if version.get("tea_claim_id"):
            fields["financing.tea_claim_id"] = {"value": version["tea_claim_id"], "source": "the case's TEA run"}
        for t, term in (version.get("terms") or {}).items():
            fields[f"financing.{t}"] = {"value": term.get("value"), "source": term.get("source"),
                                        "as_of": term.get("as_of"), "standing": term.get("standing")}
    elif default_claim:
        fields["financing.tea_claim_id"] = {"value": default_claim, "source": "latest independently reviewed TEA run"}
    plan = (version or {}).get("funding_plan") or {}
    if plan:
        capital = [{**c, "in_plan": "Yes" if c.get("in_plan", True) else "No"} for c in plan.get("sources") or []]
        return {"fields": fields, "capital": capital, "uses": list(plan.get("uses") or [])}
    capital = [{**c, "in_plan": "No" if c.get("in_plan") is False else "Yes"}
               for c in (declared or {}).get("capital_sources") or []]
    return {"fields": fields, "capital": capital, "uses": list((declared or {}).get("uses") or [])}


def fill_offtake(card: Optional[dict], declared: Optional[dict]) -> dict:
    card = card or {}
    d = declared or {}
    shared = {}
    for f in OFFTAKE_SHARED_FIELDS:
        if f in card:
            p = (d.get("shared") or {}).get(f) or {}
            shared[f"offtake.{f}"] = {"value": _cell(SPEC[f], card[f]), "source": p.get("source"),
                                      "as_of": p.get("as_of")}
    rows = card.get("buyers") or ([{k: v for k, v in card.items() if k in OFFTAKE_BUYER_FIELDS}]
                                  if any(k in card for k in OFFTAKE_BUYER_FIELDS) else [])
    buyers = []
    for n, b in enumerate(rows):
        p = (d.get("buyers") or {}).get(b.get("company_id") or f"#{n + 1}") or {}
        buyers.append({**{k: _cell(SPEC[k], v) for k, v in b.items() if k in SPEC},
                       "company_id": b.get("company_id"), "source": p.get("source"), "as_of": p.get("as_of")})
    return {"shared": shared, "buyers": buyers}


def _cell(kind: str, v):
    if kind == "bool":
        return "Yes" if v else "No"
    if kind == "list":
        return "; ".join(v)
    return v


# ── parse ──────────────────────────────────────────────────────────────────────

def _keyed(rows):
    return {str(cw._col(r, 0)).strip(): (i, r) for i, r in enumerate(rows) if not cw._blank(cw._col(r, 0))}


def parse_financing(rows, *, lists: dict) -> dict:
    """The Financing tab: the case's terms and the declared capital stack."""
    rep = cw._Report()
    keyed = _keyed(rows)
    terms, claim, case_id = {}, None, None
    provided = any(not cw._blank(cw._col(r, 2)) for k, (_, r) in keyed.items() if k.startswith("financing."))
    capital = _read_capital(cw._rows_between(rows, "capital.header", "capital.end", CAP_COLUMNS), rep)
    uses = _read_uses(cw._rows_between(rows, "uses.header", "uses.end", USE_COLUMNS), rep)
    if not provided and not capital and not uses:
        return {"provided": False, "report": [], "summary": rep.summary(), "can_commit": False}
    for f in FIN_FIELDS:
        if f.key not in keyed:
            rep.add("MISSING", "Financing", f.key, "Row removed from the template.", blocking=f.required)
            continue
        rnum, row = keyed[f.key]
        v, src = cw._col(row, 2), cw._col(row, 4)
        where = f"Financing!C{rnum + 1}"
        if v is cw._UNCALCULATED:
            rep.add("UNSUPPORTED", where, f.key, "A formula with no calculated value.", blocking=True)
            continue
        name = f.key.split(".", 1)[1]
        if cw._blank(v):
            if f.required:
                rep.add("MISSING", where, f.key, "Not stated: the case is saved as a draft.", issue=True)
            elif name == "tea_claim_id":
                rep.add("MISSING", where, f.key, "No TEA run named: the case is saved as a draft.", issue=True)
            continue
        if name in ("tea_claim_id", "case_id"):
            if name == "tea_claim_id":
                claim = str(v).strip()
            else:
                case_id = str(v).strip()
            rep.add("ACCEPTED", where, f.key, "", value=str(v).strip())
            continue
        try:
            n, note = cw._num(v)
            if f.kind == "fraction" and 1 < n <= 100:
                note, n = f"read {n} as a percentage: {n / 100}", n / 100
            if f.kind == "fraction" and not 0 <= n <= 1:
                raise ValueError("out of 0-1")
            if f.kind == "int":
                if n != int(n):
                    raise ValueError("not whole")
                n = int(n)
            if n < 0:
                raise ValueError("negative")
        except (ValueError, TypeError) as e:
            rep.add("UNSUPPORTED", where, f.key, f"'{v}' is not a valid {f.kind} ({e}).", blocking=True)
            continue
        if cw._blank(src):
            rep.add("MISSING", f"Financing!E{rnum + 1}", f.key, "State the source of this term.", blocking=True)
            continue
        standing = cw._text(cw._col(row, 6))
        if standing and standing not in cw.STANDINGS:
            rep.add("UNSUPPORTED", f"Financing!G{rnum + 1}", f.key, f"Standing must be one of {list(cw.STANDINGS)}.")
            standing = None
        terms[name] = {"value": n, "source": str(src).strip(), "as_of": cw._text(cw._col(row, 5)),
                       "standing": standing}
        rep.add("CONVERTED" if note else "ACCEPTED", where, f.key, note or "", value=n)
    _stack_checks(terms, capital, rep)
    s = rep.summary()
    issues = [{"field": r["field"], "detail": r["detail"]} for r in rep.rows if r.get("issue")]
    return {"provided": True, "case_id": case_id, "tea_claim_id": claim, "terms": terms,
            "capital_sources": capital, "funding_plan": {"sources": capital, "uses": uses}, "open_issues": issues,
            "report": rep.rows, "summary": s, "can_commit": s["blocking"] == 0}


def _read_capital(rows, rep) -> list:
    """Each row keeps its stable id when GEX gave it one; a row without one is a new source."""
    out, seen = [], set()
    for rnum, c in rows:
        where = f"Financing!row {rnum}"
        name = cw._text(c["name"])
        typ = cw._text(c["type"])
        status = cw._text(c["status"])
        if not name or typ not in CAPITAL_TYPES:
            rep.add("UNSUPPORTED", where, name or "capital", f"Name the source and give its type, one of "
                    f"{list(CAPITAL_TYPES)}.", blocking=True)
            continue
        if status and status not in CAPITAL_STATUS:
            rep.add("UNSUPPORTED", where, name, f"Status must be one of {list(CAPITAL_STATUS)}.", blocking=True)
            continue
        sid = cw._text(c["source_id"])
        if sid and sid in seen:
            rep.add("CONFLICTING", where, name, f"Id {sid} appears twice: one row per source.", blocking=True)
            continue
        seen.add(sid)
        from app.core import funding as fd
        obligation = cw._text(c["obligation"])
        if obligation and obligation not in fd.OBLIGATIONS:
            rep.add("UNSUPPORTED", where, name, f"Obligation must be one of {list(fd.OBLIGATIONS)}.", blocking=True)
            continue
        in_plan_text = {"true": "yes", "false": "no"}.get((cw._text(c["in_plan"]) or "").lower(),
                                                           (cw._text(c["in_plan"]) or "").lower())
        if in_plan_text not in ("", "yes", "no"):
            rep.add("UNSUPPORTED", where, name, "In this plan: Yes or No.", blocking=True)
            continue
        e = {"source_id": sid, "name": name, "type": typ, "status": status, "obligation": obligation,
             "conditions": cw._text(c["conditions"]), "in_plan": in_plan_text != "no",
             "source": cw._text(c["source"]), "as_of": cw._text(c["as_of"])}
        try:
            for k in ("amount_eur", "rate", "tenor_years", "received_eur", "available_eur", "lender_max_gearing"):
                e[k] = None if cw._blank(c[k]) else cw._num(c[k])[0]
            for k in ("rate", "lender_max_gearing"):
                if e[k] is not None and 1 < e[k] <= 100:
                    e[k] = e[k] / 100
        except (ValueError, TypeError):
            rep.add("UNSUPPORTED", where, name, "An amount, rate, tenor or gearing is not a number.", blocking=True)
            continue
        if e["available_eur"] and obligation != "BINDING":
            rep.add("CONFLICTING", where, name, "An amount 'available to draw' needs a BINDING obligation.",
                    blocking=True)
            continue
        if obligation is None and e["in_plan"]:
            rep.add("MISSING", where, name, "Obligation not classified: counted as uncommitted.", issue=True)
        if obligation == "CONDITIONAL" and not e["conditions"]:
            rep.add("MISSING", where, name, "A conditional obligation names its open conditions.", issue=True)
        if e["amount_eur"] is None:
            rep.add("MISSING", where, name, "State the amount.", blocking=True)
            continue
        if not e["source"]:
            rep.add("MISSING", where, name, "State its document or source.", blocking=True)
            continue
        out.append(e)
        rep.add("ACCEPTED", where, name, f"{typ} EUR {e['amount_eur']:,.0f}, {obligation or 'obligation unclassified'}"
                                         f"{'' if e['in_plan'] else ', pipeline'}")
    return out


def _read_uses(rows, rep) -> list:
    """The case's uses. Each keeps its GEX id across re-imports; blank is unknown, a zero needs its reason."""
    from app.core import funding as fd
    out, seen = [], set()
    for rnum, u in rows:
        where = f"Financing!row {rnum}"
        kind = cw._text(u["kind"])
        if kind not in fd.USE_KINDS:
            rep.add("UNSUPPORTED", where, kind or "use", f"Use must be one of {list(fd.USE_KINDS)}.", blocking=True)
            continue
        uid = cw._text(u["use_id"])
        if uid and uid in seen:
            rep.add("CONFLICTING", where, kind, f"Id {uid} appears twice.", blocking=True)
            continue
        seen.add(uid)
        component = cw._text(u["component"])
        if kind == "FINANCING_COSTS" and component not in fd.FINANCING_COMPONENTS:
            rep.add("MISSING", where, kind, f"Name the financing cost component, one of {list(fd.FINANCING_COMPONENTS)}.",
                    blocking=True)
            continue
        try:
            amount = cw._num(u["amount_eur"])[0] if not cw._blank(u["amount_eur"]) else None
        except (ValueError, TypeError):
            rep.add("UNSUPPORTED", where, kind, "The amount is not a number.", blocking=True)
            continue
        if amount is None:
            rep.add("MISSING", where, kind, "Left blank: this use stays unknown (state 0 with its reason if none).",
                    issue=True)
            continue
        if not cw._text(u["source"]):
            rep.add("MISSING", where, kind, "State the source of this use.", blocking=True)
            continue
        standing = cw._text(u["standing"])
        if standing and standing not in cw.STANDINGS:
            rep.add("UNSUPPORTED", where, kind, f"Standing must be one of {list(cw.STANDINGS)}.", blocking=True)
            continue
        out.append({"use_id": uid, "kind": kind, "component": component, "amount_eur": amount, "standing": standing,
                    "reason": cw._text(u["reason"]), "source": cw._text(u["source"]), "as_of": cw._text(u["as_of"])})
        rep.add("ACCEPTED", where, kind, f"EUR {amount:,.0f}" + (f" ({standing})" if standing else ""))
    return out


def _stack_checks(terms: dict, capital: list, rep) -> None:
    """Only the weighted rate here: grants and debt are reconciled for the case (core/funding)."""
    if not capital:
        return
    debt_rows = [c for c in capital if c["type"] in DEBT_TYPES and c.get("in_plan", True)]
    priced = [c for c in debt_rows if c.get("rate") is not None]
    if priced and "interest_rate" in terms:
        w = sum(c["amount_eur"] * c["rate"] for c in priced) / sum(c["amount_eur"] for c in priced)
        if abs(w - terms["interest_rate"]["value"]) > 1e-4:
            rep.add("CONVERTED", "Financing", "financing.interest_rate",
                    f"The stack's debt costs {w:.4f} weighted by amount; the case states "
                    f"{terms['interest_rate']['value']:.4f}. Reported, not adjusted.")


def parse_offtake(rows, *, lists: dict) -> dict:
    """The Offtake tab: the card GEX's own validation will check, and each row's source."""
    from app.core.commitment_terms import TermsValidationError, validate_card
    rep = cw._Report()
    keyed = _keyed(rows)
    shared, declared = {}, {"shared": {}, "buyers": {}}
    for fld in OFF_SHARED:
        if fld.key not in keyed:
            continue
        rnum, row = keyed[fld.key]
        v = cw._col(row, 2)
        if cw._blank(v):
            continue
        field = fld.key.split(".", 1)[1]
        try:
            shared[field] = _value(SPEC[field], field, v)
        except ValueError as e:
            rep.add("UNSUPPORTED", f"Offtake!C{rnum + 1}", fld.key, str(e), blocking=True)
            continue
        declared["shared"][field] = {"source": cw._text(cw._col(row, 4)), "as_of": cw._text(cw._col(row, 5))}
        rep.add("ACCEPTED", f"Offtake!C{rnum + 1}", fld.key, "", value=shared[field])
    buyers = []
    for rnum, b in cw._rows_between(rows, "buyers.header", "buyers.end", BUYER_COLUMNS):
        where = f"Offtake!row {rnum}"
        entry = {}
        bad = False
        for field in OFFTAKE_BUYER_FIELDS:
            v = b[field]
            if cw._blank(v):
                continue
            try:
                entry[field], note = _value(SPEC[field], field, v, with_note=True)
                if note:
                    rep.add("CONVERTED", where, field, note, value=entry[field])
            except ValueError as e:
                rep.add("UNSUPPORTED", where, field, str(e), blocking=True)
                bad = True
        company = cw._text(b["company_id"])
        label = company or entry.get("counterparty_name") or f"#{len(buyers) + 1}"
        if not cw._text(b["source"]):
            rep.add("MISSING", where, label, "State the document these terms come from (HoT, SPA, LOI...).",
                    blocking=True)
            bad = True
        if bad:
            continue
        buyers.append((company, entry))
        declared["buyers"][company or f"#{len(buyers)}"] = {"source": cw._text(b["source"]),
                                                             "as_of": cw._text(b["as_of"])}
        rep.add("ACCEPTED", where, label, ", ".join(f"{k}={v}" for k, v in list(entry.items())[:4]))
    if not shared and not buyers and not rep.rows:
        return {"provided": False, "report": [], "summary": rep.summary(), "can_commit": False}
    frame = len(buyers) > 1 or any(c for c, _ in buyers)
    if frame and not all(c for c, _ in buyers):
        rep.add("MISSING", "Offtake", "company_id", "With more than one buyer each needs its GEX company id: the "
                "frame has one sub-leg per buyer, and each buyer confirms its own. GEX staff grant project access.",
                blocking=True)
    card = dict(shared)
    if frame:
        card["buyers"] = [{"company_id": c, **e} for c, e in buyers]
    elif buyers:
        card.update(buyers[0][1])
    try:
        clean = validate_card("offtake", card)
    except TermsValidationError as e:
        for p in e.problems:
            rep.add("CONFLICTING", "Offtake", "card", p, blocking=True)
        clean = None
    if clean is not None:
        rep.add("ACCEPTED", "Offtake", "card", ("a frame of " + str(len(buyers)) + " buyers" if frame else
                                                "a single-counterparty card")
                + ". The terms reach the gate engine only once each counterparty confirms its own.")
    s = rep.summary()
    return {"provided": True, "card": clean, "frame": frame, "declared": declared, "report": rep.rows,
            "summary": s, "can_commit": s["blocking"] == 0 and clean is not None}


def _value(kind: str, field: str, v, with_note: bool = False):
    note = None
    if v is cw._UNCALCULATED:
        raise ValueError("A formula with no calculated value.")
    if kind == "bool":
        t = str(v).strip().lower()
        if isinstance(v, bool):
            out = v
        elif t in ("yes", "y", "true", "1"):
            out = True
        elif t in ("no", "n", "false", "0"):
            out = False
        else:
            raise ValueError(f"'{v}' is not Yes or No.")
    elif kind == "number":
        try:
            n, note = cw._num(v)
        except (ValueError, TypeError):
            raise ValueError(f"'{v}' is not a number.")
        if field == "take_or_pay_pct":
            if isinstance(v, str) and v.strip().endswith("%"):
                n, note = n * 100, f"read '{v}' as {n * 100:g}%"
            elif n <= 1:
                n, note = n * 100, f"read {v} as {n * 100:g}% (Excel stores 80% as 0.8)"
        out = n
    elif kind == "date":
        out = cw._text(v)
    elif kind == "list":
        out = [x.strip() for x in str(v).split(";") if x.strip()]
    elif kind.startswith("enum:"):
        out = str(v).strip()
    else:
        out = str(v).strip()
    return (out, note) if with_note else out
