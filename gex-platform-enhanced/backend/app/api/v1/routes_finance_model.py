"""
GEX Platform — Finance Model Proxy Routes
==========================================
Proxies financial modeling requests from the platform frontend to gex_pf_engine (port 8001).

Mount in main.py:

    from app.api.v1.routes_finance_model import router as finance_model_router
    app.include_router(finance_model_router, prefix="/api/v1/finance-model", tags=["Finance Model"])

Architecture:
    Frontend (React) -> Platform Backend (8000) /api/v1/finance-model/* -> Engine (8001) /api/v1/model/*
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.engine_auth import engine_auth_headers

from app.api.v1.routes_entitlements import require_finance_entitlement

router = APIRouter()

MODEL_ENGINE_URL = os.getenv("GEX_ENGINE_URL", "http://localhost:8001")
ENGINE_TIMEOUT = 30.0

# Honesty stamp on every surfaced PF metric. The waterfall/CFADS/DSCR MATH is
# engine-computed and real; the INPUTS the platform feeds today are illustrative
# (demo project parameters, not executed deal terms). Surfacing a debt metric
# without this provenance would be the Finance equivalent of the fabricated
# "P&L MTD" tile removed from Commercial. Lift basis to DEAL_TERMS once real
# financing terms are loaded per project.
PF_MODEL = "gex_pf_engine · PF cashflow / waterfall model"


# P1: cost fields a PF body may carry, mapped to the verified base-case figure they
# must match. Per-kg/rate fields (e.g. opex_eur_kg) are deliberately NOT bound — they
# are a different unit from the base case's absolute EUR figures.
_COST_BINDINGS = {"capex": "capex_eur", "total_capex": "capex_eur",
                  "opex": "opex_eur_per_year", "opex_eur_per_year": "opex_eur_per_year"}
_RECONCILE_TOL = 0.01  # 1% relative tolerance


def _reconcile_cost_basis(inputs: dict, gate: Optional[dict]) -> None:
    """P1: bind a release-gated PF body to the VERIFIED model_base_case.

    `_require_release_ready` proves a verified base case EXISTS; this proves THIS
    compute used it. Any cost field in the body that materially diverges from the
    verified figure is refused — a release-authorised DSCR may not be computed on
    numbers unrelated to the approved cost basis.
    """
    if not isinstance(inputs, dict) or not gate or gate.get("gate") != "RELEASE_READY":
        return
    for field, base_key in _COST_BINDINGS.items():
        if inputs.get(field) is None:
            continue
        base_val = gate.get(base_key)
        if not base_val:
            continue
        try:
            supplied = float(inputs[field])
        except (TypeError, ValueError):
            continue
        if abs(supplied - base_val) / base_val > _RECONCILE_TOL:
            raise HTTPException(
                status_code=409,
                detail=(f"body '{field}'={supplied:,.0f} diverges from the VERIFIED "
                        f"model_base_case {base_key}={base_val:,.0f} "
                        f"({gate.get('base_case_claim')}). Release-gated compute must "
                        f"use the approved cost basis, not unrelated inputs."),
            )


def _governed(payload: dict, inputs: dict, basis: str = "ILLUSTRATIVE_INPUTS",
              gate: Optional[dict] = None) -> dict:
    if not isinstance(payload, dict):
        payload = {"result": payload}
    # P1: a release-gated result must reconcile to the verified basis, or be refused.
    _reconcile_cost_basis(inputs, gate)
    # A RELEASE_READY gate means the cost basis is a VERIFIED model_base_case —
    # the only condition under which a PF metric may be treated as bankable.
    if gate and gate.get("gate") == "RELEASE_READY":
        basis = "RELEASE_READY_BASE_CASE"
        note = ("Engine-computed on a VERIFIED model_base_case "
                f"({gate.get('base_case_claim')}), reconciled to cost basis "
                f"{gate.get('cost_basis_hash')}. Release-gated compute authorised.")
    else:
        note = ("Engine-computed mechanics on ILLUSTRATIVE inputs (demo project "
                "parameters, not executed deal terms). Not for credit decisions.")
    gov = {
        "model": PF_MODEL,
        "basis": basis,
        "note": note,
        "input_sha": hashlib.sha256(
            json.dumps(inputs, sort_keys=True, default=str).encode()
        ).hexdigest()[:12],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    if gate and gate.get("cost_basis_hash"):
        gov["cost_basis_hash"] = gate["cost_basis_hash"]
    if gate:
        gov["release_gate"] = gate
    return {**payload, "governance": gov}


async def _require_release_ready(project_id: Optional[str]) -> dict:
    """Enforce the B7 compute-authorization rule at the PF call site.

    Release-gated PF compute (waterfall, covenants, DSCR, lifetime, structured
    financing) may run for a real project ONLY when that project's live
    model_base_case is terminal-valid (verified/satisfied). A provisional
    (submitted) cost basis is refused — you cannot derive a bankable/drawdown
    figure from an unapproved cost basis.

    When no project_id is supplied the call is ungated (legacy/illustrative path);
    the governance stamp already marks those outputs not-for-credit.
    """
    if not project_id:
        return {"gate": "UNGATED_NO_PROJECT"}
    try:
        from app.api.v1.routes_tea import release_ready_state
    except Exception:  # noqa: BLE001 — TEA bridge not mounted
        return {"gate": "TEA_BRIDGE_ABSENT"}
    st = release_ready_state(project_id)
    if st is None:
        raise HTTPException(
            status_code=409,
            detail=(f"No model_base_case for project '{project_id}'. Run "
                    f"POST /api/v1/tea/compute/{project_id} first; release-gated "
                    f"compute refused."),
        )
    if not st["is_release_ready"]:
        raise HTTPException(
            status_code=409,
            detail=(f"model_base_case for '{project_id}' is '{st['state']}' "
                    f"(PROVISIONAL). Release-gated compute requires a VERIFIED "
                    f"base case — approve via POST /api/v1/tea/base-case/"
                    f"{st['claim_id']}/approve."),
        )
    return {"gate": "RELEASE_READY", "base_case_claim": st["claim_id"],
            "cost_basis_hash": st.get("cost_basis_hash"),
            "capex_eur": st.get("capex_eur"),
            "opex_eur_per_year": st.get("opex_eur_per_year")}


async def _call_model(path: str, method: str = "GET", json_data=None,
                      request: Optional["Request"] = None):
    """
    Proxy to the PF engine (:8001). The engine verifies GEX platform JWTs, so
    every call must carry the caller's bearer or a platform service token —
    see app/services/engine_auth.py. Without it the engine answers 401 and the
    failure surfaces to the user as "engine unavailable", which is wrong and
    sends debugging in the wrong direction.
    """
    url = f"{MODEL_ENGINE_URL}/api/v1/model{path}"
    headers = engine_auth_headers(request)
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT) as client:
            resp = await (client.post(url, json=json_data, headers=headers)
                          if method == "POST" else client.get(url, headers=headers))
            if resp.status_code in (401, 403):
                raise HTTPException(
                    status_code=502,
                    detail="Finance model engine refused the call (authorization not "
                           "propagated) — this is an auth failure, not an outage.",
                )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Model engine error: {resp.text}")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Finance model engine unavailable (port 8001)")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Finance model engine timeout")


# ─── DSCR sensitivity surface ────────────────────────────────────────────────
# The model lives in app/services/dscr_sensitivity.py so that this route, the
# DSCRAggregator and the frontend all describe the same surface. It previously
# existed three times with two different sign conventions.
from app.services.dscr_sensitivity import compute_sensitivity


@router.post("/sensitivity")
async def dscr_sensitivity(body: dict, project_id: Optional[str] = None):
    """
    DSCR sensitivity: single-factor table, two-factor surface and break-even
    floors — all derived from one cashflow identity, so the tables cannot
    disagree about the sign or magnitude of a shock.

    Body (optional; defaults are illustrative structural parameters, not deal
    terms): revenue, opex_power, opex_other, debt_service, base_efficiency_pct,
    debt_share_of_capex, debt_service_pct_per_100bps, covenant_floor,
    target_dscr, power_deltas[], efficiency_deltas[].
    """
    covenant_floor = float(body.get("covenant_floor", 1.20))
    target_dscr = float(body.get("target_dscr", 1.30))
    payload = compute_sensitivity(body, covenant_floor=covenant_floor, target_dscr=target_dscr)
    gate = await _require_release_ready(project_id)
    return _governed(payload, {"sensitivity_inputs": body, "covenant_floor": covenant_floor}, gate=gate)


@router.get("/health")
async def health():
    return await _call_model("/health")


@router.post("/cfads")
async def calculate_cfads(body: dict):
    """
    Calculate Cash Flow Available for Debt Service.

    Body: { production_mtpd, offtake_price_eur_kg, subsidies?, opex_eur_kg, maintenance_capex?, period_days? }
    """
    return _governed(await _call_model("/cfads/calculate", method="POST", json_data=body), body)


@router.post("/lifetime")
async def model_lifetime(body: dict, project_id: Optional[str] = None):
    """
    Full 15–25 year project lifetime model.

    Body: { capacity_mtpd, price_eur_kg, opex_eur_kg, total_capex,
            senior_debt_amount, interest_rate, tenor_years, operations_start_year? }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/model/lifetime", method="POST", json_data=body), body, gate=gate)


