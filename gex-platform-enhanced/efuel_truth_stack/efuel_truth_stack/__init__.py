"""
efuel_truth_stack — event-sourced / CQRS / bitemporal reference core for an
e-fuel greenfield project. The ledger is the only writable store; everything
else (claims, nodes, CP status, releasable) is a projection folded from it.

Public surface:
  Ledger, new_entry, utc            — the append-only store + helpers
  fold_claims, rollup_nodes         — projectors
  evaluate_release_predicate        — the drawdown release AND-tree
  evaluate_all, run_reconciliations — the reconciliation engine
  models.*, enums.*, spec.*         — entities, vocabularies, loaded spec
"""

from . import enums, models, spec  # noqa: F401
from .ledger import (
    Ledger, new_entry, utc,
    WriteAuthorityError, ImmutabilityError, ToStateViolation,
)
from .projectors import fold_claims, rollup_nodes, node_is_green, ProjectionError
from .release import evaluate_release_predicate, open_blocking_events
from .reconciliation import evaluate_all, evaluate_constraint, run_reconciliations

__all__ = [
    "enums", "models", "spec",
    "Ledger", "new_entry", "utc",
    "WriteAuthorityError", "ImmutabilityError", "ToStateViolation",
    "fold_claims", "rollup_nodes", "node_is_green", "ProjectionError",
    "evaluate_release_predicate", "open_blocking_events",
    "evaluate_all", "evaluate_constraint", "run_reconciliations",
]
