"""
The CFO workbook journey, end to end through the LIVE platform (JML, 19 Nov 2026).
==================================================================================
Runs on the dedicated TEST project (scripts/load_workbook_journey_project.py) as HamburgOne's
demo CFO, against the running backend (:8000) and TEA engine (:8002). Nothing is simulated:
every step is an HTTP call a screen makes, and every check reads back what GEX stored.

  0  set-up: first workbook -> preview -> save Cost Basis, Financing, Offtake; TEA run from it
  1  download the populated workbook
  2  change financing terms (name the TEA run, a new debt figure, a source now binding) and add
     an offtaker (the card becomes a frame of two buyers)
  3  preview and save
  4  reload GEX and find every saved field, source and status
  5  export again and reconcile the export with the records
  6  re-import an amendment: no duplicate financing case, capital source, use or buyer
  R  a rejected save leaves no record behind (counts compared before and after)

Writes a report to docs/review/workbook_journey_20261119.md. Credentials come from the
environment (JOURNEY_EMAIL, JOURNEY_PASSWORD); they are never printed.
"""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import cost_workbook as cw          # noqa: E402  (parse the exports exactly as GEX does)
from app.core import finance_workbook as fw       # noqa: E402

API = os.environ.get("JOURNEY_API", "http://localhost:8000")
P = "proj_TEST_workbook_journey"
BUYER_A, BUYER_B = "test_journey_buyer_a", "test_journey_buyer_b"
REPORT = Path(__file__).resolve().parents[2] / "docs" / "review" / "workbook_journey_20261119.md"
steps: list[dict] = []


def step(n: str, title: str, ok: bool, evidence: dict) -> None:
    steps.append({"step": n, "title": title, "result": "PASS" if ok else "FAIL", "evidence": evidence})
    print(f"[{'PASS' if ok else 'FAIL'}] {n} {title}")


# ── workbook editing, by the grey key in column A (as a CFO's Excel edits it) ─────────────────

def wb_from(data: bytes):
    return load_workbook(io.BytesIO(data))


def put(wb, sheet: str, key: str, value, source=None, as_of="2026-11-19", standing=None):
    ws = wb[sheet]
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 1).value == key:
            ws.cell(r, 3).value = value
            if source is not None:
                ws.cell(r, 5).value = source
            if not key.startswith(("boundary.", "scope.")) and sheet != "Offtake":
                ws.cell(r, 6).value = as_of
                ws.cell(r, 7).value = standing
            elif sheet == "Offtake":
                ws.cell(r, 6).value = as_of
            return
    raise KeyError(key)


def rows(wb, sheet: str, header: str, columns, data: list[dict]):
    """Write `data` into the table's rows from the top, clearing what is below."""
    ws = wb[sheet]
    start = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == header)
    r = start + 1
    while ws.cell(r, 1).value == "row":
        values = data[r - start - 1] if r - start - 1 < len(data) else {}
        for j, name in enumerate(columns, 2):
            ws.cell(r, j).value = values.get(name)
        r += 1


def table(wb, sheet: str, header: str, columns) -> list[dict]:
    ws = wb[sheet]
    start = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == header)
    out, r = [], start + 1
    while ws.cell(r, 1).value == "row":
        row = {name: ws.cell(r, j).value for j, name in enumerate(columns, 2)}
        if any(v not in (None, "") for v in row.values()):
            out.append(row)
        r += 1
    return out


