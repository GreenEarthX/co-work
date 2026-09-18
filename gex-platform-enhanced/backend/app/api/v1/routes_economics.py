"""
Economics read model — the approved TEA picture for one project.

Increment 1 of `docs/tea-report-scope.md`. Until now the four `economics.*`
permission strings mapped to routes that were never written, and the TEA figures
existed only inside claims nobody could read back.

THE RULE THIS ROUTE EXISTS TO KEEP: it reads an APPROVED claim and never
recomputes. A document whose numbers are produced at render time is not the
document that passed IE/CFO approval. So:

  - no live base case            → 404
  - a live base case not approved → 409, naming the state, with NO figures
  - approved                      → the figures, each carrying the claim's own
                                    `cost_basis_hash`, approver and decision id

`TERMINAL_VALID` is imported from the TEA bridge rather than restated here; one
definition of "approved" is the point.

NOT SERVED, and the reason is the same each time — the compute path persists the
headline economics and the run's hash, not the run: the cost stack, the
regulatory regime and the sensitivity tornado exist only in the :8002 response at
compute time. They are named in `not_available` rather than silently omitted, and
fetching them would mean recomputing, which is the one thing this route must not
do. Persisting them is the next increment.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.routes_entitlements import require_finance_entitlement
from app.api.v1.routes_tea import TERMINAL_VALID, get_db

router = APIRouter()

# The provisional-run disclaimer that must travel with every figure. Inputs are
# public-reference first-pass values, not verifier-signed (CLAUDE_HANDOFF §5).
ASCERTAINED_NOTE = (
    "Provisional cost basis. Inputs are public-reference first-pass values, not "
    "verifier-signed; `ascertained` flips to true only when a named ISO 14067 "
    "verifier signs the dataset."
)
GREET_NOTE = (
    "The GREET path is a GREET-consistent approximation using published IRA 45V "
    "tier thresholds and a US-grid emission factor — not the licensed ANL model."
)

_LIVE_CLAIM_STATES = "('superseded','rejected','expired','failed')"


def _live_base_case(db: sqlite3.Connection, project_id: str,
                    pathway_id: Optional[str]) -> Optional[sqlite3.Row]:
    q = ("SELECT * FROM model_base_case WHERE project_id=? AND valid_to IS NULL "
         f"AND state NOT IN {_LIVE_CLAIM_STATES}")
    args: list[Any] = [project_id]
    if pathway_id:
        q += " AND pathway_id=?"
        args.append(pathway_id)
    q += " ORDER BY created_at DESC LIMIT 1"
    return db.execute(q, tuple(args)).fetchone()


def _lca_block(db: sqlite3.Connection, project_id: str,
               pathway_id: Optional[str]) -> dict[str, Any]:
    """The GHG claims for this pathway. A claim that is not approved contributes
    its state and NOT its value — the same rule the base case follows."""
    out: dict[str, Any] = {}
    for claim_type in ("g_co2e_per_mj", "ghg_saving"):
        q = ("SELECT * FROM pathway_claims WHERE project_id=? AND claim_type=? "
             f"AND valid_to IS NULL AND state NOT IN {_LIVE_CLAIM_STATES}")
        args: list[Any] = [project_id, claim_type]
        if pathway_id:
            q += " AND pathway_id=?"
            args.append(pathway_id)
        q += " ORDER BY created_at DESC LIMIT 1"
        row = db.execute(q, tuple(args)).fetchone()
        if row is None:
            out[claim_type] = None
            continue
        approved = row["state"] in TERMINAL_VALID
        entry: dict[str, Any] = {
            "claim_id": row["claim_id"],
            "state": row["state"],
            "approved": approved,
            "method": row["method"],
            "approved_by": row["approved_by"],
        }
        if approved:
            entry["value"] = row["value"]
            entry["unit"] = row["unit"]
        out[claim_type] = entry
    methods = [v["method"] for v in out.values() if v and v.get("method")]
    if any("greet" in (m or "").lower() for m in methods):
        out["method_note"] = GREET_NOTE
    return out


@router.get(
    "/snapshot/{project_id}",
    dependencies=[Depends(require_finance_entitlement("economics_snapshot"))],
)
def economics_snapshot(
    project_id: str,
    pathway_id: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    """The approved economic picture for one project: CAPEX, OPEX, LCOP and the
    GHG claims, with the identity of the claim that carries them."""
    row = _live_base_case(db, project_id, pathway_id)
    if row is None:
        raise HTTPException(404, f"no base case for project {project_id}")

    if row["state"] not in TERMINAL_VALID:
        # Deliberately no figures. A provisional run must never be read as the
        # approved one, and returning it with a flag invites exactly that.
        raise HTTPException(409, {
            "error": "BASE_CASE_NOT_APPROVED",
            "claim_id": row["claim_id"],
            "state": row["state"],
            "message": ("The live base case has not been approved. Submit it for "
                        "IE/CFO approval; provisional figures are not served here."),
        })

    return {
        "project_id": project_id,
        "claim": {
            "claim_id": row["claim_id"],
            "pathway_id": row["pathway_id"],
            "state": row["state"],
            "approved_by": row["approved_by"],
            "approval_decision_id": row["approval_decision_id"],
            "valid_from": row["valid_from"],
            "created_at": row["created_at"],
            "supersedes_claim_id": row["supersedes_claim_id"],
            "run_evidence_id": row["run_evidence_id"],
        },
        "basis": {
            "engine": row["engine"],
            "cost_basis_hash": row["cost_basis_hash"],
            "nameplate_capacity": row["nameplate_capacity"],
            "nameplate_unit": row["nameplate_unit"],
        },
        "economics": {
            "capex_eur": row["capex_eur"],
            "opex_eur_per_year": row["opex_eur_per_year"],
            "lcop": row["lcop"],
            "lcop_basis": ("levelised cost per nameplate unit of primary product "
                           f"({row['nameplate_unit']})"),
        },
        "lca": _lca_block(db, project_id, pathway_id or row["pathway_id"]),
        "integrity": {
            "ascertained": False,
            "note": ASCERTAINED_NOTE,
        },
        "not_available": {
            "cost_stack": ("not persisted: the compute path stores the run's hash, "
                           "not its equipment breakdown"),
            "regime": ("not persisted: the pathway_class fork is computed at run "
                       "time and only the resulting claims are stored"),
            "sensitivity_tornado": ("not persisted: /sensitivity on the TEA engine "
                                    "is compute-only"),
            "why": ("Serving these would mean recomputing, and a recomputed figure "
                    "is not the figure that was approved."),
        },
    }
