#!/usr/bin/env python3
"""
validate_fortaverde_knowledge.py — check a FortaVerde knowledge JSON against the running rules.

Writes nothing. Run before any loader reads the file:

    python scripts/validate_fortaverde_knowledge.py path/to/fortaverde_knowledge_v2.json

Checks, against the engine (pf_engine, never `app`):
  * every evidence_key exists, and sits in the gate the claim names
  * maturity_claimed uses MATURITY_LEVELS
  * no claim is anything but UNVERIFIED (GEX verifies nothing itself)
  * every source_id, claim_id and contradiction reference resolves; ids are unique
  * project context values are valid platform values
  * commitment card fields are COMMITMENT_CARD_FIELDS fields
  * no contact is marked as a platform account
Exit 0 when clean, 1 with a list of problems otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_POWER = ("OFF_GRID_BTM", "GRID_CONNECTED", "HYBRID")
VALID_PHASES = ("development", "construction", "commissioning", "operating")
VALID_FINANCING = ("PROJECT_FINANCE", "BALANCE_SHEET")


def _engine():
    engine_backend = str(Path(__file__).resolve().parents[3] / "gex_pf_engine" / "backend")
    if engine_backend not in sys.path:
        sys.path.insert(0, engine_backend)
    from pf_engine.core import bankability_engine  # type: ignore

    return bankability_engine


def validate(doc: dict) -> list[str]:
    be = _engine()
    gate_of = {k: g["gate_id"].split("_")[0] for g in be.GATES for k in g["required_evidence"]}
    problems: list[str] = []

    source_ids = [s["source_id"] for s in doc.get("sources", [])]
    claim_ids = [c["claim_id"] for c in doc.get("claims", [])]
    for label, ids in (("source_id", source_ids), ("claim_id", claim_ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"duplicate {label}: {sorted(dupes)}")

    for c in doc.get("claims", []):
        cid, key, gate = c["claim_id"], c.get("evidence_key"), c.get("gate")
        if key is not None:
            if key not in gate_of:
                problems.append(f"{cid}: evidence_key '{key}' is not in the engine")
            elif gate and gate_of[key] != gate:
                problems.append(f"{cid}: '{key}' belongs to {gate_of[key]}, claim says {gate}")
        m = c.get("maturity_claimed")
        if m is not None and m not in be.MATURITY_LEVELS:
            problems.append(f"{cid}: maturity_claimed '{m}' not in {be.MATURITY_LEVELS}")
        if "declared_maturity" in c:
            problems.append(f"{cid}: 'declared_maturity' is the submitter's field; use maturity_claimed")
        if c.get("verification_state") != "UNVERIFIED":
            problems.append(f"{cid}: verification_state must be UNVERIFIED, is {c.get('verification_state')}")
        for s in c.get("source_ids", []):
            if s not in source_ids:
                problems.append(f"{cid}: unknown source {s}")
        if not c.get("source_ids"):
            problems.append(f"{cid}: no source")

    for x in doc.get("contradictions", []):
        for r in x.get("claim_ids", []):
            if r not in claim_ids:
                problems.append(f"{x['id']}: unknown claim {r}")
    for q in doc.get("open_questions", []):
        for k in q.get("evidence_keys", []):
            if k not in gate_of:
                problems.append(f"{q['id']}: evidence_key '{k}' is not in the engine")
        for r in q.get("claim_ids", []):
            if r not in claim_ids:
                problems.append(f"{q['id']}: unknown claim {r}")
    for f in doc.get("funding", []) + doc.get("offtake_prospects", []):
        for r in f.get("claim_ids", []):
            if r not in claim_ids:
                problems.append(f"funding/offtake entry: unknown claim {r}")

    ctx = (doc.get("project") or {}).get("context") or {}
    for field, valid in (("power_model", VALID_POWER), ("phase", VALID_PHASES), ("financing_model", VALID_FINANCING)):
        v = (ctx.get(field) or {}).get("value")
        if v not in valid:
            problems.append(f"project.context.{field} '{v}' not in {valid}")

    cards = doc.get("commitment_cards") or {}
    for card, terms in cards.items():
        if card == "load_after":
            continue
        allowed = be.COMMITMENT_CARD_FIELDS.get(card)
        if allowed is None:
            problems.append(f"commitment card '{card}' is not a card type")
            continue
        for f in terms:
            if f not in allowed:
                problems.append(f"commitment_cards.{card}.{f} is not a card field")

    for p in doc.get("contacts", []):
        if p.get("is_platform_account"):
            problems.append(f"{p['contact_id']}: contacts are not platform accounts")

    return problems


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, list):
        print(f"  {path.name}: a bare list of claims, schema v1 — no company, contacts, funding,\n"
              "  contradictions or project context. Checking the claims only.\n")
        doc = {"claims": doc, "sources": []}
    problems = validate(doc)
    for p in problems:
        print(f"  - {p}")
    print(f"\n  {path.name}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
