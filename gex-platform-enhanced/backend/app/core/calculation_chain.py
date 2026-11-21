"""
The calculation chain — plant -> economics -> financing -> returns (JML, 2026-11-18).
====================================================================================
Four records, each citing the exact version before it by id AND hash:

  1. cost_basis_version      the Cost Basis the OWNER saved: its configuration and
                             the result the SERVER recomputed from it (never the
                             client's figures).
  2. model_base_case         a TEA run priced FROM one saved cost basis (TEA inputs
                             derived here, not typed), then REVIEWED by someone other
                             than the person who ran it.
  3. financing_case_version  debt, rate, tenor and grant, each with its source, on
                             ONE reviewed TEA base case.
  4. returns_case_version    published by the owner; the chain fields of its inputs
                             (FCI, OPEX, output, life, debt) are set from 1-3 here,
                             and the version stores the source versions, every
                             reconciliation check and every remaining assumption.

Rules held here, as pure functions:

  * A figure that comes from the chain is never accepted from the caller; a caller
    value that contradicts it is refused (CHAIN_CONFLICT), not silently replaced.
  * Product output counts only the lines that produce the cost basis's molecule.
    The Cost Basis screen's "annual output" adds every line's output, so a
    120 MW electrolyser's hydrogen and the reactor's methanol were summed into one
    tonnage. The chain reports that figure beside the product output; it never
    feeds it forward.
  * No reconciliation tolerance has been agreed. A difference between two
    sources is REPORTED with its size, never judged PASS by a number nobody set.
    Checks that are identities (the same figure carried forward) are PASS/FAIL.
  * Review standing is stated, never implied: an appointed INDEPENDENT_ENGINEER
    of another company reviews as INDEPENDENT; the owner's own finance or
    executive function reviews as OWNER_INTERNAL, labelled "not independent".
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from typing import Iterable, Optional

COST_BASIS_FUNCTIONS = frozenset({"ENGINEERING", "FINANCE_TREASURY", "EXECUTIVE"})
OWNER_REVIEW_FUNCTIONS = frozenset({"FINANCE_TREASURY", "EXECUTIVE"})
REVIEW_OUTCOMES = ("approve", "approve_with_conditions", "reject")

# The returns inputs the chain sets. Anything else in a ReturnsRequest is an
# assumption the owner states, with its source.
CHAIN_FIELDS = ("fci_eur", "opex_y1_eur", "operating_years", "debt_eur", "interest_rate",
                "debt_tenor_years", "grant_eur")


class ChainError(ValueError):
    """A request that would break the chain. `code` is the API's refusal code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def catalogue_sha256(catalogue: Iterable) -> str:
    """The equipment catalogue a cost basis was priced from: a catalogue change
    reprices visibly instead of silently."""
    return sha256(sorted((asdict(i) for i in catalogue), key=lambda d: d["id"]))


# ── 1. Cost basis ────────────────────────────────────────────────────────────

def product_output(configuration: dict, catalogue: dict) -> dict:
    """Nameplate and annual output of the configured MOLECULE only.

    A derived converter (rated MW and SEC) runs at the capacity factor; its
    nameplate is the full-year figure. A literal line states its capacity, which
    the Cost Basis counts as annual output without a run time.
    """
    molecule = configuration["molecule"]
    cf = configuration.get("capacity_factor")
    nameplate = annual = 0.0
    lines, derived = [], False
    for line in configuration.get("equipment", []):
        item = catalogue.get(line["equipment_id"])
        if item is None or item.molecule_output != molecule:
            continue
        qty = int(line.get("quantity", 1))
        if item.rated_mw > 0 and item.sec_kwh_per_kg > 0:
            full = item.rated_mw * 8760 * qty * 1000 / item.sec_kwh_per_kg / 1000
            nameplate += full
            annual += full * (cf or 0)
            derived = True
        elif item.capacity_tonnes_year > 0:
            nameplate += item.capacity_tonnes_year * qty
            annual += item.capacity_tonnes_year * qty
        else:
            continue                         # e.g. product storage: no output of its own
        lines.append(line["equipment_id"])
    stated = configuration.get("stated_nameplate") or {}
    if stated.get("value"):
        # Workbook (19 Nov): the CFO states the nameplate when no catalogue line makes the product.
        # A catalogue line that disagrees is refused at preview; here the stated figure governs.
        return {"molecule": molecule, "nameplate_t_per_year": round(float(stated["value"]), 1),
                "cost_basis_annual_t": round(float(stated["value"]) * (cf or 0), 1),
                "product_lines": lines, "basis": "STATED_NAMEPLATE", "source": stated.get("source")}
    if nameplate <= 0:
        raise ChainError("NO_PRODUCT_LINE", f"No equipment in this configuration produces {molecule}. "
                         "Add the line that makes the product before saving a cost basis.")
    return {"molecule": molecule, "nameplate_t_per_year": round(nameplate, 1),
            "cost_basis_annual_t": round(annual, 1), "product_lines": lines,
            "basis": "DERIVED_AT_CAPACITY_FACTOR" if derived else "LITERAL_CAPACITY_NO_RUN_TIME"}


def cost_basis_record(*, project_id: str, owner_tenant: str, configuration: dict, result: dict,
                      product: dict, catalogue_hash: str, previous: Optional[dict], saved_by: str,
                      saved_by_function: Optional[str], open_issues: Optional[list] = None) -> dict:
    """A DRAFT carries `open_issues` (an open plant boundary, a conflict): it is kept, shown,
    and no TEA runs from it until a version without them (READY) is saved (127)."""
    record = {
        "version_id": str(uuid.uuid4()),
        "project_id": project_id,
        "owner_tenant_id": owner_tenant,
        "version_number": (previous["version_number"] + 1) if previous else 1,
        "molecule": configuration["molecule"],
        "configuration": configuration,
        "result": {**result, "product": product},
        "catalogue_sha256": catalogue_hash,
        "supersedes_version_id": previous["version_id"] if previous else None,
        "saved_by": saved_by,
        "saved_by_function": saved_by_function,
        "status": "DRAFT" if open_issues else "READY",
        "open_issues": list(open_issues or []),
    }
    record["content_sha256"] = sha256({k: record[k] for k in (
        "project_id", "version_number", "molecule", "configuration", "result", "catalogue_sha256",
        "supersedes_version_id", "status", "open_issues")})
    return record


