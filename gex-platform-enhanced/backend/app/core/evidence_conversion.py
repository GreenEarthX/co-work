"""
Turn invented evidence rows into open requests owned by real people.

Pure planning — no I/O. scripts/convert_invented_evidence.py reads the rows,
calls plan_conversion(), prints the plan, and applies it in one transaction.

Why this exists. On 2026-09-26 every row in bankability_evidence was invented:
125 written by the demo seed endpoint (removed 2026-09-23) and 2 entered by hand
with invented content under real people's names. The gates, the bankability
state and capital eligibility are computed from that table, so an invented
VERIFIED row is a lie the engine repeats. Deleting the rows would lose the only
useful thing in them — which documents each project was meant to produce.

So each invented row becomes one of three things, and is archived verbatim first:

  REQUEST   the key is live and the project has an owning company: the row is
            reset to an open NOT_STARTED request (no status, submitter, verifier,
            hash or maturity survives) and assigned to a named ACTIVE account of
            that company, by owner function (bankability_engine.resolve_assignee).
  REPLACED  the key was retired in rules 3.0.0: the row is removed and an open
            request is created for its replacement — unless the project already
            has a row for that key. Never a relabel: nothing the old row claimed
            carries over to the new key.
  REMOVED   the project has no owning company (the placeholder 'default'), or the
            key is unknown: there is no one to ask, so the row is removed.

Unassignable requests stay unassigned with the reason recorded. A gap that says
"this company has no one who can produce this" is information; a guessed
assignee is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

REQUEST, REPLACED, REMOVED = "REQUEST", "REPLACED", "REMOVED"


@dataclass
class Disposition:
    row: dict                          # the invented row, verbatim
    kind: str                          # REQUEST | REPLACED | REMOVED
    reason: str                        # why this disposition
    assignee: Optional[str] = None     # REQUEST only
    assign_reason: str = ""            # REQUEST only
    replaced_by: Optional[str] = None  # REPLACED only


@dataclass
class NewRequest:
    project_id: str
    evidence_key: str
    assignee: Optional[str]
    assign_reason: str
    source_row_id: int                 # the retired row it replaces


@dataclass
class Plan:
    dispositions: list[Disposition] = field(default_factory=list)
    new_requests: list[NewRequest] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for d in self.dispositions if d.kind == kind)


def plan_conversion(
    selected: list[dict],
    all_rows: list[dict],
    project_owner: dict[str, Optional[str]],
    active_accounts: dict[str, list[dict]],
    live_keys: set[str],
    retired: dict[str, dict],
    resolve: Callable[[str, list[dict]], tuple[Optional[str], str]],
) -> Plan:
    """Decide what happens to each selected row. Deterministic for a given input.

    selected        rows to convert (dicts with id, project_id, evidence_key, ...)
    all_rows        every row in the table — a replacement is not created where
                    the project already has a row for that key, selected or not
    project_owner   project_id -> owning company id (None: no owner)
    active_accounts company id -> ACTIVE auth_users rows (user_id, business_function)
    """
    plan = Plan()
    present = {(r["project_id"], r["evidence_key"]) for r in all_rows}
    planned: set[tuple[str, str]] = set()

    for row in sorted(selected, key=lambda r: r["id"]):
        pid, key = row["project_id"], row["evidence_key"]
        owner = project_owner.get(pid)
        if owner is None:
            plan.dispositions.append(Disposition(
                row, REMOVED, f"project '{pid}' has no owning company — no one to request it from"))
            continue
        accounts = active_accounts.get(owner, [])
        if key in live_keys:
            who, why = resolve(key, accounts)
            plan.dispositions.append(Disposition(
                row, REQUEST, "live evidence item — reset to an open request",
                assignee=who, assign_reason=why))
        elif key in retired:
            new_key = retired[key]["replaced_by"]
            plan.dispositions.append(Disposition(
                row, REPLACED, f"retired in rules 3.0.0 — replaced by '{new_key}'", replaced_by=new_key))
            if (pid, new_key) not in present and (pid, new_key) not in planned:
                who, why = resolve(new_key, accounts)
                plan.new_requests.append(NewRequest(pid, new_key, who, why, row["id"]))
                planned.add((pid, new_key))
        else:
            plan.dispositions.append(Disposition(
                row, REMOVED, f"'{key}' is not an evidence item of any gate"))
    return plan