@router.post("/covenants")
async def check_covenants(body: dict, project_id: Optional[str] = None):
    """
    Check financial covenant compliance.

    Body: { dscr, dsra_funded, completion_guarantee, covenant_requirements }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/covenants/check", method="POST", json_data=body), body, gate=gate)


@router.post("/waterfall")
async def execute_waterfall(body: dict, project_id: Optional[str] = None):
    """
    Distribute CFADS across reserve accounts, debt tranches, and equity.

    Body: { cfads, senior_debt_service, junior_debt_service?, mezzanine_service?, dsra_required?, maintenance_reserve? }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/waterfall/execute", method="POST", json_data=body), body, gate=gate)


@router.post("/metrics")
async def calculate_metrics(body: dict, project_id: Optional[str] = None):
    """
    Calculate core project financial metrics (CFADS, DSCR, covenant status).

    Body: { revenue, opex, capex, debt_service, period }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/metrics/calculate", method="POST", json_data=body), body, gate=gate)


# ─── Concessional / DFI-aware endpoints ─────────────────────────────────

@router.post("/cfads-with-financing")
async def calculate_cfads_with_financing(body: dict, project_id: Optional[str] = None):
    """
    CFADS with multi-tranche financing structure (DFI, concessional, senior).
    Release-gated via `project_id`.

    Body: { production_mtpd, offtake_price_eur_kg, opex_eur_kg, year?,
            subsidies?, maintenance_capex?, tranches[], equity_amount,
            equity_cost?, grants_amount? }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/cfads/calculate-with-financing", method="POST", json_data=body), body, gate=gate)