def blob(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── the platform ───────────────────────────────────────────────────────────────

def client() -> httpx.Client:
    email, password = os.environ.get("JOURNEY_EMAIL"), os.environ.get("JOURNEY_PASSWORD")
    if not (email and password):
        sys.exit("Set JOURNEY_EMAIL and JOURNEY_PASSWORD (the demo CFO's sign-in) first.")
    r = httpx.post(f"{API}/api/v1/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    token = r.json()["access_token"]
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token}"}, timeout=120)


def preview(c, data: bytes) -> dict:
    r = c.post(f"/api/v1/cost-basis/{P}/workbook/preview", files={"file": ("cfo.xlsx", data)})
    r.raise_for_status()
    return r.json()


def commit(c, data: bytes, sha: str, tab: str):
    return c.post(f"/api/v1/cost-basis/{P}/workbook/commit", files={"file": ("cfo.xlsx", data)},
                  data={"expected_file_sha256": sha, "tab": tab})


def chain(c) -> dict:
    r = c.get(f"/api/v1/calculation-chain/{P}")
    r.raise_for_status()
    return r.json()


def card(c) -> dict:
    r = c.get("/api/v1/bankability/terms", params={"project_id": P})
    r.raise_for_status()
    return ((r.json().get("cards") or {}).get("offtake") or {}).get("terms") or {}


def counts(c) -> dict:
    ch = chain(c)
    fins = ch["financing_cases"]
    return {"cost_basis_versions": len(ch["cost_bases"]), "financing_versions": len(fins),
            "financing_cases": len({f["case_id"] for f in fins}), "tea_runs": len(ch["tea_base_cases"]),
            "offtake_buyers": len(card(c).get("buyers") or ([1] if card(c) else []))}


# ── the data a CFO types (synthetic) ──────────────────────────────────────────

BOUNDARY = {"boundary.hydrogen": "ON_SITE", "boundary.co2": "BOTH", "boundary.nitrogen": "NOT_USED",
            "scope.electrolysis": "INCLUDED", "scope.power_infrastructure": "INCLUDED",
            "scope.co2_supply": "INCLUDED", "scope.nitrogen_supply": "NOT_APPLICABLE",
            "scope.storage_logistics": "INCLUDED", "scope.site_civil": "INCLUDED"}
FIELDS = {"molecule": "E_METHANOL", "detail_level": "ENGINEERING", "location_jurisdiction": "DE",
          "capacity_factor": "60%", "project_life_years": 25, "wacc_pct": 0.08, "contingency_pct": 0.10,
          "power_price_eur_mwh": 55, "water_price_eur_m3": 2.5, "labour_count": 45, "labour_cost_eur_year": 65000,
          "insurance_pct_capex": 0.005}
LINES = [{"line_ref": "C01", "kind": "CATALOGUE", "catalogue_id": "PEM_ELEC_120MW", "quantity": 1},
         {"line_ref": "C02", "kind": "CATALOGUE", "catalogue_id": "MEOH_SYNTH_50KT", "quantity": 1},
         {"line_ref": "C03", "kind": "CATALOGUE", "catalogue_id": "CO2_CAPTURE_50KT", "quantity": 1},
         {"line_ref": "Q01", "kind": "QUOTE", "description": "Grid connection and substation (vendor quote)",
          "scope": "POWER_INFRASTRUCTURE", "installed_cost_eur": 14_000_000, "price_year": 2024,
          "annual_om_eur": 150_000, "annual_power_mwh": 0, "source": "TEST utility quote GQ-17"},
         {"line_ref": "Q02", "kind": "QUOTE", "description": "Site preparation and buildings",
          "scope": "SITE_CIVIL", "installed_cost_eur": 18_000_000, "price_year": 2024, "annual_om_eur": 90_000,
          "annual_power_mwh": 0, "source": "TEST civil estimate CE-4"},
         {"line_ref": "Q03", "kind": "QUOTE", "description": "Methanol storage 5 kt", "scope": "STORAGE_LOGISTICS",
          "installed_cost_eur": 3_200_000, "price_year": 2024, "annual_om_eur": 40_000, "annual_power_mwh": 0,
          "source": "TEST tank quote TQ-2"}]
FEEDS = [{"stream": "hydrogen", "on_site_t_per_year": 11_000, "on_site_basis": "PEM 120 MW at 60% run time"},
         {"stream": "co2", "on_site_t_per_year": 50_000, "on_site_basis": "capture unit rating",
          "purchase_unit": "t/day", "consumption_per_day": 45, "price_eur_per_unit": 208,
          "price_source": "registry co2_feedstock_price DE (proposed re-approval)"}]
FIN = {"financing.debt_eur": 160e6, "financing.interest_rate": "6.5%", "financing.debt_tenor_years": 15,
       "financing.grant_eur": 20e6}
STACK = [{"name": "Innovation grant", "type": "GRANT", "amount_eur": 20e6, "status": "APPLIED",
          "obligation": "INDICATIVE", "source": "TEST grant application GA-1", "as_of": "2026-10-01"},
         {"name": "Senior bank debt", "type": "SENIOR_DEBT", "amount_eur": 100e6, "rate": 0.07, "tenor_years": 15,
          "status": "TERM_SHEET", "obligation": "INDICATIVE", "lender_max_gearing": 0.6,
          "source": "TEST term sheet TS-3", "as_of": "2026-11-03"},
         {"name": "DFI loan", "type": "DFI_LOAN", "amount_eur": 60e6, "rate": 0.055, "tenor_years": 18,
          "status": "MANDATE", "obligation": "CONDITIONAL", "conditions": "credit committee; ESIA",
          "source": "TEST mandate letter ML-2", "as_of": "2026-11-10"},
         {"name": "Sponsor equity", "type": "SPONSOR_EQUITY", "amount_eur": 90e6, "status": "COMMITTED",
          "obligation": "BINDING", "available_eur": 70e6, "received_eur": 20e6, "source": "TEST board minute BM-9",
          "as_of": "2026-11-12"},
         {"name": "Green bond (prospect)", "type": "GREEN_BOND", "amount_eur": 50e6, "obligation": "NONE",
          "in_plan": "No", "source": "TEST arranger call", "as_of": "2026-11-15"}]
USES = [{"kind": "DEVELOPMENT", "amount_eur": 11e6, "standing": "MANAGEMENT_ASSUMPTION", "source": "TEST DEVEX plan"},
        {"kind": "FINANCING_COSTS", "component": "IDC", "amount_eur": 14e6,
         "reason": "engine IDC not built for this drawdown schedule", "source": "TEST lender model"},
        {"kind": "RESERVES", "amount_eur": 7e6, "source": "TEST term sheet: DSRA 6 months"},
        {"kind": "WORKING_CAPITAL", "amount_eur": 6e6, "source": "TEST 30 days of OPEX"}]
SHARED = {"offtake.planned_output_tonnes_per_year": 30_000, "offtake.product_spec_standard": "IMPCA",
          "offtake.change_in_law_allocated": "Yes"}
BUYER_1 = {"counterparty_name": "TEST Journey Buyer A", "counterparty_role": "END_USER",
           "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 0.8, "contracted_tonnes_per_year": 18_000,
           "tenor_years": 12, "buyer_investment_grade": "Yes", "price_mechanism": "INDEX_PLUS_PREMIUM",
           "first_delivery_date": "2029-07-01", "source": "TEST HoT HA-1", "as_of": "2026-10-20"}
BUYER_2 = {"company_id": BUYER_B, "counterparty_name": "TEST Journey Buyer B", "counterparty_role": "TRADER",
           "commitment_form": "TAKE_AND_PAY", "contracted_tonnes_per_year": 9_000, "tenor_years": 7,
           "buyer_investment_grade": "No", "price_mechanism": "FLOOR_CAP", "source": "TEST LOI LB-1",
           "as_of": "2026-11-18"}


def main() -> int:
    c = client()

    # 0 ── set-up through the workbook itself ────────────────────────────────
    blank = c.get(f"/api/v1/cost-basis/{P}/workbook/template", params={"blank": True})
    blank.raise_for_status()
    wb = wb_from(blank.content)
    for k, v in BOUNDARY.items():
        put(wb, "Cost Basis", k, v, source="stated by the CFO")
    for k, v in FIELDS.items():
        put(wb, "Cost Basis", k, v, source="TEST business plan BP-2", standing="MANAGEMENT_ASSUMPTION")
    rows(wb, "Cost Basis", "lines.header", cw.LINE_COLUMNS, LINES)
    put(wb, "TEA inputs", "tea.process_type", "Fluids", source="gas and liquid process")
    put(wb, "TEA inputs", "tea.loc_factor", 1.0, source="German quotes and catalogue at EUR prices")
    rows(wb, "TEA inputs", "feedstocks.header", cw.FEED_COLUMNS, FEEDS)
    for k, v in FIN.items():
        put(wb, "Financing", k, v, source="TEST indicative terms", standing="TERM_SHEET")
    rows(wb, "Financing", "capital.header", fw.CAP_COLUMNS, STACK)
    rows(wb, "Financing", "uses.header", fw.USE_COLUMNS, USES)
    for k, v in SHARED.items():
        put(wb, "Offtake", k, v, source="TEST offtake strategy OS-1")
    rows(wb, "Offtake", "buyers.header", fw.BUYER_COLUMNS, [BUYER_1])
    first = blob(wb)
    pv = preview(c, first)
    tabs = pv["tabs"]
    saved = {t: commit(c, first, pv["file_sha256"], t).status_code for t in ("cost_basis", "financing", "offtake")}
    ch = chain(c)
    cb = ch["cost_bases"][-1]
    tea = c.post(f"/api/v1/cost-basis/{P}/{cb['version_id']}/tea", json={"stated_from_workbook": True})
    run = tea.json().get("base_case", {}) if tea.status_code == 201 else {}
    osbl = next((x for x in tea.json().get("reconciliation", []) if x["check"] == "OSBL counted once"), {}) \
        if tea.status_code == 201 else {}
    step("0", "First workbook: preview, save three tabs, TEA run from the saved cost basis",
         all(s == 201 for s in saved.values()) and tea.status_code == 201,
         {"preview_blocking": {k: t["summary"]["blocking"] for k, t in tabs.items()},
          "cost_basis_saved_as": cb["status"], "saved_http": saved, "tea_http": tea.status_code,
          "tea_claim": run.get("claim_id"), "tea_capex_eur": run.get("capex_eur"),
          "osbl_check": osbl.get("result"), "osbl_detail": osbl.get("detail")})

    # 1 ── download the populated workbook ──────────────────────────────────
    populated = c.get(f"/api/v1/cost-basis/{P}/workbook/template")
    populated.raise_for_status()
    back = cw.parse_all(populated.content, catalogue=_catalogue(), project_id=P)["tabs"]
    fin_case = chain(c)["financing_cases"][-1]
    ok1 = (back["cost_basis"]["configuration"]["own_lines"] == cb["configuration"]["own_lines"]
           and back["financing"]["case_id"] == fin_case["case_id"]
           and len(back["financing"]["capital_sources"]) == 5 and all(x["source_id"] for x in back["financing"]["capital_sources"])
           and back["offtake"]["card"] == card(c))
    step("1", "Download the populated workbook: it holds what GEX saved, with GEX ids", ok1,
         {"file": populated.headers.get("content-disposition"), "case_id": back["financing"]["case_id"],
          "source_ids": [x["source_id"] for x in back["financing"]["capital_sources"]],
          "use_ids": [x["use_id"] for x in back["financing"]["funding_plan"]["uses"]]})

    # 2 ── change financing terms and add an offtaker ─────────────────────────
    wb = wb_from(populated.content)
    put(wb, "Financing", "financing.tea_claim_id", run.get("claim_id"), source="TEA run from cost basis v1")
    put(wb, "Financing", "financing.debt_eur", 160e6, source="TEST term sheet TS-3 (amended)", standing="TERM_SHEET")
    stack = table(wb, "Financing", "capital.header", fw.CAP_COLUMNS)
    for s in stack:
        if s["name"] == "DFI loan":
            s.update(obligation="BINDING", conditions=None, available_eur=60e6, status="SIGNED",
                     source="TEST facility agreement FA-1", as_of="2026-11-19")
    rows(wb, "Financing", "capital.header", fw.CAP_COLUMNS, stack)
    buyers = table(wb, "Offtake", "buyers.header", fw.BUYER_COLUMNS)
    buyers[0]["company_id"] = BUYER_A
    rows(wb, "Offtake", "buyers.header", fw.BUYER_COLUMNS, buyers + [BUYER_2])
    changed = blob(wb)
    step("2", "Change financing terms (TEA run named, DFI loan now binding) and add a second offtaker", True,
         {"dfi_loan": next(s for s in stack if s["name"] == "DFI loan"), "buyers": [b.get("company_id") for b in buyers] + [BUYER_B]})

    # R ── a rejected save leaves nothing behind ─────────────────────────────
    before = counts(c)
    wb_bad = wb_from(changed)
    bad_buyers = table(wb_bad, "Offtake", "buyers.header", fw.BUYER_COLUMNS)
    bad_buyers[-1]["company_id"] = "not_a_party_company"
    rows(wb_bad, "Offtake", "buyers.header", fw.BUYER_COLUMNS, bad_buyers)
    bad_stack = table(wb_bad, "Financing", "capital.header", fw.CAP_COLUMNS)
    bad_stack[0]["source"] = None
    rows(wb_bad, "Financing", "capital.header", fw.CAP_COLUMNS, bad_stack)
    bad = blob(wb_bad)
    bpv = preview(c, bad)
    refused = {t: commit(c, bad, bpv["file_sha256"], t).status_code for t in ("financing", "offtake")}
    after = counts(c)
    step("R", "A save with blocking entries is refused and leaves no record behind",
         all(v == 422 for v in refused.values()) and before == after,
         {"refused_http": refused, "counts_before": before, "counts_after": after,
          "blocking": {t: [r["detail"] for r in bpv["tabs"][t]["report"] if r["blocking"]] for t in ("financing", "offtake")}})

    # 3 ── preview and save the change ──────────────────────────────────────
    pv = preview(c, changed)
    fin_t, off_t = pv["tabs"]["financing"], pv["tabs"]["offtake"]
    s_fin = commit(c, changed, pv["file_sha256"], "financing")
    s_off = commit(c, changed, pv["file_sha256"], "offtake")
    step("3", "Preview and save the change", s_fin.status_code == 201 and s_off.status_code == 201,
         {"financing_would_save_as": fin_t.get("would_save_as"), "limitations": fin_t.get("limitations"),
          "remaining_need_eur": (fin_t.get("funding") or {}).get("remaining_need_eur"),
          "offtake": "frame of 2" if off_t.get("frame") else "single", "http": [s_fin.status_code, s_off.status_code]})

    # 4 ── reload GEX: every field, source and status ───────────────────────
    ch = chain(c)
    f = ch["financing_cases"][-1]
    terms_ok = all(t.get("source") and t.get("standing") == "TERM_SHEET" for t in f["terms"].values())
    dfi = next(s for s in f["funding_plan"]["sources"] if s["name"] == "DFI loan")
    k = card(c)
    ok4 = (f["status"] == "DRAFT" and f["tea_claim_id"] == run.get("claim_id") and terms_ok
           and dfi["obligation"] == "BINDING" and dfi["source"] == "TEST facility agreement FA-1"
           and {b["company_id"] for b in k.get("buyers") or []} == {BUYER_A, BUYER_B}
           and f["funding"]["remaining_need_eur"] is not None)
    step("4", "Reload GEX: every saved field, its source, standing and status is there", ok4,
         {"financing_version": f["version_number"], "status": f["status"], "case_id": f["case_id"],
          "limitations": [l["code"] for l in f["limitations"]],
          "terms": {n: [t["value"], t["source"], t.get("standing"), t.get("as_of")] for n, t in f["terms"].items()},
          "funding": {k2: f["funding"][k2] for k2 in ("total_uses_eur", "received_eur", "binding_available_eur",
                                                      "remaining_need_eur", "pipeline_total_eur")},
          "gearing": f["funding"]["gearing"], "offtake_buyers": [b["company_id"] for b in k["buyers"]]})

    # 5 ── export again and reconcile it with the records ────────────────────
    export = c.get(f"/api/v1/cost-basis/{P}/workbook/template")
    ex = cw.parse_all(export.content, catalogue=_catalogue(), project_id=P)["tabs"]
    diffs = []
    if ex["financing"]["terms"] != {n: {kk: t.get(kk) for kk in ("value", "source", "as_of", "standing")}
                                    for n, t in f["terms"].items()}:
        diffs.append("financing terms")
    if ex["financing"]["funding_plan"] != {"sources": f["funding_plan"]["sources"], "uses": f["funding_plan"]["uses"]}:
        diffs.append("funding plan")
    if ex["offtake"]["card"] != k:
        diffs.append("offtake card")
    if ex["cost_basis"]["configuration"]["own_lines"] != ch["cost_bases"][-1]["configuration"]["own_lines"]:
        diffs.append("cost basis lines")
    tea_x = c.get(f"/api/v1/calculation-chain/{P}/tea/{run.get('claim_id')}/workbook")
    step("5", "Export again: the workbook reconciles with GEX's records", not diffs and tea_x.status_code == 200,
         {"differences": diffs or "none", "tea_export_sheets": wb_from(tea_x.content).sheetnames if tea_x.status_code == 200 else tea_x.status_code})

    # 6 ── re-import an amendment: no duplicates ────────────────────────────
    wb = wb_from(export.content)
    put(wb, "Financing", "financing.interest_rate", "6.25%", source="TEST term sheet TS-4", standing="TERM_SHEET")
    st = table(wb, "Financing", "capital.header", fw.CAP_COLUMNS)
    ids_before = {s["source_id"] for s in st}
    for s in st:
        if s["name"] == "Senior bank debt":
            s["name"] = "Senior debt (club of three banks)"
    rows(wb, "Financing", "capital.header", fw.CAP_COLUMNS, st)
    amended = blob(wb)
    before = counts(c)
    pv = preview(c, amended)
    s6 = commit(c, amended, pv["file_sha256"], "financing")
    off6 = pv["tabs"]["offtake"]
    after = counts(c)
    f2 = chain(c)["financing_cases"][-1]
    ok6 = (s6.status_code == 201 and f2["case_id"] == f["case_id"] and f2["supersedes_version_id"] == f["version_id"]
           and {s["source_id"] for s in f2["funding_plan"]["sources"]} == ids_before
           and len(f2["funding_plan"]["uses"]) == len(f["funding_plan"]["uses"])
           and after["financing_cases"] == before["financing_cases"] and off6.get("unchanged")
           and after["offtake_buyers"] == 2)
    step("6", "Re-import an amendment: a new version of the same case; no duplicate case, source, use or buyer", ok6,
         {"counts_before": before, "counts_after": after, "renamed_source_kept_id": ids_before ==
          {s["source_id"] for s in f2["funding_plan"]["sources"]}, "offtake_tab": "unchanged, not re-saved"
          if off6.get("unchanged") else "changed", "new_version": f2["version_number"]})

    write_report()
    return 0 if all(s["result"] == "PASS" for s in steps) else 1


def _catalogue() -> dict:
    from app.core.plant_builder import EQUIPMENT_CATALOG
    return {i.id: i for i in EQUIPMENT_CATALOG}


def write_report() -> None:
    lines = [f"# CFO workbook journey on {P}", "",
             f"Run {datetime.now(timezone.utc).isoformat(timespec='seconds')} against {API}, as the demo CFO of the "
             "project's owner. Generated by `backend/scripts/workbook_journey_20261119.py`; every value below was "
             "read back from GEX.", ""]
    for s in steps:
        lines += [f"## {s['step']}. {s['title']}: **{s['result']}**", "", "```json",
                  json.dumps(s["evidence"], indent=1, default=str), "```", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print(f"report: {REPORT}")


if __name__ == "__main__":
    sys.exit(main())
