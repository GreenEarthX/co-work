#!/usr/bin/env python3
"""validate_pathway.py — validate a GEX .pathway.yaml and round-trip it into
the efuel_truth_stack ledger.

This is the cheap test of the central architectural bet (Play #2): that a GEX
canonical pathway object binds cleanly to the *existing* truth-stack primitives
(Claim, CanonicalLedgerEntry, Node, ApprovalRequirement) and the 9-state
ClaimState machine — with no new ledger, no new state engine.

It runs two passes:

  PASS A — Level-1 structural validation (the bottom rung of the 6-level ladder)
    · required top-level sections present
    · every {claim: X} reference resolves to a declared claim id
    · every node.required_claims / gate.required_claims id resolves
    · the node dependency graph (depends_on) is acyclic
    · gate.validation_level is within the declared ladder

  PASS B — truth-stack round-trip (proves the binding)
    · each pathway claim → efuel_truth_stack.models.Claim   (validates ValueType,
      ClaimState enum membership, dates, evidence links)
    · the TEA run → CanonicalLedgerEntry via new_entry(projection_snapshot),
      appended to a Ledger (proves auto-hash + append-only immutability)
    · each pathway node → models.Node, then rollup_nodes() over the claims
      (proves the projection layer accepts the pathway's claims)
    · each gate.approval → models.ApprovalRequirement

Exit 0 on PASS, 1 on FAIL. Usage:
    python schemas/validate_pathway.py schemas/examples/breizh_emethanol.pathway.yaml
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# --- make efuel_truth_stack importable regardless of cwd --------------------
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "efuel_truth_stack"))

from efuel_truth_stack import Ledger, new_entry  # noqa: E402
from efuel_truth_stack.enums import (  # noqa: E402
    ClaimState, EntryType, Layer, ValueType, is_terminal_valid,
)
from efuel_truth_stack.models import (  # noqa: E402
    ApprovalRequirement,
    Claim,
    EvidenceLink,
    Node,
)
from efuel_truth_stack.projectors import NODES, rollup_nodes  # noqa: E402

REQUIRED_SECTIONS = ["metadata", "claims", "nodes", "engineering", "tea", "gates"]
LADDER = [
    "structural", "mass_energy", "tea_lca_plausible",
    "certification_fit", "finance_cp_cost", "measured_recon",
]


class Report:
    def __init__(self) -> None:
        self.checks: list[tuple[bool, str, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append((True, name, detail))

    def fail(self, name: str, detail: str) -> None:
        self.checks.append((False, name, detail))

    @property
    def passed(self) -> bool:
        return all(c[0] for c in self.checks)

    def render(self) -> str:
        lines = []
        for ok, name, detail in self.checks:
            mark = "PASS" if ok else "FAIL"
            lines.append(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        verdict = "PASS" if self.passed else "FAIL"
        lines.append(f"\n  ==> {verdict} ({sum(c[0] for c in self.checks)}/{len(self.checks)} checks)")
        return "\n".join(lines)


def _claim_refs(obj: Any):
    """Yield every claim id referenced via a {claim: <id>} mapping, recursively."""
    if isinstance(obj, dict):
        if set(obj.keys()) == {"claim"}:
            yield obj["claim"]
        else:
            for v in obj.values():
                yield from _claim_refs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _claim_refs(v)


def _has_cycle(adj: dict[str, list[str]]) -> list[str] | None:
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}

    def dfs(n: str, stack: list[str]) -> list[str] | None:
        color[n] = GREY
        for m in adj.get(n, []):
            if m not in color:
                continue  # dangling edge handled elsewhere
            if color[m] == GREY:
                return stack + [n, m]
            if color[m] == WHITE:
                r = dfs(m, stack + [n])
                if r:
                    return r
        color[n] = BLACK
        return None

    for n in adj:
        if color[n] == WHITE:
            r = dfs(n, [])
            if r:
                return r
    return None


def validate(doc: dict) -> Report:
    r = Report()

    # ---- PASS A: structural (Level 1) --------------------------------------
    missing = [s for s in REQUIRED_SECTIONS if s not in doc]
    if missing:
        r.fail("A1 required sections", f"missing: {missing}")
        return r  # nothing else is meaningful without the spine
    r.ok("A1 required sections", f"{len(REQUIRED_SECTIONS)} present")

    claims = {c["id"]: c for c in doc["claims"]}
    nodes = {n["id"]: n for n in doc["nodes"]}

    # claim-ref resolution
    unresolved = sorted({cid for cid in _claim_refs(doc) if cid not in claims})
    if unresolved:
        r.fail("A2 claim refs resolve", f"dangling: {unresolved}")
    else:
        r.ok("A2 claim refs resolve", f"{len(claims)} claims, all refs bind")

    # gate.required_claims are claim IDS → must resolve to declared claims
    bad_gate = []
    for g in doc["gates"]:
        bad_gate += [(g["gate_id"], c) for c in g.get("required_claims", []) if c not in claims]
    if bad_gate:
        r.fail("A3 gate.required_claims resolve", f"dangling ids: {bad_gate}")
    else:
        r.ok("A3 gate.required_claims resolve", f"{len(doc['gates'])} gates")

    # node.required_claims are claim TYPES → mirror efuel_truth_stack Node;
    # each must be a real claim_type declared by a claim on that node.
    declared_by_node: dict[str, set[str]] = {}
    for c in doc["claims"]:
        declared_by_node.setdefault(c["subject_node"], set()).add(c["claim_type"])
    bad_node = []
    for n in doc["nodes"]:
        for ct in n.get("required_claims", []):
            if ct not in declared_by_node.get(n["id"], set()):
                bad_node.append((n["id"], ct))
    if bad_node:
        r.fail("A3b node.required_claims declared", f"no claim provides: {bad_node}")
    else:
        r.ok("A3b node.required_claims declared", "every node requirement has a claim")

    # node DAG acyclic + depends_on targets exist
    adj = {n["id"]: list(n.get("depends_on", [])) for n in doc["nodes"]}
    dangling_dep = sorted({d for deps in adj.values() for d in deps if d not in nodes})
    if dangling_dep:
        r.fail("A4 depends_on targets exist", f"unknown: {dangling_dep}")
    else:
        r.ok("A4 depends_on targets exist", f"{len(nodes)} nodes")
    cycle = _has_cycle(adj)
    if cycle:
        r.fail("A5 node DAG acyclic", f"cycle: {' -> '.join(cycle)}")
    else:
        r.ok("A5 node DAG acyclic", "no cycles")

    # gate validation_level within ladder
    declared = doc.get("validation_ladder", {}).get("levels", LADDER)
    lvl_bad = [g["gate_id"] for g in doc["gates"]
               if not (isinstance(g.get("validation_level"), int)
                       and 1 <= g["validation_level"] <= len(declared))]
    if lvl_bad:
        r.fail("A6 gate validation_level", f"out of 1..{len(declared)}: {lvl_bad}")
    else:
        r.ok("A6 gate validation_level", f"ladder depth {len(declared)}")

    # ---- PASS B: truth-stack round-trip ------------------------------------
    # B1: every pathway claim -> models.Claim (enum + type validation)
    built: dict[str, Claim] = {}
    try:
        for cid, c in claims.items():
            built[cid] = Claim(
                id=cid,
                subject_node=c["subject_node"],
                claim_type=c["claim_type"],
                value_type=ValueType(c["value_type"]),
                value=c.get("value"),
                unit=c.get("unit"),
                state=ClaimState(c["state"]),
                period=c.get("period"),
                valid_from=c["valid_from"],
                valid_to=c.get("valid_to"),
                evidence_refs=[EvidenceLink(**e) for e in c.get("evidence_refs", [])],
                authority_rule=c.get("authority_rule", ""),
            )
        r.ok("B1 claims -> truth-stack Claim", f"{len(built)} claims, states valid")
    except Exception as e:  # noqa: BLE001
        r.fail("B1 claims -> truth-stack Claim", f"{type(e).__name__}: {e}")

    # B2: TEA run -> CanonicalLedgerEntry, appended (auto-hash + immutability)
    try:
        ledger = Ledger()
        entry = new_entry(
            project_id=doc["metadata"]["project_id"],
            entry_type=EntryType.PROJECTION_SNAPSHOT,   # kind=derived inferred
            produced_by="tea_engine",
            valid_from=doc["claims"][0]["valid_from"],
            recorded_at=datetime.now(timezone.utc),
            payload={"cost_basis_hash": doc["tea"]["cost_basis_hash"],
                     "engine": "openpytea"},
        )
        ledger.append(entry)
        assert entry.hash, "entry hash not computed"
        immutable = False
        try:
            ledger.append(entry)            # re-append must be rejected
        except Exception:                   # noqa: BLE001
            immutable = True
        if immutable:
            r.ok("B2 TEA run -> ledger entry", f"hash={entry.hash[:12]}…, append-only enforced")
        else:
            r.fail("B2 TEA run -> ledger entry", "ledger accepted a duplicate (not immutable)")
    except Exception as e:  # noqa: BLE001
        r.fail("B2 TEA run -> ledger entry", f"{type(e).__name__}: {e}")

    # B3: pathway nodes -> models.Node (Layer enum validation only)
    try:
        for n in doc["nodes"]:
            Node(id=n["id"], layer=Layer(n["layer"]), label=n.get("label", ""),
                 depends_on=n.get("depends_on", []),
                 required_claims=n.get("required_claims", []))
        r.ok("B3 nodes -> models.Node", f"{len(doc['nodes'])} nodes, layers valid")
    except Exception as e:  # noqa: BLE001
        r.fail("B3 nodes -> models.Node", f"{type(e).__name__}: {e}")

    # B5: claims bind to the CANONICAL truth-stack vocabulary.
    #     rollup_nodes is hardwired to the spec's node registry (projectors.NODES);
    #     a pathway only folds if its (subject_node, claim_type) pairs are members
    #     of that registry. This is the check that prevents vocabulary entropy.
    unbound = []
    for cid, c in claims.items():
        sn, ct = c["subject_node"], c["claim_type"]
        if sn not in NODES:
            unbound.append(f"{cid}: node '{sn}' not in registry")
        elif ct not in NODES[sn].get("required_claims", []):
            unbound.append(f"{cid}: '{ct}' not a required_claim of '{sn}'")
    if unbound:
        r.fail("B5 claims bind to canonical spine", "; ".join(unbound))
    else:
        r.ok("B5 claims bind to canonical spine", f"{len(claims)} claims on registry nodes")

    # B6: rollup actually fires — at least one canonical node goes non-None when
    #     the pathway's claims are folded through the real projector.
    try:
        rolled = rollup_nodes(built) if built else {}
        green = {nid: n.rolled_up_state.value for nid, n in rolled.items()
                 if n.rolled_up_state is not None}
        if green:
            r.ok("B6 rollup fires on pathway", f"{len(green)} nodes rolled up: {green}")
        else:
            r.fail("B6 rollup fires on pathway",
                   "no canonical node rolled up — claims not bound to registry (see B5)")
    except Exception as e:  # noqa: BLE001
        r.fail("B6 rollup fires on pathway", f"{type(e).__name__}: {e}")

    # B4: gate.approval -> models.ApprovalRequirement
    try:
        for g in doc["gates"]:
            a = g["approval"]
            ApprovalRequirement(
                check_id=a["check_id"],
                required_actor=a["required_actor"],
                waivable=a.get("waivable", True),
                veto_right=a.get("veto_right", False),
                drawstop_right=a.get("drawstop_right", False),
            )
        r.ok("B4 gates -> ApprovalRequirement", f"{len(doc['gates'])} gates")
    except Exception as e:  # noqa: BLE001
        r.fail("B4 gates -> ApprovalRequirement", f"{type(e).__name__}: {e}")

    # A7: every evidence_ref / run_evidence resolves to a declared evidence entry
    ev_ids = {e["id"] for e in doc.get("evidence_entries", [])}
    if ev_ids:
        referenced = {er["ledger_entry_id"] for c in doc["claims"]
                      for er in c.get("evidence_refs", [])}
        if "run_evidence" in doc.get("tea", {}):
            referenced.add(doc["tea"]["run_evidence"])
        dangling = sorted(referenced - ev_ids)
        if dangling:
            r.fail("A7 evidence refs resolve", f"undeclared entries: {dangling}")
        else:
            r.ok("A7 evidence refs resolve", f"{len(ev_ids)} entries, all refs bind")

    # B7: COMPUTE AUTHORIZATION guard — no release-gated gate may be open while
    #     the model_base_case is still provisional (not terminal-valid).
    try:
        ca = doc.get("compute_authorization", {})
        bc_id = (ca.get("base_case_claim", {}) or {}).get("claim")
        if not bc_id:
            bc_id = next((cid for cid, c in claims.items()
                          if c["claim_type"] == "model_base_case"), None)
        bc_terminal = bool(bc_id) and is_terminal_valid(ClaimState(claims[bc_id]["state"]))
        mode = "RELEASE-READY" if bc_terminal else "PROVISIONAL"

        def _gate_openable(g):
            return all(is_terminal_valid(ClaimState(claims[c]["state"]))
                       for c in g.get("required_claims", []) if c in claims)

        violations = [g["gate_id"] for g in doc["gates"]
                      if g.get("blocks_release_until") and _gate_openable(g) and not bc_terminal]
        if violations:
            r.fail("B7 release-gate guard",
                   f"release-gated {violations} open while base case PROVISIONAL")
        else:
            ready = [g["gate_id"] for g in doc["gates"]
                     if g.get("blocks_release_until") and _gate_openable(g)]
            r.ok("B7 release-gate guard", f"compute mode={mode}; release-ready gates={ready or 'none'}")
    except Exception as e:  # noqa: BLE001
        r.fail("B7 release-gate guard", f"{type(e).__name__}: {e}")

    # B8: supersession lineage — supersedes_claim target exists and is SUPERSEDED
    bad_lineage = []
    for cid, c in claims.items():
        tgt = c.get("supersedes_claim")
        if tgt is None:
            continue
        if tgt not in claims:
            bad_lineage.append(f"{cid} supersedes missing {tgt}")
        elif claims[tgt]["state"] != ClaimState.SUPERSEDED.value:
            bad_lineage.append(f"{cid} supersedes {tgt} but it is '{claims[tgt]['state']}', not superseded")
    if bad_lineage:
        r.fail("B8 supersession lineage", "; ".join(bad_lineage))
    else:
        n = sum(1 for c in claims.values() if c.get("supersedes_claim"))
        r.ok("B8 supersession lineage", f"{n} superseding claim(s), lineage consistent")

    # B9: each evidence entry -> CanonicalLedgerEntry (kind admits entry_type)
    try:
        first_vf = doc["claims"][0]["valid_from"]
        for e in doc.get("evidence_entries", []):
            new_entry(project_id=doc["metadata"]["project_id"],
                      entry_type=EntryType(e["entry_type"]),
                      produced_by=e["produced_by"],
                      valid_from=first_vf,
                      recorded_at=datetime.now(timezone.utc),
                      payload={"summary": e.get("summary", "")})
        r.ok("B9 evidence -> ledger entries", f"{len(doc.get('evidence_entries', []))} entries, kinds admit types")
    except Exception as e:  # noqa: BLE001
        r.fail("B9 evidence -> ledger entries", f"{type(e).__name__}: {e}")

    return r


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    doc = yaml.safe_load(path.read_text())
    print(f"Validating {path} against gex_pathway.schema.yaml\n")
    report = validate(doc)
    print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
