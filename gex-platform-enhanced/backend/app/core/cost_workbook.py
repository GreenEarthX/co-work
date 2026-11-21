"""The Cost Basis and TEA workbook: a CFO's spreadsheet into GEX, and GEX's TEA back out (19 Nov 2026).

Into GEX (`template`, `parse`, `compute_result`):
  - progressive detail: a line is a GEX CATALOGUE item, a vendor QUOTE or an AGGREGATE estimate
    (with its estimate class). An aggregate is a legitimate input, labelled as such everywhere; it
    never becomes an equipment-based TEA silently;
  - the PLANT BOUNDARY is stated first: is hydrogen / CO2 / nitrogen made on site or bought, and
    does the CAPEX include electrolysis, power infrastructure, CO2 supply ...; the lines and the TEA
    inputs are checked against it;
  - a blank cell is UNKNOWN, never zero;
  - every value carries its source; an external result (a consultant's TEA) is kept as an
    attributed external assessment, beside GEX's own, never in place of it;
  - `parse` writes nothing: it returns a report (ACCEPTED, CONVERTED, MISSING, CONFLICTING,
    UNSUPPORTED) and what would be saved. The route saves only what was previewed.

Out of GEX (`export_tea`): a frozen published case, values only, whose Cost Basis and TEA inputs
sheets are the template's own layout (so re-importing it reproduces the inputs), plus the TEA
results, the OpenPyTEA defaults still applied, the feedstock balance, the checks, external vs GEX,
and the exact OpenPyTEA config. It recalculates nothing: GEX's TEA engine computed it.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

TEMPLATE_VERSION = "gex-cost-tea-1"
SUPPORTED_VERSIONS = (TEMPLATE_VERSION,)          # an older version is migrated explicitly, never guessed

DETAIL_LEVELS = ("EARLY_ESTIMATE", "ENGINEERING", "FINANCING_PREP")
LINE_KINDS = ("CATALOGUE", "QUOTE", "AGGREGATE")
STANDINGS = ("VENDOR_QUOTE", "ENGINEERING_ESTIMATE", "CONSULTANT_REPORT", "TERM_SHEET", "CONTRACT",
             "MANAGEMENT_ASSUMPTION")
SUPPLY_ROUTES = ("ON_SITE", "PURCHASED", "BOTH", "NOT_USED")
SCOPE_ANSWERS = ("INCLUDED", "EXCLUDED", "NOT_APPLICABLE", "UNKNOWN")
SCOPES = ("ELECTROLYSIS", "SYNTHESIS", "POWER_INFRASTRUCTURE", "CO2_SUPPLY", "NITROGEN_SUPPLY",
          "STORAGE_LOGISTICS", "SITE_CIVIL", "UTILITIES", "WHOLE_PLANT", "OTHER")
BOUNDARY_SCOPES = ("ELECTROLYSIS", "POWER_INFRASTRUCTURE", "CO2_SUPPLY", "NITROGEN_SUPPLY",
                   "STORAGE_LOGISTICS", "SITE_CIVIL")
STREAMS = ("hydrogen", "co2", "nitrogen")          # the feedstocks whose route decides the boundary
STREAM_SCOPE = {"hydrogen": "ELECTROLYSIS", "co2": "CO2_SUPPLY", "nitrogen": "NITROGEN_SUPPLY"}
PURCHASE_UNITS = ("kg/day", "t/day", "Nm3/day", "MWh/day", "m3/day")
PROCESS_TYPES = ("Fluids", "Solids", "Mixed")
EXTERNAL_METRICS = ("CAPEX_EUR", "FCI_EUR", "OPEX_EUR_PER_YEAR", "LCOP_EUR_PER_KG", "OTHER")
GEX_FOR_EXTERNAL = {"CAPEX_EUR": "capex_eur", "FCI_EUR": "capex_eur", "OPEX_EUR_PER_YEAR": "opex_eur_per_year",
                    "LCOP_EUR_PER_KG": "lcop"}
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                 # text | list:<name> | number | int | fraction
    unit: str = ""
    required: bool = False
    help: str = ""


PROJECT_FIELDS = (
    Field("molecule", "Product", "list:molecules", "", True, "What the plant sells."),
    Field("detail_level", "Detail level of this cost basis", "list:detail_levels", "", True,
          "EARLY_ESTIMATE allows aggregate CAPEX; FINANCING_PREP needs equipment or quotes."),
    Field("location_jurisdiction", "Country", "text", "ISO 3166-1 alpha-2", True),
    Field("nameplate_t_per_year", "Nameplate output of the product", "number", "t/yr", False,
          "Required when no GEX catalogue line makes the product."),
    Field("capacity_factor", "Run time", "fraction", "share of the year, 0-1", True,
          "Follows from the power contract. 0.9 or 90% both read as 0.9."),
    Field("project_life_years", "Operating life", "int", "years", True),
    Field("wacc_pct", "Discount rate (WACC)", "fraction", "0-1", True),
    Field("contingency_pct", "Contingency on installed cost", "fraction", "0-1", True),
    Field("power_price_eur_mwh", "Electricity price", "number", "EUR/MWh", True),
    Field("water_price_eur_m3", "Water price", "number", "EUR/m3", False),
    Field("labour_count", "Operating staff", "int", "FTE", True),
    Field("labour_cost_eur_year", "Cost per FTE", "number", "EUR/yr", True),
    Field("insurance_pct_capex", "Insurance", "fraction", "share of CAPEX per year", False,
          "Blank: unknown. The TEA then applies OpenPyTEA's default, and says so."),
    Field("target_market_price_eur_t", "Expected selling price", "number", "EUR/t", False),
)
BOUNDARY_FIELDS = tuple(
    [Field(f"boundary.{s}", f"{s.upper() if s != 'hydrogen' else 'Hydrogen'}: made on site or bought?",
           "list:supply_routes", "", True) for s in STREAMS]
    + [Field(f"scope.{s.lower()}", f"Does the CAPEX include {s.replace('_', ' ').lower()}?",
             "list:scope_answers", "", True) for s in BOUNDARY_SCOPES])
LINE_COLUMNS = ("line_ref", "kind", "catalogue_id", "description", "scope", "quantity", "installed_cost_eur",
                "price_year", "estimate_class", "annual_om_eur", "annual_power_mwh", "source", "as_of")
LINE_HEADERS = ("Line ref", "Kind", "GEX catalogue id", "Description", "Scope", "Quantity",
                "Installed cost, whole line (EUR)", "Price year", "Estimate class (AACE 1-5)",
                "O&M per year (EUR)", "Power at the run time (MWh/yr)", "Source", "As of / document")
FEED_COLUMNS = ("stream", "on_site_t_per_year", "on_site_basis", "purchase_unit", "consumption_per_day",
                "price_eur_per_unit", "price_source", "as_of")
FEED_HEADERS = ("Stream", "Made on site (t/yr)", "Basis of on-site figure", "Purchase unit",
                "Purchase per day", "Price (EUR per unit)", "Price source", "As of")
EXT_COLUMNS = ("metric", "value", "unit", "author", "model_and_date", "document")
EXT_HEADERS = ("Metric", "Value", "Unit", "Author (organisation)", "Model / report and date", "Document")
TEA_FIELDS = (Field("tea.process_type", "Process type (OpenPyTEA factors)", "list:process_types", "", True),
              Field("tea.loc_factor", "Location factor", "number", "1.0 = prices already local", True))


class WorkbookError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


# ── catalogue helpers ──────────────────────────────────────────────────────────

def catalogue_scope(item) -> str:
    i, c = item.id, item.category
    if c == "ELECTROLYSER":
        return "ELECTROLYSIS"
    if i.startswith(("CO2_", "DAC_")):
        return "CO2_SUPPLY"
    if i.startswith(("ASU_", "N2_")):
        return "NITROGEN_SUPPLY"
    if i.startswith(("GRID_", "POWER_", "BESS_")):
        return "POWER_INFRASTRUCTURE"
    if c == "STORAGE":
        return "STORAGE_LOGISTICS"
    if i.startswith(("SITE_", "BUILDINGS_")):
        return "SITE_CIVIL"
    if c == "REACTOR":
        return "SYNTHESIS"
    return "UTILITIES"


def molecules(catalogue: dict) -> tuple:
    return tuple(sorted({i.molecule_output for i in catalogue.values() if i.molecule_output != "ALL"}))


def _lists(catalogue: dict) -> dict:
    return {"molecules": molecules(catalogue), "detail_levels": DETAIL_LEVELS, "line_kinds": LINE_KINDS,
            "standings": STANDINGS, "supply_routes": SUPPLY_ROUTES, "scope_answers": SCOPE_ANSWERS,
            "scopes": SCOPES, "purchase_units": PURCHASE_UNITS, "process_types": PROCESS_TYPES,
            "external_metrics": EXTERNAL_METRICS, **_finance_lists(), "catalogue_ids": tuple(sorted(catalogue))}


def _finance_lists() -> dict:
    from app.core import finance_workbook as fw
    return fw.extra_lists()


# ── template (and the filled template of the export) ──────────────────────────

def template(catalogue: dict, *, project_id: str, project_name: str = "", cost_basis: Optional[dict] = None,
             base_case: Optional[dict] = None, financing: Optional[dict] = None,
             offtake: Optional[dict] = None) -> bytes:
    """The empty template, or the template filled from the project's saved records.
    `financing` / `offtake` are already filled values (finance_workbook.fill_*)."""
    from app.core import finance_workbook as fw
    wb = _new_workbook()
    _read_me(wb, project_id, project_name, filled=cost_basis is not None)
    filled = fill_values(cost_basis, base_case) if cost_basis else None
    _cost_sheet(wb, catalogue, project_id, filled)
    _tea_sheet(wb, catalogue, filled)
    fw.financing_sheet(wb, _lists(catalogue), financing)
    fw.offtake_sheet(wb, _lists(catalogue), offtake)
    _lists_sheet(wb, catalogue)
    return _save(wb)


def _new_workbook():
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _styles():
    from openpyxl.styles import Font, PatternFill, Alignment
    return {"title": Font(bold=True, size=14), "h": Font(bold=True, size=11), "key": Font(color="999999", size=8),
            "head": Font(bold=True, color="FFFFFF"), "headfill": PatternFill("solid", fgColor="2F5D50"),
            "input": PatternFill("solid", fgColor="E8F1FB"), "wrap": Alignment(wrap_text=True, vertical="top")}


def _read_me(wb, project_id: str, project_name: str, *, filled: bool):
    s = _styles()
    ws = wb.create_sheet("Read me")
    rows = [
        ("GEX Cost Basis and TEA workbook", s["title"]),
        (f"Template {TEMPLATE_VERSION}. Project: {project_id} {project_name}".strip(), None),
        ("", None),
        ("How to fill it", s["h"]),
        ("1. Blue cells are yours. Grey keys in column A are how GEX reads a row: do not change them.", None),
        ("2. Start with the PLANT BOUNDARY on 'Cost Basis': what you make on site, what you buy, what the CAPEX covers.", None),
        ("3. Give the detail you have. An aggregate CAPEX is fine at EARLY_ESTIMATE: enter it as an AGGREGATE line "
         "with its estimate class. GEX labels it as an aggregate everywhere.", None),
        ("4. A blank cell means UNKNOWN. It is never read as zero. Do not type 0 for 'not known'.", None),
        ("5. Every value needs its source (a quote, a study, a contract, a management assumption) and a date.", None),
        ("6. Do not type conclusions GEX computes (gate states, PASS/FAIL, bankability scores). If you hold an "
         "external TEA or model, put its results under 'External results' on 'TEA inputs': GEX keeps them, "
         "attributed, beside its own figures.", None),
        ("7. Type values, not formulas. A formula Excel has not calculated has no value GEX can read.", None),
        ("8. Give every quote its PRICE YEAR (the year the price was stated). A quote from an earlier year is brought "
         "to the TEA's cost base with the CEPCI index and its approved Gabillon forward, and the TEA report shows the "
         "Gabillon band on it. A quote with no price year is taken at the cost base: nothing is escalated and the "
         "band is zero.", None),
        ("", None),
        ("What happens on upload", s["h"]),
        ("GEX first shows a PREVIEW: every entry ACCEPTED, CONVERTED, MISSING, CONFLICTING or UNSUPPORTED, and "
         "what changed against the current cost basis. Nothing is saved until you confirm that exact file.", None),
        ("The same project permissions apply as on the screens: an engineering, finance or executive user of the "
         "owner saves a cost basis.", None),
    ]
    if filled:
        rows += [("", None), ("This copy is FILLED from a saved cost basis: amend it and upload it again to save "
                              "the next version.", s["h"])]
    for r, (text, font) in enumerate(rows, 1):
        c = ws.cell(r, 1, text)
        if font:
            c.font = font
    ws.column_dimensions["A"].width = 140


def _field_rows(ws, start: int, fields, values: dict, lists: dict, dv_cache: dict, *, with_source=True) -> int:
    s = _styles()
    heads = ("key", "Field", "Value", "Unit", "Source", "As of", "Standing") if with_source else \
        ("key", "Question", "Answer", "", "Basis / notes")
    for col, h in enumerate(heads, 1):
        c = ws.cell(start, col, h)
        c.font, c.fill = s["head"], s["headfill"]
    r = start + 1
    for f in fields:
        v = values.get(f.key) or {}
        ws.cell(r, 1, f.key).font = s["key"]
        ws.cell(r, 2, f.label + (" *" if f.required else ""))
        cell = ws.cell(r, 3, v.get("value"))
        cell.fill = s["input"]
        if with_source:
            ws.cell(r, 4, f.unit)
            for col, k in ((5, "source"), (6, "as_of"), (7, "standing")):
                ws.cell(r, col, v.get(k)).fill = s["input"]
            _validate(ws, dv_cache, "standings", lists, f"G{r}")
        else:
            ws.cell(r, 5, v.get("source")).fill = s["input"]
        if f.kind.startswith("list:"):
            _validate(ws, dv_cache, f.kind[5:], lists, f"C{r}")
        if f.help:
            ws.cell(r, 8 if with_source else 6, f.help).font = s["key"]
        r += 1
    return r


def _validate(ws, cache: dict, name: str, lists: dict, ref: str):
    from openpyxl.worksheet.datavalidation import DataValidation
    key = (ws.title, name)
    if key not in cache:
        col = list(lists).index(name) + 1
        from openpyxl.utils import get_column_letter
        L = get_column_letter(col)
        dv = DataValidation(type="list", formula1=f"=Lists!${L}$2:${L}${len(lists[name]) + 1}", allow_blank=True)
        ws.add_data_validation(dv)
        cache[key] = dv
    cache[key].add(ref)


def _table(ws, start: int, key: str, headers, columns, rows: list, n_blank: int, lists: dict, dv_cache: dict,
           lists_for: dict) -> int:
    s = _styles()
    ws.cell(start, 1, key).font = s["key"]
    for col, h in enumerate(headers, 2):
        c = ws.cell(start, col, h)
        c.font, c.fill, c.alignment = s["head"], s["headfill"], s["wrap"]
    r = start + 1
    from openpyxl.utils import get_column_letter
    for row in rows + [{}] * n_blank:
        ws.cell(r, 1, "row").font = s["key"]
        for col, name in enumerate(columns, 2):
            ws.cell(r, col, row.get(name)).fill = s["input"]
            if name in lists_for:
                _validate(ws, dv_cache, lists_for[name], lists, f"{get_column_letter(col)}{r}")
        r += 1
    ws.cell(r, 1, f"{key.split('.')[0]}.end").font = s["key"]
    return r + 1


def _cost_sheet(wb, catalogue: dict, project_id: str, filled: Optional[dict]):
    s = _styles()
    ws = wb.create_sheet("Cost Basis")
    lists, dv = _lists(catalogue), {}
    f = filled or {}
    ws.cell(1, 2, "COST BASIS").font = s["title"]
    ws.cell(2, 1, "template_version").font = s["key"]
    ws.cell(2, 2, TEMPLATE_VERSION)
    ws.cell(3, 1, "project_id").font = s["key"]
    ws.cell(3, 2, project_id)
    ws.cell(5, 2, "1. Plant boundary: answer first").font = s["h"]
    r = _field_rows(ws, 6, BOUNDARY_FIELDS, f.get("fields", {}), lists, dv, with_source=False)
    ws.cell(r + 1, 2, "2. Project and run").font = s["h"]
    r = _field_rows(ws, r + 2, PROJECT_FIELDS, f.get("fields", {}), lists, dv)
    ws.cell(r + 1, 2, "3. CAPEX lines: CATALOGUE (GEX prices it), QUOTE (your vendor's installed price) or "
                      "AGGREGATE (an estimate covering several items; state its class)").font = s["h"]
    _table(ws, r + 2, "lines.header", LINE_HEADERS, LINE_COLUMNS, f.get("lines", []), 25, lists, dv,
           {"kind": "line_kinds", "scope": "scopes", "catalogue_id": "catalogue_ids"})
    for col, w in zip("ABCDEFGHIJKLMN", (16, 34, 16, 26, 34, 20, 10, 18, 10, 12, 14, 16, 30, 22)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C5"


def _tea_sheet(wb, catalogue: dict, filled: Optional[dict]):
    s = _styles()
    ws = wb.create_sheet("TEA inputs")
    lists, dv = _lists(catalogue), {}
    f = filled or {}
    ws.cell(1, 2, "TEA INPUTS").font = s["title"]
    ws.cell(2, 2, "Electricity and water come from the Cost Basis. State here what the TEA engine needs besides.")
    ws.cell(4, 2, "1. Engine inputs").font = s["h"]
    r = _field_rows(ws, 5, TEA_FIELDS, f.get("tea_fields", {}), lists, dv)
    ws.cell(r + 1, 2, "2. Feedstocks: made on site, bought, or both (must match the plant boundary)").font = s["h"]
    r = _table(ws, r + 2, "feedstocks.header", FEED_HEADERS, FEED_COLUMNS, f.get("feedstocks", []), 6, lists, dv,
               {"purchase_unit": "purchase_units"})
    ws.cell(r + 1, 2, "3. External results (optional): a consultant's or lender's figures, kept as attributed "
                      "external assessments beside GEX's own").font = s["h"]
    _table(ws, r + 2, "external.header", EXT_HEADERS, EXT_COLUMNS, f.get("external", []), 6, lists, dv,
           {"metric": "external_metrics"})
    for col, w in zip("ABCDEFGHI", (16, 30, 16, 26, 16, 16, 16, 26, 16)):
        ws.column_dimensions[col].width = w


def _lists_sheet(wb, catalogue: dict):
    ws = wb.create_sheet("Lists")
    for col, (name, values) in enumerate(_lists(catalogue).items(), 1):
        ws.cell(1, col, name)
        for r, v in enumerate(values, 2):
            ws.cell(r, col, v)
    cat = wb.create_sheet("Catalogue")
    for col, h in enumerate(("GEX catalogue id", "Name", "Scope", "Product", "Unit price (EUR)",
                             "Installation multiplier"), 1):
        cat.cell(1, col, h)
    for r, i in enumerate(sorted(catalogue.values(), key=lambda i: i.id), 2):
        for col, v in enumerate((i.id, i.name, catalogue_scope(i), i.molecule_output, i.unit_price_eur,
                                 i.installation_multiplier), 1):
            cat.cell(r, col, v)


def fill_values(cost_basis: dict, base_case: Optional[dict] = None) -> dict:
    """The template's cells for a saved cost basis (and TEA run): the inverse of `parse`."""
    cfg = cost_basis["configuration"]
    prov = cfg.get("provenance") or {}
    legacy = f"saved on the Cost Basis screen, v{cost_basis.get('version_number')}"
    fields = {}
    for f in PROJECT_FIELDS:
        if f.key == "nameplate_t_per_year":
            p = cfg.get("stated_nameplate") or {}
            value = p.get("value")
        else:
            value, p = cfg.get(f.key), prov.get(f.key) or {}
        if value is None:
            continue
        fields[f.key] = {"value": value, "source": p.get("source") or legacy, "as_of": p.get("as_of"),
                         "standing": p.get("standing")}
    pb = cfg.get("plant_boundary") or {}
    for f in BOUNDARY_FIELDS:
        b = pb.get(f.key)
        if b:
            fields[f.key] = {"value": b.get("value"), "source": b.get("basis")}
    lines = [{"line_ref": f"C{n:02d}", "kind": "CATALOGUE", "catalogue_id": e["equipment_id"],
              "quantity": e.get("quantity", 1), "source": e.get("source") or legacy}
             for n, e in enumerate(cfg.get("equipment") or [], 1)]
    lines += [{k: l.get(k) for k in LINE_COLUMNS} for l in cfg.get("own_lines") or []]
    wbk = cfg.get("workbook") or {}
    out = {"fields": fields, "lines": lines, "external": list(wbk.get("external") or []),
           "tea_fields": {}, "feedstocks": []}
    stated = wbk.get("tea_stated")
    if base_case and (base_case.get("tea_inputs") or {}).get("request"):
        req = base_case["tea_inputs"]["request"]
        q = req.get("quote_plant") or {}
        stated = {"process_type": {"value": req.get("plant_process_type"), "basis": None},
                  "loc_factor": {"value": q.get("loc_factor"), "basis": q.get("loc_factor_basis")},
                  "feedstocks": {}}
        for k, v in (q.get("on_site_supply") or {}).items():
            stated["feedstocks"].setdefault(k, {}).update(on_site_t_per_year=v["t_per_year"], basis=v["basis"])
        for k, v in (q.get("variable_opex") or {}).items():
            if k in ("electricity", "water"):
                continue                       # from the cost basis
            stated["feedstocks"].setdefault(k, {}).update(unit=v["unit"], consumption_per_day=v["consumption"],
                                                          price_eur_per_unit=v["price"], source=v["source"])
        old = (wbk.get("tea_stated") or {})
        stated["process_type"]["basis"] = (old.get("process_type") or {}).get("basis") or "stated with the TEA run"
    if stated:
        for key in ("process_type", "loc_factor"):
            t = stated.get(key) or {}
            p = (wbk.get("tea_provenance") or {}).get(key) or {}
            out["tea_fields"][f"tea.{key}"] = {"value": t.get("value"), "source": t.get("basis"),
                                               "as_of": p.get("as_of"), "standing": p.get("standing")}
        for k, v in (stated.get("feedstocks") or {}).items():
            out["feedstocks"].append({"stream": k, "on_site_t_per_year": v.get("on_site_t_per_year"),
                                      "on_site_basis": v.get("basis"), "purchase_unit": v.get("unit"),
                                      "consumption_per_day": v.get("consumption_per_day"),
                                      "price_eur_per_unit": v.get("price_eur_per_unit"),
                                      "price_source": v.get("source"), "as_of": v.get("as_of")})
    return out


