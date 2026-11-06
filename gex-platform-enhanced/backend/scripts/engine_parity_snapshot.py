"""
Gate-engine parity snapshot — READ ONLY (JML 2026-11-05, "One contract record").

Every phase of the contract-record work must leave the engine's answer for every
stored project unchanged. This evaluates each project exactly as
routes_bankability_proxy.reevaluate does (same evidence, same context, same
terms path) but stores nothing: no snapshot, no ledger event, no gate clock, no
notification. It writes the comparable part of each answer to --out, and with
--compare it diffs against an earlier file and exits 1 on any difference.

Compared per project: the WHOLE engine answer except its two timestamps — state,
every gate's determination, counts and blocking items, the offtake and EPC
readouts, every coherence check (C1–C10) and commitment check. Run before and
after on the same day: expiry-dependent fields move with the date. Runs as PLATFORM_ADMIN
(a system read across tenants, logged by _tenant_context), like the expiry sweep.

    python scripts/engine_parity_snapshot.py --out before.json
    python scripts/engine_parity_snapshot.py --out after.json --compare before.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VOLATILE = ("evaluated_at", "as_of")


def comparable(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k not in VOLATILE}


async def evaluate_all() -> dict:
    from app.api.v1 import routes_bankability_proxy as proxy
    from app.core.projects_store import _rows
    from app.core.request_tenant import reset_current_company, set_current_company

    token = set_current_company("PLATFORM_ADMIN")
    try:
        ids = [r["project_id"] for r in _rows("SELECT project_id FROM projects ORDER BY project_id", {})]
        out = {}
        for pid in ids:
            snap = await proxy._call_engine("/evaluate", method="POST", json_data={
                "project_id": pid, "evidence": proxy._load_evidence(pid),
                **proxy._engine_context(pid)})
            out[pid] = comparable(snap)
        return out
    finally:
        reset_current_company(token)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare")
    ap.add_argument("--keys", action="store_true", help="print one raw snapshot's top-level keys and stop")
    args = ap.parse_args()
    if args.keys:
        from app.api.v1 import routes_bankability_proxy as proxy
        from app.core.request_tenant import set_current_company
        set_current_company("PLATFORM_ADMIN")
        pid = "proj_TEST_gates_reference"
        snap = asyncio.run(proxy._call_engine("/evaluate", method="POST", json_data={
            "project_id": pid, "evidence": proxy._load_evidence(pid), **proxy._engine_context(pid)}))
        print(sorted(snap.keys()))
        print(sorted((snap.get("gate_evaluations") or [{}])[0].keys()))
        return 0
    result = asyncio.run(evaluate_all())
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print(f"{len(result)} projects evaluated -> {args.out}")
    if args.compare:
        before = json.loads(Path(args.compare).read_text())
        diffs = [pid for pid in sorted(set(before) | set(result)) if before.get(pid) != result.get(pid)]
        if diffs:
            print("PARITY FAILED:", ", ".join(diffs))
            return 1
        print(f"parity: identical for all {len(result)} projects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
