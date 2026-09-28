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
    for field, value in terms.items():
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
