"""
Commitment cards — the structured terms behind a project's offtake, EPC,
schedule, supply and model (evidence rules 4.0.0).

The engine derives the offtake ladder (O0–O7), the EPC ladder (E0–E6) and ten
coherence checks from these cards together with the evidence. The cards are
facts the parties negotiate anyway — volumes, dates, damages caps, the commitment
form — recorded once so GEX can compare one contract with another. That
comparison is the convergence the mantra promises.

This module only validates. It is written against COMMITMENT_CARD_FIELDS in
app/core/bankability_engine.py, which a test holds identical to the engine's
own copy, so a field cannot be accepted here and ignored there.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.core.bankability_engine import COMMITMENT_CARD_FIELDS, TERMS_CARD_GATE

CARD_TYPES: list[str] = list(COMMITMENT_CARD_FIELDS)

# The offtake frame (Phase 3 of "One contract record", Q2): with several buyers the
# offtake card holds the SHARED terms at its top level and one entry per buyer in
# `buyers`, each naming the buyer's company (a party to the project). The engine
# never sees `buyers`: it reads one offtake card built from the CONFIRMED buyers
# (core/contract_tokens.frame_engine_card), so its spec stays the engine's own.
OFFTAKE_SHARED_FIELDS = ("product_spec_standard", "certification_scheme", "compliance_regime",
                         "fm_definition_ref", "change_in_law_allocated", "planned_output_tonnes_per_year")
OFFTAKE_BUYER_FIELDS = tuple(f for f in COMMITMENT_CARD_FIELDS["offtake"] if f not in OFFTAKE_SHARED_FIELDS)
_MAX_BUYERS = 20

# Fields that are shares, not amounts.
_PERCENT_FIELDS = {"take_or_pay_pct", "expected_availability_pct"}
_MAX_TEXT = 300
_MAX_LIST = 20


class TermsValidationError(ValueError):
    """Raised with every problem found, not just the first."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def validate_card(card_type: str, terms: Any) -> dict:
    """Return a clean copy of `terms` for `card_type`, or raise TermsValidationError.

    Empty values (None, "", []) are dropped: an unknown fact is absent, not zero.
    """
    if card_type not in COMMITMENT_CARD_FIELDS:
        raise TermsValidationError([f"Unknown card '{card_type}'. Cards: {', '.join(CARD_TYPES)}."])
    if not isinstance(terms, dict):
        raise TermsValidationError(["Terms must be an object of field: value."])
    spec = COMMITMENT_CARD_FIELDS[card_type]
    clean: dict[str, Any] = {}
    problems: list[str] = []
    if card_type == "offtake" and terms.get("buyers") not in (None, []):
        clean["buyers"] = _buyers(terms["buyers"], problems)
        stray = sorted(f for f in terms if f in OFFTAKE_BUYER_FIELDS and terms[f] not in (None, "", []))
        if stray:
            problems.append("A frame keeps each buyer's terms in `buyers`; not at the top: " + ", ".join(stray) + ".")
    for field, value in terms.items():
        if field == "buyers" and card_type == "offtake":
            continue
        if field not in spec:
            problems.append(f"'{field}' is not a field of the {card_type} card.")
            continue
        if value is None or value == "" or value == []:
            continue
        kind = spec[field]
        try:
            clean[field] = _coerce(field, kind, value)
        except ValueError as exc:
            problems.append(f"{field}: {exc}")
    if problems:
        raise TermsValidationError(problems)
    return clean


def _buyers(value: Any, problems: list[str]) -> list[dict]:
    """Each buyer of a frame: its company and its own offtake fields, validated as the card's."""
    if not isinstance(value, list) or not all(isinstance(b, dict) for b in value):
        problems.append("buyers: must be a list of buyers, each an object of field: value.")
        return []
    if len(value) > _MAX_BUYERS:
        problems.append(f"buyers: more than {_MAX_BUYERS}.")
    out, seen = [], set()
    spec = COMMITMENT_CARD_FIELDS["offtake"]
    for n, b in enumerate(value, start=1):
        company = b.get("company_id")
        if not isinstance(company, str) or not company.strip():
            problems.append(f"buyers[{n}]: company_id is required (the buyer's company, a party to the project).")
            continue
        company = company.strip()
        if company in seen:
            problems.append(f"buyers[{n}]: {company} appears twice; a frame has one sub-leg per buyer.")
        seen.add(company)
        entry: dict[str, Any] = {"company_id": company}
        for field, v in b.items():
            if field == "company_id" or v is None or v == "" or v == []:
                continue
            if field not in OFFTAKE_BUYER_FIELDS:
                problems.append(f"buyers[{n}]: '{field}' is not a buyer's field "
                                f"({'shared terms sit at the top of the card' if field in spec else 'unknown'}).")
                continue
            try:
                entry[field] = _coerce(field, spec[field], v)
            except ValueError as exc:
                problems.append(f"buyers[{n}].{field}: {exc}")
        out.append(entry)
    return out


def _coerce(field: str, kind: str, value: Any) -> Any:
    if kind == "str":
        if not isinstance(value, str):
            raise ValueError("must be text.")
        text = value.strip()
        if len(text) > _MAX_TEXT:
            raise ValueError(f"longer than {_MAX_TEXT} characters.")
        return text
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number.")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("must be a finite number, zero or more.")
        if field in _PERCENT_FIELDS and number > 100:
            raise ValueError("is a percentage and cannot exceed 100.")
        return number
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false.")
        return value
    if kind == "date":
        if not isinstance(value, str):
            raise ValueError("must be a date as YYYY-MM-DD.")
        try:
            return date.fromisoformat(value.strip()[:10]).isoformat()
        except ValueError:
            raise ValueError("must be a date as YYYY-MM-DD.")
    if kind == "list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError("must be a list of text values.")
        items = [v.strip() for v in value if v.strip()]
        if len(items) > _MAX_LIST:
            raise ValueError(f"more than {_MAX_LIST} entries.")
        return items
    if kind.startswith("enum:"):
        allowed = kind[5:].split("|")
        if value not in allowed:
            raise ValueError(f"must be one of {', '.join(allowed)}.")
        return value
    raise ValueError(f"unsupported field type '{kind}'.")  # a spec bug, never user input


def gate_for_card(card_type: str | None) -> str | None:
    """The gate a card belongs to, for write authorisation."""
    return TERMS_CARD_GATE.get(card_type) if card_type else None
