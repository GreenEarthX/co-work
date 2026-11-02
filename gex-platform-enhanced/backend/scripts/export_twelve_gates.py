"""
Generate "The Twelve Bankability Gates" at the current evidence rules (JML, 2026-10-30).

The same document, in the same format, as the 26 September 2026 edition (rules 3.0.0),
brought up to the running rules. What the engine knows — gates, items, severity, maturity,
owners, applicability, commitment ladders, coherence checks, reviewer roles, states, capital
decisions — is read from the engine and the platform, never typed. What only a person can
say stays authored: each gate's "establishes" and "milestone", its accountable and
responsible functions (scripts/data/gate_narrative_3_0_0.json, carried over from the
3.0.0 edition and extended below where the engine added items), the status of the work in
section 7, and the measurements in section 8.

    cd backend && ./venv/bin/python -I scripts/export_twelve_gates.py [out.html] [--fragment out_fragment.html]

The CSS is the 3.0.0 edition's, verbatim (scripts/data/twelve_gates.css), plus one rule
(.n-done) in its own palette. The stable explanation without status lives in
scripts/export_gex_process.py.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.append(str(HERE.parent.parent.parent / "gex_pf_engine" / "backend"))

from app.core import contract_tokens as ct                              # noqa: E402
from app.core.abac import REVIEWER_GATES                                # noqa: E402
from app.core.vocabulary import display_label                           # noqa: E402
from pf_engine.core import bankability_engine as E                      # noqa: E402

h = html.escape
OLD = json.loads((HERE / "data" / "gate_narrative_3_0_0.json").read_text())
CSS = (HERE / "data" / "twelve_gates.css").read_text()
TODAY = date(2026, 10, 30)
READINESS = {"G1", "G2", "G3", "G7"}
ROLE = {"CERTIFIER": "Certifier", "INDEPENDENT_ENGINEER": "Independent engineer", "LENDERS_ADVISER": "Lenders’ adviser",
        "INSURER": "Insurer", "GRANT_ASSESSOR": "Grant assessor", "SEED_INVESTOR_ADVISER": "Seed investor’s adviser",
        "STRATEGIC_INVESTOR_ADVISER": "Strategic investor’s adviser"}
SEV = {"deal_killer": ("sev-dk", E.SEVERITY_LABELS["deal_killer"]), "warning": ("sev-w", E.SEVERITY_LABELS["warning"]),
       "advisory": ("sev-a", E.SEVERITY_LABELS["advisory"])}
MCLASS = {"INTENT": "m-intent", "INDICATIVE": "m-indicative", "AGREED": "m-agreed", "EXECUTED": "m-executed",
          "EFFECTIVE": "m-effective"}


def short(gate_id: str) -> str:
    return gate_id.split("_")[0]


def state_name(state: str | None) -> str:
    return h(display_label("readiness", state).upper()) if state else "—"


def words(s: str) -> str:
    return h(str(s).replace("_", " ").title())


def lender_only(key: str) -> bool:
    return E.EVIDENCE_SCOPE.get(key) == "PROJECT_FINANCE"


def counterparty_kind(key: str) -> str | None:
    return next((k for k, keys in ct.CONTRACT_EVIDENCE.items() if key in keys), None)


def reviewers_for(gid: str) -> list[str]:
    return [ROLE.get(getattr(r, "value", str(r)), str(r)) for r, gates in REVIEWER_GATES.items() if short(gid) in gates]


def scale(level: str | None) -> str:
    if not level:
        return '<span class="nomat">—</span>'
    n = E.MATURITY_LEVELS.index(level) + 1
    bars = "".join(f'<i class="{"on" if i < n else ""}"></i>' for i in range(5))
    return (f'<span class="mat" title="{h(E.MATURITY_DEFINITIONS[level])}"><span class="scale" aria-hidden="true">{bars}</span>'
            f'<span class="mlabel {MCLASS[level]}">{level}</span></span>')


# ── authored: what a gate's evidence says that the engine's labels do not ───────────────────────────
ADD_ESTABLISHES = {
    "G0": " Its technical suitability — major-hazard siting, geotechnics, logistics access — is evidenced.",
    "G1": " The technology basis is evidenced as well: maturity, a named licensor, and a mass and energy balance at the design basis.",
    "G2": " The product’s qualification pathway is identified.",
    "G3": " The feedstock specification is matched to the design basis and to the certification scheme.",
    "G4": " The seller’s own exposure — delivery, specification, delay and shortfall caps, certification warranty, longstop — has been reviewed.",
    "G5": " The design is mature (FEED complete and independently reviewed), the technology is wrapped, long-lead items are reserved and the contractor’s security is in place.",
    "G7": " First-of-a-kind exclusions and the equipment makers’ warranty backstop are reviewed.",
    "G11": " The first certificates are issued and the first on-specification deliveries have been accepted by the offtaker.",
}
ADD_MILESTONE = {
    "G1": " Technology maturity dossier, licensor term sheet and a design-basis mass and energy balance.",
    "G5": " FEED complete and independently reviewed; technology licence and process guarantee; long-lead items reserved; EPC security package.",
    "G10": " Funding committed; insurance bound; operating organisation in place.",
    "G11": " First certificates issued; first deliveries accepted.",
}
CHANGED = {
    "G4": "Graded on the offtake ladder: it needs O4 — binding, subject to conditions precedent with a longstop date. Checks C1–C3 and C5–C8 compare the offtake with the EPC, supply, power and certification terms. The offtaker’s confirmation covers the contract and its terms; the credit support — a letter of credit or a guarantee — is a third party’s instrument and is reviewed independently (4.3.0).",
    "G5": "Graded on the EPC ladder: it needs E4 — agreed form, with price, schedule, guarantees, damages, caps and security all agreed. Check C4 tests the offtake’s delay exposure against EPC damages, contingency and sponsor support. The contractor’s confirmation covers the contract; the bond or guarantee behind it is a third party’s instrument and is reviewed independently, like the offtaker’s credit support.",
    "G6": "4.3.0: applies to every project. The report and the energy-balance, CAPEX and OPEX opinions protect the sponsor’s own capital as much as a lender’s; only the completion-test definitions stay lender-only. Before, all five items were waived for balance-sheet funding.",
    "G7": "Binding and the lenders’ loss-payee endorsement remain at G10; this gate establishes insurability.",
    "G8": "4.3.0: the base case, downside cases and consistency with the engineer apply to every project; the model audit opinion, covenant suite, reserve logic and hedging plan stay lender-only. Before, the whole gate was waived for balance-sheet funding. 4.2.0: if check C10 cannot run for lack of confirmed terms the gate reads UNRESOLVED, not SATISFIED. The state it leads to is now called “Ready for credit decision”: it says the financial assessment is complete, never that a lender has approved.",
    "G10": "Check C9 compares force-majeure clauses across the offtake, EPC and supply contracts. The state it completes also needs the offtake in force (O7 under project finance, O5 on the balance sheet) and the EPC at E6.",
}
ALSO_CHECKS = {   # checks scored on G4 that test what this gate establishes
    "G1": ["C6"], "G2": ["C7", "C8"], "G3": ["C6"], "G5": ["C1", "C3", "C5"],
}
REMAINING = {     # old "convergence to compute" items the ten checks do not cover
    "G0": ["site footprint ↔ plant layout", "tenure term ↔ construction schedule", "zoning ↔ proposed facilities"],
    "G1": ["P50/P90 generation ↔ production case", "connection date ↔ COD", "PPA tenor ↔ debt tenor", "water volume ↔ process requirement"],
    "G2": ["GHG methodology ↔ process and energy inputs"],
    "G3": ["feedstock volume and quality ↔ process mass balance", "supply tenor ↔ debt tenor"],
    "G4": ["offtake volume ↔ the P50/P90 production case (C2 tests guaranteed capacity)", "price formula ↔ model revenue", "buyer credit ↔ exposure"],
    "G5": ["scope ↔ plant configuration", "performance guarantees ↔ the production model"],
    "G6": ["IE production and capex conclusions ↔ TEA and model base case", "IE-reviewed version ↔ current model"],
    "G7": ["coverage and deductibles ↔ EPC and operating risks", "insured values ↔ capex"],
    "G8": ["capex, opex and production ↔ verified TEA/IE basis", "PPA terms ↔ model assumptions", "debt structure ↔ CFADS and DSCR"],
    "G9": ["consented capacity ↔ design", "permit conditions ↔ schedule and cost", "permit validity ↔ construction and COD"],
    "G10": ["facility terms ↔ debt schedule", "funded equity and DSRA ↔ closing statement", "security package ↔ asset and entity structure"],
    "G11": ["tested capacity and efficiency ↔ model and guarantees", "COD ↔ offtake, debt and refinancing dates"],
}


def item_changes(g: dict) -> str | None:
    old = set(OLD["g" + short(g["gate_id"])[1:]]["items"])
    new = [E.EVIDENCE_META[k]["label"] for k in g["required_evidence"]]
    added = [n for n in new if n not in old]
    gone = [o for o in OLD["g" + short(g["gate_id"])[1:]]["items"] if o not in new]
    if added and gone:
        return f"{len(added)} added, {len(gone)} replaced since 3.0.0: " + "; ".join(added) + "."
    if added:
        return f"{len(added)} item{'s' if len(added) > 1 else ''} added since 3.0.0: " + "; ".join(added) + "."
    return None


def gate_card(g: dict) -> str:
    gid, sid = g["gate_id"], short(g["gate_id"])
    o = OLD["g" + sid[1:]]
    kind = ('k-read">Readiness gate' if sid in READINESS else 'k-ach">Achievement gate')
    caps = ", ".join(E.CAPITAL_TYPE_LABELS.get(c, c) for c in g.get("unlocks_capital") or []) \
        or "None — this gate advances the state only"
    rows = []
    for key in g["required_evidence"]:
        m = E.EVIDENCE_META[key]
        cls, lab = SEV[m["severity"]]
        applies = ", ".join(words(a) if a != "ALL" else "All" for a in (m.get("applies_to") or ["ALL"]))
        if lender_only(key):
            applies += " · lender-financed only"
        by = "Counterparty" if counterparty_kind(key) else "Reviewer"
        lapses = (' <span class="mono" style="color:var(--muted)">· lapses</span>' if key in E.EXPIRY_REQUIRED else "")
        rows.append(f'<tr><td>{h(m["label"])}{lapses}</td><td class="own">{h(m["owner_function"])}</td>'
                    f'<td><span class="sev {cls}">{lab}</span></td><td>{scale(E.REQUIRED_MATURITY.get(key))}</td>'
                    f'<td class="app">{h(applies)}</td><td class="own">{by}</td></tr>')
    ver = " · ".join(reviewers_for(gid)) or "Counterparty confirmation only"
    if any(counterparty_kind(k) for k in g["required_evidence"]):
        ver += " · contracts also by counterparty confirmation"
    commit = E.GATE_COMMITMENT_REQUIREMENTS.get(gid)
    notes = []
    chg = [CHANGED.get(sid), item_changes(g)]
    if commit and sid not in CHANGED:
        chg.insert(0, f"Needs the {commit[0]} commitment at {commit[1]}.")
    chg = [c for c in chg if c]
    if chg:
        notes.append('<div class="note n-changed"><span class="nk">Changed since 3.0.0</span>'
                     + "".join(f"<p>{h(c)}</p>" for c in chg) + "</div>")
    checks = [c for c in E.COHERENCE_CHECKS if c["gate"] == gid]
    also = [c for c in E.COHERENCE_CHECKS if c["id"] in ALSO_CHECKS.get(sid, [])]
    if checks or also:
        body = "; ".join(f"<b>{h(c['id'])}</b> {h(c['title'])}" for c in checks)
        if also:
            body += ("" if not body else ". ") + "Also tested here, scored on G4: " + "; ".join(
                f"<b>{h(c['id'])}</b> {h(c['title'])}" for c in also)
        notes.append('<div class="note n-done"><span class="nk">Checks now computed</span><p>'
                     + body + ". A failing check blocks the gate; one that cannot run for lack of confirmed terms holds it "
                     "UNRESOLVED.</p></div>")
    rem = REMAINING.get(sid, [])
    if rem:
        notes.append('<div class="note n-conv"><span class="nk">Convergence still to compute</span><p>'
                     + " · ".join(h(r) for r in rem) + "</p></div>")
    return f"""