@router.post("/waterfall-structured")
async def execute_waterfall_structured(body: dict, project_id: Optional[str] = None):
    """
    Structured waterfall with multi-tranche priority cascade.
    Release-gated via `project_id`.

    Body: { cfads, year?, tranches[], equity_amount, grants_amount? }
    """
    gate = await _require_release_ready(project_id)
    return _governed(await _call_model("/waterfall/execute-structured", method="POST", json_data=body), body, gate=gate)


# ─── Increment 4: multi-currency CFADS (contract-specified per-stream rates) ──

def _require_contract_fx(streams: list, base_ccy: str) -> None:
    """Each foreign-currency stream must carry its OWN contract-specified fx_rate —
    the rate is a contract term, not the platform's dated benchmark. A stream in the
    base currency needs none (rate 1.0)."""
    for s in streams or []:
        if not isinstance(s, dict):
            continue
        ccy = (s.get("currency") or base_ccy).upper()
        if ccy != base_ccy and s.get("fx_rate") is None:
            raise HTTPException(
                status_code=422,
                detail=(f"stream '{s.get('label', '?')}' is in {ccy} but has no contract-specified "
                        f"fx_rate to {base_ccy}. Multi-currency CFADS requires each foreign-currency "
                        f"stream to carry its own contract rate (not the platform benchmark)."))


