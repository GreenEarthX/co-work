"""
Non-finite numbers must never enter — or leave — this API.
==========================================================
`Infinity`, `-Infinity` and `NaN` are Python floats that `json.dumps` will
happily emit as bare tokens. They are NOT valid JSON: `JSON.parse` rejects them
and any strict parser raises. Python's own `json.loads` accepts them on the way
in, so an inf can enter a request body, survive validation, and only explode
later.

MEASURED 2026-09-09, before this module existed:

    POST /api/v1/model/covenants/check
    {"dscr": 1e400, "covenant_requirements": {...}}      # 1e400 parses as inf
      → HTTP 500 "Internal Server Error"

The request was genuinely invalid — it omitted `dsra_funded` and
`completion_guarantee` — so it should have been a 422. FastAPI builds that 422
body by echoing the offending input back to the caller, the echo contained
`inf`, and serialising the error response failed. The server logged 422 and
sent 500. A caller could not tell a bad request from a broken engine.

TWO HALVES, BOTH NEEDED
-----------------------
1. `FiniteModel` rejects non-finite floats at validation, with a message that
   says why. This is the honest error.
2. `finite_safe_validation_handler` scrubs the echoed input before serialising,
   so the 422 body is always valid JSON — including for a field that is not
   declared as a float, or a model that has not adopted `FiniteModel` yet.

(1) alone is not enough: the error response still echoes the raw input.
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

NON_FINITE_MESSAGE = (
    "must be a finite number — Infinity and NaN are not valid JSON and cannot "
    "be used in a financial calculation"
)


def _scrub(value: Any) -> Any:
    """Replace non-finite floats with a readable marker, recursively."""
    if isinstance(value, float) and not math.isfinite(value):
        return f"<non-finite: {value}>"
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


class FiniteModel(BaseModel):
    """Base for request models: no field may carry Infinity or NaN.

    Applied with `"*"` rather than per-field so a float added later is covered
    without anyone remembering. `routes_model.py` alone declares 26 float
    fields across 6 models; annotating each one would have been 26 chances to
    miss one.
    """

    @field_validator("*", mode="after")
    @classmethod
    def _reject_non_finite(cls, v: Any) -> Any:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(NON_FINITE_MESSAGE)
        if isinstance(v, (list, tuple)) and any(
            isinstance(x, float) and not math.isfinite(x) for x in v
        ):
            raise ValueError(NON_FINITE_MESSAGE)
        return v


async def finite_safe_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI's 422, but guaranteed to serialise.

    Same shape as the default handler; the only difference is that `input` is
    scrubbed of non-finite floats first, so building the error can never be the
    thing that fails.
    """
    errors = []
    for err in exc.errors():
        e = dict(err)
        if "input" in e:
            e["input"] = _scrub(e["input"])
        e.pop("ctx", None)          # may hold un-serialisable exception objects
        errors.append(e)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )
