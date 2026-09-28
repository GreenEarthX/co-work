"""Commitment state is derived at read time, so 'overdue' can never go stale."""
from datetime import date

import pytest

from app.core.evidence_due_dates import (
    COMMITTED, DONE, NOT_COMMITTED, OVERDUE, UNASSIGNED, commitment_state, parse_commitment_date,
)

TODAY = date(2026, 10, 1)
C = "2026-09-26 09:00:00"


@pytest.mark.parametrize("item, expected", [
    ({"status": "VERIFIED", "assignee_user_id": "u", "due_date": "2026-01-01", "committed_at": C}, (DONE, 0)),
    ({"status": "NOT_STARTED"}, (UNASSIGNED, 0)),
    ({"status": "NOT_STARTED", "assignee_user_id": "u"}, (NOT_COMMITTED, 0)),
    # a date with no commitment behind it is not a commitment
    ({"status": "NOT_STARTED", "assignee_user_id": "u", "due_date": "2026-12-01"}, (NOT_COMMITTED, 0)),
    ({"status": "IN_PROGRESS", "assignee_user_id": "u", "due_date": "2026-10-01", "committed_at": C}, (COMMITTED, 0)),
    ({"status": "SUBMITTED", "assignee_user_id": "u", "due_date": "2026-09-21", "committed_at": C}, (OVERDUE, 10)),
    ({"status": "IN_PROGRESS", "assignee_user_id": "u", "due_date": "garbage", "committed_at": C}, (NOT_COMMITTED, 0)),
])
def test_commitment_state(item, expected):
    assert commitment_state(item, TODAY) == expected


def test_due_today_is_not_overdue_until_tomorrow():
    item = {"status": "IN_PROGRESS", "assignee_user_id": "u", "due_date": "2026-10-01", "committed_at": C}
    assert commitment_state(item, TODAY)[0] == COMMITTED
    assert commitment_state(item, date(2026, 10, 2)) == (OVERDUE, 1)


def test_a_commitment_date_must_not_be_in_the_past():
    assert parse_commitment_date("2026-10-01", TODAY) == TODAY
    with pytest.raises(ValueError):
        parse_commitment_date("2026-09-30", TODAY)
    with pytest.raises(ValueError):
        parse_commitment_date("01/10/2026", TODAY)
