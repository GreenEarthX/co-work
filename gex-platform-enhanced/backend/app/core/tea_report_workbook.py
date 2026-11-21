"""The TEA report sheets of the exported workbook (20 Nov 2026).

The same content, in the same order, as the results view on the Calculation chain
(TeaRunReport.tsx): Report, Capital, Operating costs, Cost by year, Sensitivity, Index band
(Gabillon), Gabillon price. Values only, read from the run's record: no formula, nothing
recomputed, so the workbook carries the report reference of the screen.

House style (docs/GEX_UI_Reform_Project_Edit.md): dense tables, a unit on every figure, a
basis on every factor, a standing on every value (CALCULATED, STATED, DEFAULT, MODEL), no
adjectives, no verdicts. One header style, one number format per kind of figure.
"""
from __future__ import annotations

from typing import Any, Optional

INK, MUTED, RULE, HEAD = "1F2937", "6B7280", "D1D5DB", "2F5D50"
M_FMT, KG_FMT, INT_FMT, PCT_FMT, F4_FMT = '#,##0.00', '0.000', '#,##0', '0.0%', '0.0000'

OPEX_LABEL = {
    "operating_labor": "Operating labour", "supervision": "Supervision",
    "direct_salary_overhead": "Direct salary overhead", "laboratory_charges": "Laboratory",
    "maintenance": "Maintenance", "taxes_insurance": "Taxes and insurance", "rent_of_land": "Rent of land",
    "environmental_charges": "Environmental charges", "operating_supplies": "Operating supplies",
    "general_plant_overhead": "General plant overhead", "interest_working_capital": "Interest on working capital",
    "patents_royalties": "Patents and royalties", "distribution_selling": "Distribution and selling",
    "rnd": "Research and development",
}
_DEFAULT_NAME = {"interest_working_capital": "working_capital_interest"}
_COMPONENT_STATED = {"supervision": "supervision_costs", "maintenance": "maintenance_costs",
                     "taxes_insurance": "taxes_insurance_costs", "rent_of_land": "rent_of_land_costs",
                     "distribution_selling": "distribution_selling_costs", "rnd": "RnD_costs"}


class _Sheet:
    """A sheet written top to bottom: title, status line, blocks of tables, footnotes."""

    def __init__(self, wb, title: str, widths: tuple, index: Optional[int] = None):
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        self.ws = wb.create_sheet(title, index)
        self.ws.sheet_view.showGridLines = False
        for i, w in enumerate(widths):
            self.ws.column_dimensions[chr(65 + i)].width = w
        self.r = 1
        self.f = {"title": Font(name="Arial", bold=True, size=12, color=INK),
                  "line": Font(name="Arial", size=8, color=MUTED),
                  "block": Font(name="Arial", bold=True, size=9, color=INK),
                  "head": Font(name="Arial", bold=True, size=8, color="FFFFFF"),
                  "cell": Font(name="Arial", size=9, color=INK),
                  "bold": Font(name="Arial", size=9, bold=True, color=INK),
                  "foot": Font(name="Arial", size=8, italic=True, color=MUTED)}
        self.fill = PatternFill("solid", fgColor=HEAD)
        self.rule = Border(bottom=Side(style="thin", color=RULE))
        self.top = Border(top=Side(style="thin", color=INK))
        self.wrap = Alignment(wrap_text=True, vertical="top")
        self.right = Alignment(horizontal="right", vertical="top")

    def title(self, text: str, line: str = "") -> None:
        self.ws.cell(self.r, 1, text).font = self.f["title"]
        self.r += 1
        if line:
            self.ws.cell(self.r, 1, line).font = self.f["line"]
            self.r += 1
        self.r += 1

    def block(self, text: str) -> None:
        self.ws.cell(self.r, 1, text.upper()).font = self.f["block"]
        self.r += 1

    def table(self, headers: tuple, rows: list[tuple], fmts: tuple = (), *, total_last: bool = False) -> None:
        for c, h in enumerate(headers, 1):
            cell = self.ws.cell(self.r, c, h)
            cell.font, cell.fill = self.f["head"], self.fill
            if fmts and c - 1 < len(fmts) and fmts[c - 1]:
                cell.alignment = self.right
        self.r += 1
        for i, row in enumerate(rows):
            last = total_last and i == len(rows) - 1
            for c, v in enumerate(row, 1):
                cell = self.ws.cell(self.r, c, v)
                cell.font = self.f["bold"] if last else self.f["cell"]
                cell.border = self.top if last else self.rule
                fmt = fmts[c - 1] if fmts and c - 1 < len(fmts) else None
                if fmt and isinstance(v, (int, float)):
                    cell.number_format, cell.alignment = fmt, self.right
                else:
                    cell.alignment = self.wrap
            self.r += 1
        self.r += 1

    def foot(self, *lines: str) -> None:
        for t in lines:
            self.ws.cell(self.r, 1, t).font = self.f["foot"]
            self.r += 1
        self.r += 1


