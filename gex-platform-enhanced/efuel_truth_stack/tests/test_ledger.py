"""Ledger: write_authority, append-only immutability, bitemporal as_of."""

from datetime import date

import pytest

from efuel_truth_stack.enums import EntryType
from efuel_truth_stack.ledger import (
    ImmutabilityError, Ledger, WriteAuthorityError, new_entry, utc,
)


def _measurement(producer):
    return new_entry(project_id="P", entry_type=EntryType.MEASUREMENT, produced_by=producer,
                     valid_from=date(2030, 3, 1), recorded_at=utc(2030, 3, 2),
                     payload={"claim_type": "h2_t", "value": 10})


def test_write_authority_rejects_non_mrv_measurement():
    led = Ledger()
    with pytest.raises(WriteAuthorityError):
        led.append(_measurement("epc_contractor"))      # not an MRV actor
    led.append(_measurement("metering_mrv_actor"))       # allowed writer -> ok
    assert len(led.entries) == 1


def test_append_only_rejects_duplicate_id():
    led = Ledger()
    e = _measurement("metering_mrv_actor")
    led.append(e)
    with pytest.raises(ImmutabilityError):
        led.append(e)  # same id again


def test_as_of_returns_old_belief_before_correction_new_after():
    led = Ledger()
    vt = date(2030, 3, 1)
    # original belief 'A', recorded 2030-03-10
    f1 = new_entry(entry_id="f1", project_id="P", entry_type=EntryType.CONTRACT,
                   produced_by="offtaker", valid_from=vt, recorded_at=utc(2030, 3, 10),
                   payload={"value": "A"})
    led.append(f1)

    # retroactive correction 'B' for the SAME valid-time, recorded later (2030-04-01)
    f2 = new_entry(entry_id="f2", project_id="P", entry_type=EntryType.CONTRACT,
                   produced_by="offtaker", valid_from=vt, recorded_at=utc(2030, 4, 1),
                   payload={"value": "B"}, supersedes="f1")
    led.append(f2)

    before = led.as_of(transaction_time=utc(2030, 3, 20), valid_time=vt)
    after = led.as_of(transaction_time=utc(2030, 4, 2), valid_time=vt)

    assert [e.payload["value"] for e in before] == ["A"]   # correction not yet recorded
    assert [e.payload["value"] for e in after] == ["B"]    # superseded after correction


def test_as_of_supports_retroactive_decertification():
    """A correction can revise valid_to so an as-of at the new tt no longer sees the row as valid."""
    led = Ledger()
    vt = date(2030, 3, 1)
    led.append(new_entry(entry_id="c1", project_id="P", entry_type=EntryType.CERTIFICATE,
                         produced_by="certification_body_auditor", valid_from=vt,
                         recorded_at=utc(2030, 3, 5), payload={"claim_type": "rfnbo_issued", "value": True}))
    # de-cert: same certificate restated with valid_to = vt (no longer valid AT vt), recorded later
    led.append(new_entry(entry_id="c2", project_id="P", entry_type=EntryType.CERTIFICATE,
                         produced_by="certification_body_auditor", valid_from=vt, valid_to=vt,
                         recorded_at=utc(2030, 6, 1), payload={"claim_type": "rfnbo_issued", "value": True},
                         supersedes="c1"))
    assert led.as_of(utc(2030, 4, 1), vt)   # before de-cert: certificate valid at vt
    assert not led.as_of(utc(2030, 7, 1), vt)  # after de-cert: valid_to==vt excludes it
