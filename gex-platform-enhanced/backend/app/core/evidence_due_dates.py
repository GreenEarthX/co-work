"""
Commitment state of an evidence request — derived, never stored.

    UNASSIGNED      nobody owns it
    NOT_COMMITTED   assigned, but the assignee has not committed to a date
    COMMITTED       assigned, dated, not yet due
    OVERDUE         the committed date has passed and the item is not VERIFIED
    DONE            VERIFIED

Derived at read time so "overdue" can never go stale. A request is created by
assignment and accepted by commitment (migration 057): the date is the
assignee's word, so the platform never supplies one.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

UNASSIGNED, NOT_COMMITTED, COMMITTED, OVERDUE, DONE = (
    "UNASSIGNED", "NOT_COMMITTED", "COMMITTED", "OVERDUE", "DONE")


def commitment_state(item: dict, today: Optional[date] = None) -> tuple[str, int]:
    """(state, days_overdue). days_overdue is 0 unless state is OVERDUE."""
    today = today or date.today()
    if item.get("status") == "VERIFIED":
        return DONE, 0
    if not item.get("assignee_user_id"):
        return UNASSIGNED, 0
    due = item.get("due_date")
    if not due or not item.get("committed_at"):
        return NOT_COMMITTED, 0
    try:
        days = (today - date.fromisoformat(due)).days
    except ValueError:
        return NOT_COMMITTED, 0          # an unreadable date is not a commitment
    return (OVERDUE, days) if days > 0 else (COMMITTED, 0)


def parse_commitment_date(value: str, today: Optional[date] = None) -> date:
    """A commitment date must be a real date, today or later. Raises ValueError."""
    d = date.fromisoformat(value)
    if d < (today or date.today()):
        raise ValueError("a commitment cannot be made to a date that has already passed")
    return d
