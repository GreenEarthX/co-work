"""
ledger.py — the append-only, immutable, bitemporal store.

This is the ONLY writable thing in the system. Everything else (Claim, Node, CP
status, balances, releasable) is a projection folded from here. `append()` is the
single write path and enforces the two invariants that make it a *truth* ledger:
  - write_authority: produced_by must be an allowed writer for that entry_type.
  - immutability: ids are unique and rows are frozen; corrections are new rows
    that `supersedes` a prior one — never edits.

`as_of(transaction_time, valid_time)` answers the bitemporal question: "given
only what we had recorded by `transaction_time`, what did we believe was true at
`valid_time`?" Supersedes are resolved *within* the transaction-time slice, so a
correction recorded later is invisible to an earlier as-of — which is exactly
what makes retroactive de-certification representable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from .enums import EntryType, KIND_OF_ENTRY_TYPE, LedgerKind
from .models import CanonicalLedgerEntry
from .spec import WRITE_AUTHORITY


class WriteAuthorityError(PermissionError):
    """Raised when produced_by is not an allowed writer for the entry_type."""


class ImmutabilityError(ValueError):
    """Raised on any attempt to re-use an id or mutate an existing row."""


class ToStateViolation(ValueError):
    """Raised when payload.to_state tries to smuggle terminal truth (spec v0.3
    §payload_conventions.to_state): fact/derived entries may express NON-TERMINAL
    progression only; terminal-valid states require decision-kind entries."""


# States payload.to_state may NEVER assert on fact/derived entries:
# terminal-valid (smuggled truth) AND demoting terminal-invalid (griefing vector
# — a counterparty's fact expiring your verified claim blocks capital as
# effectively as forging one). Temporal lapses (insurance, certificates) are
# modelled as valid_to narrowing on a correction row, not state demotion.
_TERMINAL_VALID_STATES = frozenset({"verified", "satisfied", "waived"})
_DEMOTING_STATES = frozenset({"expired", "rejected", "failed", "superseded"})


class Ledger:
    def __init__(self) -> None:
        self.entries: list[CanonicalLedgerEntry] = []
        self._ids: set[str] = set()

    # ── write path ───────────────────────────────────────────────────────────
    def append(self, entry: CanonicalLedgerEntry) -> CanonicalLedgerEntry:
        if entry.id in self._ids:
            raise ImmutabilityError(
                f"ledger entry id '{entry.id}' already exists — the ledger is "
                f"append-only; corrections must be new rows that supersede."
            )
        allowed = WRITE_AUTHORITY.get(entry.entry_type.value)
        if allowed is not None and entry.produced_by not in allowed:
            raise WriteAuthorityError(
                f"actor '{entry.produced_by}' may not append '{entry.entry_type.value}' "
                f"rows (allowed writers: {sorted(allowed)})"
            )
        if entry.supersedes is not None and entry.supersedes not in self._ids:
            raise ImmutabilityError(
                f"entry '{entry.id}' supersedes unknown row '{entry.supersedes}'"
            )
        # v0.3 §3.4: to_state on non-decision entries is bounded to non-terminal
        # progression. Terminal-valid truth arrives only via decision entries
        # (approval_decision / waiver / release_decision) from authorised actors.
        to_state = entry.payload.get("to_state")
        if (to_state in _TERMINAL_VALID_STATES
                and entry.kind is not LedgerKind.DECISION):
            raise ToStateViolation(
                f"entry '{entry.id}' ({entry.kind.value}/{entry.entry_type.value}) "
                f"asserts to_state='{to_state}' — terminal-valid states require a "
                f"decision-kind entry from an authorised actor, never a payload."
            )
        if (to_state in _DEMOTING_STATES
                and entry.kind is not LedgerKind.DECISION):
            raise ToStateViolation(
                f"entry '{entry.id}' ({entry.kind.value}/{entry.entry_type.value}) "
                f"asserts demoting to_state='{to_state}' — demotions require a "
                f"decision-kind entry; temporal lapses are expressed by narrowing "
                f"valid_to on a correction row, not by state."
            )
        self.entries.append(entry)
        self._ids.add(entry.id)
        return entry

    # ── bitemporal reads ──────────────────────────────────────────────────────
    def _visible(self, transaction_time: Optional[datetime],
                 project_id: Optional[str]) -> list[CanonicalLedgerEntry]:
        return [
            e for e in self.entries
            if (transaction_time is None or e.recorded_at <= transaction_time)
            and (project_id is None or e.project_id == project_id)
        ]

    def live(self, transaction_time: Optional[datetime] = None,
             project_id: Optional[str] = None) -> list[CanonicalLedgerEntry]:
        """Non-superseded rows as known at `transaction_time` (now if None)."""
        visible = self._visible(transaction_time, project_id)
        superseded = {e.supersedes for e in visible if e.supersedes}
        return [e for e in visible if e.id not in superseded]

    def as_of(self, transaction_time: datetime, valid_time: date,
              project_id: Optional[str] = None) -> list[CanonicalLedgerEntry]:
        """Rows believed-current at `transaction_time` AND valid at `valid_time`."""
        return [e for e in self.live(transaction_time, project_id)
                if e.is_valid_at(valid_time)]

    def current_hashes(self, transaction_time: Optional[datetime] = None,
                       project_id: Optional[str] = None) -> set[str]:
        """Content hashes of all live rows — the basis for approval staleness."""
        return {e.hash for e in self.live(transaction_time, project_id)}

    def by_entry_type(self, entry_type: EntryType,
                      transaction_time: Optional[datetime] = None,
                      project_id: Optional[str] = None) -> list[CanonicalLedgerEntry]:
        return [e for e in self.live(transaction_time, project_id)
                if e.entry_type == entry_type]

    def get(self, entry_id: str) -> Optional[CanonicalLedgerEntry]:
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None


def new_entry(*, project_id: str, entry_type: EntryType, produced_by: str,
              valid_from: date, recorded_at: datetime,
              payload: Optional[dict] = None, valid_to: Optional[date] = None,
              verified_by: Optional[str] = None, supersedes: Optional[str] = None,
              regulatory_cliff: Optional[date] = None,
              reconciliation_group_id: Optional[str] = None,
              entry_id: Optional[str] = None) -> CanonicalLedgerEntry:
    """
    Convenience constructor: infers `kind` from `entry_type`, generates an id and
    content hash. The hash is auto-computed by the model validator.
    """
    return CanonicalLedgerEntry(
        id=entry_id or f"le_{uuid.uuid4().hex[:12]}",
        project_id=project_id,
        kind=KIND_OF_ENTRY_TYPE[entry_type],
        entry_type=entry_type,
        produced_by=produced_by,
        verified_by=verified_by,
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=recorded_at,
        regulatory_cliff=regulatory_cliff,
        payload=payload or {},
        supersedes=supersedes,
        reconciliation_group_id=reconciliation_group_id,
    )


def utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    """Tiny helper for deterministic transaction-times in fixtures/tests."""
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)