<section class="gate" id="g{sid[1:]}">
  <header class="gh">
    <span class="gnum">{sid}</span>
    <div class="gtitle">
      <h3>{h(g['gate_name'])}</h3>
      <p class="gmeta"><span class="kind {kind}</span>
        <code>{h(gid)}</code><span class="leads">leads to <b>{state_name(g.get('unlocks_state'))}</b></span></p>
    </div>
  </header>
  <p><b>Establishes.</b> {h(o['establishes'])}{h(ADD_ESTABLISHES.get(sid, ''))}</p>
  <p><b>Milestone.</b> {h(o['milestone'])}{h(ADD_MILESTONE.get(sid, ''))}</p>
  <div class="tw"><table class="ev">
    <thead><tr><th>Evidence required</th><th>Owner function</th><th>Severity</th><th>Maturity</th><th>Applies to</th><th>Verified by</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>
  <div class="facts">
    <div><span class="fk">Capital decision made eligible</span><span class="fv">{h(caps)}</span></div>
    <div><span class="fk">Verified by</span><span class="fv ver">{h(ver)}</span></div>
    <div><span class="fk">Accountable</span><span class="fv">{h(o['accountable'])}</span></div>
    <div><span class="fk">Responsible</span><span class="fv">{h(o['responsible'])}</span></div>
  </div>
  {''.join(notes)}