# ── parse: the preview ─────────────────────────────────────────────────────────

class _Report:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, status: str, where: str, field: str, detail: str, *, blocking: bool = False, value=None,
            issue: bool = False):
        """`blocking`: nothing can be saved. `issue`: saved as a DRAFT, stated, and the next step
        (a TEA run, a promotion) refuses until a version without it is saved."""
        self.rows.append({"status": status, "where": where, "field": field, "detail": detail,
                          "blocking": blocking, "value": value, "issue": issue})

    def summary(self) -> dict:
        out = {s: 0 for s in ("ACCEPTED", "CONVERTED", "MISSING", "CONFLICTING", "UNSUPPORTED")}
        for r in self.rows:
            out[r["status"]] += 1
        out["blocking"] = sum(1 for r in self.rows if r["blocking"])
        out["open_issues"] = sum(1 for r in self.rows if r.get("issue"))
        return out


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v):
    """(number, converted_note) — a numeric string is read, a '%' is a percentage."""
    if isinstance(v, bool):
        raise ValueError("not a number")
    if isinstance(v, (int, float)):
        return float(v), None
    t = str(v).strip().replace(" ", "").replace(" ", "")
    pct = t.endswith("%")
    t = t.rstrip("%").replace(",", "")
    n = float(t)
    return (n / 100.0, f"read '{v}' as {n / 100.0}") if pct else (n, f"read text '{v}' as {n}")


def _cells(ws_values, ws_formulas):
    """Rows as lists, with a marker for a formula Excel never calculated."""
    rows = []
    for rv, rf in zip(ws_values.iter_rows(values_only=True), ws_formulas.iter_rows(values_only=True)):
        row = []
        for v, f in zip(rv, rf):
            if v is None and isinstance(f, str) and f.startswith("="):
                row.append(_UNCALCULATED)
            else:
                row.append(v)
        rows.append(row)
    return rows


class _Uncalculated:
    def __repr__(self):
        return "UNCALCULATED_FORMULA"


_UNCALCULATED = _Uncalculated()


def _col(row, i):
    return row[i] if i < len(row) else None


def parse(data: bytes, *, catalogue: dict, project_id: str) -> dict:
    """Read a filled template. Writes nothing; returns what would be saved and the report."""
    if len(data) > MAX_BYTES:
        raise WorkbookError("WORKBOOK_TOO_LARGE", f"The workbook is over {MAX_BYTES // 1_000_000} MB.")
    from openpyxl import load_workbook
    try:
        wv = load_workbook(io.BytesIO(data), data_only=True)
        wf = load_workbook(io.BytesIO(data), data_only=False)
    except Exception as e:  # noqa: BLE001 — anything openpyxl cannot open is not a GEX workbook
        raise WorkbookError("NOT_A_WORKBOOK", f"This file cannot be read as an .xlsx workbook ({type(e).__name__}).")
    for sheet in ("Cost Basis", "TEA inputs"):
        if sheet not in wv.sheetnames:
            raise WorkbookError("NOT_A_GEX_TEMPLATE", f"The workbook has no '{sheet}' sheet: download the template.")
    rep = _Report()
    cost = _cells(wv["Cost Basis"], wf["Cost Basis"])
    tea = _cells(wv["TEA inputs"], wf["TEA inputs"])
    keyed = {str(_col(r, 0)).strip(): (i, r) for i, r in enumerate(cost) if not _blank(_col(r, 0))}
    version = _col(keyed.get("template_version", (0, []))[1], 1)
    if version not in SUPPORTED_VERSIONS:
        raise WorkbookError("TEMPLATE_VERSION_UNSUPPORTED",
                            f"Template version '{version}' is not one GEX reads ({', '.join(SUPPORTED_VERSIONS)}). "
                            "Download the current template; an older one is migrated on request, never guessed.")
    wb_project = _col(keyed.get("project_id", (0, []))[1], 1)
    if wb_project != project_id:
        raise WorkbookError("WRONG_PROJECT", f"This workbook is for project '{wb_project}', not '{project_id}'.")

    lists = _lists(catalogue)
    fields, prov = {}, {}

    def read_field(f: Field, row, sheet: str, rnum: int, *, with_source: bool):
        where = f"{sheet}!C{rnum + 1}"
        v = _col(row, 2)
        src = _col(row, 4)
        if v is _UNCALCULATED:
            rep.add("UNSUPPORTED", where, f.key, "A formula with no calculated value: type the value, or open and "
                    "save the file in Excel.", blocking=f.required)
            return
        if _blank(v):
            if f.key.startswith(("boundary.", "scope.")):
                rep.add("MISSING", where, f.key, "Not answered: the plant boundary is open.", issue=True)
                return
            rep.add("MISSING", where, f.key, "Required." if f.required else "Left blank: unknown, not zero.",
                    blocking=f.required)
            return
        note = None
        try:
            if f.kind.startswith("list:"):
                v = str(v).strip()
                if v not in lists[f.kind[5:]]:
                    rep.add("UNSUPPORTED", where, f.key, f"'{v}' is not one of {list(lists[f.kind[5:]])}.",
                            blocking=True, value=v)
                    return
            elif f.kind in ("number", "int", "fraction"):
                v, note = _num(v)
                if f.kind == "fraction" and 1 < v <= 100:
                    note, v = f"read {v} as a percentage: {v / 100}", v / 100
                if f.kind == "fraction" and not (0 <= v <= 1):
                    raise ValueError("out of 0-1")
                if f.kind == "int":
                    if v != int(v):
                        raise ValueError("not whole")
                    v = int(v)
                if v < 0:
                    raise ValueError("negative")
            else:
                v = str(v).strip()
        except (ValueError, TypeError) as e:
            rep.add("UNSUPPORTED", where, f.key, f"'{_col(row, 2)}' is not a valid {f.kind} ({e}).", blocking=True)
            return
        if with_source and f.required and _blank(src):
            rep.add("MISSING", f"{sheet}!E{rnum + 1}", f.key, "State the source of this value.", blocking=True,
                    value=v)
        fields[f.key] = v
        if with_source:
            prov[f.key] = {"source": None if _blank(src) else str(src).strip(),
                           "as_of": _text(_col(row, 5)), "standing": _text(_col(row, 6))}
            if prov[f.key]["standing"] and prov[f.key]["standing"] not in STANDINGS:
                rep.add("UNSUPPORTED", f"{sheet}!G{rnum + 1}", f.key, f"Standing must be one of {list(STANDINGS)}.")
                prov[f.key]["standing"] = None
        else:
            prov[f.key] = {"basis": None if _blank(src) else str(src).strip()}
        rep.add("CONVERTED" if note else "ACCEPTED", where, f.key, note or "", value=v)

    for f in BOUNDARY_FIELDS:
        if f.key not in keyed:
            rep.add("MISSING", "Cost Basis", f.key, "Row removed from the template.", blocking=True)
            continue
        rnum, row = keyed[f.key]
        read_field(f, row, "Cost Basis", rnum, with_source=False)
    for f in PROJECT_FIELDS:
        if f.key not in keyed:
            rep.add("MISSING", "Cost Basis", f.key, "Row removed from the template.", blocking=f.required)
            continue
        rnum, row = keyed[f.key]
        read_field(f, row, "Cost Basis", rnum, with_source=True)
    known = {f.key for f in PROJECT_FIELDS + BOUNDARY_FIELDS} | {"template_version", "project_id", "row", "key",
                                                                 "lines.header", "lines.end"}
    for k, (rnum, _) in keyed.items():
        if k not in known:
            rep.add("UNSUPPORTED", f"Cost Basis!A{rnum + 1}", k, "GEX does not read this row; it was not imported.")

    lines = _rows_between(cost, "lines.header", "lines.end", LINE_COLUMNS)
    catalogue_lines, own_lines = _read_lines(lines, catalogue, fields, rep)

    tkeyed = {str(_col(r, 0)).strip(): (i, r) for i, r in enumerate(tea) if not _blank(_col(r, 0))}
    tea_fields = {}
    for f in TEA_FIELDS:
        if f.key not in tkeyed:
            rep.add("MISSING", "TEA inputs", f.key, "Row removed from the template.", blocking=True)
            continue
        rnum, row = tkeyed[f.key]
        read_field(f, row, "TEA inputs", rnum, with_source=True)
        if f.key in fields:
            tea_fields[f.key] = fields.pop(f.key)
    feeds = _read_feeds(_rows_between(tea, "feedstocks.header", "feedstocks.end", FEED_COLUMNS), rep)
    external = _read_external(_rows_between(tea, "external.header", "external.end", EXT_COLUMNS), rep)

    provided = bool(fields or catalogue_lines or own_lines)
    boundary = {f.key: {"value": fields.pop(f.key), "basis": (prov.pop(f.key, {}) or {}).get("basis")}
                for f in BOUNDARY_FIELDS if f.key in fields}
    _boundary_checks(boundary, catalogue_lines, own_lines, feeds, catalogue, rep)
    _detail_checks(fields.get("detail_level"), own_lines, rep)
    nameplate = fields.pop("nameplate_t_per_year", None)
    if nameplate is not None:
        _nameplate_check(nameplate, fields, catalogue_lines, catalogue, rep)
    elif not any(catalogue[l["equipment_id"]].molecule_output == fields.get("molecule")
                 and (catalogue[l["equipment_id"]].capacity_tonnes_year > 0 or catalogue[l["equipment_id"]].rated_mw > 0)
                 for l in catalogue_lines):
        rep.add("MISSING", "Cost Basis", "nameplate_t_per_year",
                "No catalogue line makes the product: state the nameplate output.", blocking=True)

    tea_stated = {
        "process_type": {"value": tea_fields.get("tea.process_type"),
                         "basis": (prov.get("tea.process_type") or {}).get("source")},
        "loc_factor": {"value": tea_fields.get("tea.loc_factor"),
                       "basis": (prov.get("tea.loc_factor") or {}).get("source")},
        "feedstocks": {k: {kk: vv for kk, vv in v.items() if kk != "as_of"} for k, v in feeds.items()},
    }
    tea_prov = {k: prov.pop(f"tea.{k}") for k in ("process_type", "loc_factor") if f"tea.{k}" in prov}
    configuration = {
        **{k: v for k, v in fields.items()},
        "equipment": catalogue_lines,
        "own_lines": own_lines,
        "stated_nameplate": ({"value": nameplate, **(prov.pop("nameplate_t_per_year", {}) or {})}
                             if nameplate is not None else None),
        "plant_boundary": boundary,
        "provenance": prov,
        "workbook": {"template_version": version, "file_sha256": hashlib.sha256(data).hexdigest(),
                     "tea_stated": tea_stated, "tea_provenance": tea_prov, "external": external,
                     "feedstock_dates": {k: v.get("as_of") for k, v in feeds.items() if v.get("as_of")}},
    }
    summary = rep.summary()
    issues = [{"field": r["field"], "detail": r["detail"]} for r in rep.rows if r.get("issue")]
    if not provided:
        return {"provided": False, "template_version": version, "file_sha256": configuration["workbook"]["file_sha256"],
                "report": [], "summary": _Report().summary(), "can_commit": False}
    return {"provided": True, "open_issues": issues, "would_save_as": "DRAFT" if issues else "READY",
            "template_version": version, "file_sha256": configuration["workbook"]["file_sha256"],
            "configuration": configuration, "tea_stated": tea_stated, "external": external,
            "report": rep.rows, "summary": summary, "can_commit": summary["blocking"] == 0}


