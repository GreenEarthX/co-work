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
    if nameplate <= 0:
        raise ChainError("NO_PRODUCT_LINE", f"No equipment in this configuration produces {molecule}. "
                         "Add the line that makes the product before saving a cost basis.")
    return {"molecule": molecule, "nameplate_t_per_year": round(nameplate, 1),
            "cost_basis_annual_t": round(annual, 1), "product_lines": lines,
            "basis": "DERIVED_AT_CAPACITY_FACTOR" if derived else "LITERAL_CAPACITY_NO_RUN_TIME"}


def cost_basis_record(*, project_id: str, owner_tenant: str, configuration: dict, result: dict,
                      product: dict, catalogue_hash: str, previous: Optional[dict], saved_by: str,
                      saved_by_function: Optional[str]) -> dict:
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
    }
    record["content_sha256"] = sha256({k: record[k] for k in (
        "project_id", "version_number", "molecule", "configuration", "result", "catalogue_sha256",
        "supersedes_version_id")})
    return record


# ── 2. TEA from a saved cost basis, and its review ─────────────────────────────

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
    equipment = [{"name": f"{l['equipment_id']} x{l['quantity']}", "installed_cost": float(l["installed_cost_eur"]),
                  "source": f"cost basis v{n}: catalogue {l['equipment_id']} x{l['quantity']}"} for l in lines]
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
    summed = res["output"]["annual_output_tonnes"]
    if abs(summed - product["cost_basis_annual_t"]) > 0.5:
        checks.append({"check": "Cost Basis screen output", "result": "REPORTED",
                       "screen_annual_t": summed, "product_annual_t": product["cost_basis_annual_t"],
                       "detail": "The Cost Basis screen adds every line's output (other molecules included). "
                                 "The chain uses the product lines only."})
    if product["basis"] == "LITERAL_CAPACITY_NO_RUN_TIME":
        checks.append({"check": "Run time on product output", "result": "REPORTED",
                       "detail": "The Cost Basis counts the product line at its stated capacity with no run "
                                 "time; the TEA applies the capacity factor to the nameplate."})
    return checks


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
                    owner_tenant: str, appointed_ie: bool) -> str:
    """INDEPENDENT or OWNER_INTERNAL, or ChainError. `reviewer` is the token payload."""
    uid = reviewer.get("user_id")
    if not uid:
        raise ChainError("NO_REVIEWER", "Sign in to review a TEA base case.")
    if uid in {run_by, cost_basis_saved_by}:
        raise ChainError("SELF_REVIEW", "The person who saved the cost basis or ran the TEA cannot review it.")
    company = reviewer.get("company_id") or reviewer.get("tenant_id")
    if appointed_ie and company and company != owner_tenant:
        return "INDEPENDENT"
    if company == owner_tenant and reviewer.get("business_function") in OWNER_REVIEW_FUNCTIONS:
        return "OWNER_INTERNAL"
    raise ChainError("NOT_A_REVIEWER", "A TEA base case is reviewed by an independent engineer appointed on "
                     "this project, or by the owner's finance or executive function.")


# ── 3. Financing case ──────────────────────────────────────────────────────────

FINANCING_TERMS = ("debt_eur", "interest_rate", "debt_tenor_years", "grant_eur")


def financing_record(*, project_id: str, owner_tenant: str, base_case: dict, terms: dict,
                     previous: Optional[dict], saved_by: str) -> dict:
    """`terms`: {name: {value, source, verification_status}} for FINANCING_TERMS."""
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
    if float(v["debt_eur"]) + float(v["grant_eur"]) > fci:
        raise ChainError("DEBT_EXCEEDS_FCI", "Debt plus grant exceed the reviewed CAPEX.")
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
        "terms": {t: {"value": terms[t]["value"], "source": terms[t]["source"],
                      "verification_status": terms[t].get("verification_status") or "ASSUMPTION"}
                  for t in terms},
        "supersedes_version_id": previous["version_id"] if previous else None,
        "saved_by": saved_by,
    }
    record["content_sha256"] = sha256({k: record[k] for k in (
        "project_id", "version_number", "tea_claim_id", "tea_cost_basis_hash", "fci_eur", "debt_eur",
        "interest_rate", "debt_tenor_years", "grant_eur", "terms", "supersedes_version_id")})
    return record


# ── 4. Returns inputs from the chain ───────────────────────────────────────────

def returns_inputs(*, cost_basis: dict, base_case: dict, financing: dict, stated: dict,
                   project_capex_eur: Optional[float], approved_gearing: Optional[dict],
                   previous: Optional[dict] = None) -> dict:
    """Engine inputs, source versions, checks and remaining assumptions.

    `stated`: {field: {value, source, verification_status}} for every ReturnsRequest
    field that is NOT a chain field (revenue price, tax, depreciation, hurdle ...).
    """
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