</section>"""


def commit_needs(state: str) -> str:
    label = {"PROJECT_FINANCE": "project finance", "BALANCE_SHEET": "balance sheet"}
    parts = []
    for model, req in E.STATE_COMMITMENT_REQUIREMENTS.get(state, {}).items():
        bits = []
        if "offtake" in req:
            bits.append(f"offtake {req['offtake']}" + (" in force" if req.get("offtake_effective") else ""))
        if "offtake_coverage_pct" in req:
            bits.append(f"offtake terms for {req['offtake_coverage_pct']:g} % of output")
        if "epc" in req:
            bits.append(f"EPC {req['epc']}")
        if bits:
            parts.append(f"{label.get(model, model)}: {', '.join(bits)}")
    if state == "REFINANCING_ELIGIBLE":
        parts.append(f"{E.REFINANCING_STABLE_MONTHS} months since the actual COD date")
    gate = [f"{short(g)} needs {'EPC' if k == 'epc' else k} {lvl}" for g, (k, lvl) in E.GATE_COMMITMENT_REQUIREMENTS.items()
            if g in E.STATE_REQUIREMENTS.get(state, [])]
    return "; ".join(gate + parts)


def ladder_rows() -> str:
    rows = []
    for state in E.STATE_ORDER:
        gates = E.STATE_REQUIREMENTS.get(state, [])
        name = {g["gate_id"]: g["gate_name"] for g in E.GATES}
        caps = sorted({E.CAPITAL_TYPE_LABELS.get(c, c) for g in E.GATES if g["gate_id"] in gates
                       for c in g.get("unlocks_capital") or []})
        need = ("Entry state" if state == "SPECULATIVE" else
                "No gate yet defined — unreachable" if not gates else "; ".join(h(name[x]) for x in gates))
        extra = commit_needs(state)
        if extra:
            need += f'<br><span class="mono" style="color:var(--muted)">{h(extra)}</span>'
        rows.append(f'<tr><td class="st">{state_name(state)}</td><td class="mono">{h(", ".join(short(x) for x in gates)) or "—"}</td>'
                    f"<td>{need}</td><td>{h(', '.join(caps).upper()) or '—'}</td></tr>")
    return "".join(rows)


def commitment_tables() -> str:
    def t(head, levels, defs):
        r = "".join(f'<tr><td class="st mono">{l}</td><td>{h(defs[l])}</td></tr>' for l in levels)
        return f'<div class="tw"><table><thead><tr><th>{head}</th><th>What it means</th></tr></thead><tbody>{r}</tbody></table></div>'
    return (t("Offtake", E.OFFTAKE_LEVELS, E.OFFTAKE_LEVEL_DEFINITIONS)
            + t("EPC", E.EPC_LEVELS, E.EPC_LEVEL_DEFINITIONS))


def build() -> tuple[str, dict]:
    n_items = sum(len(g["required_evidence"]) for g in E.GATES)
    n_lender = sum(1 for g in E.GATES for k in g["required_evidence"] if lender_only(k))
    sev = {s: sum(1 for g in E.GATES for k in g["required_evidence"] if E.EVIDENCE_META[k]["severity"] == s)
           for s in ("deal_killer", "warning", "advisory")}
    v = E.EVIDENCE_RULES_VERSION
    stats = {"rules": v, "items": n_items, "maturity": len(E.REQUIRED_MATURITY), "lender_only_items": n_lender, "sev": sev}

    rail_gates = "".join(
        f'<li><a href="#g{short(g["gate_id"])[1:]}"><span class="rn">{short(g["gate_id"])}</span>{h(g["gate_name"])}'
        f'<span class="rk {"k-read" if short(g["gate_id"]) in READINESS else "k-ach"}">'
        f'{"R" if short(g["gate_id"]) in READINESS else "A"}</span></a></li>' for g in E.GATES)
    def ladder_item(idx: int, level: str) -> str:
        bars = "".join(f'<i class="{"on" if i <= idx else ""}"></i>' for i in range(5))
        return (f'<li><span class="scale" aria-hidden="true">{bars}</span><b class="{MCLASS[level]}">{level}</b>'
                f'<span class="def">{h(E.MATURITY_DEFINITIONS[level])}</span></li>')

    maturity_ladder = "".join(ladder_item(i, l) for i, l in enumerate(E.MATURITY_LEVELS))

    body = f"""<div class="wrap">