@router.post("/cfads-multi-currency")
async def calculate_cfads_multi_currency(body: dict, project_id: Optional[str] = None):
    """Multi-currency CFADS: each revenue/opex stream carries its OWN currency and its
    CONTRACT-SPECIFIED fx_rate to the project base currency. Release-gated via `project_id`.

    Body: { revenue_streams:[{label,amount,currency,fx_rate}], opex_streams:[...],
            base_currency?, maintenance_capex?, working_capital_change?, tax_rate? }
    """
    gate = await _require_release_ready(project_id)
    # base currency: explicit → the project's persisted setting (increment 2) → EUR
    base_ccy = (body.get("base_currency") or "").upper()
    if not base_ccy and project_id:
        try:
            from app.api.v1.routes_tea import _project_currency
            base_ccy = (_project_currency(project_id) or "").upper()
        except Exception:  # noqa: BLE001 — TEA bridge not mounted
            base_ccy = ""
    base_ccy = base_ccy or "EUR"

    rev = body.get("revenue_streams") or []
    opx = body.get("opex_streams") or []
    _require_contract_fx(rev, base_ccy)
    _require_contract_fx(opx, base_ccy)

    payload = {
        "revenue_streams": rev, "opex_streams": opx, "base_currency": base_ccy,
        "maintenance_capex": body.get("maintenance_capex", 0),
        "working_capital_change": body.get("working_capital_change", 0),
        "tax_rate": body.get("tax_rate", 0.21),
    }
    return _governed(
        await _call_model("/cfads/calculate-multi-currency", method="POST", json_data=payload),
        body, gate=gate)


# ─── B1: DSCR Heatmap from trading book cashflows ────────────────────────

from datetime import date
from decimal import Decimal
from typing import Optional
from fastapi import Query