def _mn(v) -> Optional[float]:
    return None if v is None else v / 1e6


def _default(defaults: list, name: str) -> Optional[dict]:
    return next((d for d in defaults if d.get("name") == name), None)


def _factor_basis(defaults: list, name: str, stated: Optional[str] = None) -> tuple[str, str]:
    d = _default(defaults, name)
    if d:
        return "DEFAULT", f"{d.get('basis')} (OpenPyTEA default {d.get('value')})"
    return "STATED", stated or "Stated on the cost basis"


def _state_word(base: dict) -> str:
    if base.get("state") == "verified" and base.get("review_basis") == "INDEPENDENT":
        return "CONFIRMED (independent review)"
    if base.get("state") == "verified":
        return "SUBMITTED (owner's internal review; not independent)"
    if base.get("state") == "superseded":
        return "SUPERSEDED"
    return "SUBMITTED (not independently reviewed)"


def write(wb, base: dict, cost_basis: dict, project_id: str, project_name: str) -> None:
    """Insert the report sheets at the front of the workbook. A run made before results were
    recorded with each run gets one sheet saying so, and nothing invented."""
    ti = base.get("tea_inputs") or {}
    a = ti.get("analysis") or {}
    bd = a.get("breakdown")
    report = base.get("report") or {}
    inputs = base.get("inputs_now") or {}
    defaults = ti.get("defaults_used") or []
    req = ti.get("request") or {}
    q = req.get("quote_plant") or {}
    s = _Sheet(wb, "Report", (34, 16, 12, 16, 70), 0)
    cb = a.get("cost_basis") or {}
    s.title(f"TEA report  {report.get('ref', base.get('claim_id'))}",
            "  ·  ".join(x for x in (f"{project_name or project_id}", f"{base.get('engine')} {base.get('engine_version') or ''}".strip(),
                                     cb.get("cepci_basis") or (f"cost year {cb.get('cost_year')}" if cb.get("cost_year") else ""),
                                     (bd or {}).get("currency", ""), _state_word(base)) if x))
    s.block("Record")
    s.table(("Item", "Value", "", "", "Basis"), [
        ("Report reference", report.get("ref"), None, None, report.get("basis")),
        ("Report sha256", report.get("sha256"), None, None, "Over the stored run and its inputs; the review is not part of it"),
        ("TEA run", base.get("claim_id"), None, None, f"Run {str(base.get('created_at'))[:16]} by {base.get('run_by')}"),
        ("Standing", _state_word(base), None, None, base.get("review_conditions") or ""),
        ("Cost basis", f"v{cost_basis.get('version_number')}", None, None, f"sha256 {cost_basis.get('content_sha256')}"),
        ("Engine", f"{base.get('engine')} {base.get('engine_version') or ''}", None, None, "OpenPyTEA, the open-source TEA engine GEX runs"),
    ])
    if inputs.get("checks"):
        word = {True: "Inputs unchanged since this run", False: "Inputs changed since this run"}.get(
            inputs.get("unchanged"), "Inputs not fully checked")
        s.block(f"Inputs now: {word}")
        s.table(("Check", "Result", "", "", "Detail"),
                [(c["check"], c["result"], None, None, c.get("detail")) for c in inputs["checks"]])
    if not bd:
        s.foot("This run was made before results were recorded with each run (20 Nov 2026): only its headline "
               "figures exist. Run the TEA again from the same cost basis for the full report.")
        return
    ccy = bd["currency"]
    cap, pk = bd["capital_costs"], bd["per_kg"]
    lcop = base.get("lcop")
    s.block("Headline")
    s.table(("Figure", "Value", "Unit", "Standing", "Basis"), [
        ("Required price (LCOP)", lcop, f"{ccy}/kg", "CALCULATED",
         f"Discounted cost ÷ discounted output at {bd['discount_rate']:.1%}; pre-tax, unfinanced"),
        ("Fixed capital", _mn(cap["fixed_capital"]), f"M {ccy}", "CALCULATED", "ISBL + OSBL + D&E + contingency (Capital)"),
        ("Working capital", _mn(cap["working_capital"]), f"M {ccy}", "CALCULATED", "Not in fixed capital; returned in the last year"),
        ("Operating cost, full output", _mn(bd["variable_opex"]["total"] + bd["fixed_opex"]["total"]), f"M {ccy}/yr",
         "CALCULATED", "Variable + fixed (Operating costs)"),
        ("Output, full rate", bd["production_kg_per_year_full"] / 1000, "t/yr", "STATED",
         f"Nameplate × utilisation {bd['plant_utilization']:.2f}"),
        ("Operating life", bd["project_lifetime"], "years", "STATED", "Including construction"),
    ], ("", KG_FMT, "", "", ""))
    # the Headline column B holds mixed kinds: format each figure by its unit
    var = pk.get("variable") or {}
    fixed = pk.get("fixed") or {}
    vt, ft = sum(var.values()), sum(fixed.values())
    rows = [("Capital (fixed + working, discounted)", pk["capital"], pk["capital"] / lcop if lcop else None)]
    rows += [(f"   {k}", v, v / lcop if lcop else None) for k, v in var.items()]
    rows += [("Variable, total", vt, vt / lcop if lcop else None),
             ("Fixed operating", ft, ft / lcop if lcop else None)]
    if pk.get("by_product_credit"):
        rows.append(("By-product credit", pk["by_product_credit"], pk["by_product_credit"] / lcop if lcop else None))
    rows.append(("LCOP", pk["levelized_cost"], 1.0))
    s.block("Cost per kg")
    kg_head = s.r
    s.table((f"Part", f"{ccy}/kg", "Share", "", ""), rows, ("", KG_FMT, PCT_FMT), total_last=True)
    parts = [("Capital", pk["capital"])] + list(var.items()) + [("Fixed operating", ft)]
    if pk.get("by_product_credit"):
        parts.append(("By-product credit", pk["by_product_credit"]))
    _chart_cost_per_kg(s.ws, kg_head, parts, ccy)
    s.foot(f"{bd.get('note') or ''} The parts add back to the LCOP (difference "
           f"{0 if abs(pk.get('check') or 0) < 5e-7 else pk['check']:.6f}).")
    mr = a.get("market_reference") or {}
    s.block("Market reference: Gabillon (PF engine)")
    if mr.get("applies"):
        s.table(("Figure", "Value", "Unit", "Standing", "Basis"), [
            ("Required price, this run", lcop, "EUR/kg", "CALCULATED", "LCOP"),
            ("Gabillon price, levelised (real)", mr["levelised_price"], "EUR/kg", f"MODEL · {mr['calibration_status']}",
             mr["basis"]),
            ("Difference", mr.get("difference"), "EUR/kg", "CALCULATED", "Required price − Gabillon price"),
            ("Gabillon spot", mr["spot"], "EUR/kg", f"MODEL · {mr['calibration_status']}", f"{mr['molecule']}"),
            ("Long-run equilibrium (e^μ)", mr["long_term_equilibrium"], "EUR/kg", f"MODEL · {mr['calibration_status']}",
             f"Mean-reversion half-life {mr.get('half_life_months')} months"),
            ("Capex floor", mr["capex_floor"], "EUR/kg", f"MODEL · {mr['calibration_status']}", "Gabillon parameter"),
        ], ("", KG_FMT))
        s.foot(mr["standing"], f"Calibrated {mr.get('last_calibrated')}, {mr.get('n_observations')} observations. "
               "Year by year on 'Gabillon price'.")
    else:
        s.foot(f"Not compared: {mr.get('reason') or 'not recorded for this run.'}")
    _fmt_headline(s)

    # ── Capital ──
    c = _Sheet(wb, "Capital", (34, 30, 10, 16, 18, 60), 1)
    c.title(f"Capital  {report.get('ref', '')}", f"M {ccy}; cost base {bd['equipment'][0].get('target_year') if bd['equipment'] else ''}")
    quotes = {e.get("name"): e for e in q.get("equipment") or []}
    lines = [(e["name"], (quotes.get(e["name"]) or {}).get("source") or e.get("category"), e.get("cost_year"),
              _mn((quotes.get(e["name"]) or {}).get("installed_cost")), _mn(e["direct_cost"]), "")
             for e in bd["equipment"]]
    lines.append(("Lines, total", None, None, None, _mn(sum(e["direct_cost"] for e in bd["equipment"])), ""))
    c.block("Lines")
    c.table(("Line", "Source", "Price year", f"Quote, M {ccy}", f"At cost base, M {ccy}", ""), lines,
            ("", "", "0", M_FMT, M_FMT), total_last=True)
    isbl_osbl = cap["isbl"] + cap["osbl"]
    ob = _factor_basis(defaults, "openpytea.osbl_factor", f"STATED: {q['osbl_factor_basis']}" if q.get("osbl_factor_basis") else None)
    de = _factor_basis(defaults, "openpytea.de_factor")
    co = _factor_basis(defaults, "openpytea.contingency_factor")
    wc = _factor_basis(defaults, "openpytea.working_capital")
    c.block("Build-up")
    c.table(("Item", f"M {ccy}", "Factor", "Of", "Standing", "Basis"), [
        ("ISBL", _mn(cap["isbl"]), bd.get("location_factor") or 1.0, "lines", "STATED",
         "Lines × location factor" + (f" ({q['loc_factor_basis']})" if q.get("loc_factor_basis") else "")
         + ("; quotes taken as installed, no install factors" if q else "")),
        ("OSBL", _mn(cap["osbl"]), cap["osbl"] / cap["isbl"] if cap["isbl"] else None, "ISBL", ob[0], ob[1]),
        ("Design and engineering", _mn(cap["design_and_engineering"]),
         cap["design_and_engineering"] / isbl_osbl if isbl_osbl else None, "ISBL+OSBL", de[0], de[1]),
        ("Contingency", _mn(cap["contingency"]), cap["contingency"] / isbl_osbl if isbl_osbl else None,
         "ISBL+OSBL", co[0], co[1]),
        ("Fixed capital", _mn(cap["fixed_capital"]), None, None, "CALCULATED", ""),
    ], ("", M_FMT, '0.00', "", "", ""), total_last=True)
    c.table(("Item", f"M {ccy}", "Factor", "Of", "Standing", "Basis"), [
        ("Working capital", _mn(cap["working_capital"]),
         cap["working_capital"] / cap["fixed_capital"] if cap["fixed_capital"] else None, "fixed capital", wc[0],
         wc[1] + "; not in fixed capital")], ("", M_FMT, '0.00'))
    c.foot("Fixed capital is the plant, not the funding requirement: interest during construction, financing fees, "
           "development and owner's costs and reserves are sized in the financing case.")

    # ── Operating costs ──
    o = _Sheet(wb, "Operating costs", (34, 14, 12, 12, 16, 60), 2)
    o.title(f"Operating costs  {report.get('ref', '')}", f"M {ccy}/yr at full output")
    streams = q.get("variable_opex") or {}
    vrows = [(k, (streams.get(k) or {}).get("consumption"), (streams.get(k) or {}).get("unit"),
              (streams.get(k) or {}).get("price"), _mn(v), (streams.get(k) or {}).get("source") or "")
             for k, v in bd["variable_opex"]["streams"].items()]
    vrows.append(("Variable, at full output", None, None, None, _mn(bd["variable_opex"]["total"]), ""))
    o.block("Variable inputs")
    o.table(("Input", "Per day", "Unit", f"Price, {ccy}", f"M {ccy}/yr", "Source"), vrows,
            ("", '#,##0.0', "", '#,##0.00', M_FMT), total_last=True)
    stated = q.get("fixed_opex_components") or {}
    frows, on_cap = [], 0.0
    for k, v in bd["fixed_opex"]["components"].items():
        d = _default(defaults, f"openpytea.{_DEFAULT_NAME.get(k, k)}")
        if k == "operating_labor" and q.get("operators_hired"):
            standing, basis = "STATED", f"{q['operators_hired']} operators × {q.get('operator_hourly_rate', 0):.2f} {ccy}/h"
        elif stated.get(_COMPONENT_STATED.get(k, k)) is not None:
            standing, basis = "STATED", "Stated on the cost basis"
        elif d:
            standing, basis = "DEFAULT", f"{d.get('value')} {d.get('basis')} (OpenPyTEA default)"
        else:
            standing, basis = "", ""
        capital_driven = bool(d) and any(w in str(d.get("basis")) for w in ("ISBL", "OSBL"))
        on_cap += v if capital_driven else 0.0
        frows.append((OPEX_LABEL.get(k, k) + (" †" if capital_driven else ""), _mn(v), standing, None, None, basis))
    frows.append(("Fixed, per year in production", _mn(bd["fixed_opex"]["total"]), "CALCULATED", None, None, ""))
    o.block("Fixed costs")
    o.table(("Cost", f"M {ccy}/yr", "Standing", "", "", "Basis"), frows, ("", M_FMT), total_last=True)
    total_fixed = bd["fixed_opex"]["total"] or 1.0
    o.foot(f"† Set as a percentage of capital: {on_cap / 1e6:,.2f} M {ccy}/yr, {on_cap / total_fixed:.0%} of fixed cost. "
           "These move with the capital estimate; state the real figure on the cost basis to replace a default.")

    # ── Cost by year ──
    y = _Sheet(wb, "Cost by year", (8, 14, 14, 14, 14, 14, 14, 14), 3)
    y.title(f"Cost by year  {report.get('ref', '')}", f"M {ccy}; constant {cb.get('cost_year') or ''} money, pre-tax, unfinanced")
    ys = bd["years"]
    yrows = [(r["year"], r["production_kg"] / 1000, _mn(r["capital"]), _mn(r["fixed_opex"]), _mn(r["variable_opex"]),
              _mn(-r["by_product_revenue"]), _mn(r["cost"]), r["discount_factor"]) for r in ys]
    dc = sum(r["cost"] * r["discount_factor"] for r in ys)
    dq = sum(r["production_kg"] * r["discount_factor"] for r in ys)
    yr_head = y.r
    y.table(("Year", "Output, t", "Capital", "Fixed", "Variable", "By-product", "Cost", "Discount factor"), yrows,
            (INT_FMT, INT_FMT, M_FMT, M_FMT, M_FMT, M_FMT, M_FMT, F4_FMT))
    y.foot(f"Discounted cost {dc / 1e6:,.2f} M {ccy} ÷ discounted output {dq / 1000:,.0f} t = "
           f"{dc / dq if dq else 0:.3f} {ccy}/kg (the LCOP). Revenue, tax and debt are the financing case's.")
    y.ws.freeze_panes = "B4"
    _chart_cost_by_year(y.ws, yr_head, len(yrows), ccy)

    # ── Sensitivity ──
    t = _Sheet(wb, "Sensitivity", (30, 14, 14, 14, 12, 12, 12, 50), 4)
    sv = a.get("sensitivity") or {}
    t.title(f"Sensitivity  {report.get('ref', '')}", f"Required price, {ccy}/kg; each lever moved alone, every point a full run")
    if sv.get("tornado"):
        trows = []
        for r in sv["tornado"]:
            big = abs(r.get("base_input") or 0) >= 1e5
            f = (lambda x: _mn(x)) if big else (lambda x: x)
            trows.append((r.get("label") or r["parameter"], f(r.get("base_input")), f(r.get("low_input")),
                          f(r.get("high_input")), (f"M {r.get('unit')}" if big else r.get("unit") or ""),
                          r["low_lcop"], r["high_lcop"], r.get("range_basis") or ""))
        t.table(("Lever", "Base", "Low", "High", "Unit", "LCOP low", "LCOP high", "Range basis"), trows,
                ("", '#,##0.00', '#,##0.00', '#,##0.00', "", KG_FMT, KG_FMT))
        t.foot("Ranges are screening conventions until a governed range exists. The cost-index range is Gabillon's "
               "('Index band'); electricity has no Gabillon range because power is not storable.")
    else:
        t.foot(f"Not recorded for this run{': ' + sv['error'] if sv.get('error') else ''}.")

    # ── Index band (Gabillon) ──
    ib = a.get("index_band") or {}
    g = _Sheet(wb, "Index band", (26, 14, 14, 14, 40), 5)
    g.title(f"Index band (Gabillon)  {report.get('ref', '')}", ib.get("method") or "")
    if ib.get("applies"):
        g.block("CEPCI forward, approved rows")
        g.table(("Year", "CEPCI 5%", "Expected", "CEPCI 95%", "Approved row"),
                [(int(k), v.get("low"), v.get("value"), v.get("high"), str(v.get("ref_id"))[:8])
                 for k, v in (ib.get("years") or {}).items()], ("0", '#,##0.0', '#,##0.0', '#,##0.0'))
        g.block("Plant at the band")
        g.table(("Case", f"Fixed capital, M {ccy}", f"LCOP, {ccy}/kg", "", ""), [
            ("Index at 5%", _mn(ib["index_low"]["fixed_capital"]), ib["index_low"]["lcop"], None, None),
            ("Expected (this run)", _mn(ib["base"]["fixed_capital"]), ib["base"]["lcop"], None, None),
            ("Index at 95%", _mn(ib["index_high"]["fixed_capital"]), ib["index_high"]["lcop"], None, None),
        ], ("", M_FMT, KG_FMT))
        if ib["index_low"]["fixed_capital"] == ib["base"]["fixed_capital"] == ib["index_high"]["fixed_capital"]:
            g.foot("No line is priced before the cost-base year, so the index moves nothing: the band is zero. "
                   "A line whose real price year is earlier must state it, or this band understates the uncertainty.")
    else:
        g.foot(ib.get("reason") or ib.get("error") or "Not recorded for this run.")
    if ib.get("not_covered"):
        g.block("Not in this band")
        g.table(("Item", "", "", "", ""), [(n, None, None, None, None) for n in ib["not_covered"]])

    # ── Gabillon price by year ──
    if mr.get("applies"):
        p = _Sheet(wb, "Gabillon price", (10, 14, 16, 16, 16, 16), 6)
        p.title(f"Gabillon price  {mr['molecule']}", f"EUR/kg; {mr['standing']}")
        prod = {r["year"]: r for r in ys}
        g_head = p.r
        p.table(("Year", "Operating year", "Nominal", "Real", "Output, t", "Required price"),
                [(r["year"], r["operating_year"], r["price_nominal"], r["price_real"],
                  prod.get(r["year"], {}).get("production_kg", 0) / 1000, lcop) for r in mr["years"]],
                (INT_FMT, INT_FMT, KG_FMT, KG_FMT, INT_FMT, KG_FMT))
        p.foot(mr["basis"], "Required price = this run's LCOP, the same every year.")
        _chart_gabillon(p.ws, g_head, len(mr["years"]), mr)