def parse_all(data: bytes, *, catalogue: dict, project_id: str) -> dict:
    """Every tab of the workbook, each with its own report and whether it can be saved.
    A tab left empty is `provided: false`, not an error."""
    from openpyxl import load_workbook
    from app.core import finance_workbook as fw
    cost = parse(data, catalogue=catalogue, project_id=project_id)
    wv = load_workbook(io.BytesIO(data), data_only=True)
    wf = load_workbook(io.BytesIO(data), data_only=False)
    lists = _lists(catalogue)
    tabs = {"cost_basis": cost}
    for name, sheet, fn in (("financing", "Financing", fw.parse_financing), ("offtake", "Offtake", fw.parse_offtake)):
        tabs[name] = (fn(_cells(wv[sheet], wf[sheet]), lists=lists) if sheet in wv.sheetnames else
                      {"provided": False, "report": [], "summary": _Report().summary(), "can_commit": False})
    return {"file_sha256": cost["file_sha256"], "template_version": cost["template_version"], "tabs": tabs}


def _text(v) -> Optional[str]:
    if _blank(v) or v is _UNCALCULATED:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v).strip()


def _rows_between(rows, start_key: str, end_key: str, columns) -> list[tuple[int, dict]]:
    out, inside = [], False
    for i, r in enumerate(rows):
        k = _col(r, 0)
        if k == start_key:
            inside = True
            continue
        if k == end_key:
            break
        if inside and k == "row":
            vals = {name: _col(r, j + 1) for j, name in enumerate(columns)}
            if any(not _blank(v) for v in vals.values()):
                out.append((i + 1, vals))
    return out