<nav class="rail" aria-label="Contents">
  <h4>Contents</h4>
  <ol>
    <li><a href="#verdict"><span class="rn">1</span>Verdict</a></li>
    <li><a href="#how"><span class="rn">2</span>How a gate works</a></li>
    <li><a href="#maturity"><span class="rn">3</span>Maturity</a></li>
    <li><a href="#ladder"><span class="rn">4</span>The ladder</a></li>
    <li><a href="#gates"><span class="rn">5</span>The twelve gates</a></li>
    <li><a href="#ownership"><span class="rn">6</span>Who is accountable</a></li>
    <li><a href="#remaining"><span class="rn">7</span>Closed and open</a></li>
    <li><a href="#sources"><span class="rn">8</span>Sources</a></li>
  </ol>
  <h4>Gates · R readiness · A achievement</h4>
  <ul>{rail_gates}</ul>
</nav>

<main>
<header class="mast">
  <p class="eyebrow">GreenEarthX</p>
  <h1>The Twelve Bankability Gates</h1>
  <p class="sub">Evidence rules {v} — convergence computed, the credit decision left to the lender</p>
  <blockquote class="mantra">Projects don’t become bankable because the story is convincing. They become bankable when the evidence converges.</blockquote>
  <p class="aud">Reference for producers, financiers, certifiers and the GEX platform team.</p>
  <div class="meta"><span><b>Rules {v}</b></span><span>{len(E.GATES)} gates</span><span>{n_items} evidence items</span>
    <span>{len(E.REQUIRED_MATURITY)} maturity requirements</span><span>{len(E.RETIRED_EVIDENCE)} keys retired</span><span>{len(E.STATE_ORDER)} states</span><span>{len(E.CAPITAL_TYPES)} capital types</span></div>
  <p class="revised">Revised 30 October 2026, after the review of 29–30 October of the process against an outside reviewer’s remarks, lender practice and the market record. Every gate, evidence item, maturity requirement, check and owner in this document was exported from the running engine on that date; the engine and the platform registry are held identical by a guardrail test. The stable explanation of the process, without status, is “The GEX Process”.</p>
