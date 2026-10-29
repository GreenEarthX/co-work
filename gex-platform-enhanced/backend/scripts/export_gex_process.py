"""
Generate "The GEX Process" from the running rules (JML, 2026-10-28).

The stable explanation of how a project becomes bankable on GEX, for producers,
financiers, certifiers and verifiers. Every gate, evidence item, maturity bar,
owner, check and capital decision in it is read from the code that applies
them — the PF engine (pf_engine.core.bankability_engine), the platform's
reviewer map (app.core.abac.REVIEWER_GATES) and contract tokens
(app.core.contract_tokens) — so the document cannot drift from the rules.
Status, defects and open items are NOT in it; they live in docs/CLAUDE_HANDOFF.md.

    cd backend && ./venv/bin/python -I scripts/export_gex_process.py [out.html] [--json out.json]
    NODE_PATH=<dir with docx> node scripts/gex_process_docx.cjs out.json ../docs/GEX_Process.docx

Writes page content (no <html>/<body> wrapper: it is published as an Artifact,
which adds the skeleton) to ../docs/GEX_Process.html by default. `--json` also
writes the same page as blocks (headings, paragraphs, lists, tables, inline
bold/italic/mono) for the Word builder, so the .docx is the page, not a retelling.
"""
from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                                    # platform `app` first
sys.path.append(str(HERE.parent.parent.parent / "gex_pf_engine" / "backend"))

from app.core import contract_tokens as ct                              # noqa: E402
from app.core.abac import REVIEWER_GATES                                # noqa: E402
from pf_engine.core import bankability_engine as E                      # noqa: E402

h = html.escape
READINESS = {"G1_GRID_UTILITIES_REALITY", "G2_CERTIFICATION_PATH_LOCKED", "G3_INPUTS_SECURED", "G7_INSURANCE_BOUND"}
ROLE_LABEL = {
    "CERTIFIER": "Certifier", "INDEPENDENT_ENGINEER": "Independent engineer", "LENDERS_ADVISER": "Lenders' adviser",
    "INSURER": "Insurer", "GRANT_ASSESSOR": "Grant assessor", "SEED_INVESTOR_ADVISER": "Seed investor's adviser",
    "STRATEGIC_INVESTOR_ADVISER": "Strategic investor's adviser",
}
SEVERITY = {"deal_killer": "Deal-killer", "warning": "Warning", "advisory": "Advisory"}
KIND_LABEL = {"offtake": "Offtake", "ppa": "Power purchase", "supply": "Feedstock supply", "epc": "EPC",
              "licence": "Technology licence", "technical": "Technical basis and schedule", "model": "Financial model"}


def words(s: str) -> str:
    return h(str(s).replace("_", " ").title()) if s else "—"


def reviewers_for(gate_id: str) -> list[str]:
    prefix = gate_id.split("_")[0]
    return [ROLE_LABEL.get(getattr(r, "value", str(r)), str(r)) for r, gates in REVIEWER_GATES.items()
            if prefix in gates]


def counterparty_kind(key: str) -> str | None:
    return next((k for k, keys in ct.CONTRACT_EVIDENCE.items() if key in keys), None)