def _read_lines(lines, catalogue, fields, rep) -> tuple[list, list]:
    from openpyxl.utils import get_column_letter
    cat_lines, own, refs = [], [], set()

    def at(rnum, name):
        return f"Cost Basis!{get_column_letter(LINE_COLUMNS.index(name) + 2)}{rnum}"

    for rnum, l in lines:
        if any(v is _UNCALCULATED for v in l.values()):
            rep.add("UNSUPPORTED", f"Cost Basis!row {rnum}", "line", "A formula with no calculated value.",
                    blocking=True)
            continue
        kind = _text(l["kind"])
        ref = _text(l["line_ref"]) or f"R{rnum}"
        if ref in refs:
            rep.add("CONFLICTING", at(rnum, "line_ref"), ref, "Two lines share this reference.", blocking=True)
        refs.add(ref)
        if kind not in LINE_KINDS:
            rep.add("UNSUPPORTED", at(rnum, "kind"), ref, f"Kind must be one of {list(LINE_KINDS)}.", blocking=True)
            continue
        qty = 1
        if not _blank(l["quantity"]):
            try:
                q, _ = _num(l["quantity"])
                if q < 1 or q != int(q):
                    raise ValueError
                qty = int(q)
            except (ValueError, TypeError):
                rep.add("UNSUPPORTED", at(rnum, "quantity"), ref, "Quantity must be a whole number >= 1.",
                        blocking=True)
                continue
        if kind == "CATALOGUE":
            cid = _text(l["catalogue_id"])
            if cid not in catalogue:
                rep.add("UNSUPPORTED", at(rnum, "catalogue_id"), ref,
                        f"'{cid}' is not in the GEX catalogue (sheet 'Catalogue'). Enter your own price as a QUOTE.",
                        blocking=True)
                continue
            typed = [n for n in ("installed_cost_eur", "annual_om_eur", "annual_power_mwh") if not _blank(l[n])]
            if typed:
                rep.add("CONFLICTING", at(rnum, typed[0]), ref,
                        f"A CATALOGUE line is priced by GEX's catalogue, yet {typed} were typed. Keep the catalogue "
                        "line and clear them, or enter your figures as a QUOTE line.", blocking=True)
                continue
            line = {"equipment_id": cid, "quantity": qty}
            if _text(l["source"]):
                line["source"] = _text(l["source"])
            cat_lines.append(line)
            rep.add("ACCEPTED", at(rnum, "catalogue_id"), ref, f"catalogue {cid} x{qty}")
            continue
        out = {"line_ref": ref, "kind": kind, "description": _text(l["description"]),
               "scope": _text(l["scope"]), "quantity": qty, "catalogue_id": None,
               "source": _text(l["source"]), "as_of": _text(l["as_of"])}
        ok = True
        for name, required in (("installed_cost_eur", True), ("annual_om_eur", False), ("annual_power_mwh", False),
                               ("price_year", False), ("estimate_class", kind == "AGGREGATE")):
            v = l[name]
            if _blank(v):
                out[name] = None
                if required:
                    rep.add("MISSING", at(rnum, name), ref, f"{name} is required on a {kind} line.", blocking=True)
                    ok = False
                continue
            try:
                n, note = _num(v)
                if n < 0:
                    raise ValueError
                if name in ("price_year", "estimate_class"):
                    n = int(n)
                    if name == "estimate_class" and not 1 <= n <= 5:
                        raise ValueError
                out[name] = n
                if note:
                    rep.add("CONVERTED", at(rnum, name), ref, note, value=n)
            except (ValueError, TypeError):
                rep.add("UNSUPPORTED", at(rnum, name), ref, f"'{v}' is not a valid {name}.", blocking=True)
                ok = False
        if out["scope"] not in SCOPES:
            rep.add("MISSING" if not out["scope"] else "UNSUPPORTED", at(rnum, "scope"), ref,
                    f"State the line's scope, one of {list(SCOPES)}: the plant boundary is checked against it.",
                    blocking=True)
            ok = False
        if not out["source"]:
            rep.add("MISSING", at(rnum, "source"), ref, "State the source (quote, study, assumption).", blocking=True)
            ok = False
        if not ok:
            continue
        if out["annual_power_mwh"] is None and out["scope"] in ("ELECTROLYSIS", "WHOLE_PLANT"):
            rep.add("MISSING", at(rnum, "annual_power_mwh"), ref,
                    "An electrolysis (or whole-plant) line must state its power at the run time: without it the "
                    "electricity bill is not priced.", blocking=True)
            continue
        for name, what in (("annual_om_eur", "O&M"), ("annual_power_mwh", "power"), ("price_year", "price year")):
            if out[name] is None:
                rep.add("MISSING", at(rnum, name), ref, f"{what} not stated: unknown, not zero.")
        own.append(out)
        rep.add("ACCEPTED", at(rnum, "installed_cost_eur"), ref,
                f"{kind} EUR {out['installed_cost_eur']:,.0f} ({out['scope']})", value=out["installed_cost_eur"])
    if not cat_lines and not own:
        rep.add("MISSING", "Cost Basis", "lines", "No CAPEX line.", blocking=True)
    return cat_lines, own