# ── The three graphs, as native Excel charts on the cells beside them (21 Nov 2026) ──
# The same three as the screen (TeaCharts.tsx). Each reads the sheet's own cells, so a reader
# sees the figures it is drawn from; nothing is computed in the chart.

def _style(ch, title: str, y_title: str, x_title: Optional[str] = None):
    ch.title, ch.y_axis.title = title, y_title
    if x_title:
        ch.x_axis.title = x_title
    ch.height, ch.width = 7.5, 17
    ch.legend.position = "b"
    return ch


def _chart_cost_per_kg(ws, head: int, parts: list, ccy: str) -> None:
    """The parts that add up to the required price (no subtotal), written in columns K:L as the
    chart's own source cells, then drawn as one bar per part."""
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Font
    ws.cell(head, 11, "Chart data: parts").font = Font(name="Arial", size=8, bold=True)
    ws.cell(head, 12, f"{ccy}/kg").font = Font(name="Arial", size=8, bold=True)
    for i, (k, v) in enumerate(parts, 1):
        ws.cell(head + i, 11, k).font = Font(name="Arial", size=8)
        c = ws.cell(head + i, 12, v)
        c.font, c.number_format = Font(name="Arial", size=8), KG_FMT
    n = len(parts)
    ch = _style(BarChart(), "Where the required price comes from", f"{ccy}/kg")
    ch.type = "bar"
    ch.add_data(Reference(ws, min_col=12, min_row=head, max_row=head + n), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=11, min_row=head + 1, max_row=head + n))
    ch.y_axis.numFmt = KG_FMT
    ch.series[0].graphicalProperties.solidFill = "475569"
    ch.legend = None
    ws.add_chart(ch, f"G{head + n + 2}")