# ── 2. TEA from a saved cost basis, and its review ─────────────────────────────

# OSBL (outside battery limits: offsites and utilities) vs ISBL, for the OSBL rule (JML, 19 Nov 2026).
# Units that make the plant's own feedstock (CO2 capture, DAC, ASU, N2 PSA) are process units: ISBL.
OSBL_CATEGORIES = frozenset({"INFRASTRUCTURE", "STORAGE", "SAFETY", "UTILITIES"})
FEED_UNIT_PREFIXES = ("CO2_", "DAC_", "ASU_", "N2_")
OSBL_SCOPES = frozenset({"POWER_INFRASTRUCTURE", "SITE_CIVIL", "STORAGE_LOGISTICS", "UTILITIES"})
OSBL_BOUNDARY_SCOPES = ("scope.power_infrastructure", "scope.site_civil", "scope.storage_logistics")


def osbl_kind(line: dict, catalogue: Optional[dict] = None) -> Optional[str]:
    """The OSBL kind of a cost basis line, or None for ISBL."""
    if line.get("kind") in ("QUOTE", "AGGREGATE"):
        return line.get("scope") if line.get("scope") in OSBL_SCOPES else None
    cat = line.get("category") or getattr((catalogue or {}).get(line.get("equipment_id")), "category", None)
    if cat in OSBL_CATEGORIES and not str(line.get("equipment_id", "")).startswith(FEED_UNIT_PREFIXES):
        return cat
    return None


def osbl_rule(cost_basis: dict) -> Optional[dict]:
    """{factor: 0, basis} when the cost basis prices OSBL itself, else None (OpenPyTEA's default
    applies and is listed). Never both: that is the double count this rule removes."""
    lines = cost_basis["result"].get("equipment_lines") or []
    n = cost_basis["version_number"]
    osbl = [l for l in lines if osbl_kind(l)]
    if osbl:
        total = sum(float(l["installed_cost_eur"]) for l in osbl)
        return {"factor": 0.0, "basis": f"OSBL priced line by line in cost basis v{n}: "
                f"{', '.join(l['equipment_id'] for l in osbl)} (EUR {total:,.0f})"}
    pb = cost_basis["configuration"].get("plant_boundary") or {}
    whole = [l for l in lines if l.get("kind") == "AGGREGATE" and l.get("scope") == "WHOLE_PLANT"]
    if whole and all((pb.get(k) or {}).get("value") == "INCLUDED" for k in OSBL_BOUNDARY_SCOPES):
        return {"factor": 0.0, "basis": f"the whole-plant aggregate in cost basis v{n} includes OSBL "
                "(plant boundary: power infrastructure, site and civil, storage INCLUDED)"}
    return None


HOURS_PER_OPERATOR_YEAR = 1960   # OpenPyTEA: 49 weeks x 5 shifts x 8 h (plant.py defaults, pinned by test)
PROCESS_TYPES = ("Fluids", "Solids", "Mixed")


def outputs_by_molecule(cost_basis: dict, catalogue: dict) -> dict:
    """What the saved plant makes, by catalogue molecule (t/yr at its run time), from the
    stored equipment lines. A hint for stating on-site feedstock supply; never applied silently."""
    out: dict = {}
    for line in cost_basis["result"].get("equipment_lines", []):
        t = float(line.get("annual_output_tonnes") or 0)
        item = catalogue.get(line.get("equipment_id"))
        mol = getattr(item, "molecule_output", None)
        if t > 0 and mol:
            out[mol] = out.get(mol, 0.0) + t
    return out