</header>

<section class="sec" id="verdict">
  <h2><span class="n">1</span>Verdict</h2>
  <p><b>The gate structure is right, and the bar now tests more than whether documents exist.</b> Since 3.0.0 the engine has required achievements rather than intentions. It grades the offtake and the EPC on their own commitment ladders; it compares terms across contracts; a gate whose checks cannot run for lack of confirmed terms reads UNRESOLVED, never SATISFIED; and no party can verify its own evidence or change, alone, the premises that decide what applies to it.</p>
  <p><b>The half of the mantra that was missing — convergence — is now partly true.</b> Ten checks compare delivery dates, capacity, specification, damages, longstops, power, certification, force majeure and the model’s inputs. They run only on terms the other party to the contract has confirmed on its token, so a figure the producer typed alone reaches no check. Convergence is not complete: section 5 lists, gate by gate, the comparisons still to compute.</p>
  <div class="panel good"><span class="pk">What 4.3.0 to 4.8.0 changed</span>
    <p>Until 4.3.0 a balance-sheet-funded project skipped every item in G6 and G8, because the engine called them all lender protection. It could climb to the state then named “Credit approved” with no independent engineer’s report and no base case — the pattern of a project that takes an investment decision on its own balance sheet before cost and offtake are settled. Seven of those items protect the sponsor’s own capital, and they now apply to every project. {n_lender} items that protect only a lender still drop out. No gate is waived wholesale, and a state is never reached on waivers alone.</p>
    <p>4.5.0 added expiry: a verified item with a validity date stops counting the day after it, with no new upload. 4.6.0 made the dates unavoidable for the instruments that lapse in practice — the land option or lease, the permits, the grid reservation, credit support and the EPC security package, the insurance quotation and the bound cover (marked “lapses” in each table): with no declared date such an item counts for 12 months after its verification and then stops, and one with neither a date nor a verification date counts for nothing. A declared date always wins, so a lease can say 25 years.</p>
    <p>4.4.0 settled severity. Every applicable item stays mandatory, because a lender wants the full set; what changed is the reading. A deal-killer blocks the gate while it is missing. A <b>Required</b> item — the 62 formerly called warnings — leaves the gate incomplete, and becomes a deal-killer once capital is at work where the item says so. An <b>advisory</b> (two items) is shown and never blocks, so a gate can be satisfied below 100 %.</p>
    <p>The state is now “Ready for credit decision”. It says the financial assessment is complete; whether a lender approves is the lender’s, and GEX does not record it. The offtaker’s confirmation no longer verifies the letter of credit behind its own payments: it confirms the contract.</p>
    <p>Measured on 30 October: of the 11 stored evaluations, 10 are SPECULATIVE and the synthetic test project is TECHNICALLY PLAUSIBLE. They date from rules 4.2.0 and earlier and re-evaluate under {v} on next read. The one balance-sheet project has one evidence row, none verified, so its state cannot change; it gains seven applicable items, and the seven requests were raised on 30 October: three assigned to its executive, four — the independent engineer’s — with no one to ask yet.</p>
  </div>
</section>

<section class="sec" id="how">
  <h2><span class="n">2</span>How a gate works</h2>
  <p>Seven steps, executed on every change.</p>
  <ol class="steps">
    <li><p><b>Evidence carries a status.</b> NOT_STARTED, IN_PROGRESS, SUBMITTED, UNDER_REVIEW, VERIFIED, REJECTED, EXPIRED. Only VERIFIED can count. An item that carries a validity date reads EXPIRED the day after it, with no new upload, and counts for nothing. For the instruments that lapse in practice, no declared date means 12 months from verification.</p></li>
    <li><p><b>Instruments also carry a maturity.</b> Contracts, permits, policies, opinions, certificates and funding events declare how far they have progressed. A VERIFIED instrument counts only at or above the maturity its gate requires; {len(E.REQUIRED_MATURITY)} of the {n_items} items set a minimum, and for the rest verification alone counts.</p></li>
    <li><p><b>Verification is independent.</b> A contract is verified by its counterparty’s confirmation on the contract’s token, which confirms the terms and the execution; an instrument a third party issues — a letter of credit — is reviewed independently. Studies, opinions, audits and the producer’s own plan are verified by an appointed independent reviewer, never the submitter or the project owner’s company. GEX verifies no party’s evidence.</p></li>
    <li><p><b>A gate scores its applicable items.</b> Items that do not apply to the project’s power model, or protect only a lender it does not have, leave the denominator. A gate is complete when every required item is verified — an advisory is shown and never blocks — and its commitment checks, coherence checks and triggers also pass.</p></li>
    <li><p><b>Each gate gets one determination.</b> SATISFIED; BLOCKED (a deal-killer is missing, a commitment is below the level the gate needs, or a check failed); UNRESOLVED (the items are verified but a check cannot run for lack of confirmed terms); INCOMPLETE; or WAIVED (not required for this financing model). A waived gate is never shown as satisfied by evidence.</p></li>
    <li><p><b>Satisfied gates set the state.</b> The nine-state ladder is strictly sequential; no state is reachable without every gate of every state before it, and none on waivers alone.</p></li>
    <li><p><b>States make capital decisions eligible, and every change re-evaluates.</b> GEX establishes that the evidence conditions are met; the bank, investor, DFI or grant authority still decides. Any change to evidence, a document, a premise, a contract term or a confirmation re-evaluates the project at once, and the designated executives are told when the state or a gate’s answer moves. Losing evidence moves the project backwards and withdraws eligibility, naming the gate responsible.</p></li>
  </ol>