def gate_section(g: dict) -> str:
    gid, meta = g["gate_id"], E.EVIDENCE_META
    kind = "Readiness gate" if gid in READINESS else "Achievement gate"
    capital = ", ".join(E.CAPITAL_TYPE_LABELS.get(c, c) for c in g.get("unlocks_capital") or []) or "—"
    commit = E.GATE_COMMITMENT_REQUIREMENTS.get(gid)
    lender = gid in E.LENDER_ONLY_GATES
    rows = []
    for key in g["required_evidence"]:
        m = meta.get(key, {})
        cp = counterparty_kind(key)
        rows.append(
            f"<tr><td>{h(m.get('label') or key)}</td>"
            f"<td><span class='sev sev-{h(m.get('severity', 'advisory'))}'>{SEVERITY.get(m.get('severity'), '—')}</span></td>"
            f"<td class='mono'>{h(E.REQUIRED_MATURITY.get(key) or '—')}</td>"
            f"<td>{words(m.get('owner_function'))}</td>"
            f"<td>{', '.join(words(a) for a in (m.get('applies_to') or ['ALL']))}</td>"
            f"<td>{'Counterparty (' + h(KIND_LABEL[cp]) + ')' if cp else 'Independent reviewer'}</td></tr>")
    notes = []
    if commit:
        notes.append(f"Also needs the {h(commit[0])} commitment at level <b>{h(commit[1])}</b> or above.")
    if lender:
        notes.append("Every item protects a lender: waived for a balance-sheet-funded project.")
    checks = [c for c in E.COHERENCE_CHECKS if c["gate"] == gid]
    if checks:
        notes.append("Cross-contract checks on this gate: " + "; ".join(
            f"<b>{h(c['id'])}</b> {h(c['title'])}" for c in checks) + ".")
    return f"""
<section class="gate" id="{h(gid.split('_')[0].lower())}">
  <header class="gate-head">
    <span class="gate-id mono">{h(gid.split('_')[0])}</span>
    <h3>{h(g['gate_name'])}</h3>
    <span class="gate-kind">{kind}</span>
  </header>
  <dl class="facts">
    <div><dt>Leads to</dt><dd>{words(g.get('unlocks_state'))}</dd></div>
    <div><dt>Capital decision made eligible</dt><dd>{h(capital)}</dd></div>
    <div><dt>Verified by</dt><dd>{h(', '.join(reviewers_for(gid)) or 'Counterparty confirmation only')}</dd></div>
    <div><dt>Seen by</dt><dd>{', '.join(words(p) for p in g.get('personas', []))} and the owner's executives</dd></div>
  </dl>
  {''.join(f'<p class="note">{n}</p>' for n in notes)}
  <div class="scroll"><table>
    <thead><tr><th>Evidence item</th><th>Severity</th><th>Maturity</th><th>Owner</th><th>Applies to</th><th>Verified by</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
</section>"""


def ladder() -> str:
    rows = []
    for state in E.STATE_ORDER:
        gates = E.STATE_REQUIREMENTS.get(state, [])
        caps = sorted({E.CAPITAL_TYPE_LABELS.get(c, c) for g in E.GATES if g["gate_id"] in gates
                       for c in g.get("unlocks_capital") or []})
        if state == "SPECULATIVE":
            need = "Entry state"
        elif not gates:
            need = "No gate defined yet — this state cannot be reached"
        else:
            need = ", ".join(f"<span class='mono'>{h(x.split('_')[0])}</span> {h(next(g['gate_name'] for g in E.GATES if g['gate_id'] == x))}"
                             for x in gates)
        rows.append(f"<tr><td><b>{words(state)}</b><br><span class='muted'>{h(E.STATE_COMMITMENT_LABELS.get(state, ''))}</span></td>"
                    f"<td>{need}</td><td>{h(', '.join(caps)) or '—'}</td></tr>")
    return "".join(rows)


def checks_table() -> str:
    return "".join(f"<tr><td class='mono'>{h(c['id'])}</td><td>{h(c['title'])}</td>"
                   f"<td class='mono'>{h(c['gate'].split('_')[0])}</td></tr>" for c in E.COHERENCE_CHECKS)


def token_table() -> str:
    rows = []
    for kind in list(ct.COUNTERPARTY_KINDS) + list(ct.REVIEWER_KINDS):
        who = ("The counterparty company registered on the contract" if kind in ct.COUNTERPARTY_KINDS
               else f"An independent reviewer appointed for {ct.REVIEWER_KINDS[kind]}")
        ev = ", ".join(h(E.EVIDENCE_META.get(k, {}).get("label") or k) for k in ct.CONTRACT_EVIDENCE.get(kind, ()))
        rows.append(f"<tr><td>{h(KIND_LABEL[kind])}</td><td>{h(who)}</td><td>{ev or '—'}</td></tr>")
    return "".join(rows)