def tea_request(cost_basis: dict, *, fuel_id: str, pathway_id: str, stated: dict) -> dict:
    """The /tea/compute body in QUOTE mode: the saved plant's own lines, priced by OpenPyTEA.

    `stated` (by the person who runs the TEA, each with its basis):
      process_type   {value: Fluids|Solids|Mixed, basis}
      loc_factor     {value: float > 0, basis}
      feedstocks     {stream: {on_site_t_per_year, basis} | {price_eur_per_unit, unit, consumption_per_day, source}}
    Everything else is derived from the saved version; nothing is taken from a model default unseen.
    """
    cfg, res = cost_basis["configuration"], cost_basis["result"]
    if cost_basis.get("status") == "DRAFT":
        raise ChainError("COST_BASIS_DRAFT", f"Cost basis v{cost_basis['version_number']} is a draft: "
                         + "; ".join(i.get("detail", str(i)) for i in cost_basis.get("open_issues") or [])
                         + ". Save a version without open issues to run the TEA.")
    cf = cfg.get("capacity_factor")
    if not cf:
        raise ChainError("CAPACITY_FACTOR_REQUIRED", "The saved cost basis states no run time; the TEA "
                         "cannot be priced from it. Save a cost basis that states the run time.")
    for key in ("process_type", "loc_factor"):
        term = stated.get(key) or {}
        if term.get("value") in (None, "") or not str(term.get("basis") or "").strip():
            raise ChainError("TEA_INPUT_REQUIRED", f"State {key} with its basis.")
    if stated["process_type"]["value"] not in PROCESS_TYPES:
        raise ChainError("TEA_INPUT_INVALID", f"process_type must be one of {list(PROCESS_TYPES)}.")
    lines = res.get("equipment_lines") or []
    if not lines:
        raise ChainError("NO_EQUIPMENT", "The saved cost basis has no equipment lines.")
    n = cost_basis["version_number"]
    equipment = []
    for l in lines:
        own = l.get("kind") in ("QUOTE", "AGGREGATE")
        e = {"name": f"{l['equipment_id']} x{l['quantity']}", "installed_cost": float(l["installed_cost_eur"]),
             "source": (f"cost basis v{n}: {l['kind'].lower()} {l['equipment_id']}, {l.get('source')}" if own
                        else f"cost basis v{n}: catalogue {l['equipment_id']} x{l['quantity']}")}
        if own and l.get("price_year"):
            e["cost_year"] = int(l["price_year"])
        equipment.append(e)
    variable_opex = {}
    days = 365.0 * cf                                    # OpenPyTEA: per-day x 365 x utilisation
    power = float(res["output"].get("total_annual_power_mwh") or 0)
    if power > 0:
        variable_opex["electricity"] = {"consumption": power / days, "unit": "MWh/day",
                                        "price": float(cfg["power_price_eur_mwh"]),
                                        "source": f"cost basis v{n}: power use and price"}
    water = float(res["output"].get("total_annual_water_m3") or 0)
    if water > 0:
        variable_opex["water"] = {"consumption": water / days, "unit": "m3/day",
                                  "price": float(cfg["water_price_eur_m3"]),
                                  "source": f"cost basis v{n}: water use and price"}
    on_site = {}
    for stream, f in (stated.get("feedstocks") or {}).items():
        on, buy = "on_site_t_per_year" in f, "price_eur_per_unit" in f
        if not (on or buy):
            raise ChainError("TEA_INPUT_INVALID", f"{stream}: state an on-site supply with its basis, a "
                             "purchase with unit, daily consumption, price and source, or both.")
        if on:
            if not str(f.get("basis") or "").strip():
                raise ChainError("TEA_INPUT_REQUIRED", f"State the basis of the on-site {stream}.")
            on_site[stream] = {"t_per_year": float(f["on_site_t_per_year"]), "basis": f["basis"]}
        if buy:
            if stream in variable_opex or not str(f.get("source") or "").strip() or not f.get("unit"):
                raise ChainError("TEA_INPUT_INVALID", f"{stream}: a purchase needs unit, daily consumption, "
                                 "price and source.")
            variable_opex[stream] = {"consumption": float(f["consumption_per_day"]), "unit": f["unit"],
                                     "price": float(f["price_eur_per_unit"]), "source": f["source"]}
    return {
        "pathway_id": pathway_id,
        "fuel_id": fuel_id,
        "nameplate_capacity": cost_basis["result"]["product"]["nameplate_t_per_year"],
        "nameplate_unit": "t_per_year",
        "assumptions": {
            "capacity_factor": cf,
            "project_life_years": cfg["project_life_years"],
            "discount_rate_pct": round(cfg["wacc_pct"] * 100, 6),
            "provenance": {k: "project_document" for k in ("capacity_factor", "project_life_years",
                                                           "discount_rate_pct")},
        },
        "quote_plant": {
            "equipment": equipment,
            "variable_opex": variable_opex,
            "loc_factor": float(stated["loc_factor"]["value"]),
            "loc_factor_basis": stated["loc_factor"]["basis"],
            "contingency": float(cfg["contingency_pct"]),
            "operators_hired": float(cfg["labour_count"]),
            "operator_hourly_rate": float(cfg["labour_cost_eur_year"]) / HOURS_PER_OPERATOR_YEAR,
            "fixed_opex_components": {k: float(v) for k, v in (
                ("maintenance_costs", res["opex"].get("annual_om_eur")),
                ("taxes_insurance_costs", res["opex"].get("annual_insurance_eur"))) if v},
            "on_site_supply": on_site,
            **({"osbl_factor": rule["factor"], "osbl_factor_basis": rule["basis"]}
               if (rule := osbl_rule(cost_basis)) else {}),
        },
        "plant_process_type": stated["process_type"]["value"],
    }


def tea_stated_assumptions(base_case: dict) -> list[dict]:
    """What the TEA run relied on that nobody verified: the stated inputs and every OpenPyTEA default."""
    ti = base_case.get("tea_inputs") or {}
    req = ti.get("request") or {}
    q = req.get("quote_plant") or {}
    out = []
    if q:
        out.append({"name": "tea.loc_factor", "value": q.get("loc_factor"), "source": q.get("loc_factor_basis"),
                    "verification_status": "STATED"})
        out.append({"name": "tea.process_type", "value": req.get("plant_process_type"),
                    "source": "stated with the TEA run", "verification_status": "STATED"})
        for stream, s in (q.get("on_site_supply") or {}).items():
            out.append({"name": f"tea.on_site.{stream}", "value": s.get("t_per_year"), "source": s.get("basis"),
                        "verification_status": "STATED"})
        for stream, v in (q.get("variable_opex") or {}).items():
            out.append({"name": f"tea.purchase.{stream}", "value": v.get("price"),
                        "source": f"{v.get('source')} ({v.get('consumption'):.3f} {v.get('unit')})",
                        "verification_status": "DECLARED"})
    for d in ti.get("defaults_used") or []:
        out.append({"name": f"tea.{d['name']}", "value": d.get("value"), "source": d.get("basis"),
                    "verification_status": "OPENPYTEA_DEFAULT"})
    return out


def _diff(name: str, a_label: str, a: Optional[float], b_label: str, b: Optional[float], unit: str) -> dict:
    if a is None or b is None:
        return {"check": name, "result": "MISSING", "detail": f"{a_label}: {a}; {b_label}: {b}"}
    pct = (b - a) / a if a else None
    return {"check": name, "result": "REPORTED", a_label: a, b_label: b, "difference": b - a,
            "difference_pct": round(pct, 4) if pct is not None else None, "unit": unit,
            "detail": "No reconciliation tolerance has been agreed: the difference is reported, not judged."}


def _identity(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "result": "PASS" if ok else "FAIL", "detail": detail}


