"""
Does this listing meet this RFQ? Eligibility, per requirement — decided here and nowhere else
(discovery Phase 1, R7; report §6.1–6.3).

Two stages. ELIGIBILITY: every requirement the buyer stated (core/requirements.py) and the RFQ's
own molecule and window give one outcome each:

    compatible       the listing shows it holds
    incompatible     the listing shows it does not, with the reason
    needs_evidence   the listing does not show either way, or shows it below the evidence the buyer
                     requires, with what is missing

A requirement the buyer marked `mandatory` decides eligibility: one mandatory `incompatible`
excludes the listing, whatever its price (check 6). RANKING is commercial and only among the
eligible: price against the ceiling, volume cover, evidence; it never makes an excluded listing
eligible.

Only the ANONYMOUS listing is read (market_engine.public_listing: what any member sees, D-C), so an
assessment never depends on, or reveals, what the seller's identity would. Nothing here writes:
storing an assessment when a company acts on it is market_engine's (alembic 118).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

COMPATIBLE, INCOMPATIBLE, NEEDS = "compatible", "incompatible", "needs_evidence"
CI_ORDER = {"declared_at_mint": 0, "estimate": 1, "calculated": 2, "measured": 3}
EVIDENCE_ORDER = {"asserted": 1, "submitted": 2, "verified": 3}          # expired / rejected count for nothing
FORM_WORDS = {"gas": "gas", "compressed_gas": "compressed gas", "liquid": "liquid", "liquefied_gas": "liquefied gas"}
STATUS_ORDER = {COMPATIBLE: 0, NEEDS: 1, INCOMPATIBLE: 2}


def _day(v) -> str:
    return str(v)[:10]


def requirements_sha256(req: dict) -> str:
    return hashlib.sha256(json.dumps(req or {}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _o(key: str, outcome: str, reason: str, mandatory: bool, label: str) -> dict:
    return {"requirement": key, "label": label, "outcome": outcome, "reason": reason, "mandatory": mandatory}


def _evidence(status: Optional[str]) -> int:
    return EVIDENCE_ORDER.get(status or "", 0)


def _certs(listing: dict) -> list[dict]:
    return ((listing.get("product") or {}).get("certificates") or [])


def _required_level(req: dict) -> int:
    return EVIDENCE_ORDER.get(req.get("min_evidence_state") or "", 0)


def _ci(req: dict, listing: dict, mandatory: set) -> Optional[dict]:
    if "max_ci_gco2e_mj" not in req and "ci_min_basis" not in req:
        return None
    key = "max_ci_gco2e_mj" if "max_ci_gco2e_mj" in req else "ci_min_basis"
    m = bool(mandatory & {"max_ci_gco2e_mj", "ci_min_basis"})
    ci = (listing.get("product") or {}).get("carbon_intensity")
    if not ci or ci.get("value_gco2e_mj") is None:
        return _o(key, NEEDS, "No carbon intensity is recorded for this product.", m, "Carbon intensity")
    value, basis = float(ci["value_gco2e_mj"]), ci.get("basis") or "declared_at_mint"
    if "max_ci_gco2e_mj" in req and value > float(req["max_ci_gco2e_mj"]):
        return _o(key, INCOMPATIBLE, f"CI {value:g} gCO2e/MJ exceeds your {float(req['max_ci_gco2e_mj']):g} limit.", m,
                  "Carbon intensity")
    want = req.get("ci_min_basis")
    if want and CI_ORDER.get(basis, 0) < CI_ORDER[want]:
        return _o(key, NEEDS, f"CI {value:g} gCO2e/MJ is {basis.replace('_', ' ')}; you require {want} or better.", m,
                  "Carbon intensity")
    return _o(key, COMPATIBLE, f"CI {value:g} gCO2e/MJ ({basis.replace('_', ' ')}).", m, "Carbon intensity")


def _regimes(req: dict, listing: dict, m: bool) -> dict:
    """A regime is claimed by the token's certification pathway or by a certificate of that name;
    its evidence is that certificate's status, or 'asserted' for a bare claim."""
    pathway = (listing.get("certification_pathway") or "").lower()
    level, missing, weak = _required_level(req), [], []
    for regime in req["regimes"]:
        r = regime.lower()
        best = max((_evidence(c["status"]) for c in _certs(listing) if (c.get("scheme") or "").lower() == r), default=0)
        if not best and r in pathway:
            best = EVIDENCE_ORDER["asserted"]
        if not best:
            missing.append(regime)
        elif best < level:
            weak.append(regime)
    if missing:
        return _o("regimes", NEEDS, f"No {', '.join(missing)} claim on this listing.", m, "Regime")
    if weak:
        return _o("regimes", NEEDS, f"{', '.join(weak)} is claimed but not {req['min_evidence_state']}.", m, "Regime")
    return _o("regimes", COMPATIBLE, f"{', '.join(req['regimes'])} claimed.", m, "Regime")


