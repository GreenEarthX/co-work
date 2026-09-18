"""
CHARACTERIZATION — DSCR/LLCR as they behave TODAY, across three services.
=========================================================================
THIS FILE RECORDS A DEFECT. IT DOES NOT ENDORSE IT.

Every assertion here pins current behaviour so a fix has a baseline. Where the
current behaviour is wrong, the test says so and states what it should become.
**When the fix lands, these tests are expected to fail — that is the point.**
Update them deliberately; do not "repair" them to keep the suite green.

THREE SERVICES COMPUTE DSCR/LLCR
--------------------------------
  1. `files/gex_pf_engine/backend/app/core/`   the sibling, serving :8001
       engine.py `_calculate_dscr`, cfads.py:313, waterfall.py:368
  2. `gex-platform-enhanced/deal_engine/compute/ratios.py`
       `compute_dscr`, `compute_llcr` — dormant, no launch entry, no caller
  3. `gex-platform-enhanced/backend/app/api/v1/pre_cod_metrics.py`
       `_compute_llcr` — the consumer; expects PV(CFADS) as an INPUT

The arithmetic agrees everywhere: DSCR = CFADS / debt service. **The guard on
the undefined case does not.**

THE DEFECT
----------
When debt service is zero the sibling returns `float('inf')`, and
`engine.py:70` immediately evaluates `dscr >= 1.3`. Measured:

    calculate_project_metrics(revenue=10M, opex=4M, capex=0, debt_service=0)
      → dscr = inf, dscr_compliant = True

`inf` is not a very good DSCR. It is *the absence of debt service*, and it
conflates two different situations — pre-FID with no debt drawn, and a
modelling gap where `total_annual_debt_service()` returned 0 by mistake — into
the strongest possible pass. **A missing input produces maximum confidence**,
which is the inverse of fail-closed and the same shape as the PLATFORM_ADMIN
default that was removed from the shim on 2026-09-08.

`deal_engine.compute_dscr` returns **None** on identical input, and `None >= 1.3`
raises TypeError rather than silently passing. That is the correct direction.

WHAT THE FIX SHOULD DO (then update this file)
----------------------------------------------
  · undefined DSCR must not compare as compliant — return None, or a sentinel
    plus an explicit "no debt service" status
  · the covenant check must treat undefined as NOT compliant
  · `inf` must never reach a response body: json.dumps emits `Infinity`, which
    is not valid JSON and JSON.parse rejects it
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

# A THIRD NAME COLLISION, found writing this test: the platform package and the
# sibling package are BOTH called `app`. Whichever loads first wins and the
# other's submodules become unreachable. `_sibling_engine()` therefore loads the
# sibling by file path rather than by import, so this plain import is safe.
from app.api.v1.pre_cod_metrics import _compute_llcr  # noqa: E402

SIBLING = Path(__file__).resolve().parents[2].parent / "gex_pf_engine" / "backend"
CFADS = 10_000_000.0
NO_DEBT_SERVICE = 0.0
COVENANT = 1.30


def _sibling(snippet: str) -> dict:
    """Evaluate `snippet` against the sibling engine and return its JSON.

    Direct in-process import, restored 2026-09-09. It used to shell out to the
    sibling's own interpreter, because BOTH repos had a top-level package named
    `app` — whichever imported first won, and the other's submodules vanished.
    Two earlier approaches failed on that: sys.path insertion (killed
    `app.api.v1`) and importlib-by-path (broke the moment engine.py imported
    from its own package, and this file turned that into a SKIP — five tests
    silently stopped running while the suite stayed green).

    The sibling package is now `pf_engine`, so there is nothing to collide and
    a plain import is correct again.
    """
    if not (SIBLING / "pf_engine" / "core" / "engine.py").exists():
        pytest.skip(f"sibling gex_pf_engine not present at {SIBLING}")
    if str(SIBLING) not in sys.path:
        sys.path.insert(0, str(SIBLING))
    try:
        import pf_engine.core.dscr_guard as guard          # noqa: F401
        from pf_engine.core.engine import ProjectFinanceEngine
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"sibling engine no longer importable: {exc}")
    return {"engine": ProjectFinanceEngine("char", "c"), "guard": guard}


# ── 1. The sibling: undefined DSCR becomes infinity ─────────────────────────

def test_sibling_dscr_is_infinite_when_debt_service_is_zero():
    """CURRENT: the raw ratio is still inf. The 2026-09-09 fix deliberately did
    NOT change the sentinel — too many call sites do sum()/min()/comparisons on
    the series — it changed every DECISION and OUTPUT to fail closed instead."""
    e = _sibling("")["engine"]
    assert e._calculate_dscr(10_000_000.0, 0.0) == math.inf

def test_undefined_dscr_is_NOT_covenant_compliant():
    """
    FIXED 2026-09-09. Was `dscr_compliant: True` — a project with no debt
    service modelled reported as PASSING its DSCR covenant. A missing input
    produced maximum confidence.
    """
    e = _sibling("")["engine"]
    cc = e.calculate_project_metrics(revenue=10_000_000, opex=4_000_000, capex=0,
                                     debt_service=0, period="2027")["covenant_compliance"]
    assert cc["dscr_compliant"] is False, "the undefined-DSCR defect is back"
    assert cc["dscr_defined"] is False
    assert cc["dscr_value"] is None, "inf must never reach a response body"

def test_check_covenants_treats_undefined_as_critical():
    """FIXED. Was `compliant: True, severity: ok` for an infinite DSCR."""
    e = _sibling("")["engine"]
    r = e.check_covenants({"dscr": math.inf}, {"dscr_minimum": 1.30})
    c = r["checks"][0]
    assert c["compliant"] is False and c["severity"] == "critical"
    assert c["actual"] is None
    assert "no debt service" in (c.get("reason") or "")
    assert r["all_compliant"] is False

def test_rounding_does_not_remove_infinity():
    """Why it survives cfads.py: `result["dscr"] = round(dscr, 3)`."""
    assert round(math.inf, 3) == math.inf


# ── 2. deal_engine: the same case, the correct direction ────────────────────

def test_deal_engine_returns_none_for_the_same_input():
    """CURRENT and CORRECT. Keep this one when the fix lands."""
    from deal_engine.compute.ratios import compute_dscr

    assert compute_dscr(CFADS, NO_DEBT_SERVICE) is None


def test_none_cannot_silently_pass_a_covenant():
    """The property `inf` lacks: an undefined DSCR raises rather than passing."""
    from deal_engine.compute.ratios import compute_dscr

    dscr = compute_dscr(CFADS, NO_DEBT_SERVICE)
    with pytest.raises(TypeError):
        _ = dscr >= COVENANT  # type: ignore[operator]


def test_the_two_engines_no_longer_disagree_on_the_DECISION():
    """
    The raw sentinels still differ — sibling `inf`, deal_engine `None` — but
    both now refuse to call an undefined DSCR compliant, which is the property
    that mattered. Divergence in a value nobody compares is tolerable;
    divergence in a covenant verdict is not.
    """
    from deal_engine.compute.ratios import compute_dscr

    got = _sibling("")
    raw = got["engine"]._calculate_dscr(10_000_000.0, 0.0)
    assert raw == math.inf and got["guard"].meets(raw, 1.30) is False
    assert compute_dscr(CFADS, NO_DEBT_SERVICE) is None

def test_both_agree_when_debt_service_is_real():
    """The disagreement was always confined to the undefined case."""
    from deal_engine.compute.ratios import compute_dscr

    e = _sibling("")["engine"]
    assert e._calculate_dscr(10_000_000.0, 5_000_000.0) == pytest.approx(
        compute_dscr(CFADS, 5_000_000.0))
    assert compute_dscr(CFADS, 5_000_000.0) == pytest.approx(2.0)

# ── 3. LLCR: two halves of one calculation, not two versions ────────────────

def test_deal_engine_llcr_discounts_the_stream_itself():
    """`deal_engine` takes a CFADS STREAM and does the NPV."""
    from deal_engine.compute.ratios import compute_llcr

    stream = [1_000_000.0] * 3
    v = compute_llcr(stream, 0.10, 2_000_000.0)
    expected = sum(1_000_000.0 / (1.10 ** (t + 1)) for t in range(3)) / 2_000_000.0
    assert v == pytest.approx(expected)


def test_deal_engine_llcr_is_none_without_debt():
    from deal_engine.compute.ratios import compute_llcr

    assert compute_llcr([1_000_000.0], 0.10, 0.0) is None


def test_backend_llcr_expects_the_pv_as_an_input_and_pends_without_it():
    """
    `pre_cod_metrics` is the CONSUMER: it takes PV(CFADS) already discounted and
    only divides. Its own PENDING text names the PF engine as the source — but
    `deal_engine` computes exactly that PV too, so two services can supply one
    number and nothing declares which is canonical.
    """
    r = _compute_llcr(None)
    assert r.status == "PENDING"
    assert "pv_cfads" in r.formatted or "PENDING" in r.formatted
    assert "PF engine" in r.next_action


# ── 4. Infinity is not valid JSON ───────────────────────────────────────────

def test_infinity_serialises_to_invalid_json():
    """
    A second failure riding the same value: Python emits `Infinity`, which
    `JSON.parse` rejects. The frontend either errors or drops the field.
    """
    assert json.dumps({"dscr": math.inf}) == '{"dscr": Infinity}'
    with pytest.raises(json.JSONDecodeError):
        json.loads('{"dscr": Infinity}', parse_constant=_reject)


def _reject(_name: str):
    raise json.JSONDecodeError("Infinity is not valid JSON", "", 0)
