#!/usr/bin/env python3
"""
load_comprehension_test_project.py — the gates comprehension-test fixture.
=========================================================================
Loads the synthetic reference project of
`docs/usability/gates_first_use_comprehension_test.md` (Appendix A) so a test
participant can log in and read it, and verifies that what the engine computes
for it equals the published answer key (Appendix B).

WHY THIS EXISTS
---------------
Every live project sits at SPECULATIVE with nothing verified, which makes the
comprehension tasks trivial — "where does this project stand?" has the same
answer everywhere. The test needs a project mid-ladder: four gates satisfied,
one coherence check failing, offtake coverage just below the bar.

JML chose the labelled-TEST-project route (2026-10-02) over restoring a backup
into a throwaway database.

WHAT IT WRITES, AND WHY THAT IS NOT INVENTED EVIDENCE
-----------------------------------------------------
One project, its context, its five commitment cards and ~50 VERIFIED evidence
rows. Those rows are SYNTHETIC and say so: every one carries
`submitted_by = TEST_FIXTURE_COMPREHENSION`, the same marker in `verified_by`,
and a note naming this script. The marker is how you find them, exactly as
`SEED_GRANDFATHERED` marks the unvetted accounts.

They are not a client's submissions and must never be read as any: the project
is named TEST, owned by a demo tenant, and carries no document hashes — the
2026-09-26 rule stands, that no archived or seeded row is a client submission.
`--remove` deletes every row this script wrote, by project id.

The evidence LIST is derived from the running engine (`GATES`,
`REQUIRED_MATURITY`, `_evidence_applies`), never hand-typed, so it cannot drift
from the rules the test is about.

WHO CAN SEE IT
--------------
Owner `hamburgone_com`, so the HamburgOne demo accounts (Lisa Friedrich and
colleagues) see it. A runtime project grants nothing to other companies at the
ABAC level — `project_registry._runtime_profile` returns no associated
companies — so bank and insurer accounts cannot open it. All participants use
the producer executive account; the script says so again when it finishes.

USAGE
    export ALEMBIC_DATABASE_URL=...        # gex_user: this writes data
    python scripts/load_comprehension_test_project.py              # dry run
    python scripts/load_comprehension_test_project.py --execute
    python scripts/load_comprehension_test_project.py --verify     # engine vs key
    python scripts/load_comprehension_test_project.py --remove --execute

Idempotent: --execute deletes this project's own rows first, then writes them.
No other project is touched; every statement is scoped to PROJECT_ID.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PROJECT_ID = "proj_TEST_gates_reference"
PROJECT_NAME = "TEST — Gates Comprehension Reference (synthetic)"
OWNER_TENANT = "hamburgone_com"
MARKER = "TEST_FIXTURE_COMPREHENSION"
POWER_MODEL, PHASE, FINANCING_MODEL = "GRID_CONNECTED", "FEED", "PROJECT_FINANCE"
PLANNED_OUTPUT = 50_000

# Appendix A. Gates whose every applicable item is verified, then the two
# partial gates. Maturity comes from the engine's REQUIRED_MATURITY unless named
# here, because the point of an item like the offtake is its declared maturity.
FULL_GATES = ("G0", "G1", "G2", "G3")
PARTIAL = {
    "binding_offtake_contract_executed": "INDICATIVE",   # heads of terms
    "feed_complete_class3": None,
    "epc_contract_fixed_price_or_capped_gmp": "INDICATIVE",  # a priced proposal
}
OVERRIDE_MATURITY = {"land_option_or_lease_executed": "EXECUTED"}

CARDS = {
    "offtake": {
        "counterparty_name": "TEST Buyer GmbH", "counterparty_role": "OBLIGATED_SUPPLIER",
        "planned_output_tonnes_per_year": PLANNED_OUTPUT,
        "contracted_tonnes_per_year": 27_500,          # 55% — just under the 60% bar
        "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 70,
        "tenor_years": 10, "buyer_investment_grade": True,
    },
    "epc": {
        "contracting_model": "LSTK",
        "guaranteed_capacity_tonnes_per_year": PLANNED_OUTPUT,
        "expected_availability_pct": 90,
    },
    "supply": {                                         # C6 fails on both counts
        "feedstock_required_tonnes_per_year": 70_000,
        "feedstock_contracted_tonnes_per_year": 60_000,
        "feedstock_tenor_years": 8,
    },
    "schedule": {},
    "model": {},
}

# Appendix B — what the engine must say once this is loaded.
ANSWER_KEY = {
    "state": "TECHNICALLY_PLAUSIBLE",
    "complete_gates": {"G0", "G1", "G2", "G3"},
    "eligible_capital": {"Grants & TA", "Seed / VC / Angel", "Strategic Equity"},
    "offtake_level": "O2", "offtake_coverage_pct": 55.0, "offtake_effective": False,
    "epc_level": "E3",
    "failing_checks": {"C6"},
    "blocked_next": "offtake_coverage",
}


def _engine():
    """The runtime engine (:8001), the authority on gate scope and maturity.

    Imported as `pf_engine`, never as `app`: both trees define a top-level `app`
    package and the sibling's `app/__init__.py` refuses to alias when this
    backend is also on sys.path — whichever loaded first would silently supply
    the wrong service's modules.
    """
    engine_backend = str(Path(__file__).resolve().parents[3] / "gex_pf_engine" / "backend")
    if engine_backend not in sys.path:
        sys.path.insert(0, engine_backend)
    from pf_engine.core import bankability_engine  # type: ignore

    return bankability_engine


def evidence_rows() -> list[tuple[str, str | None]]:
    """(evidence_key, maturity) from the ENGINE, so the fixture cannot drift."""
    be = _engine()
    items_of = {g["gate_id"]: list(g["required_evidence"]) for g in be.GATES}
    applies = lambda k: be._evidence_applies(k, POWER_MODEL)  # noqa: E731
    maturity_of = be.REQUIRED_MATURITY

    rows: list[tuple[str, str | None]] = []
    for gate_id, keys in items_of.items():
        # Split on "_" — never a character prefix. "G10_FINANCIAL_CLOSE_CP"[:2]
        # is "G1", which quietly pulled all of G10's and G11's items into the
        # fixture and made both gates complete with no evidence behind them.
        if gate_id.split("_")[0] not in FULL_GATES:
            continue
        for key in keys:
            if applies(key):
                rows.append((key, OVERRIDE_MATURITY.get(key, maturity_of.get(key))))
    for key, maturity in PARTIAL.items():
        rows.append((key, maturity))
    return rows


def connect():
    import psycopg2
    import psycopg2.extras

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn:
        sys.exit("set ALEMBIC_DATABASE_URL (the gex_user credential) — this script writes data")
    conn = psycopg2.connect(dsn)
    conn.cursor_factory = psycopg2.extras.DictCursor
    return conn


DELETES = [
    ("bankability_evidence", "DELETE FROM bankability_evidence WHERE project_id = %s"),
    ("evidence_events", "DELETE FROM evidence_events WHERE project_id = %s"),
    ("bankability_snapshots", "DELETE FROM bankability_snapshots WHERE project_id = %s"),
    ("commitment_terms", "DELETE FROM commitment_terms WHERE project_id = %s"),
    ("project_access", "DELETE FROM project_access WHERE project_id = %s"),
    ("project_context", "DELETE FROM project_context WHERE project_id = %s"),
    ("projects", "DELETE FROM projects WHERE project_id = %s"),
]


def remove(conn, execute: bool) -> None:
    cur = conn.cursor()
    for table, sql in DELETES:
        cur.execute(f"SELECT count(*) FROM {table} WHERE project_id = %s", (PROJECT_ID,))
        n = cur.fetchone()[0]
        if n:
            print(f"  {'delete' if execute else 'would delete'} {n:3d} from {table}")
            if execute:
                cur.execute(sql, (PROJECT_ID,))
    if execute:
        conn.commit()
        print("  removed.")


def load(conn, execute: bool) -> None:
    rows = evidence_rows()
    undeclared = [k for k, m in rows if m is None]
    print(f"  {len(rows)} evidence items from the engine "
          f"({len(rows) - len(undeclared)} carry a required maturity)")
    print(f"  cards: {', '.join(k for k, v in CARDS.items() if v)}")
    if not execute:
        print("\n  DRY RUN — nothing written. Re-run with --execute.")
        return

    remove(conn, execute=True)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute("""
        INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, status,
                              jurisdiction, capacity_mtpd, location, country, is_active,
                              created_by, created_at, updated_at)
        VALUES (%s,%s,%s,'MEO','development','EU',%s,'Hamburg (synthetic)','DE',true,%s,now(),now())
    """, (PROJECT_ID, PROJECT_NAME, OWNER_TENANT, round(PLANNED_OUTPUT / 365.0, 4), MARKER))

    cur.execute("""
        INSERT INTO project_context (project_id, power_model, phase, financing_model,
                                     updated_by, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (PROJECT_ID, POWER_MODEL, PHASE, FINANCING_MODEL, MARKER, now))

    cur.execute("""
        INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by)
        VALUES (%s,%s,'PRODUCER','OWNER',%s)
    """, (PROJECT_ID, OWNER_TENANT, MARKER))

    for key, maturity in rows:
        cur.execute("""
            INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by,
                                              verified_by, submitted_at, verified_at, notes,
                                              maturity, updated_at)
            VALUES (%s,%s,'VERIFIED',%s,%s,%s,%s,%s,%s,%s)
        """, (PROJECT_ID, key, MARKER, MARKER, now, now,
              "SYNTHETIC comprehension-test fixture — not a client submission. "
              "scripts/load_comprehension_test_project.py", maturity, now))

    for card, terms in CARDS.items():
        if not terms:
            continue
        cur.execute("""
            INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, updated_at)
            VALUES (%s,%s,%s,%s,%s)
        """, (PROJECT_ID, card, json.dumps(terms), MARKER, now))

    conn.commit()
    print(f"  WROTE project, context, access, {len(rows)} evidence rows, "
          f"{sum(1 for v in CARDS.values() if v)} cards.")