</section>

<section class="sec" id="maturity">
  <h2><span class="n">3</span>Maturity — the axis the decision added</h2>
  <p>Verification answers whether a document is authentic. Maturity answers how far the instrument behind it has progressed. They are independent: a letter of intent can be perfectly authentic, and it must never count as an executed contract.</p>
  <ol class="ladder">{maturity_ladder}</ol>
  <div class="panel"><span class="pk">The maker/checker rule</span>
    <p>The submitter declares maturity. A reviewer may confirm it or lower it, and may never raise it — verification must not turn a term sheet into a contract. A reviewer also cannot introduce a maturity the submitter never declared. Both rules are enforced on the platform’s write path, and every maturity change is recorded in the append-only audit trail even when the status does not change.</p>
    <p>Where a gate sets a minimum, an instrument with no declared maturity does not count until someone declares it. The {n_items - len(E.REQUIRED_MATURITY)} items without a minimum are shown with a dash.</p>
  </div>
</section>

<section class="sec" id="ladder">
  <h2><span class="n">4</span>The ladder</h2>
  <div class="tw"><table>
    <thead><tr><th>State</th><th>Gates</th><th>What must be satisfied</th><th>Capital decision made eligible</th></tr></thead>
    <tbody>{ladder_rows()}</tbody></table></div>
  <p>No gate is waived wholesale. For a balance-sheet project the {n_lender} items marked “lender-financed only” drop out of their gates and the rest still apply; a state is never reached on waivers alone. Capital eligibility is generic by state: a named provider’s own requirements are not modelled.</p>
  <p>Readiness gates (G1, G2, G3, G7) test what can be true at their stage — indicative terms, a feasible pathway, confirmed insurability. Every instrument they rely on must be EXECUTED at G10. That is the design: terms are established early, and financial close is where they become commitments.</p>
  <h3 class="sub3">The commitment ladders</h3>
  <p>The offtake and the EPC are graded on their own ladders, computed from the confirmed terms on the contract tokens plus the maturity of their documents. Each state names the level it needs, shown beneath it above.</p>
  {commitment_tables()}
</section>

<section class="sec" id="gates">
  <h2><span class="n">5</span>The twelve gates</h2>
  <p>Each gate as the engine now defines it. “Maturity” is the minimum at which a verified instrument counts, drawn as a position on the five-level ladder above; a dash means the item sets no minimum and verification alone counts. “Verified by” says whether the contract’s counterparty confirms the item or an independent reviewer does. Severity says what a missing item costs: a deal-killer blocks the gate ({sev['deal_killer']} items); a required item leaves it incomplete ({sev['warning']}); an advisory is shown and never blocks ({sev['advisory']}). Every applicable item that is not an advisory must be verified.</p>
{''.join(gate_card(g) for g in E.GATES)}
</section>

<section class="sec" id="ownership">
  <h2><span class="n">6</span>Who is accountable for what</h2>
  <p>Producing a document, uploading it, controlling access to it and accepting responsibility for its conclusions are different things. An engineer may author a report, the producer submit it, and a lender commission it and rely on it.</p>
  <div class="tw"><table>
    <thead><tr><th>Role</th><th>Accountable for</th><th>Must never own</th></tr></thead>
    <tbody>
      <tr><td class="st">Evidence owner</td><td>Obtaining, maintaining and updating the required evidence, and declaring what each instrument is and how far it has progressed.</td><td>The verification of its own evidence.</td></tr>
      <tr><td class="st">Author or issuer</td><td>The document’s statements and professional conclusions, within its stated scope.</td><td>The decision to rely on it.</td></tr>
      <tr><td class="st">Counterparty</td><td>Confirming its contractual agreement and the authority of its representative.</td><td>Terms it has not confirmed; the authentication of a third party’s instrument.</td></tr>
      <tr><td class="st">Reviewer</td><td>A defined assessment: its scope, qualifications, limitations and findings.</td><td>Any commercial interest in the outcome — and the power to raise a declared maturity.</td></tr>
      <tr><td class="st">GEX</td><td>Identity and permission controls, governance of the rules, the computation, version history and auditability. It appoints reviewers, may be the second party on a premise change, and decides a contested one.</td><td>The evidence, its verification, and the capital decision.</td></tr>
      <tr><td class="st">Decision authority</td><td>Accepting residual risk and taking the investment, credit or drawdown decision.</td><td>Letting a GEX gate stand in for its own approval.</td></tr>
    </tbody></table></div>
  <p>Stated as one line: GEX must never own the evidence or the capital decision, the producer must never own the verification, and a counterparty’s confirmation covers what the counterparty can know. Every gate has two ownership axes, carried identically in both registries — personas, who sees the gate, and accountable functions, who does the work. Evidence requests are assigned to named people at the company that owns the work; due dates exist and are not yet used.</p>