def cost_basis_vs_tea(cost_basis: dict, base_case: dict) -> list[dict]:
    """What a reviewer sees before deciding: identity checks, cost coverage, the feedstock
    balance, and the differences that remain (OpenPyTEA's factors on the same lines)."""
    res, product = cost_basis["result"], cost_basis["result"]["product"]
    ti = base_case.get("tea_inputs") or {}
    checks = [
        _identity("TEA priced from this saved cost basis",
                  base_case.get("cost_basis_version_id") == cost_basis["version_id"]
                  and base_case.get("cost_basis_sha256") == cost_basis["content_sha256"],
                  f"cost basis v{cost_basis['version_number']} {cost_basis['content_sha256'][:12]}"),
        _identity("Nameplate carried forward", abs((base_case.get("nameplate_capacity") or 0)
                                                    - product["nameplate_t_per_year"]) < 0.05,
                  f"{product['nameplate_t_per_year']} t/yr {product['molecule']}"),
    ]
    boundary = (ti.get("calculation_boundary") or {}).get("basis")
    checks.append(_identity("TEA priced the cost basis's own lines (quote mode)", boundary == "QUOTE_LINES",
                            "QUOTE_LINES" if boundary == "QUOTE_LINES" else
                            "No: the TEA priced its own generic train (no recorded inputs, or canonical mode)"))
    if boundary == "QUOTE_LINES":
        priced = {e["name"]: float(e["purchased_cost"]) for e in (ti.get("openpytea_config") or {}).get("equipment", [])}
        lines = {f"{l['equipment_id']} x{l['quantity']}": float(l["installed_cost_eur"])
                 for l in res.get("equipment_lines", [])}
        missing = sorted(k for k in lines if k not in priced or abs(priced[k] - lines[k]) > 0.5)
        extra = sorted(k for k in priced if k not in lines)
        checks.append(_identity("Every cost basis line priced in the TEA, at its installed cost",
                                not missing and not extra,
                                f"{len(lines)} lines, EUR {sum(lines.values()):,.0f}" if not (missing or extra)
                                else f"missing or different: {missing}; not in the cost basis: {extra}"))
        for f in ti.get("feedstock_balance") or []:
            st = f.get("status")
            result = {"COVERED": "PASS", "COVERED_WITH_PURCHASE": "PASS", "PURCHASED": "REPORTED"}.get(st, "FAIL")
            detail = _feed_detail(f)
            checks.append({"check": f"Feedstock balance: {f.get('feedstock')}", "result": result, "detail": detail})
    checks += [
        _diff("CAPEX: Cost Basis vs TEA fixed capital", "cost_basis_eur", res["capex"]["total_capex_eur"],
              "tea_eur", base_case.get("capex_eur"), "EUR"),
        _diff("OPEX per year: Cost Basis vs TEA", "cost_basis_eur", res["opex"]["total_annual_opex_eur"],
              "tea_eur", base_case.get("opex_eur_per_year"), "EUR/yr"),
    ]
    checks += boundary_vs_tea(cost_basis, ti)
    checks.append(osbl_check(cost_basis, ti))
    agg = [l for l in res.get("equipment_lines", []) if l.get("kind") == "AGGREGATE"]
    if agg:
        checks.append({"check": "Cost detail", "result": "REPORTED",
                       "detail": f"{len(agg)} AGGREGATE estimate(s), EUR {sum(l['installed_cost_eur'] for l in agg):,.0f} "
                                 f"(class {', '.join(str(l.get('estimate_class')) for l in agg)}): this TEA prices an "
                                 "aggregate CAPEX estimate, not an equipment list."})
    if res["opex"].get("om_unknown_lines"):
        checks.append({"check": "O&M stated", "result": "REPORTED",
                       "detail": f"O&M unknown on {res['opex']['om_unknown_lines']}: the TEA applies OpenPyTEA's "
                                 "maintenance default to the whole plant (listed under defaults)."})
    summed = res["output"]["annual_output_tonnes"]
    if res.get("basis") != "WORKBOOK" and abs(summed - product["cost_basis_annual_t"]) > 0.5:
        checks.append({"check": "Cost Basis screen output", "result": "REPORTED",
                       "screen_annual_t": summed, "product_annual_t": product["cost_basis_annual_t"],
                       "detail": "The Cost Basis screen adds every line's output (other molecules included). "
                                 "The chain uses the product lines only."})
    if product["basis"] == "LITERAL_CAPACITY_NO_RUN_TIME":
        checks.append({"check": "Run time on product output", "result": "REPORTED",
                       "detail": "The Cost Basis counts the product line at its stated capacity with no run "
                                 "time; the TEA applies the capacity factor to the nameplate."})
    return checks


def osbl_check(cost_basis: dict, tea_inputs: dict) -> dict:
    """OSBL counted once: by the lines, or by OpenPyTEA's factor, never both (JML, 19 Nov 2026)."""
    lines = cost_basis["result"].get("equipment_lines") or []
    kinds = sorted({k for l in lines if (k := osbl_kind(l))})
    q = ((tea_inputs.get("request") or {}).get("quote_plant") or {})
    factor = q.get("osbl_factor")
    if not tea_inputs.get("request"):
        return {"check": "OSBL counted once", "result": "MISSING", "detail": "The TEA run recorded no request."}
    if kinds and factor not in (0, 0.0):
        return {"check": "OSBL counted once", "result": "FAIL",
                "detail": f"The cost basis prices OSBL ({', '.join(kinds)}) and the TEA added OpenPyTEA's OSBL "
                          "factor on top: run the TEA again from this cost basis."}
    if kinds:
        missing = sorted({"INFRASTRUCTURE", "STORAGE", "UTILITIES", "SAFETY"} - set(kinds)) if all(
            l.get("kind", "CATALOGUE") == "CATALOGUE" for l in lines) else []
        return {"check": "OSBL counted once", "result": "REPORTED",
                "detail": f"OSBL priced by the lines ({', '.join(kinds)}); OpenPyTEA's factor set to 0."
                          + (f" Not priced as lines: {', '.join(missing)}." if missing else "")}
    return {"check": "OSBL counted once", "result": "REPORTED" if factor is None else "PASS",
            "detail": "No OSBL line: OpenPyTEA's OSBL factor applies (listed under defaults)." if factor is None
            else f"OSBL factor {factor}: {q.get('osbl_factor_basis')}"}