@router.get(
    "/dscr-heatmap/{asset_id}",
    dependencies=[Depends(require_finance_entitlement("dscr_sensitivity"))],
)
async def dscr_heatmap(
    asset_id: str,
    request: Request,
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    annual_debt_service: Optional[float] = Query(
        default=None,
        description="Annual debt service assumption (EUR). Required pre-financial-close.",
    ),
    covenant_floor: float = Query(default=1.20),
    power_opex_share: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Power's fraction of total OPEX (0..1). REQUIRED for the "
                    "stress grid, sensitivity rows and break-evens: both stress "
                    "axes act on the power component, and the trading book "
                    "projection carries one undifferentiated OPEX total. Omit it "
                    "and those three outputs come back empty with "
                    "sensitivityBasis=none_power_opex_split_not_supplied, rather "
                    "than stressed against a fabricated split.",
    ),
    base_efficiency_pct: Optional[float] = Query(
        default=None,
        gt=0.0,
        description="System efficiency (%) this project's efficiency axis is "
                    "quoted against. Denominator of the efficiency shock — a "
                    "project at 60%% stressed against the illustrative 72%% "
                    "understates its own sensitivity.",
    ),
):
    """
    DSCR sensitivity heatmap driven by real trading book cashflows.

    Fetches the cashflow projection for `asset_id` from the B1 trading book
    endpoint, then aggregates into CFADS/DSCR per period plus the 5x5
    stress grid the frontend DSCRHeatmap.tsx expects.

    Pre-financial-close projects have no debt_service contract lines.
    Pass `annual_debt_service` to supply a synthetic assumption so DSCR
    can still be computed (flagged as debt_service_source=synthetic_assumption).
    """
    from app.services.cashflow_client import cashflow_client
    from app.services.dscr_aggregator import DSCRAggregator

    fd = date.fromisoformat(from_date) if from_date else None
    td = date.fromisoformat(to_date) if to_date else None

    try:
        projection = await cashflow_client.fetch_projection(
            asset_id=asset_id, from_date=fd, to_date=td, request=request,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            # Do not relabel an internal auth failure as a downstream outage —
            # that is what made this present as "engine unavailable" before.
            raise HTTPException(
                status_code=502,
                detail="Trading book refused the internal cashflow call "
                       "(authorization not propagated). DSCR cannot be computed.",
            )
        raise HTTPException(status_code=502, detail=f"Trading book error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Trading book error: {e}")

    ads = Decimal(str(annual_debt_service)) if annual_debt_service else None
    overrides: dict = {}
    if base_efficiency_pct is not None:
        overrides["base_efficiency_pct"] = base_efficiency_pct
    aggregator = DSCRAggregator(
        annual_debt_service=ads,
        covenant_floor=Decimal(str(covenant_floor)),
        power_opex_share=power_opex_share,
        sensitivity_overrides=overrides,
    )
    result = aggregator.compute(projection)

    return {
        "project_asset_id": result.project_asset_id,
        "project_name": result.project_name,
        "from_date": result.from_date.isoformat(),
        "to_date": result.to_date.isoformat(),
        "baseDSCR": result.base_dscr,
        "minDSCR": result.min_dscr,
        "avgDSCR": result.avg_dscr,
        "sensitivityRows": [
            {
                "factor": r.factor,
                "label": r.label,
                "unit": r.unit,
                "deltaLabels": r.delta_labels,
                "values": r.values,
            }
            for r in result.sensitivity_rows
        ],
        "heatmapCells": [
            {"powerDelta": c.power_delta, "effDelta": c.eff_delta, "dscr": c.dscr}
            for c in result.heatmap_cells
        ],
        "breakevenMetrics": [
            {
                "label": m.label,
                "value": m.value,
                "description": m.description,
                "breached": m.breached,
            }
            for m in result.breakeven_metrics
        ],
        "monthlySeries": result.monthly_series,
        "debtServiceSource": result.debt_service_source,
        "sensitivityBasis": result.sensitivity_basis,
        "hasEstimates": result.has_estimates,
        "estimatePeriodCount": result.estimate_period_count,
    }


# ─── R1: Protected drawdown / Financial Close timeline layer ──────────────────
# The sensitive layer (Financial Close phase: term sheets, facility agreements,
# lender names; plus per-milestone drawdown amounts and funding triggers) lives
# here, NOT in the frontend bundle. Served only to users authorised for THIS
# project (qualified finance role + relationship, or active FINANCE_REVIEW grant).
# Unauthorized / unknown project → 403 (no sensitive detail leaks).

_DRAWDOWN_DEFAULT = {
    "financial_close": {
        "phase": "FINANCIAL_CLOSE", "status": "PLANNED",
        "milestones": [
            {"name": "Term Sheet", "status": "PLANNED", "targetDate": "2027-Q3", "owner": "CFO", "fundingTrigger": True, "drawdownAmount": 95_000_000},
            {"name": "FID Decision", "status": "PLANNED", "targetDate": "2027-Q4", "owner": "Board", "fundingTrigger": False},
            {"name": "Facility Agreement", "status": "PLANNED", "targetDate": "2028-Q1", "owner": "Legal", "fundingTrigger": True, "drawdownAmount": 40_000_000},
        ],
    },
    "drawdowns": [
        {"phase": "FINANCIAL_CLOSE", "name": "Term Sheet", "targetDate": "2027-Q3", "drawdownAmount": 95_000_000},
        {"phase": "FINANCIAL_CLOSE", "name": "Facility Agreement", "targetDate": "2028-Q1", "drawdownAmount": 40_000_000},
        {"phase": "CONSTRUCTION", "name": "NTP Issued", "targetDate": "2028-Q1", "drawdownAmount": 45_000_000},
    ],
}

_DRAWDOWN_BY_PROJECT: dict[str, dict] = {
    "proj_le_havre_eng": {
        "financial_close": {
            "phase": "FINANCIAL_CLOSE", "status": "IN_PROGRESS",
            "milestones": [
                {"name": "IE Final Signoff", "status": "IN_PROGRESS", "targetDate": "2026-Q2", "owner": "IE (Mott MacDonald)", "fundingTrigger": False},
                {"name": "BPI+EIB Term Sheet", "status": "IN_PROGRESS", "targetDate": "2026-Q2", "owner": "CFO", "fundingTrigger": True, "drawdownAmount": 210_000_000},
                {"name": "Credit Committee", "status": "PLANNED", "targetDate": "2026-Q3", "owner": "BPI", "fundingTrigger": False},
                {"name": "FID Decision", "status": "PLANNED", "targetDate": "2026-Q3", "owner": "Board", "fundingTrigger": False},
                {"name": "Facility Agreement", "status": "PLANNED", "targetDate": "2026-Q3", "owner": "Legal", "fundingTrigger": True, "drawdownAmount": 42_000_000},
            ],
        },
        "drawdowns": [
            {"phase": "FINANCIAL_CLOSE", "name": "BPI+EIB Term Sheet", "targetDate": "2026-Q2", "drawdownAmount": 210_000_000},
            {"phase": "FINANCIAL_CLOSE", "name": "Facility Agreement", "targetDate": "2026-Q3", "drawdownAmount": 42_000_000},
            {"phase": "CONSTRUCTION", "name": "NTP Issued", "targetDate": "2026-Q3", "drawdownAmount": 85_000_000},
            {"phase": "CONSTRUCTION", "name": "Electrolyser Delivery", "targetDate": "2027-Q1", "drawdownAmount": 55_000_000},
            {"phase": "CONSTRUCTION", "name": "Methanation Unit FAT", "targetDate": "2027-Q4", "drawdownAmount": 28_000_000},
        ],
    },
    "proj_bremen_h2": {
        "financial_close": {
            "phase": "FINANCIAL_CLOSE", "status": "PLANNED",
            "milestones": [
                {"name": "KfW Term Sheet", "status": "PLANNED", "targetDate": "2026-Q3", "owner": "CFO", "fundingTrigger": True, "drawdownAmount": 120_000_000},
                {"name": "FID Decision", "status": "PLANNED", "targetDate": "2026-Q4", "owner": "Board", "fundingTrigger": False},
            ],
        },
        "drawdowns": [
            {"phase": "FINANCIAL_CLOSE", "name": "KfW Term Sheet", "targetDate": "2026-Q3", "drawdownAmount": 120_000_000},
            {"phase": "CONSTRUCTION", "name": "NTP Issued", "targetDate": "2027-Q1", "drawdownAmount": 60_000_000},
        ],
    },
}


@router.get(
    "/drawdown-timeline/{project_id}",
    dependencies=[Depends(require_finance_entitlement("drawdown_timeline"))],
)
async def drawdown_timeline(project_id: str):
    """
    Sensitive Financial Close / drawdown layer for a project. Authorization is
    enforced by the dependency (403 for unauthorized callers and unknown
    projects). Returns the FINANCIAL_CLOSE phase + per-milestone drawdown
    amounts that are deliberately NOT shipped in the frontend bundle.
    """
    layer = _DRAWDOWN_BY_PROJECT.get(project_id, _DRAWDOWN_DEFAULT)
    return {"project_id": project_id, **layer}