def verify() -> int:
    """Evaluate through the engine and compare with the published answer key."""
    be = _engine()
    evidence = [{"key": k, "status": "VERIFIED", "maturity": m} for k, m in evidence_rows()]
    terms = {k: v for k, v in CARDS.items() if v}
    snap = be.evaluate(PROJECT_ID, evidence, None, POWER_MODEL, PHASE, FINANCING_MODEL, terms)

    gates = snap["gate_evaluations"]
    gates = list(gates.values()) if isinstance(gates, dict) else gates
    off, epc = snap.get("offtake", {}), snap.get("epc", {})
    got = {
        "state": snap["current_state"],
        "complete_gates": {g["gate_id"].split("_")[0] for g in gates if g.get("is_complete")},
        "eligible_capital": {c.get("label") for c in snap.get("capital_unlocks", [])
                             if c.get("decision_eligible")},
        "offtake_level": off.get("level"), "offtake_coverage_pct": off.get("coverage_pct"),
        "offtake_effective": off.get("effective"), "epc_level": epc.get("level"),
        "failing_checks": {c["id"] for c in snap.get("coherence_checks", []) if c["status"] == "FAIL"},
        "blocked_next": (snap.get("commitments_blocking_next_state") or [{}])[0].get("kind"),
    }
    bad = {k: (ANSWER_KEY[k], got[k]) for k in ANSWER_KEY if got[k] != ANSWER_KEY[k]}
    for k in ANSWER_KEY:
        mark = "FAIL" if k in bad else "ok  "
        print(f"  [{mark}] {k:22} {got[k]}")
    if bad:
        print("\n  ANSWER KEY MISMATCH — the fixture or Appendix B is wrong:")
        for k, (want, is_) in bad.items():
            print(f"    {k}: key says {want!r}, engine says {is_!r}")
        return 1
    print(f"\n  Matches Appendix B of docs/usability/"
          f"gates_first_use_comprehension_test.md (rules {snap.get('rules_version', '?')}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--remove", action="store_true", help="delete every row this script wrote")
    ap.add_argument("--verify", action="store_true", help="engine vs answer key; writes nothing")
    args = ap.parse_args()

    print(f"\n  project: {PROJECT_ID}  ({PROJECT_NAME})")
    print(f"  owner:   {OWNER_TENANT}   marker: {MARKER}\n")

    if args.verify:
        return verify()

    conn = connect()
    try:
        if args.remove:
            remove(conn, args.execute)
            if not args.execute:
                print("\n  DRY RUN — nothing deleted. Re-run with --execute.")
            return 0
        load(conn, args.execute)
    finally:
        conn.close()

    if args.execute:
        print("\n  Participants log in as a HamburgOne account (the owner); a runtime project\n"
              "  grants nothing to other companies at the ABAC level, so bank and insurer\n"
              "  accounts cannot open it. Remove it with --remove --execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