BOUNDARY_ROUTES = {"ON_SITE": (True, False), "PURCHASED": (False, True), "BOTH": (True, True),
                   "NOT_USED": (False, False)}


def boundary_vs_tea(cost_basis: dict, tea_inputs: dict) -> list[dict]:
    """The plant boundary stated with the cost basis against what the TEA actually priced:
    a stream made on site must be supplied on site, a bought one bought (v1's defect)."""
    pb = cost_basis["configuration"].get("plant_boundary")
    if not pb:
        return [{"check": "Plant boundary", "result": "REPORTED",
                 "detail": "This cost basis states no plant boundary (saved before the workbook, 19 Nov)."}]
    q = (tea_inputs.get("request") or {}).get("quote_plant") or {}
    out = []
    for key, b in sorted(pb.items()):
        if not key.startswith("boundary."):
            continue
        stream, route = key.split(".", 1)[1], b.get("value")
        if route not in BOUNDARY_ROUTES:
            continue
        got = (stream in (q.get("on_site_supply") or {}), stream in (q.get("variable_opex") or {}))
        ok = got == BOUNDARY_ROUTES[route]
        out.append({"check": f"Plant boundary: {stream}", "result": "PASS" if ok else "FAIL",
                    "detail": f"stated {route}; the TEA has {'on-site supply' if got[0] else 'no on-site supply'} "
                              f"and {'a purchase' if got[1] else 'no purchase'}"})
    open_scopes = sorted(k.split(".", 1)[1] for k, b in pb.items()
                         if k.startswith("scope.") and b.get("value") == "UNKNOWN")
    scopes = ", ".join(f"{k.split('.', 1)[1]} {b.get('value')}" for k, b in sorted(pb.items()) if k.startswith("scope."))
    out.append({"check": "Plant boundary: CAPEX scope", "result": "REPORTED",
                "detail": scopes + (f". Not settled: {open_scopes}" if open_scopes else "")})
    return out


def _feed_detail(f: dict) -> str:
    def t(key):
        v = f.get(key)
        return "?" if v is None else f"{v:,.0f}"
    st = f.get("status")
    if st == "COVERED":
        return f"required {t('required_t_per_year')} t/yr, on site {t('on_site_t_per_year')} ({f.get('on_site_basis')})"
    if st == "COVERED_WITH_PURCHASE":
        return (f"required {t('required_t_per_year')} t/yr = on site {t('on_site_t_per_year')} ({f.get('on_site_basis')}) "
                f"+ bought {t('purchased_t_per_year')}")
    if st == "PURCHASED":
        return f"required {t('required_t_per_year')} t/yr; bought at a stated price" + (
            f", plus {t('on_site_t_per_year')} on site" if f.get("on_site_t_per_year") else "")
    if st == "SHORTFALL":
        return (f"required {t('required_t_per_year')} t/yr, on site {t('on_site_t_per_year')}: short "
                f"{t('shortfall_t_per_year')} t/yr, neither bought nor priced")
    if st == "NOT_COVERED":
        return f"required {t('required_t_per_year')} t/yr: neither on site nor bought"
    return f.get("detail") or str(st)


def failed(checks: list[dict]) -> list[str]:
    return [c["check"] for c in checks if c.get("result") == "FAIL"]


def review_standing(*, reviewer: dict, run_by: Optional[str], cost_basis_saved_by: Optional[str],
                    owner_tenant: str, appointed_ie: bool, test_account: bool = False) -> str:
    """INDEPENDENT, OWNER_INTERNAL or TEST, or ChainError. `reviewer` is the token payload.
    A test fixture account's review is TEST whatever its role: recorded and shown, never
    independent, so it promotes and publishes nothing (19 Nov 2026)."""
    uid = reviewer.get("user_id")
    if not uid:
        raise ChainError("NO_REVIEWER", "Sign in to review a TEA base case.")
    if uid in {run_by, cost_basis_saved_by}:
        raise ChainError("SELF_REVIEW", "The person who saved the cost basis or ran the TEA cannot review it.")
    company = reviewer.get("company_id") or reviewer.get("tenant_id")
    if appointed_ie and company and company != owner_tenant:
        return "TEST" if test_account else "INDEPENDENT"
    if company == owner_tenant and reviewer.get("business_function") in OWNER_REVIEW_FUNCTIONS:
        return "TEST" if test_account else "OWNER_INTERNAL"
    raise ChainError("NOT_A_REVIEWER", "A TEA base case is reviewed by an independent engineer appointed on "
                     "this project, or by the owner's finance or executive function.")


# ── 3. Financing case ──────────────────────────────────────────────────────────

FINANCING_TERMS = ("debt_eur", "interest_rate", "debt_tenor_years", "grant_eur")


