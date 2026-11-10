"""
The ledger anchor, pure (Phase 4 of "One contract record"; JML's prompt §8, Phase 0 Q11, Q12).

What leaves for the ledger is exactly five keys; the pseudonymous id is an HMAC that
links one contract's events and nothing else; mainnet is not a value; the backoff is
1 min, 5 min, 30 min, 2 h, then 12 h; the worker starts only when switched on and
configured; the Hedera adapter reads the public mirror node and never leaks its key.
Nothing here reaches a database or a ledger.
"""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import ledger_anchor as la

ROW = {"id": 7, "pseudo_id": "a" * 64 + "  ", "event_type": "CONFIRMED", "event_hash": "b" * 64,
       "prev_hash": "c" * 64, "contract_id": "4b0c…", "company_id": "etfuels_sa", "actor": "u_x",
       "price": "1.20", "contracted_tonnes_per_year": 30000, "contract_ref": "GEX-TB-2026-000001"}


def test_the_payload_is_exactly_five_keys_whatever_the_row_carries():
    p = la.payload(ROW)
    assert tuple(sorted(p)) == tuple(sorted(la.PAYLOAD_KEYS))
    assert p == {"schema_version": 1, "pseudo_id": "a" * 64, "event_type": "CONFIRMED", "event_hash": "b" * 64,
                 "prev_hash": "c" * 64}
    assert json.loads(la.message(ROW)) == p
    with pytest.raises(ValueError):
        la.payload({**ROW, "pseudo_id": None})                 # never sent without a pseudonymous id


def test_the_pseudonymous_id_links_one_contract_and_nothing_else():
    a1, a2 = la.pseudo_id("GEX-TB-2026-000001", "s1"), la.pseudo_id("GEX-TB-2026-000001", "s1")
    assert a1 == a2 and len(a1) == 64
    assert la.pseudo_id("GEX-TB-2026-000002", "s1") != a1     # two contracts cannot be linked
    assert la.pseudo_id("GEX-TB-2026-000001", "s2") != a1     # the salt is the secret
    assert "GEX-TB" not in a1 and la.pseudo_id("GEX-TB-2026-000001", "") is None


