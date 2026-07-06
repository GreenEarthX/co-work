"""
spec.py — loads efuel_truth_stack_v0_2.json (the source of truth) and exposes
derived registries the code needs: a flattened node registry, the CP register,
reconciliation constraints, write-authority rules, the event taxonomy, actors,
and the configurable numeric inputs (GHG threshold, tolerances).

DERIVATIONS ARE DONE IN CODE, NEVER BY EDITING THE JSON. Two documented gaps in
the spec are filled here (flagged, not silently):
  1. Nodes are spread across molecule_chain / engineering / certification /
     commercial sections — flattened into NODES.
  2. cp_register references four nodes that are not defined in any node section:
     `financial_model`, `kyc_aml`, `state_aid_approval`, `no_default_cert`.
     We synthesize minimal node definitions for them (see SYNTHESIZED_NODES).
     This fills a referential gap; it changes no enum and no rule. If the review
     prefers explicit node defs in the JSON instead, say so and we move them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.environ.get(
    "EFUEL_SPEC_PATH",
    os.path.join(os.path.dirname(_HERE), "efuel_truth_stack_v0_3.json"),
)


def load_spec(path: str = SPEC_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


SPEC: dict = load_spec()


# ── Node registry (flattened from the per-section node lists) ────────────────
# Review-resolved: financial_model + public_controls node sections were added to
# the JSON so cp_register references resolve to defined nodes (was gap #2).
_NODE_SECTIONS = ["molecule_chain", "engineering", "certification", "commercial",
                  "financial_model", "public_controls"]

# Belt-and-suspenders fallback (the JSON now defines these). Kept so the code is
# robust if a node section is ever trimmed; setdefault means the JSON wins.
SYNTHESIZED_NODES: dict[str, dict] = {
    "financial_model": {"id": "financial_model", "layer": "financial", "required_claims": ["model_base_case"]},
    "kyc_aml": {"id": "kyc_aml", "layer": "public_controls", "required_claims": ["kyc_passed"]},
    "state_aid_approval": {"id": "state_aid_approval", "layer": "public_controls", "required_claims": ["state_aid_cleared"]},
    "no_default_cert": {"id": "no_default_cert", "layer": "financial", "required_claims": ["no_default"]},
}


# ── Biofuel-regime certification nodes (regime fork) ─────────────────────────
# FORMALISED in efuel_truth_stack_v0_3.json (certification.nodes) — the JSON is
# now the source of truth for these. This dict remains ONLY as the same
# belt-and-suspenders fallback pattern as SYNTHESIZED_NODES above (setdefault:
# the JSON wins).
BIOFUEL_NODES: dict[str, dict] = {
    "feedstock_sustainability": {"id": "feedstock_sustainability", "layer": "certification",
                                 "required_claims": ["feedstock_sustainability"]},
    "annex_ix":                 {"id": "annex_ix", "layer": "certification",
                                 "required_claims": ["annex_ix_class"]},
    "land_criteria":            {"id": "land_criteria", "layer": "certification",
                                 "required_claims": ["land_criteria"]},
    "ghg_saving":               {"id": "ghg_saving", "layer": "certification",
                                 "required_claims": ["ghg_saving"]},
}


def _build_nodes() -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for section in _NODE_SECTIONS:
        for nd in SPEC.get(section, {}).get("nodes", []):
            nodes[nd["id"]] = dict(nd)
    for nid, nd in SYNTHESIZED_NODES.items():
        nodes.setdefault(nid, dict(nd))
    for nid, nd in BIOFUEL_NODES.items():
        nodes.setdefault(nid, dict(nd))
    return nodes


NODES: dict[str, dict] = _build_nodes()

# claim_type -> node_id that requires it (a claim is scoped to a node).
CLAIM_TYPE_TO_NODE: dict[str, str] = {}
for _nid, _nd in NODES.items():
    for _ct in _nd.get("required_claims", []):
        CLAIM_TYPE_TO_NODE.setdefault(_ct, _nid)


# ── CP register, reconciliation, write-authority, events, actors ─────────────
CP_ITEMS: list[dict] = SPEC["cp_register"]["items"]
CP_BY_ID: dict[str, dict] = {cp["id"]: cp for cp in CP_ITEMS}


def cps_of_class(cp_class: str) -> list[dict]:
    return [cp for cp in CP_ITEMS if cp["class"] == cp_class]


RECON_CONSTRAINTS: list[dict] = SPEC["reconciliation_constraints"]["constraints"]
RECON_BY_ID: dict[str, dict] = {c["id"]: c for c in RECON_CONSTRAINTS}

EVENT_TAXONOMY: dict[str, dict] = {e["type"]: e for e in SPEC["event_taxonomy"]["events"]}

RELEASE_CHECKS: list[dict] = SPEC["drawdown"]["release_predicate"]["all_of"]

ACTORS: list[str] = SPEC["actors"]

# entry_type -> frozenset of allowed writer actor ids. Entry types absent here
# carry no write restriction (only the listed types are gated, per the spec).
WRITE_AUTHORITY: dict[str, frozenset[str]] = {
    rule["entry_type"]: frozenset(rule["allowed_writers"])
    for rule in SPEC["write_authority"]["rules"]
}


def node_threshold_g_per_mj(node_id: str = "ghg_lca") -> float | None:
    return NODES.get(node_id, {}).get("threshold_g_per_mj")


# ── Configurable numeric inputs (NOT constants) ──────────────────────────────
@dataclass(frozen=True)
class StackConfig:
    """
    All tunable numeric inputs live here so nothing is hard-coded. Defaults are
    read from the spec where the spec provides them (e.g. the 28.2 g/MJ GHG
    threshold and per-constraint tolerances); everything else is an explicit
    input the caller may override per project / fuel / vintage.
    """
    ghg_threshold_g_per_mj: float = node_threshold_g_per_mj("ghg_lca") or 28.2
    # funding_order ratios are spec placeholders (null) — supplied per project.
    funding_ratios: dict[str, float] = field(default_factory=dict)
    # reconciliation op parameters, seeded from the spec, overridable.
    recon_tolerances_pct: dict[str, float] = field(
        default_factory=lambda: {c["id"]: c["tol"] for c in RECON_CONSTRAINTS if "tol" in c}
    )
    settlement_lag_days: dict[str, int] = field(
        default_factory=lambda: {c["id"]: c["window_days"] for c in RECON_CONSTRAINTS if "window_days" in c}
    )
    # float comparison epsilon for "exact" money equality.
    exact_epsilon: float = 1e-6


DEFAULT_CONFIG = StackConfig()