def financing_record(*, project_id: str, owner_tenant: str, base_case: dict, terms: dict,
                     previous: Optional[dict], saved_by: str, case_id: Optional[str] = None,
                     supersedes: Optional[dict] = None, funding_plan: Optional[dict] = None,
                     gearing_policy: Optional[dict] = None) -> dict:
    """An ELIGIBLE financing case: may feed a returns version.
    `terms`: {name: {value, source, verification_status}} for FINANCING_TERMS.
    `previous`: the project's latest version (numbering); `supersedes`: the version of the
    SAME case this one replaces (a promoted draft), else `previous` when it is that case."""
    if base_case.get("state") != "verified":
        raise ChainError("TEA_NOT_REVIEWED", f"TEA base case {base_case.get('claim_id')} is "
                         f"{base_case.get('state')}: a financing case needs a reviewed (verified) base case.")
    if not base_case.get("cost_basis_version_id"):
        raise ChainError("TEA_NOT_FROM_COST_BASIS", "This TEA base case was not priced from a saved cost basis.")
    if ((base_case.get("tea_inputs") or {}).get("calculation_boundary") or {}).get("basis") != "QUOTE_LINES":
        raise ChainError("TEA_NOT_FROM_QUOTE_MODE", "This TEA priced a generic train, not the cost basis's own "
                         "lines (the v1 defect). Run the TEA again from the saved cost basis.")
    missing = [t for t in FINANCING_TERMS if t != "grant_eur" and t not in terms]
    if missing:
        raise ChainError("TERMS_MISSING", f"State {', '.join(missing)} with a source.")
    for name, term in terms.items():
        if name not in FINANCING_TERMS:
            raise ChainError("UNKNOWN_TERM", f"'{name}' is not a financing term.")
        if not str(term.get("source") or "").strip():
            raise ChainError("SOURCE_REQUIRED", f"'{name}' needs a source.")
    fci = float(base_case["capex_eur"])
    v = {t: (terms[t]["value"] if t in terms else 0) for t in FINANCING_TERMS}
    plan = funding_plan or {}
    uses_total = None
    if plan:
        from app.core import funding
        rec = funding.reconcile(plan, base_case=base_case, terms=terms, gearing_policy=gearing_policy)
        if rec["limitations"]:
            raise ChainError("FUNDING_UNRECONCILED", "; ".join(l["detail"] for l in rec["limitations"]))
        uses_total = rec["total_uses_eur"]
    ceiling = uses_total if uses_total else fci
    if float(v["debt_eur"]) + float(v["grant_eur"]) > ceiling:
        raise ChainError("DEBT_EXCEEDS_USES" if uses_total else "DEBT_EXCEEDS_FCI",
                         "Debt plus grant exceed the case's defined uses." if uses_total else
                         "Debt plus grant exceed the reviewed CAPEX.")
    record = {
        "version_id": str(uuid.uuid4()),
        "project_id": project_id,
        "owner_tenant_id": owner_tenant,
        "version_number": (previous["version_number"] + 1) if previous else 1,
        "tea_claim_id": base_case["claim_id"],
        "tea_cost_basis_hash": base_case["cost_basis_hash"],
        "fci_eur": fci,
        "debt_eur": float(v["debt_eur"]),
        "interest_rate": float(v["interest_rate"]),
        "debt_tenor_years": int(v["debt_tenor_years"]),
        "grant_eur": float(v["grant_eur"]),
        "terms": _terms(terms),
        "supersedes_version_id": (supersedes or previous or {}).get("version_id"),
        "saved_by": saved_by,
        "case_id": case_id or (supersedes or {}).get("case_id") or str(uuid.uuid4()),
        "status": "ELIGIBLE",
        "limitations": [],
        "funding_plan": plan,
        "uses_total_eur": uses_total,
    }
    record["content_sha256"] = _financing_hash(record)
    return record


def _terms(terms: dict) -> dict:
    # the workbook's date and standing (TERM_SHEET, ...): what the CFO declared, not a verification
    return {t: {"value": terms[t]["value"], "source": terms[t]["source"],
                "verification_status": terms[t].get("verification_status") or "ASSUMPTION",
                **{k: terms[t][k] for k in ("as_of", "standing") if terms[t].get(k)}}
            for t in terms}


def _financing_hash(record: dict) -> str:
    return sha256({k: record.get(k) for k in (
        "project_id", "version_number", "tea_claim_id", "tea_cost_basis_hash", "fci_eur", "debt_eur",
        "interest_rate", "debt_tenor_years", "grant_eur", "terms", "supersedes_version_id", "case_id",
        "status", "limitations", "funding_plan", "uses_total_eur")})


def financing_draft_record(*, project_id: str, owner_tenant: str, case_id: Optional[str],
                           base_case: Optional[dict], terms: dict, previous: Optional[dict],
                           case_latest: Optional[dict], saved_by: str,
                           extra_limitations: Iterable = (), funding_plan: Optional[dict] = None,
                           gearing_policy: Optional[dict] = None) -> dict:
    """A DRAFT financing case: recorded with its limitations stated, used by nothing until promoted.
    A draft may lack a TEA run, terms and fixed capital, and may exceed it; it may not hold a
    term without a source or a term GEX does not know."""
    for name, term in terms.items():
        if name not in FINANCING_TERMS:
            raise ChainError("UNKNOWN_TERM", f"'{name}' is not a financing term.")
        if not str(term.get("source") or "").strip():
            raise ChainError("SOURCE_REQUIRED", f"'{name}' needs a source.")
    record = {
        "version_id": str(uuid.uuid4()),
        "project_id": project_id,
        "owner_tenant_id": owner_tenant,
        "version_number": (previous["version_number"] + 1) if previous else 1,
        "tea_claim_id": (base_case or {}).get("claim_id"),
        "tea_cost_basis_hash": (base_case or {}).get("cost_basis_hash"),
        "fci_eur": float(base_case["capex_eur"]) if base_case and base_case.get("capex_eur") else None,
        "debt_eur": _val(terms, "debt_eur", float),
        "interest_rate": _val(terms, "interest_rate", float),
        "debt_tenor_years": _val(terms, "debt_tenor_years", int),
        "grant_eur": _val(terms, "grant_eur", float) or 0.0,
        "terms": _terms(terms),
        "supersedes_version_id": (case_latest or {}).get("version_id"),
        "saved_by": saved_by,
        "case_id": case_id or (case_latest or {}).get("case_id") or str(uuid.uuid4()),
        "status": "DRAFT",
        "limitations": draft_limitations(base_case, terms) + list(extra_limitations),
        "funding_plan": funding_plan or {},
        "uses_total_eur": None,
    }
    if funding_plan:
        from app.core import funding
        rec = funding.reconcile(funding_plan, base_case=base_case, terms=terms, gearing_policy=gearing_policy)
        known = {l["code"] for l in record["limitations"]}
        record["limitations"] += [l for l in rec["limitations"] if l["code"] not in known]
        record["uses_total_eur"] = rec["total_uses_eur"] or None
    record["content_sha256"] = _financing_hash(record)
    return record


def _val(terms: dict, name: str, cast):
    return cast(terms[name]["value"]) if name in terms else None