def page() -> str:
    gates = "".join(gate_section(g) for g in E.GATES)
    n_items = sum(len(g["required_evidence"]) for g in E.GATES)
    toc = "".join(f"<a href='#{h(g['gate_id'].split('_')[0].lower())}'><span class='mono'>{h(g['gate_id'].split('_')[0])}</span> {h(g['gate_name'])}</a>"
                  for g in E.GATES)
    maturity = "".join(f"<li><span class='mono lvl'>{h(k)}</span> {h(v)}</li>" for k, v in E.MATURITY_DEFINITIONS.items())
    return f"""<title>The GEX Process</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Layout: one reading column with a sticky contents rail on wide screens; tables scroll in place. */
:root {{
  --bg: #f4f6f3; --paper: #fbfcfa; --ink: #18211d; --muted: #5a665f; --rule: #d3dad4;
  --accent: #0d6b57; --accent-soft: #e1efe9; --warn: #8a5a00; --stop: #a3261c;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #0f1412; --paper: #151c19; --ink: #e4ebe7; --muted: #9aa8a0; --rule: #2a3631;
  --accent: #52c2a4; --accent-soft: #173029; --warn: #e0b153; --stop: #f08a7e; color-scheme: dark }} }}
:root[data-theme="dark"] {{
  --bg: #0f1412; --paper: #151c19; --ink: #e4ebe7; --muted: #9aa8a0; --rule: #2a3631;
  --accent: #52c2a4; --accent-soft: #173029; --warn: #e0b153; --stop: #f08a7e; color-scheme: dark }}
body {{ background: var(--bg); color: var(--ink); font: 400 17px/1.6 var(--body); }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-block: 40px 80px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; grid-template-columns: minmax(0, 1fr); gap: 40px; }}
@media (min-width: 1000px) {{ .wrap {{ grid-template-columns: 220px minmax(0, 1fr); }} }}
nav.toc {{ font: 500 13px/1.4 var(--display); display: none; }}
@media (min-width: 1000px) {{ nav.toc {{ display: flex; flex-direction: column; gap: 6px; position: sticky;
  top: calc(24px + env(safe-area-inset-top, 0px)); align-self: start; max-height: calc(100vh - 48px); overflow: auto; }} }}
nav.toc a {{ color: var(--muted); text-decoration: none; }}
nav.toc a:hover, nav.toc a:focus-visible {{ color: var(--accent); }}
nav.toc .grp {{ margin-top: 12px; color: var(--ink); font-weight: 700; text-transform: uppercase; letter-spacing: .06em; font-size: 11px; }}
main {{ min-width: 0; }}
h1, h2, h3 {{ font-family: var(--display); text-wrap: balance; line-height: 1.15; }}
h1 {{ font-size: clamp(34px, 6vw, 56px); font-weight: 800; letter-spacing: -.02em; margin: 0 0 12px; }}
h2 {{ font-size: 26px; font-weight: 700; margin: 56px 0 12px; padding-top: 16px; border-top: 2px solid var(--ink); }}
h3 {{ font-size: 20px; font-weight: 700; margin: 0; }}
p, li {{ max-width: 68ch; }}
.lede {{ font-size: 20px; color: var(--muted); }}
.mantra {{ margin: 28px 0; padding: 18px 22px; background: var(--accent-soft); border-left: 4px solid var(--accent);
  font: 600 21px/1.45 var(--body); max-width: 68ch; }}
.stamp {{ font: 400 12px/1.5 var(--mono); color: var(--muted); }}
.mono {{ font-family: var(--mono); font-size: .86em; }}
.muted {{ color: var(--muted); font-size: .9em; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font: 400 14.5px/1.45 var(--body); font-variant-numeric: tabular-nums; }}
th {{ text-align: left; font: 700 11px/1.3 var(--display); text-transform: uppercase; letter-spacing: .07em;
  color: var(--muted); border-bottom: 2px solid var(--rule); padding: 8px 10px; }}
td {{ border-bottom: 1px solid var(--rule); padding: 8px 10px; vertical-align: top; }}
ol.steps {{ padding-left: 1.4em; display: grid; gap: 10px; }}
ol.steps li::marker {{ font: 700 15px var(--display); color: var(--accent); }}
ul.mat {{ list-style: none; padding: 0; display: grid; gap: 6px; }}
.lvl {{ display: inline-block; min-width: 9.5em; color: var(--accent); font-weight: 600; }}
.det {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
.det div {{ padding: 12px 14px; background: var(--paper); border: 1px solid var(--rule); }}
.det b {{ font-family: var(--display); letter-spacing: .03em; }}
.gate {{ margin: 28px 0 40px; padding: 20px; background: var(--paper); border: 1px solid var(--rule); }}
.gate-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 14px; }}
.gate-id {{ font-size: 15px; font-weight: 600; color: var(--accent); }}
.gate-kind {{ font: 600 11px var(--display); text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
dl.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px 20px; margin: 14px 0; }}
dl.facts dt {{ font: 700 11px var(--display); text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }}
dl.facts dd {{ margin: 2px 0 0; }}
.note {{ font-size: 15px; color: var(--muted); margin: 6px 0; }}
.sev {{ font: 600 11px var(--display); text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; }}
.sev-deal_killer {{ color: var(--stop); }} .sev-warning {{ color: var(--warn); }} .sev-advisory {{ color: var(--muted); }}
.never li {{ margin-bottom: 6px; }}
a {{ color: var(--accent); }}
a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
</style>
<div class="wrap">
<nav class="toc" aria-label="Contents">
  <span class="grp">The process</span>
  <a href="#owners">Who owns what</a><a href="#path">The path of one item</a><a href="#maturity">Maturity</a>
  <a href="#verify">Who verifies</a><a href="#determination">A gate's answer</a><a href="#premises">Project premises</a>
  <a href="#terms">Contract terms</a><a href="#ladder">The ladder</a><a href="#backwards">Going backwards</a>
  <a href="#reports">Reports and visibility</a><a href="#never">What GEX never does</a>
  <span class="grp">The twelve gates</span>{toc}
</nav>
<main>
<h1>The GEX Process</h1>
<p class="lede">How a green-fuel project becomes bankable on GreenEarthX: what is asked, who supplies it, who checks it,
and what each step makes possible. For producers, offtakers, financiers, insurers, certifiers and verifiers.</p>
<p class="mantra">Projects don't become bankable because the story is convincing. They become bankable when the evidence converges.</p>
<p class="stamp">Generated from the running rules — evidence rules {h(E.EVIDENCE_RULES_VERSION)} · {len(E.GATES)} gates ·
{n_items} evidence items · {len(E.REQUIRED_MATURITY)} maturity requirements · {len(E.STATE_ORDER)} states · {date.today().isoformat()}</p>

<h2 id="owners">Who owns what</h2>
<div class="scroll"><table>
<thead><tr><th>Party</th><th>Owns</th><th>Never owns</th></tr></thead>
<tbody>
<tr><td><b>The client</b> (producer, and each party to its contracts)</td><td>The evidence, the milestones, the declaration of what each instrument is and how far it has progressed.</td><td>The verification of its own evidence.</td></tr>
<tr><td><b>The counterparty</b> to a contract</td><td>Confirming, on the contract's token, the terms it agreed — which also verifies that contract.</td><td>Terms it has not confirmed.</td></tr>
<tr><td><b>The independent reviewer</b></td><td>The assertion that a study, opinion, audit or the producer's own plan is authentic and is what it claims to be.</td><td>A commercial interest in the outcome, and the power to raise a declared maturity.</td></tr>
<tr><td><b>GEX</b></td><td>The rule: what counts, at what maturity, with what severity; the scoring; and the record of who asserted what, and when.</td><td>The evidence, its verification, and the capital decision.</td></tr>
<tr><td><b>The capital provider</b></td><td>The grant, investment, credit or drawdown decision.</td><td>Letting a GEX gate stand in for its own approval.</td></tr>
</tbody></table></div>

<h2 id="path">The path of one evidence item</h2>
<ol class="steps">
<li><b>Requested.</b> Each item is assigned to a named person at the company that owns the work, with what it blocks.</li>
<li><b>Submitted.</b> The document is uploaded and its SHA-256 recorded; the submitter declares the instrument's maturity.
A new document returns the item to submitted: what was verified was the earlier file.</li>
<li><b>Verified.</b> By someone independent of the submitter and of the project owner — the contract's counterparty for a
contract, an appointed independent reviewer for everything else. Verification names the document on file.</li>
<li><b>Scored.</b> The engine counts an item only when it is verified at or above the maturity its gate requires.</li>
<li><b>Judged.</b> Each gate gets one answer (below); satisfied gates set the project's state.</li>
<li><b>Made eligible.</b> A state makes a capital decision eligible. The capital provider still decides.</li>
</ol>

<h2 id="maturity">Maturity</h2>
<p>Verification answers whether a document is authentic. Maturity answers how far the instrument behind it has progressed —
a letter of intent can be perfectly authentic. The submitter declares maturity; a reviewer may confirm or lower it, never raise
it. An instrument with no declared maturity does not count.</p>
<ul class="mat">{maturity}</ul>

<h2 id="verify">Who verifies</h2>
<p>GEX verifies nothing. A contract is verified by its counterparty's confirmation on the contract's token; an independent
reviewer may also take part, but is not required. Studies, analyses, opinions, audits and the producer's own plan need an
independent reviewer, appointed by GEX staff on the instruction of a named party. Each reviewer role covers fixed gates:</p>
<div class="scroll"><table><thead><tr><th>Reviewer</th><th>Gates</th></tr></thead><tbody>
{''.join(f"<tr><td>{h(ROLE_LABEL.get(getattr(r, 'value', str(r)), str(r)))}</td><td class='mono'>{h(', '.join(sorted(g, key=lambda x: int(x[1:]))))}</td></tr>" for r, g in REVIEWER_GATES.items())}
</tbody></table></div>
<p>Never the submitter or its company, and never the project owner's company.</p>

<h2 id="determination">A gate's answer</h2>
<div class="det">
<div><b>SATISFIED</b><br>Every applicable item verified at its maturity, every required commitment reached, every cross-contract check passed.</div>
<div><b>BLOCKED</b><br>A deal-killer is missing, a commitment is below the level the gate needs, a cross-contract check failed, or an event undermines the gate.</div>
<div><b>UNRESOLVED</b><br>The items are verified, but a cross-contract check cannot run because confirmed terms are missing. Missing data is never a pass.</div>
<div><b>INCOMPLETE</b><br>Items are still to be verified.</div>
<div><b>WAIVED</b><br>Not required for this financing model. Counts toward the ladder; never shown as satisfied by evidence.</div>
</div>

<h2 id="premises">Project premises</h2>
<p>Two premises decide which evidence applies. The <b>financing model</b>: balance-sheet funding drops the items that only protect
an external lender and waives the gates made only of them ({h(', '.join(sorted(x.split('_')[0] for x in E.LENDER_ONLY_GATES)))}).
The <b>power model</b> (grid-connected, off-grid behind the meter, hybrid): each drops the items that belong to the others.</p>
<p>A change that removes evidence takes effect only when its supporting document is registered <i>and</i> a second party confirms
it — another party to the project (a funder, the counterparty) or GEX staff, never the company that proposed it. Any party may
register a document contesting a premise; while it is contested the protective premise applies (project finance, every power
item), until GEX staff decide. A change that adds evidence back applies at once.</p>

<h2 id="terms">Contract terms and the contract token</h2>
<p>Documents can each satisfy a gate and still contradict one another. So the terms that matter — volumes, tenors, dates,
specifications, damages caps — are recorded once, and the engine compares them across contracts. Every contract has a
<b>token</b>: an append-only, hash-chained record of its versions and confirmations. A change to the terms is a new version on
the token. Only terms in the latest version confirmed by the other party reach the engine; until then the checks that need them
read UNRESOLVED.</p>
<div class="scroll"><table><thead><tr><th>Contract</th><th>Who confirms</th><th>Its confirmation also verifies</th></tr></thead>
<tbody>{token_table()}</tbody></table></div>
<p class="note">A reported adverse event — the contractor insolvent, power or support revoked, certification suspended — applies at
once and blocks the gates it undermines; clearing it needs a confirmation.</p>
<div class="scroll"><table><thead><tr><th>Check</th><th>What is compared</th><th>Gate</th></tr></thead>
<tbody>{checks_table()}</tbody></table></div>
<p class="note">Numeric equality allows {E.COHERENCE_TOLERANCE * 100:g} % for rounding in a model — not a margin for error.
COMMERCIALLY PLAUSIBLE also needs offtake terms covering at least {E.OFFTAKE_COVERAGE_MIN_PCT:g} % of planned output.</p>

<h2 id="ladder">The ladder</h2>
<p>Nine states, strictly in order: no state is reachable without every gate of every state before it.</p>
<div class="scroll"><table><thead><tr><th>State</th><th>What must be satisfied</th><th>Capital decision made eligible</th></tr></thead>
<tbody>{ladder()}</tbody></table></div>

<h2 id="backwards">What moves a project backwards</h2>
<ul>
<li>A verified item replaced by a new document, rejected, or withdrawn.</li>
<li>A cross-contract check that fails, or a term change not yet confirmed.</li>
<li>A counterparty or reviewer disputing terms it had confirmed.</li>
<li>A premise contested or rejected.</li>
<li>An adverse event: insolvency, revoked power or support, suspended certification.</li>
</ul>
<p>Each names the gate responsible, and the capital eligibility it carried is withdrawn.</p>

<h2 id="reports">Re-evaluation, reports and who sees what</h2>
<p>Every change that can move a gate — evidence, a document, a premise, a contract term, a confirmation — re-evaluates the project
at once. When the state or a gate's answer changes, the project's designated executives are notified; by default the owner's
executives. Each project has a report showing its state, the share of evidence verified, and every open item side by side —
evidence to verify, commitments not reached, contracts that disagree, data missing — each with its owner, due date and what it
holds back.</p>
<p>Each party sees the gates that concern its role. The project's state and overall figure always cover every gate, and the screen
says so when a viewer sees fewer.</p>

<h2 id="never">What GEX never does</h2>
<ul class="never">
<li>Verify a party's evidence, or confirm a party's terms.</li>
<li>Commit, release or draw capital. A state makes a decision eligible; the capital provider decides.</li>
<li>Let a gate stand in for a lender's, investor's or grant authority's own approval.</li>
<li>Show a figure the engine did not compute from verified evidence.</li>
</ul>

<h2 id="gates">The twelve gates</h2>
<p>Readiness gates test what can be true at their stage — indicative terms, a feasible pathway, confirmed insurability; every
instrument they rely on must be executed at financial close. Achievement gates require the achievement itself.</p>
{gates}
<p class="stamp">Generated from pf_engine evidence rules {h(E.EVIDENCE_RULES_VERSION)}, app.core.abac and app.core.contract_tokens
on {date.today().isoformat()} by backend/scripts/export_gex_process.py.</p>
</main>
</div>
"""