def _read_feeds(rows, rep) -> dict:
    out = {}
    for rnum, f in rows:
        stream = (_text(f["stream"]) or "").lower()
        where = f"TEA inputs!row {rnum}"
        if not stream:
            rep.add("MISSING", where, "stream", "Name the stream.", blocking=True)
            continue
        if stream in out:
            rep.add("CONFLICTING", where, stream, "This stream appears twice: put on-site and purchase on one row.",
                    blocking=True)
            continue
        e = {}
        try:
            if not _blank(f["on_site_t_per_year"]):
                e["on_site_t_per_year"], _ = _num(f["on_site_t_per_year"])
                if not _text(f["on_site_basis"]):
                    rep.add("MISSING", where, stream, "State the basis of the on-site figure.", blocking=True)
                    continue
                e["basis"] = _text(f["on_site_basis"])
            buy = [n for n in ("purchase_unit", "consumption_per_day", "price_eur_per_unit", "price_source")
                   if not _blank(f[n])]
            if buy and len(buy) < 4:
                rep.add("MISSING", where, stream, "A purchase needs unit, daily quantity, price and its source.",
                        blocking=True)
                continue
            if buy:
                unit = _text(f["purchase_unit"])
                if unit not in PURCHASE_UNITS:
                    rep.add("UNSUPPORTED", where, stream, f"Unit must be one of {list(PURCHASE_UNITS)}.", blocking=True)
                    continue
                e.update(unit=unit, consumption_per_day=_num(f["consumption_per_day"])[0],
                         price_eur_per_unit=_num(f["price_eur_per_unit"])[0], source=_text(f["price_source"]))
        except (ValueError, TypeError):
            rep.add("UNSUPPORTED", where, stream, "A quantity or price is not a number.", blocking=True)
            continue
        if not e:
            rep.add("MISSING", where, stream, "Neither an on-site figure nor a purchase.", blocking=True)
            continue
        e["as_of"] = _text(f["as_of"])
        out[stream] = e
        rep.add("ACCEPTED", where, stream, ", ".join(k for k in ("on_site_t_per_year", "unit") if k in e))
    return out


def _read_external(rows, rep) -> list:
    out = []
    for rnum, x in rows:
        where = f"TEA inputs!row {rnum}"
        metric = _text(x["metric"])
        if metric not in EXTERNAL_METRICS:
            rep.add("UNSUPPORTED", where, "external", f"Metric must be one of {list(EXTERNAL_METRICS)}.")
            continue
        if _blank(x["value"]) or not _text(x["author"]) or not _text(x["model_and_date"]):
            rep.add("MISSING", where, metric, "An external result needs its value, author and model/date; "
                    "it was not imported.")
            continue
        try:
            value, _ = _num(x["value"])
        except (ValueError, TypeError):
            rep.add("UNSUPPORTED", where, metric, "The value is not a number.")
            continue
        out.append({"metric": metric, "value": value, "unit": _text(x["unit"]), "author": _text(x["author"]),
                    "model_and_date": _text(x["model_and_date"]), "document": _text(x["document"]),
                    "standing": "EXTERNAL_ASSESSMENT"})
        rep.add("ACCEPTED", where, metric, f"kept as an external assessment by {out[-1]['author']}, not as GEX's figure")
    return out


def line_scopes(catalogue_lines, own_lines, catalogue) -> set:
    return ({catalogue_scope(catalogue[l["equipment_id"]]) for l in catalogue_lines}
            | {l["scope"] for l in own_lines})


def _boundary_checks(boundary, catalogue_lines, own_lines, feeds, catalogue, rep):
    """The control that would have caught v1: what the plant makes, buys, and what its CAPEX covers."""
    present = line_scopes(catalogue_lines, own_lines, catalogue)
    whole = "WHOLE_PLANT" in present

    def answer(k):
        return (boundary.get(k) or {}).get("value")

    for scope in BOUNDARY_SCOPES:
        a = answer(f"scope.{scope.lower()}")
        if a in ("EXCLUDED", "NOT_APPLICABLE") and scope in present:
            rep.add("CONFLICTING", "Cost Basis", f"scope.{scope.lower()}",
                    f"Answered {a}, yet a line has scope {scope}.", issue=True)
        elif a == "INCLUDED" and scope not in present:
            if whole:
                rep.add("CONVERTED", "Cost Basis", f"scope.{scope.lower()}",
                        f"{scope} is INCLUDED in a WHOLE_PLANT aggregate, not priced as its own line.")
            else:
                rep.add("CONFLICTING", "Cost Basis", f"scope.{scope.lower()}",
                        f"Answered INCLUDED, but no line has scope {scope}.", issue=True)
        elif a == "UNKNOWN":
            rep.add("MISSING", "Cost Basis", f"scope.{scope.lower()}",
                    "Not settled: the TEA and every result will say the boundary is open.", issue=True)
    for stream in STREAMS:
        route = answer(f"boundary.{stream}")
        if route is None:
            continue
        scope_answer = answer(f"scope.{STREAM_SCOPE[stream].lower()}")
        if route in ("ON_SITE", "BOTH") and scope_answer in ("EXCLUDED", "NOT_APPLICABLE"):
            rep.add("CONFLICTING", "Cost Basis", f"boundary.{stream}",
                    f"{stream} is made on site, yet the CAPEX excludes {STREAM_SCOPE[stream].lower()}.", issue=True)
        if route in ("PURCHASED", "NOT_USED") and STREAM_SCOPE[stream] in present:
            rep.add("CONFLICTING", "Cost Basis", f"boundary.{stream}",
                    f"{stream} is {route.lower().replace('_', ' ')}, yet a line makes it "
                    f"({STREAM_SCOPE[stream]}).", issue=True)
        f = feeds.get(stream) or {}
        on, buy = "on_site_t_per_year" in f, "unit" in f
        expected = {"ON_SITE": (True, False), "PURCHASED": (False, True), "BOTH": (True, True),
                    "NOT_USED": (False, False)}[route]
        if (on, buy) != expected:
            rep.add("CONFLICTING", "TEA inputs", stream,
                    f"The boundary says {stream} is {route}; the TEA feedstocks give "
                    f"{'on-site' if on else 'no on-site'} supply and {'a' if buy else 'no'} purchase.", issue=True)