def draft_limitations(base_case: Optional[dict], terms: dict) -> list[dict]:
    """What stops a draft from being ELIGIBLE, each stated (re-checked again at promotion)."""
    out = []
    if not base_case:
        out.append({"code": "NO_TEA_RUN", "detail": "No TEA run is named: fixed capital is unknown."})
    else:
        if base_case.get("state") != "verified" or base_case.get("review_basis") != "INDEPENDENT":
            out.append({"code": "TEA_NOT_INDEPENDENTLY_REVIEWED",
                        "detail": f"TEA run {base_case.get('claim_id')} is {base_case.get('state')}, review "
                                  f"{base_case.get('review_basis') or 'none'}."})
        if ((base_case.get("tea_inputs") or {}).get("calculation_boundary") or {}).get("basis") != "QUOTE_LINES":
            out.append({"code": "TEA_NOT_FROM_QUOTE_MODE", "detail": "The TEA run did not price the cost basis's own lines."})
    missing = [t for t in FINANCING_TERMS if t != "grant_eur" and t not in terms]
    if missing:
        out.append({"code": "TERMS_MISSING", "detail": f"Not stated: {', '.join(missing)}."})
    return out


def promotion_record(*, draft: dict, base_case: Optional[dict], previous: dict, saved_by: str,
                     gearing_policy: Optional[dict] = None) -> dict:
    """Promote a DRAFT to ELIGIBLE: a new version of the same case, on the 124 rules. A limitation
    the draft carries that only a new draft can clear (unreconciled grants) refuses it."""
    if draft.get("status") != "DRAFT":
        raise ChainError("NOT_A_DRAFT", "Only a draft is promoted.")
    sticky = [l for l in draft.get("limitations") or [] if l["code"] in STICKY_LIMITATIONS]
    if sticky:
        raise ChainError("DRAFT_HAS_OPEN_LIMITATIONS", "; ".join(l["detail"] for l in sticky)
                         + " Save a corrected draft first.")
    if not base_case:
        raise ChainError("NO_TEA_RUN", "Name the independently reviewed TEA run in a new draft first.")
    if base_case.get("review_basis") != "INDEPENDENT":
        raise ChainError("REVIEW_NOT_INDEPENDENT", f"TEA run {base_case.get('claim_id')} has review "
                         f"{base_case.get('review_basis') or 'none'}: promotion needs an independent review.")
    terms = {t: {k: v for k, v in term.items()} for t, term in (draft.get("terms") or {}).items()}
    return financing_record(project_id=draft["project_id"], owner_tenant=draft["owner_tenant_id"],
                            base_case=base_case, terms=terms, previous=previous, saved_by=saved_by,
                            case_id=draft["case_id"], supersedes=draft, funding_plan=draft.get("funding_plan") or {},
                            gearing_policy=gearing_policy)


STICKY_LIMITATIONS = ("GRANTS_UNRECONCILED", "STACK_DEBT_UNRECONCILED")


# ── 4. Returns inputs from the chain ───────────────────────────────────────────