</section>

<section class="sec" id="remaining">
  <h2><span class="n">7</span>What the decisions closed, and what remains</h2>
  <h3 class="sub3 good">Closed since 3.0.0</h3>
  <ul class="plain"><li><b>Convergence never tested.</b> Ten cross-contract checks compare the terms; a failing check blocks its gate (4.0.0). A check that cannot run holds the gate UNRESOLVED instead of passing it (4.2.0).</li><li><b>Terms typed by the owner alone.</b> Only terms the other party has confirmed on the contract’s token reach the engine; a changed term is held back until it is confirmed again.</li><li><b>Premises changed by the owner alone.</b> A change that removes evidence needs a registered document and a second party’s confirmation; a contested premise reverts to the protective one until GEX decides.</li><li><b>Verification self-assertable.</b> Since 1 October a reviewer status is a verify, which only an appointed independent reviewer may give, never the submitter or the owner’s company, and which must name the sha256 of a document on file.</li><li><b>Hand-typed gate figures.</b> Every figure on every screen comes from the engine; the seeded assessments were removed from the project profiles and archived.</li><li><b>A persona seeing some gates and a score over all of them.</b> The engine readout states, wherever it is shown, that the overall figure and the state cover every gate when a role sees fewer.</li><li><b>Screen locks on hand-typed gate figures.</b> Removed; a screen now says which gate it feeds and how far the engine has it.</li><li><b>Stale evaluations.</b> Every change to evidence, a document, a premise, a contract term or a confirmation re-evaluates the project; an engine outage drops the stored result instead of keeping it. Designated executives are told when the state or a gate moves.</li><li><b>Documents attached as browser URLs.</b> The screen uses the real upload, which records the SHA-256 that binds an assertion to an artefact.</li><li><b>Balance-sheet projects skipping independent validation.</b> Closed in 4.3.0, with the guard that a state is never reached on waivers alone.</li><li><b>A state that could not be reached.</b> “Proven — refinancing” is now reached when G11 is satisfied and 12 months have passed since the actual COD date, a field on the producer’s schedule card; with no date, or fewer months, the project stays Operational and the screen says which (4.8.0).</li><li><b>No clock on any gate.</b> Each gate’s first satisfaction is now recorded once, never rewritten, and shown on the project report with its distance from the project’s start. It measures from 31 October 2026: gates satisfied earlier are not measured, so it cannot yet support a claim about acceleration. It can start to.</li><li><b>A declared gate ordering that nothing enforced.</b> The registry served a prerequisite graph that nothing read, and a “100 %” completion threshold that stopped being true when an advisory stopped blocking a gate. Both are removed; the only ordering is the state ladder, which the engine enforces.</li><li><b>“Funding committed” accepting an internal approval.</b> The G10 item now reads “Funds committed to this project”: equity injected, or a committed facility or escrow. A board’s approval alone does not count; the lenders’ adviser verifies it against that wording (4.7.0).</li><li><b>Evidence that never expired.</b> A document can carry a validity date, declared with it: a permit’s validity, a letter of credit’s expiry, a policy period. The day after, the item reads EXPIRED, counts for nothing and — unless it is an advisory — blocks its gate and names the expiry; the project steps back with no new upload. A stored evaluation is re-evaluated when read once an item has expired, and a daily sweep re-evaluates projects so their designated executives are told (4.5.0). Outside those instruments an item with no date never expires, and a reviewer may add or shorten a date, never extend it. The twelve-month default is JML’s decision of 31 October (4.6.0).</li><li><b>Severity that decided nothing.</b> Every applicable item stays mandatory; a deal-killer blocks, a required item (formerly “warning”) leaves the gate incomplete, and the two advisories are shown and never block (4.4.0).</li><li><b>A state claiming a lender’s decision.</b> “Credit approved” is now “Ready for credit decision”.</li><li><b>A counterparty’s confirmation verifying its own bank’s instrument.</b> The offtaker and the EPC contractor confirm their contracts; the letter of credit and the performance bond or guarantee are reviewed independently.</li></ul>
  <h3 class="sub3 bad">Still open</h3>
  <ol class="openlist">
    <li><p><b>Applicability knows two premises.</b> The financing model and the power model decide what applies. Additionality is required of every project as a deal-killer whose blocked action is RFNBO eligibility, so a project on another certification route inherits an obligation that is not its own. The route should come from the confirmed offtake, which already names the scheme it requires.</p></li>
    <li><p><b>No reviewer is appointed on any project.</b> Everything that needs an independent reviewer cannot yet be verified on a live project. That is fail-closed, not a fault. It now includes the letter of credit and the EPC security package; the latter has the independent engineer as its only verifier, whose scope is G5 as a whole.</p></li>
    <li><p><b>One tolerance for every numeric check.</b> Equality allows 1 % of the larger value whatever the field or unit; a materiality that differs by field is not modelled.</p></li>
    <li><p><b>Convergence is incomplete.</b> The comparisons listed under each gate are still to compute, among them the production case against the offtake, the buyer’s credit against the exposure, and the debt structure against CFADS and DSCR.</p></li>
    <li><p><b>Assignment without due dates.</b> 56 of the 92 open evidence requests have an assignee and none has a due date. Most of the rest wait for an external party, because an independent engineer is not an account of the producer.</p></li>
    <li><p><b>Eligibility is generic by state.</b> A named instrument’s own requirements are not modelled, and the credit decision is not recorded: GEX shows that the decision can be taken, not that it was.</p></li>
    <li><p><b>Identifiers overclaim.</b> G3 and G7 keep SECURED and BOUND for stability while their names and evidence state what is tested; the state identifier CREDIT_APPROVED keeps its old name beside its new label.</p></li>
  </ol>