def _detail_checks(level, own_lines, rep):
    agg = [l for l in own_lines if l["kind"] == "AGGREGATE"]
    if agg and level == "FINANCING_PREP":
        rep.add("CONFLICTING", "Cost Basis", "detail_level",
                f"FINANCING_PREP with {len(agg)} AGGREGATE line(s): financing preparation needs equipment or "
                "quotes. Lower the detail level or break the aggregate down.", issue=True)
    elif agg:
        rep.add("ACCEPTED", "Cost Basis", "detail_level",
                f"{len(agg)} AGGREGATE line(s): the TEA will be labelled as pricing an aggregate estimate.")
    if level in ("ENGINEERING", "FINANCING_PREP"):
        for l in own_lines:
            if l["kind"] == "QUOTE" and l.get("price_year") is None:
                rep.add("MISSING", "Cost Basis", l["line_ref"], f"{level}: a quote needs its price year.",
                        issue=True)


def _nameplate_check(nameplate, fields, catalogue_lines, catalogue, rep):
    derived = 0.0
    for l in catalogue_lines:
        i = catalogue[l["equipment_id"]]
        if i.molecule_output != fields.get("molecule"):
            continue
        if i.rated_mw > 0 and i.sec_kwh_per_kg > 0:
            derived += i.rated_mw * 8760 * l["quantity"] / i.sec_kwh_per_kg * 1000 / 1000
        else:
            derived += i.capacity_tonnes_year * l["quantity"]
    if derived and abs(derived - nameplate) > 0.01 * nameplate:
        rep.add("CONFLICTING", "Cost Basis", "nameplate_t_per_year",
                f"Stated {nameplate:,.0f} t/yr; the catalogue product lines give {derived:,.0f} t/yr.", issue=True)


# ── the cost basis result from a parsed configuration ─────────────────────────

def compute_result(configuration: dict, catalogue: dict) -> dict:
    """The cost basis result (plant-builder shape) for catalogue lines AND the CFO's own lines.
    Unknown stays unknown: an O&M or insurance not stated is None, not 0."""
    from app.core.plant_builder import PlantConfiguration, get_plant_builder
    cfg = configuration
    lines, installed, om_known, om_unknown, power, water = [], 0.0, 0.0, [], 0.0, 0.0
    if cfg.get("equipment"):
        b = get_plant_builder().build(PlantConfiguration(
            project_id="workbook", molecule=cfg["molecule"], location_jurisdiction=cfg["location_jurisdiction"],
            equipment=cfg["equipment"], power_price_eur_mwh=cfg["power_price_eur_mwh"],
            water_price_eur_m3=cfg.get("water_price_eur_m3") or 0.0, labour_count=cfg["labour_count"],
            labour_cost_eur_year=cfg["labour_cost_eur_year"], insurance_pct_capex=0.0,
            contingency_pct=cfg["contingency_pct"], target_market_price_eur_t=cfg.get("target_market_price_eur_t") or 0,
            wacc_pct=cfg["wacc_pct"], project_life_years=cfg["project_life_years"],
            capacity_factor=cfg["capacity_factor"]))
        for l in b.equipment_lines:
            lines.append({**l, "kind": "CATALOGUE", "scope": catalogue_scope(catalogue[l["equipment_id"]])})
        installed += b.total_installed_eur
        om_known += b.annual_om_eur
        power += b.total_annual_power_mwh
        water += b.total_annual_water_m3
    for l in cfg.get("own_lines") or []:
        lines.append({"equipment_id": l["line_ref"], "name": l.get("description") or l["line_ref"],
                      "category": l["kind"], "kind": l["kind"], "scope": l["scope"], "quantity": l["quantity"],
                      "installed_cost_eur": l["installed_cost_eur"], "annual_om_eur": l.get("annual_om_eur"),
                      "annual_power_mwh": l.get("annual_power_mwh"), "price_year": l.get("price_year"),
                      "estimate_class": l.get("estimate_class"), "source": l.get("source"),
                      "annual_output_tonnes": 0})
        installed += l["installed_cost_eur"]
        if l.get("annual_om_eur") is None:
            om_unknown.append(l["line_ref"])
        else:
            om_known += l["annual_om_eur"]
        power += l.get("annual_power_mwh") or 0.0
    contingency = installed * cfg["contingency_pct"]
    capex = installed + contingency
    om = None if om_unknown else om_known
    insurance = capex * cfg["insurance_pct_capex"] if cfg.get("insurance_pct_capex") is not None else None
    power_eur = power * cfg["power_price_eur_mwh"]
    water_eur = water * (cfg.get("water_price_eur_m3") or 0.0)
    labour = cfg["labour_count"] * cfg["labour_cost_eur_year"]
    known_opex = om_known + power_eur + water_eur + labour + (insurance or 0.0)
    return {
        "capex": {"total_installed_eur": round(installed), "contingency_eur": round(contingency),
                  "total_capex_eur": round(capex)},
        "opex": {"annual_om_eur": None if om is None else round(om), "annual_om_known_eur": round(om_known),
                 "om_unknown_lines": om_unknown, "annual_power_eur": round(power_eur),
                 "annual_water_eur": round(water_eur), "annual_labour_eur": round(labour),
                 "annual_insurance_eur": None if insurance is None else round(insurance),
                 "total_annual_opex_eur": round(known_opex),
                 "opex_complete": not om_unknown and insurance is not None},
        "output": {"annual_output_tonnes": 0, "total_annual_power_mwh": round(power),
                   "total_annual_water_m3": round(water)},
        "equipment_lines": lines,
        "basis": "WORKBOOK",
    }


def versus_current(current: Optional[dict], configuration: dict) -> dict:
    """What an amended workbook changes against the latest saved cost basis."""
    if not current:
        return {"current_version": None, "changes": [], "detail": "No cost basis yet: this would be version 1."}
    old = current["configuration"]
    changes = []
    for f in PROJECT_FIELDS:
        a = (old.get("stated_nameplate") or {}).get("value") if f.key == "nameplate_t_per_year" else old.get(f.key)
        b = (configuration.get("stated_nameplate") or {}).get("value") if f.key == "nameplate_t_per_year" \
            else configuration.get(f.key)
        if a != b:
            changes.append({"field": f.key, "from": a, "to": b})
    for k in ("plant_boundary", ):
        if (old.get(k) or {}) != (configuration.get(k) or {}):
            changes.append({"field": k, "from": old.get(k), "to": configuration.get(k)})

    def keyed(cfg):
        out = {f"{e['equipment_id']} x{e.get('quantity', 1)}": e for e in cfg.get("equipment") or []}
        out.update({l["line_ref"]: l for l in cfg.get("own_lines") or []})
        return out
    a, b = keyed(old), keyed(configuration)
    for k in sorted(set(a) | set(b)):
        if k not in b:
            changes.append({"field": f"line {k}", "from": "present", "to": "removed"})
        elif k not in a:
            changes.append({"field": f"line {k}", "from": None, "to": "added"})
        elif {x: y for x, y in a[k].items() if x != "source"} != {x: y for x, y in b[k].items() if x != "source"}:
            changes.append({"field": f"line {k}", "from": a[k], "to": b[k]})
    return {"current_version": current["version_number"], "current_sha256": current["content_sha256"],
            "changes": changes, "unchanged": not changes}


