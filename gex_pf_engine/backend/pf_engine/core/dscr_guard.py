"""
One place decides whether a DSCR meets a covenant.
==================================================
`DSCR = CFADS / debt service` is UNDEFINED when debt service is zero — after
maturity, before first drawdown, or when a modelling gap leaves the schedule
empty. The engine represents that as `float('inf')`, and `inf >= 1.30` is True,
so an undefined ratio read as **passing** every covenant it was compared to.

Measured before this module existed:

    calculate_project_metrics(revenue=10M, opex=4M, capex=0, debt_service=0)
      → dscr = inf, dscr_compliant = True

    DebtSculptor(...).sculpt([...])   # horizon beyond tenor
      → sculpted_profile[10]["dscr"] = inf, is_compliant = True

That is a missing input producing maximum confidence, which is the inverse of
what a covenant test is for. `inf` is not a very good DSCR; it is the absence of
a denominator.

The sentinel is deliberately NOT changed to None inside the calculation — too
many call sites do `sum()`, `min()` and comparisons on the series, and swapping
the type there would trade a wrong answer for a crash. Instead, every place that
makes a DECISION or emits a VALUE routes through this module, and fails closed.
"""
from __future__ import annotations

import math
from typing import Any, Optional

UNDEFINED_REASON = (
    "no debt service in this period — DSCR is undefined, not infinite"
)


def is_defined(dscr: Any) -> bool:
    """True only for a real, finite ratio."""
    return isinstance(dscr, (int, float)) and not isinstance(dscr, bool) and math.isfinite(dscr)


def meets(dscr: Any, threshold: float) -> bool:
    """Does this DSCR satisfy a covenant? An undefined DSCR NEVER does."""
    return is_defined(dscr) and float(dscr) >= threshold


def breaches(dscr: Any, threshold: float) -> bool:
    """Is this DSCR below a trigger? Undefined does NOT trigger a breach either:
    with no debt service there is nothing to default on. Undefined is neither
    compliant nor in breach — it is unknown, and both questions answer False."""
    return is_defined(dscr) and float(dscr) < threshold


def for_output(dscr: Any, digits: int = 3) -> Optional[float]:
    """The value to put in a response body. `None`, never `inf`.

    `json.dumps(float('inf'))` emits the token `Infinity`, which is not valid
    JSON — `JSON.parse` rejects it and strict parsers raise. `null` is valid and
    says what is true: the ratio is not defined here.
    """
    return round(float(dscr), digits) if is_defined(dscr) else None