def returns_inputs(*, cost_basis: dict, base_case: dict, financing: dict, stated: dict,
                   project_capex_eur: Optional[float], approved_gearing: Optional[dict],
                   previous: Optional[dict] = None) -> dict:
    """Engine inputs, source versions, checks and remaining assumptions.

    `stated`: {field: {value, source, verification_status}} for every ReturnsRequest
    field that is NOT a chain field (revenue price, tax, depreciation, hurdle ...).
    """
    if financing.get("status", "ELIGIBLE") != "ELIGIBLE":
        raise ChainError("FINANCING_DRAFT", "This financing case is a draft: promote it (an independently "
                         "reviewed TEA run, every term with a source) before a returns version uses it.")
    if financing["tea_claim_id"] != base_case["claim_id"]:
        raise ChainError("CHAIN_BROKEN", "The financing case cites another TEA base case.")
    if base_case.get("state") != "verified":
        raise ChainError("TEA_NOT_REVIEWED", "The TEA base case is no longer verified.")
    if base_case.get("cost_basis_version_id") != cost_basis["version_id"]:
        raise ChainError("CHAIN_BROKEN", "The TEA base case was priced from another cost basis.")
    # JML, 18 Nov 2026: a version is published as reviewed only after the designated review,
    # i.e. by an independent engineer appointed on the project. An owner's own review is recorded
    # and shown, but publishes nothing.
    if base_case.get("review_basis") != "INDEPENDENT":
        raise ChainError("REVIEW_NOT_INDEPENDENT", "Only a TEA base case reviewed by an appointed independent "
                         "engineer can be published to readers. This one is "
                         f"{base_case.get('review_basis') or 'unreviewed'}.")
    tea_checks = cost_basis_vs_tea(cost_basis, base_case)
    if failed(tea_checks):
        raise ChainError("CHECKS_FAILED", "These checks fail: " + "; ".join(failed(tea_checks))
                         + ". Correct the cost basis or the TEA inputs and run the TEA again.")
    conflicts = sorted(set(stated) & set(CHAIN_FIELDS))
    if conflicts:
        raise ChainError("CHAIN_CONFLICT", f"{', '.join(conflicts)} come from the chain and cannot be stated.")
    for name, term in stated.items():
        if not str(term.get("source") or "").strip():
            raise ChainError("SOURCE_REQUIRED", f"'{name}' needs a source.")

    cfg, product = cost_basis["configuration"], cost_basis["result"]["product"]
    annual_t = product["nameplate_t_per_year"] * cfg["capacity_factor"]
    chain = {
        "fci_eur": float(base_case["capex_eur"]),
        "opex_y1_eur": float(base_case["opex_eur_per_year"]),
        "operating_years": int(cfg["project_life_years"]),
        "debt_eur": financing["debt_eur"],
        "interest_rate": financing["interest_rate"],
        "debt_tenor_years": financing["debt_tenor_years"],
        "grant_eur": financing["grant_eur"],
    }
    values = {k: v["value"] for k, v in stated.items()}
    price = values.pop("product_price_eur_t", None)
    if price is None and "revenue_y1_eur" not in values:
        raise ChainError("PRICE_REQUIRED", "State the product price (EUR/t) with its source.")
    if price is not None:
        values["revenue_y1_eur"] = float(price) * annual_t
    inputs = {**values, **chain}

    checks = [
        _identity("TEA base case reviewed", base_case.get("state") == "verified",
                  f"{base_case['claim_id']} {base_case.get('review_basis') or ''}".strip()),
        _identity("TEA priced from the cited cost basis",
                  base_case.get("cost_basis_sha256") == cost_basis["content_sha256"],
                  f"cost basis v{cost_basis['version_number']}"),
        _identity("Financing case on this TEA base case", financing["tea_cost_basis_hash"] ==
                  base_case["cost_basis_hash"], f"financing v{financing['version_number']}"),
        _identity("FCI = reviewed TEA CAPEX", inputs["fci_eur"] == float(base_case["capex_eur"]),
                  f"EUR {inputs['fci_eur']:,.0f}"),
        _identity("OPEX year 1 = reviewed TEA OPEX", inputs["opex_y1_eur"] == float(base_case["opex_eur_per_year"]),
                  f"EUR {inputs['opex_y1_eur']:,.0f}/yr"),
        _identity("Operating years = cost basis project life", inputs["operating_years"] == cfg["project_life_years"],
                  f"{inputs['operating_years']} years"),
        _identity("Debt + grant within FCI", inputs["debt_eur"] + inputs["grant_eur"] <= inputs["fci_eur"],
                  f"EUR {inputs['debt_eur'] + inputs['grant_eur']:,.0f} of {inputs['fci_eur']:,.0f}"),
        {"check": "Revenue volume", "result": "REPORTED",
         "detail": f"{product['nameplate_t_per_year']:,.0f} t/yr nameplate x capacity factor "
                   f"{cfg['capacity_factor']} = {annual_t:,.0f} t/yr sold"
                   + ("" if price is not None else " (revenue stated directly, not from price x volume)")},
        _diff("Project record CAPEX vs reviewed TEA CAPEX", "project_record_eur", project_capex_eur,
              "tea_eur", inputs["fci_eur"], "EUR"),
    ]
    gearing = inputs["debt_eur"] / inputs["fci_eur"]
    if approved_gearing:
        checks.append({"check": "Gearing vs approved reference", "result": "REPORTED",
                       "case_gearing": round(gearing, 4), "reference": approved_gearing.get("value"),
                       "reference_id": approved_gearing.get("ref_id"),
                       "detail": f"Case {gearing:.1%} vs reference {approved_gearing.get('value'):.1%} "
                                 f"({approved_gearing.get('source')}). Reported, not a limit."})

    source_versions = {
        "cost_basis": {"version_id": cost_basis["version_id"], "version_number": cost_basis["version_number"],
                       "content_sha256": cost_basis["content_sha256"],
                       "catalogue_sha256": cost_basis["catalogue_sha256"],
                       "saved_by": cost_basis["saved_by"], "saved_at": str(cost_basis.get("saved_at"))},
        "tea_base_case": {"claim_id": base_case["claim_id"], "cost_basis_hash": base_case["cost_basis_hash"],
                          "engine": base_case.get("engine"), "engine_version": base_case.get("engine_version"),
                          "result_status": base_case.get("result_status"), "run_by": base_case.get("run_by"),
                          "reviewed_by": base_case.get("approved_by"),
                          "review_basis": base_case.get("review_basis"),
                          "reviewed_at": base_case.get("reviewed_at"),
                          "review_conditions": base_case.get("review_conditions")},
        "financing_case": {"version_id": financing["version_id"], "version_number": financing["version_number"],
                           "content_sha256": financing["content_sha256"], "saved_by": financing["saved_by"]},
    }
    remaining = [{"name": k, "value": v["value"], "source": v["source"],
                  "verification_status": v.get("verification_status") or "ASSUMPTION"} for k, v in sorted(stated.items())]
    remaining += [{"name": f"financing.{k}", **v} for k, v in sorted(financing["terms"].items())
                  if (v.get("verification_status") or "ASSUMPTION") != "VERIFIED"]
    remaining += tea_stated_assumptions(base_case)
    remaining += [{"name": f"cost_basis.{k}", "value": cfg[k], "source": f"cost basis v{cost_basis['version_number']}",
                   "verification_status": "DECLARED"} for k in (
                       "power_price_eur_mwh", "capacity_factor", "contingency_pct", "wacc_pct", "project_life_years")]
    checks += [{**c, "check": f"TEA: {c['check']}"} for c in tea_checks
               if not c["check"].startswith("TEA priced from this saved cost basis")]
    out = {"inputs": inputs, "source_versions": source_versions, "checks": checks, "remaining_assumptions": remaining}
    if previous is not None:
        out["reconciliation_vs_previous"] = versus_previous(previous, inputs)
    return out


def versus_previous(previous: dict, inputs: dict) -> dict:
    """What changed against the version this one supersedes (stored figures only, nothing recomputed)."""
    prev_in, prev_res = previous.get("inputs") or {}, previous.get("results") or {}
    rows = [{"item": k, "previous": prev_in.get(k), "this": inputs.get(k)}
            for k in ("fci_eur", "opex_y1_eur", "revenue_y1_eur", "operating_years", "debt_eur",
                      "interest_rate", "debt_tenor_years", "grant_eur", "tax_rate", "cost_of_equity")
            if prev_in.get(k) != inputs.get(k)]
    w = previous.get("withdrawal")
    return {"previous_version_id": previous["version_id"], "previous_version_number": previous["version_number"],
            "previous_content_sha256": previous["content_sha256"],
            "previous_withdrawn": bool(w), "previous_withdrawal_reason": (w or {}).get("reason"),
            "previous_results": {k: prev_res.get(k) for k in ("unlevered_irr", "levered_irr", "npv_unlevered_eur",
                                                              "npv_levered_eur")},
            "inputs_changed": rows}