def _chart_cost_by_year(ws, head: int, n: int, ccy: str) -> None:
    from openpyxl.chart import BarChart, Reference
    ch = _style(BarChart(), "Cost by year", f"M {ccy}", "Year")
    ch.type, ch.grouping, ch.overlap = "col", "stacked", 100
    ch.add_data(Reference(ws, min_col=3, max_col=5, min_row=head, max_row=head + n), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=head + 1, max_row=head + n))
    for sr, colour in zip(ch.series, ("1E293B", "64748B", "94A3B8")):
        sr.graphicalProperties.solidFill = colour
    ws.add_chart(ch, f"J{head}")


def _chart_gabillon(ws, head: int, n: int, mr: dict) -> None:
    from openpyxl.chart import LineChart, Reference
    ch = _style(LineChart(), f"Gabillon {mr['molecule']} against the required price ({mr['calibration_status']})",
                "EUR/kg", "Operating year")
    for col in (3, 4, 6):
        ch.add_data(Reference(ws, min_col=col, min_row=head, max_row=head + n), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=2, min_row=head + 1, max_row=head + n))
    for sr, colour in zip(ch.series, ("94A3B8", "1E293B", "B45309")):
        sr.graphicalProperties.line.solidFill = colour
        sr.smooth = False
    ws.add_chart(ch, f"H{head}")


def _fmt_headline(s: _Sheet) -> None:
    """Column B of the Report sheet mixes EUR/kg, M EUR, t and years: one format per unit."""
    by_unit = {"EUR/kg": KG_FMT, "t/yr": INT_FMT, "years": "0"}
    for row in s.ws.iter_rows(min_row=1, max_row=s.ws.max_row):
        unit = row[2].value if len(row) > 2 else None
        v = row[1]
        if isinstance(v.value, (int, float)) and isinstance(unit, str):
            v.number_format = by_unit.get(unit, KG_FMT if unit.endswith("/kg") else M_FMT)
