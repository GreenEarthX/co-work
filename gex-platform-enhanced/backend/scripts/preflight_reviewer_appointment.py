#!/usr/bin/env python
"""
Preflight a reviewer appointment: every refusal the real appointment would raise, and what the reviewer
would be asked to verify — WITHOUT writing anything. Always rolls back.

    set -a && source .env && set +a
    venv/bin/python scripts/preflight_reviewer_appointment.py \\
        --project proj_hamburgone_emethanol --user <reviewer user id> --role INDEPENDENT_ENGINEER \\
        --instructed-by "NordLB" --instruction-sha256 $(shasum -a 256 instruction.pdf | cut -d' ' -f1)

It calls the same `reviewer_appointments.appoint` the route calls, inside a transaction that is rolled back,
so "OK" here means the real call would be accepted, and a refusal reads exactly as it would. The appointment
itself is made by a GEX administrator on the Gates & Evidence screen ("Who verifies"), which writes the
audit event; this script cannot appoint.

Why it exists: an appointment needs a vetted ACTIVE account, a registered company, a named instructing
party who is not the project owner, and the sha256 of its instruction — and until one is made nobody can
verify evidence on a live project. Find every blocker before the people are in the room.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def preflight(project_id: str, user_id: str, role: str, instructed_by: str, instruction_sha256: str,
              appointer_id: str) -> int:
    from app.api.v1.routes_reviewer_appointments import _project, _store
    from app.core import reviewer_appointments as ra
    from app.core.request_tenant import reset_current_company, set_current_company

    pid, profile = _project(project_id)
    token = set_current_company("PLATFORM_ADMIN")        # as a GEX administrator's request binds it
    conn, write_access = _store()
    try:
        try:
            result = ra.appoint(conn, project_id=pid, owner_company_id=profile.owner_company_id,
                                appointee_user_id=user_id, role=role, appointer={"user_id": appointer_id},
                                instructed_by=instructed_by, instruction_sha256=instruction_sha256,
                                write_project_access=write_access)
        except ra.AppointmentRefused as exc:
            print(f"REFUSED  {exc.code} ({exc.status})\n  {exc.message}")
            return 1
        finally:
            conn.rollback()                              # always: this script never writes
        print(f"OK       {result['user_id']} ({result['company_id']}) could be appointed {result['role']} on {pid}")
        print(f"         verifies gates: {', '.join(result['gates'])}")
        print(f"         instructed by:  {result['instructed_by']}   ({result['instruction_sha256'][:12]}…)")
        print(f"         takes effect:   {result['effective']}")
        _print_workload(conn, pid, result["gates"], profile)
        print("\nNothing was written. A GEX administrator makes the appointment on Gates & Evidence → Who verifies.")
        return 0
    finally:
        conn.close()
        reset_current_company(token)


def _print_workload(conn, pid: str, gates: list[str], profile) -> None:
    """What this reviewer would be asked to verify here: applicable items of its gates that a counterparty's
    confirmation does not cover, with their present status."""
    from app.core import contract_tokens as ct
    from app.core.bankability_engine import GATE_REGISTRY, inapplicability
    from app.core.project_registry import get_effective_context

    ctx = get_effective_context(pid)
    power, financing = getattr(ctx, "power_model", None), getattr(ctx, "financing_model", None)
    status = {r["evidence_key"]: r["status"] for r in conn.execute(
        "SELECT evidence_key, status FROM bankability_evidence WHERE project_id = ?", (pid,)).fetchall()}
    counterparty = {k for keys in ct.CONTRACT_EVIDENCE.values() for k in keys}
    rows = []
    for g in GATE_REGISTRY:
        if g.id.split("_")[0] not in gates:
            continue
        for key in g.required_evidence:
            if key in counterparty or inapplicability(key, power, financing):
                continue
            rows.append((g.id.split("_")[0], key, status.get(key, "no request raised")))
    open_rows = [r for r in rows if r[2] != "VERIFIED"]
    print(f"\n  {len(rows)} items on this project need an independent reviewer in these gates; "
          f"{len(open_rows)} are not yet verified:")
    for gate, key, st in open_rows[:40]:
        print(f"    {gate:<4} {key:<48} {st}")
    if len(open_rows) > 40:
        print(f"    … and {len(open_rows) - 40} more")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--user", required=True, help="the reviewer's user id (an ACTIVE account)")
    ap.add_argument("--role", required=True, help="e.g. INDEPENDENT_ENGINEER, LENDERS_ADVISER, INSURER, CERTIFIER")
    ap.add_argument("--instructed-by", required=True, help="the party whose decision relies on the gate")
    ap.add_argument("--instruction-sha256", required=True)
    ap.add_argument("--as", dest="appointer", default="jean-marie_greenearthx_com",
                    help="the GEX administrator who would appoint (default: jean-marie_greenearthx_com)")
    a = ap.parse_args()
    sys.exit(preflight(a.project, a.user, a.role, a.instructed_by, a.instruction_sha256, a.appointer))


if __name__ == "__main__":
    main()