def _schemes(req: dict, listing: dict, m: bool) -> dict:
    accepted = {s.lower() for s in req["accepted_schemes"]}
    level = max(_required_level(req), EVIDENCE_ORDER["asserted"])
    mine = [c for c in _certs(listing) if (c.get("scheme") or "").lower() in accepted]
    live = [c for c in mine if _evidence(c["status"]) >= level]
    if live:
        c = max(live, key=lambda c: _evidence(c["status"]))
        cover = "" if c.get("scope") == "batch" else f" ({c.get('covers') or c.get('scope')}, not this quantity)"
        return _o("accepted_schemes", COMPATIBLE, f"{c['scheme']} certificate, {c['status']}{cover}.", m, "Certificate")
    if mine:
        states = ", ".join(sorted({f"{c['scheme']} {c['status']}" for c in mine}))
        return _o("accepted_schemes", NEEDS, f"Certificate below what you require: {states}.", m, "Certificate")
    return _o("accepted_schemes", NEEDS, f"No {' or '.join(req['accepted_schemes'])} certificate recorded.", m,
              "Certificate")


def _evidence_floor(req: dict, listing: dict, m: bool) -> dict:
    """min_evidence_state on its own: at least one certificate at that level."""
    level, want = _required_level(req), req["min_evidence_state"]
    if any(_evidence(c["status"]) >= level for c in _certs(listing)):
        return _o("min_evidence_state", COMPATIBLE, f"At least one certificate is {want} or better.", m, "Evidence")
    return _o("min_evidence_state", NEEDS, f"No certificate is {want} yet.", m, "Evidence")


def _form(req: dict, listing: dict, m: bool) -> dict:
    have, want = (listing.get("product") or {}).get("physical_form"), req["physical_form"]
    if not have:
        return _o("physical_form", NEEDS, "The physical form is not stated.", m, "Form")
    if have != want:
        return _o("physical_form", INCOMPATIBLE, f"{FORM_WORDS.get(have, have)} offered; you require "
                                                 f"{FORM_WORDS.get(want, want)}.", m, "Form")
    return _o("physical_form", COMPATIBLE, f"{FORM_WORDS.get(have, have)}.", m, "Form")


def _quality(req: dict, listing: dict, m: bool) -> dict:
    values = {q["parameter"]: q for q in ((listing.get("product") or {}).get("quality") or [])}
    missing, out = [], []
    for p, lim in req["quality_limits"].items():
        q = values.get(p)
        if q is None:
            missing.append(p.replace("_", " "))
            continue
        v = float(q["value"])
        if lim.get("min") is not None and v < float(lim["min"]):
            out.append(f"{p.replace('_', ' ')} {v:g} below {float(lim['min']):g}")
        if lim.get("max") is not None and v > float(lim["max"]):
            out.append(f"{p.replace('_', ' ')} {v:g} above {float(lim['max']):g}")
    if out:
        return _o("quality_limits", INCOMPATIBLE, "; ".join(out) + ".", m, "Specification")
    if missing:
        return _o("quality_limits", NEEDS, f"Not stated: {', '.join(missing)}.", m, "Specification")
    return _o("quality_limits", COMPATIBLE, "Every stated limit is met (values as recorded by the seller).", m,
              "Specification")


def _incoterm(req: dict, listing: dict, m: bool) -> dict:
    have = listing.get("incoterm")
    if not have:
        return _o("incoterms", NEEDS, "The listing states no Incoterm.", m, "Delivery basis")
    if have not in req["incoterms"]:
        return _o("incoterms", INCOMPATIBLE, f"{have} offered; you accept {'/'.join(req['incoterms'])}.", m,
                  "Delivery basis")
    want, place = req.get("named_place"), listing.get("named_place")
    if want and not place:
        return _o("incoterms", NEEDS, f"{have}, but no named place is stated.", m, "Delivery basis")
    if want and place.strip().lower() != want.strip().lower():
        return _o("incoterms", INCOMPATIBLE, f"{have} {place}; you require {want}.", m, "Delivery basis")
    return _o("incoterms", COMPATIBLE, f"{have} {place or ''}".strip() + ".", m, "Delivery basis")


