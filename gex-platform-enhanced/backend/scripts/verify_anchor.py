#!/usr/bin/env python
"""
Verify contract records against the public ledger (Phase 4 of "One contract record").

    set -a && source .env && set +a
    venv/bin/python scripts/verify_anchor.py                   # every contract record
    venv/bin/python scripts/verify_anchor.py --contract <id>   # one
    venv/bin/python scripts/verify_anchor.py --json            # the full report

For each contract: re-computes its event chain from the record (each event by its own
hash scheme), checks the outbox row of every event against the record, recomputes
the pseudonymous id from the salt, and for every ANCHORED event reads the topic from
the PUBLIC MIRROR NODE and checks that the FIRST message carrying the event hash is
the one recorded, with exactly the expected five-key payload and the recorded
consensus timestamp. Later messages carrying the same hash (a crash between the
ledger's acceptance and the outbox update, Q11) are reported as duplicates, not
failures. Rows not anchored are listed, never counted as verified.

Reads only: as PLATFORM_ADMIN on the runtime connection (logged by _tenant_context),
and the mirror node over HTTPS. Exit 0 all verified; 1 a problem found; 2 unreachable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def collect(contract_id=None) -> list[dict]:
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record

    conn = market_connection(company_id=PLATFORM_ADMIN)
    try:
        where, params = ("AND id = ?", (contract_id,)) if contract_id else ("", ())
        out = []
        for c in record._rows(conn, "SELECT id, contract_ref, pseudo_id FROM tb_contract "
                                    f"WHERE contract_type = 'terms' {where} ORDER BY created_at", params):
            out.append({**c, "events": record.events(conn, str(c["id"])),
                        "outbox": record._rows(conn, "SELECT * FROM ledger_anchor_outbox WHERE contract_id = ? "
                                                     "ORDER BY id", (str(c["id"]),))})
        return out
    finally:
        conn.close()


def main(argv=None, anchor=None) -> int:
    from app.core import ledger_anchor as la
    from app.core.config import settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contract")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        contracts = collect(args.contract)
    except Exception as exc:  # noqa: BLE001
        print(f"database unreachable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    topics = {o["ledger_topic_id"] for c in contracts for o in c["outbox"] if o["status"] == "ANCHORED"}
    ledger: dict = {}
    if topics:
        anchor = anchor or la.anchor_from_settings(settings)
        try:
            for t in topics:
                for h, msgs in la.index_messages(anchor.messages(t)).items():
                    ledger.setdefault(h, []).extend(msgs)
        except Exception as exc:  # noqa: BLE001
            print(f"mirror node unreachable: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    reports = [la.verify_contract(c["contract_ref"], c["pseudo_id"], c["events"], c["outbox"], ledger,
                                  salt=settings.LEDGER_ANCHOR_SALT or None) for c in contracts]
    if args.json:
        print(json.dumps(reports, indent=2, default=str))
    else:
        for r in reports:
            dup = sum(len(e["duplicates"]) for e in r["events"])
            print(f"{r['contract_ref']}: chain {'intact' if r['chain_intact'] else 'BROKEN'}, "
                  f"{r['anchored']}/{len(r['events'])} anchored"
                  + (f", {dup} duplicate message(s)" if dup else "")
                  + ("" if r["ok"] else "  PROBLEMS: " + "; ".join(r["problems"])))
    return 0 if all(r["ok"] for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
