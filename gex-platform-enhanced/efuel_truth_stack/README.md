# e-fuel greenfield truth stack (v0.2.0)

Event-sourced / CQRS / bitemporal reference core. The ledger is the only writable
store; **all** state (claims, nodes, CP status, releasable) is a projection folded
from it. In-memory + JSON fixtures, no DB. Python 3.11+, Pydantic v2, pytest.

`efuel_truth_stack_v0_2.json` is the source of truth (verbatim). Code never edits
it; `spec.py` derives registries from it and a consistency test pins the enums.

## Layout
```
efuel_truth_stack_v0_2.json     # spec (source of truth)
efuel_truth_stack/
  enums.py          # vocabularies + kind→entry_type map + claim_state transitions
  spec.py           # loads the JSON; node registry, CP register, recon, write_authority, StackConfig
  models.py         # Pydantic entities (frozen CanonicalLedgerEntry, Claim, Node, FundingCommitment…)
  ledger.py         # append() (write_authority + immutability) + as_of() bitemporal
  projectors.py     # fold_claims (transitions enforced) + rollup_nodes (worst-of)
  release.py        # evaluate_release_predicate — the 9-check AND-tree (per-check pass/fail + reason)
  reconciliation.py # op-aware operators + engine (writes reconciliation_result + raises events)
tests/              # 30 tests, incl. the five required
```

## Run
```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q
```

## The six non-negotiables (all enforced)
1. Event-sourced/CQRS — `CanonicalLedgerEntry` is the only writable store (frozen, append-only).
2. State on projections only — ledger rows carry no `claim_state`; `fold_claims` derives it.
3. Bitemporal — `valid_from/valid_to` vs `recorded_at`; `as_of(tt, vt)` resolves supersedes within the tt slice (retroactive de-certification representable).
4. Evidence is a relationship — `EvidenceLink` (hash-pinned); no `evidence` entry_type.
5. Approvals bind to evidence hashes — superseding a fact makes the approval fail `approvals_fresh`.
6. `write_authority` enforced on append.

## Review resolutions
Three of the four flagged gaps were **baked into the JSON** (data); one stays code-level (it is an algorithm, not data):
- **#2 CP nodes — baked.** `financial_model` + `public_controls` node sections added to the JSON, so `cp_register` references resolve to defined nodes.
- **#3 `ghg_pass` op — baked.** New `threshold` op added to the `reconciliation_op` enum; `ghg_pass` now declares `op: threshold` (its expr is `<=`, not `==`).
- **#4 constraint→event map — baked.** Each reconciliation constraint declares its `event`; `reconciliation.CONSTRAINT_EVENT_MAP` is now read from the spec.
- **#1 fold convention — code-level (by design).** Claim-bearing rows carry `payload.claim_id` + a target `to_state`, applied in transaction-time order along the legal transition path (`projectors.py`). This is a fold *algorithm*; a data spec is the wrong place for it.

`test_spec_consistency.py` asserts #2/#3/#4 are present in the JSON, so they cannot regress.

## Configurable inputs (not constants)
`spec.StackConfig` — GHG threshold (default 28.2 from the spec, overridable), per-constraint tolerances and settlement-lag windows, funding ratios (spec placeholders), float epsilon.