</section>

<section class="sec" id="sources">
  <h2><span class="n">8</span>Sources</h2>
  <div class="tw"><table>
    <thead><tr><th>Source</th><th>Role</th><th>Used for</th></tr></thead>
    <tbody>
      <tr><td class="mono">gex_pf_engine/backend/pf_engine/core/bankability_engine.py</td><td><span class="srole src-auth">Authoritative</span></td><td>Every gate, evidence item, maturity requirement, commitment ladder, check, state and capital decision in this document — rules {v}.</td></tr>
      <tr><td class="mono">gex-platform-enhanced/backend/app/core/bankability_engine.py</td><td><span class="srole ">Registry</span></td><td>Held identical to the engine by tests/test_gate_registries_agree.py. Also resolves evidence keys for authorisation.</td></tr>
      <tr><td class="mono">backend/app/core/abac.py (REVIEWER_GATES) and contract_tokens.py</td><td><span class="srole ">Platform</span></td><td>Which reviewer role verifies which gate, and which contract instruments a counterparty’s confirmation verifies.</td></tr>
      <tr><td class="mono">The GEX Process, rules {v}</td><td><span class="srole ">Companion</span></td><td>The stable explanation without status, generated from the same rules.</td></tr>
      <tr><td class="mono">Reviewer’s remarks of 29 October 2026</td><td><span class="srole ">Review</span></td><td>Responsibility allocation, counterparty assurance, the credit-decision state, balance-sheet scope, applicability, and the internal inconsistencies. Each point was checked against the engine; one claim — that O4 and E4 are undefined — was wrong, and they are published in section 4.</td></tr>
      <tr><td class="mono">Hydrogen Council with McKinsey; MEED; IFC; OECD; GH2; Oxford Energy; Ørsted (FlagshipONE)</td><td><span class="srole ">Market record</span></td><td>That offtake is where projects fail, that credit support is a separate instrument, that the pre-FID stage is the financing gap, and the FlagshipONE case. Several figures reach us through trade press and are not used as thresholds.</td></tr>
      <tr><td class="mono">Live database, 30 October 2026</td><td><span class="srole ">Measured</span></td><td>11 stored evaluations (10 SPECULATIVE, 1 synthetic test project TECHNICALLY PLAUSIBLE); 92 open requests, 56 assigned, none with a due date; no reviewer appointed; platform suite 1234 pass, engine suite 266 pass.</td></tr>
    </tbody></table></div>
</section>

<footer>
  Exported from the running engine on 30 October 2026 · evidence rules {v}<br>
  Generated by <span class="mono">backend/scripts/export_twelve_gates.py</span>; wording that only a person can say is in <span class="mono">scripts/data/gate_narrative_3_0_0.json</span> and in the script.
</footer>
</main>
</div>
"""
    return body, stats


def page(body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>The Twelve Bankability Gates</title>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;600&display=swap">'
            f"<style>\n{CSS}</style></head><body>\n{body}\n</body></html>")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    frag = None
    if "--fragment" in args:
        i = args.index("--fragment")
        frag = Path(args[i + 1])
        del args[i:i + 2]
    out = Path(args[0]) if args else HERE.parent.parent / "docs" / "The_Twelve_Bankability_Gates.html"
    body, stats = build()
    out.write_text(page(body))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) {stats}")
    if frag:
        frag.write_text('<title>The Twelve Bankability Gates</title>\n'
                        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;600&display=swap">\n'
                        f"<style>\n{CSS}</style>\n{body}")
        print(f"wrote {frag}")