def _default_standing(d: dict) -> str:
    """What applied the value: OpenPyTEA's own default, the caller's stated value, or a rename."""
    basis = str(d.get("basis") or "")
    if basis.startswith("RENAMED"):
        return "TRANSLATED"
    if basis.startswith("STATED"):
        return "STATED"
    return "OPENPYTEA_DEFAULT"


# ── export: the published TEA case ─────────────────────────────────────────────

def export_tea(catalogue: dict, *, project_id: str, project_name: str, cost_basis: dict, base_case: dict,
               checks: list[dict], generated_by: Optional[str]) -> bytes:
    """A frozen record of one TEA run on one saved cost basis. Values only."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(template(catalogue, project_id=project_id, project_name=project_name,
                                           cost_basis=cost_basis, base_case=base_case)))
    s = _styles()
    ti = base_case.get("tea_inputs") or {}
    readme = wb["Read me"]
    readme.delete_rows(1, readme.max_row)
    notes = [
        ("GEX published TEA case: a frozen record", s["title"]),
        (f"Project {project_id} {project_name}".strip(), None),
        (f"TEA run {base_case['claim_id']}, state {base_case.get('state')}, review "
         f"{base_case.get('review_basis') or 'none'}", None),
        (f"Cost basis v{cost_basis['version_number']}, sha256 {cost_basis['content_sha256']}", None),
        (f"Engine {base_case.get('engine')} {base_case.get('engine_version') or ''}; generated "
         f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} for {generated_by or 'unknown'}", None),
        ("", None),
        ("What this workbook is", s["h"]),
        ("It records the inputs, the results, the OpenPyTEA defaults still applied, the feedstock balance and the "
         "checks of this run. It does NOT recalculate: the figures come from GEX's TEA engine. Changing a cell "
         "here changes no result.", None),
        ("'Cost Basis' and 'TEA inputs' are in the upload template's layout: amend them and upload the file to "
         "save the next cost basis version; GEX then runs a new TEA.", None),
        ("'OpenPyTEA config' is the exact config the engine received: give it to OpenPyTEA "
         "(Equipment(**item) for each equipment, then Plant(config).calculate_all()) to reproduce the run. "
         "Money is in the cost basis currency (EUR).", None),
        ("The first sheets are the TEA report, in the order of the screen: Report (headline, cost per kg, "
         "Gabillon market reference), Capital, Operating costs, Cost by year, Sensitivity, Index band (Gabillon) "
         "and Gabillon price. Every figure carries its unit, standing (CALCULATED, STATED, DEFAULT, MODEL) and "
         "basis. The report reference on each sheet is the screen's: the same reference, the same figures.", None),
    ]
    for r, (t, font) in enumerate(notes, 1):
        c = readme.cell(r, 1, t)
        if font:
            c.font = font

    def sheet(title, headers, rows):
        ws = wb.create_sheet(title)
        for col, h in enumerate(headers, 1):
            c = ws.cell(1, col, h)
            c.font, c.fill = s["head"], s["headfill"]
        for r, row in enumerate(rows, 2):
            for col, v in enumerate(row, 1):
                ws.cell(r, col, v if not isinstance(v, (dict, list)) else json.dumps(v))
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[chr(64 + col)].width = 28 if col > 1 else 40
        return ws

    res = cost_basis["result"]
    sheet("TEA results", ("Figure", "Value", "Unit", "Standing"), [
        ("Fixed capital (TEA)", base_case.get("capex_eur"), "EUR", "CALCULATED by GEX's TEA engine"),
        ("Operating cost per year (TEA)", base_case.get("opex_eur_per_year"), "EUR/yr", "CALCULATED"),
        ("Levelised cost of product (TEA)", base_case.get("lcop"), "EUR/kg", "CALCULATED"),
        ("Nameplate", base_case.get("nameplate_capacity"), base_case.get("nameplate_unit"), "FROM THE COST BASIS"),
        ("Result status", base_case.get("result_status"), "", ""),
        ("Calculation boundary", (ti.get("calculation_boundary") or {}).get("basis"), "", ""),
        ("CAPEX in the cost basis", res["capex"]["total_capex_eur"], "EUR", "ENTERED / CATALOGUE"),
        ("OPEX in the cost basis", res["opex"]["total_annual_opex_eur"], "EUR/yr",
         "ENTERED / CATALOGUE" + ("" if res["opex"].get("opex_complete", True) else " (incomplete: unknowns left out)")),
        ("Reviewed by (company)", base_case.get("reviewed_by_company"), "", base_case.get("review_basis")),
        ("Review conditions", base_case.get("review_conditions"), "", ""),
    ])
    sheet("Cost lines", ("Line", "Kind", "Scope", "Description", "Quantity", "Installed cost (EUR)",
                         "O&M per year (EUR)", "Power (MWh/yr)", "Price year", "Estimate class", "Source"),
          [(l["equipment_id"], l.get("kind", "CATALOGUE"), l.get("scope"), l.get("name"), l.get("quantity"),
            l.get("installed_cost_eur"), l.get("annual_om_eur"), l.get("annual_power_mwh"), l.get("price_year"),
            l.get("estimate_class"), l.get("source") or "GEX catalogue")
           for l in res.get("equipment_lines", [])])
    sheet("Defaults used", ("Name", "Value", "Basis", "Standing"),
          [(d["name"], d.get("value"), d.get("basis"), _default_standing(d)) for d in ti.get("defaults_used") or []])
    sheet("Feedstock balance", ("Feedstock", "Status", "Required (t/yr)", "On site (t/yr)", "Bought (t/yr)",
                                "Shortfall (t/yr)", "Detail"),
          [(f.get("feedstock"), f.get("status"), f.get("required_t_per_year"), f.get("on_site_t_per_year"),
            f.get("purchased_t_per_year"), f.get("shortfall_t_per_year"), f.get("detail") or f.get("on_site_basis"))
           for f in ti.get("feedstock_balance") or []])
    sheet("Checks", ("Check", "Result", "Detail"),
          [(c["check"], c["result"], c.get("detail")) for c in checks])
    sheet("External vs GEX", ("Metric", "External value", "Unit", "Author", "Model / date", "GEX value",
                              "Difference", "Note"),
          [(x["metric"], x["value"], x.get("unit"), x["author"], x["model_and_date"],
            base_case.get(GEX_FOR_EXTERNAL.get(x["metric"], "")),
            (base_case.get(GEX_FOR_EXTERNAL[x["metric"]]) - x["value"])
            if x["metric"] in GEX_FOR_EXTERNAL and base_case.get(GEX_FOR_EXTERNAL[x["metric"]]) is not None else None,
            "Reported for reconciliation; no tolerance agreed. The external figure is the author's, not GEX's.")
           for x in ((cost_basis["configuration"].get("workbook") or {}).get("external") or [])])
    cfg = ti.get("openpytea_config")
    ws = sheet("OpenPyTEA config", ("Equipment", "Purchased cost", "Cost year", "Category"),
               [(e.get("name"), e.get("purchased_cost"), e.get("cost_year"), e.get("category"))
                for e in (cfg or {}).get("equipment", [])])
    ws.cell(1, 6, "Exact config (JSON)").font = s["h"]
    ws.cell(2, 6, json.dumps(cfg, indent=1) if cfg else "No config recorded for this run.").alignment = s["wrap"]
    ws.column_dimensions["F"].width = 90
    from app.core import tea_report_workbook
    tea_report_workbook.write(wb, base_case, cost_basis, project_id, project_name)
    wb.active = 0
    return _save(wb)