def blocks(page_html: str) -> list[dict]:
    """The page as blocks for gex_process_docx.cjs. Parses only markup this file writes."""
    from bs4 import BeautifulSoup, NavigableString

    def runs(el, fmt=None) -> list[dict]:
        fmt = fmt or {}
        out: list[dict] = []
        for c in el.children:
            if isinstance(c, NavigableString):
                raw = str(c)
                t = " ".join(raw.split())
                t = (" " if raw[:1].isspace() and t else "") + t + (" " if raw[-1:].isspace() else "")
                if t:
                    out.append({"text": t, **fmt})
                continue
            if c.name == "br":
                out.append({"br": True})
                continue
            f = dict(fmt)
            cls = c.get("class") or []
            if c.name in ("b", "strong") or "lvl" in cls:
                f["b"] = True
            if c.name == "i":
                f["i"] = True
            if "mono" in cls:
                f["mono"] = True
            if "muted" in cls:
                f["muted"] = True
            for tone in ("deal_killer", "warning"):
                if f"sev-{tone}" in cls:
                    f["tone"], f["b"] = tone, True
            out += runs(c, f)
            if "lvl" in cls:
                out.append({"text": " —", **fmt})
        return out

    soup = BeautifulSoup(page_html, "html.parser")
    out: list[dict] = []

    def walk(el):
        for c in el.children:
            if isinstance(c, NavigableString) or c.name in ("nav", "style", "title", "link", "meta"):
                continue
            cls = c.get("class") or []
            if c.name in ("h1", "h2", "h3"):
                out.append({"t": c.name, "runs": runs(c)})
            elif c.name == "p":
                out.append({"t": "p", "style": cls[0] if cls else None, "runs": runs(c)})
            elif c.name in ("ol", "ul"):
                out.append({"t": c.name, "items": [runs(li) for li in c.find_all("li", recursive=False)]})
            elif c.name == "table":
                out.append({"t": "table", "head": [th.get_text(" ", strip=True) for th in c.select("thead th")],
                            "rows": [[runs(td) for td in tr.find_all("td")] for tr in c.select("tbody tr")]})
            elif c.name == "div" and "det" in cls:
                out.append({"t": "det", "items": [runs(d) for d in c.find_all("div", recursive=False)]})
            elif c.name == "header" and "gate-head" in cls:
                gid, kind = c.select_one(".gate-id").get_text(), c.select_one(".gate-kind").get_text()
                out.append({"t": "h3", "runs": [{"text": f"{gid}  ", "mono": True},
                                                {"text": c.h3.get_text()}, {"text": f"   {kind}", "muted": True}]})
            elif c.name == "dl":
                out.append({"t": "facts", "items": [[d.dt.get_text(), runs(d.dd)] for d in c.find_all("div")]})
            else:
                walk(c)

    walk(soup)
    return out


if __name__ == "__main__":
    import json

    args = [a for a in sys.argv[1:] if a != "--json"]
    json_out = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
    if json_out:
        args.remove(str(sys.argv[sys.argv.index("--json") + 1]))
    out = Path(args[0]) if args else HERE.parent.parent / "docs" / "GEX_Process.html"
    content = page()
    out.write_text(content)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    if json_out:
        json_out.write_text(json.dumps({"rules": E.EVIDENCE_RULES_VERSION, "date": date.today().isoformat(),
                                        "blocks": blocks(content)}, ensure_ascii=False))
        print(f"wrote {json_out}")