def test_the_migration_and_the_application_compute_the_same_id():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "095_ledger_anchor_outbox.py"
    spec = importlib.util.spec_from_file_location("m095", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m._pseudo_id("salt", "GEX-TB-2026-000042") == la.pseudo_id("GEX-TB-2026-000042", "salt")


def test_the_backoff_is_one_five_thirty_minutes_two_hours_then_twelve():
    assert [la.backoff_seconds(n) for n in range(1, 9)] == [60, 300, 1800, 7200, 43200, 43200, 43200, 43200]
    assert la.MAX_ATTEMPTS == 8


def test_mainnet_is_not_a_value():
    from pydantic import ValidationError

    from app.core.config import Settings

    for value in ("hedera_mainnet", "hedera", "mainnet"):
        with pytest.raises(ValidationError):
            Settings(LEDGER_ANCHOR_BACKEND=value)
    assert Settings(LEDGER_ANCHOR_BACKEND="none").LEDGER_ANCHOR_BACKEND == "none"
    with pytest.raises(ValueError, match="mainnet"):
        la.HederaHcsAnchor(operator_id="0.0.1", operator_key="k", topic_id="0.0.2", mirror_url="https://m",
                           network="mainnet")


def _settings(**kw):
    base = dict(LEDGER_ANCHOR_BACKEND="hedera_testnet", LEDGER_ANCHOR_SALT="s",
                LEDGER_ANCHOR_DATABASE_URL="postgresql://gex_anchor:pw@h:1/d", HEDERA_OPERATOR_ID="0.0.1",
                HEDERA_OPERATOR_KEY="k", HEDERA_TOPIC_ID="0.0.2", HEDERA_MIRROR_URL="https://m",
                LEDGER_ANCHOR_INTERVAL_SECONDS=30)
    return SimpleNamespace(**{**base, **kw})


def test_a_switched_on_backend_names_what_it_lacks():
    assert la.config_problems(_settings()) == []
    assert la.config_problems(_settings(LEDGER_ANCHOR_BACKEND="none", LEDGER_ANCHOR_SALT="")) == []
    assert "LEDGER_ANCHOR_SALT is not set" in la.config_problems(_settings(LEDGER_ANCHOR_SALT=""))
    assert "HEDERA_OPERATOR_KEY is not set" in la.config_problems(_settings(HEDERA_OPERATOR_KEY=""))
    assert "LEDGER_ANCHOR_DATABASE_URL must use the gex_anchor role" in la.config_problems(
        _settings(LEDGER_ANCHOR_DATABASE_URL="postgresql://gex_app:pw@h:1/d"))
    assert isinstance(la.anchor_from_settings(_settings(LEDGER_ANCHOR_BACKEND="none")), la.NullAnchor)
    assert isinstance(la.anchor_from_settings(_settings()), la.HederaHcsAnchor)


def test_the_worker_starts_only_when_switched_on_and_configured(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(la, "STATE", dict(la.STATE))          # the process's own worker state is left alone
    monkeypatch.setattr(settings, "LEDGER_ANCHOR_BACKEND", "none")
    assert la.start_worker()["running"] is False and la._TASK is None
    monkeypatch.setattr(settings, "LEDGER_ANCHOR_BACKEND", "hedera_testnet")
    monkeypatch.setattr(settings, "HEDERA_OPERATOR_KEY", "")
    state = la.start_worker()
    assert state["running"] is False and "HEDERA_OPERATOR_KEY is not set" in state["refused"] and la._TASK is None


def test_the_hedera_adapter_reads_the_public_mirror_node():
    msg = la.message(ROW)
    pages = {
        "https://m/api/v1/topics/0.0.2/messages?limit=100&order=asc": {
            "messages": [{"sequence_number": 1, "consensus_timestamp": "1.000000001",
                          "message": base64.b64encode(msg).decode()}],
            "links": {"next": "/api/v1/topics/0.0.2/messages?limit=100&order=asc&sequencenumber=gt:1"}},
        "https://m/api/v1/topics/0.0.2/messages?limit=100&order=asc&sequencenumber=gt:1": {
            "messages": [{"sequence_number": 2, "consensus_timestamp": "1.000000002",
                          "message": base64.b64encode(b"not ours").decode()}], "links": {"next": None}},
        "https://m/api/v1/topics/0.0.2/messages/1": {"sequence_number": 1, "consensus_timestamp": "1.000000001",
                                                    "message": base64.b64encode(msg).decode()},
    }
    a = la.HederaHcsAnchor(operator_id="0.0.1", operator_key="k", topic_id="0.0.2", mirror_url="https://m/",
                           http_get=lambda url: pages.get(url, {}))
    assert a.lookup("0.0.2", 1) == {"sequence_number": 1, "consensus_timestamp": "1.000000001", "message": msg}
    assert a.lookup("0.0.2", 9) is None
    idx = la.index_messages(a.messages("0.0.2"))
    assert list(idx) == ["b" * 64] and idx["b" * 64][0]["body"] == la.payload(ROW)


def test_without_the_sdk_a_submit_is_a_retry(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "hiero_sdk_python", None)       # import fails as when not installed
    a = la.HederaHcsAnchor(operator_id="0.0.1", operator_key="k", topic_id="0.0.2", mirror_url="https://m")
    with pytest.raises(la.AnchorUnavailable, match="not installed"):
        a.submit(la.message(ROW))


def test_a_ledger_error_never_carries_the_operator_key(monkeypatch):
    """A stand-in SDK whose failure quotes the key it was given: the outbox and the log
    must never see it."""
    import sys
    from types import ModuleType

    secret = "302e020100300506032b657004220420deadbeef"

    class Boom:
        def __init__(self, *a, **kw):
            pass

        @classmethod
        def from_string(cls, v):
            return cls()

        def set_operator(self, *a):
            raise RuntimeError(f"INVALID_SIGNATURE for key {secret}")

    sdk = ModuleType("hiero_sdk_python")
    for name in ("AccountId", "Client", "Network", "PrivateKey", "TopicId", "TopicMessageSubmitTransaction"):
        setattr(sdk, name, Boom)
    monkeypatch.setitem(sys.modules, "hiero_sdk_python", sdk)
    a = la.HederaHcsAnchor(operator_id="0.0.1", operator_key=secret, topic_id="0.0.2", mirror_url="https://m")
    with pytest.raises(la.AnchorUnavailable) as exc:
        a.submit(la.message(ROW))
    assert "INVALID_SIGNATURE" in str(exc.value) and secret not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None     # the original is not kept