def assess(rfq: dict, listing: dict) -> dict:
    """The outcome of each requirement, the overall status and eligibility. Pure: no I/O."""
    req = rfq.get("requirements") or {}
    mandatory = set(req.get("mandatory") or [])
    out: list[dict] = []
    # The RFQ's own terms. Molecule and window are always mandatory: no trade without them.
    if listing.get("molecule") != rfq.get("molecule"):
        out.append(_o("molecule", INCOMPATIBLE, f"{listing.get('molecule')} offered; you request {rfq.get('molecule')}.",
                      True, "Molecule"))
    else:
        out.append(_o("molecule", COMPATIBLE, f"{rfq.get('molecule')}.", True, "Molecule"))
    ls, le, rs, re_ = (_day(listing["delivery_start"]), _day(listing["delivery_end"]),
                       _day(rfq["delivery_start"]), _day(rfq["delivery_end"]))
    start, end = max(ls, rs), min(le, re_)
    if start > end:
        out.append(_o("window", INCOMPATIBLE, f"Delivers {ls} to {le}; you need {rs} to {re_}.", True, "Delivery window"))
    else:
        out.append(_o("window", COMPATIBLE, f"Overlap {start} to {end}.", True, "Delivery window"))
    ci = _ci(req, listing, mandatory)
    if ci:
        out.append(ci)
    for key, f in (("regimes", _regimes), ("accepted_schemes", _schemes), ("physical_form", _form),
                   ("quality_limits", _quality), ("incoterms", _incoterm)):
        if key in req:
            out.append(f(req, listing, key in mandatory))
    if "min_evidence_state" in req and "accepted_schemes" not in req and "regimes" not in req:
        out.append(_evidence_floor(req, listing, "min_evidence_state" in mandatory))
    if "delivery_country" in req:
        out.append(_o("delivery_country", NEEDS, f"The listing does not state delivery to {req['delivery_country']}; "
                                                 f"ask in an enquiry.", "delivery_country" in mandatory, "Destination"))
    # Ranking only: never mandatory.
    ceiling, price = rfq.get("max_price_eur_kg"), float(listing["price_eur_kg"])
    if ceiling:
        out.append(_o("price", COMPATIBLE if price <= float(ceiling) else INCOMPATIBLE,
                      f"€{price:g}/kg against your €{float(ceiling):g}/kg ceiling.", False, "Price"))
    vol, need = float(listing["volume_mtpd"]), float(rfq["volume_mtpd"])
    out.append(_o("volume", COMPATIBLE if vol >= need else INCOMPATIBLE,
                  f"{vol:g} of your {need:g} MTPD" + ("." if vol >= need else " (a partial fill)."), False, "Volume"))
    if listing.get("offer_type") == "indicative":
        out.append(_o("offer_type", NEEDS, "Indicative: the terms are to be confirmed by the seller.", False, "Offer"))

    hard = [o for o in out if o["mandatory"]]
    status = (INCOMPATIBLE if any(o["outcome"] == INCOMPATIBLE for o in hard)
              else NEEDS if any(o["outcome"] == NEEDS for o in hard) else COMPATIBLE)
    counts = {k: sum(1 for o in out if o["outcome"] == k) for k in (COMPATIBLE, INCOMPATIBLE, NEEDS)}
    return {"status": status, "eligible": status != INCOMPATIBLE, "counts": counts, "outcomes": out,
            "requirements_sha256": requirements_sha256(req)}


def rank_key(a: dict, listing: dict) -> tuple:
    """Eligibility first (compatible, then needs evidence, then excluded), then price, then volume."""
    return (STATUS_ORDER[a["status"]], float(listing["price_eur_kg"]), -float(listing["volume_mtpd"]))


def blocking(a: dict) -> list[str]:
    """The reasons of the mandatory requirements this listing fails."""
    return [o["reason"] for o in a["outcomes"] if o["mandatory"] and o["outcome"] == INCOMPATIBLE]


def outcome_of(a: dict, key: str) -> Optional[dict[str, Any]]:
    return next((o for o in a["outcomes"] if o["requirement"] == key), None)
