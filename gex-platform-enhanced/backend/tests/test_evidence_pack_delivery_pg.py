"""
The evidence pack, extended with deliveries (GreenMesh Phase 2 Step 5; pack version 2).

On REAL flows: a custody-backed token from a closed RFNBO period, a confirmed order-book trade,
an agreed inspector, a certificate, and (where the title clause allows) title. Pinned: quality
VERIFIED only with an agreed inspector's certificate on file, DECLARED/FAIL under a waiver,
MISSING without one; title VERIFIED from the recomputed chain; route and Incoterm DECLARED;
`compliance_complete` needs every delivery's quality VERIFIED and PASS; a delivery contract's
tokens come from its draws even with no settlement; settlements say they are not linked to
deliveries; the manifest is deterministic. Throwaway database (pg_store).
"""
from __future__ import annotations

from test_contract_clauses import PAYMENT
from test_delivery_inspection_pg import (GOOD, OFF, _accounts, _appoint, _certify, _confirm, _doc,  # noqa: F401
                                         _docs_dir, _inspection, _party, inspectors)
from test_delivery_record_pg import _parties, world  # noqa: F401
from test_delivery_title_pg import _title
from test_evidence_pack_pg import GSELLER, _pack, client, seeded  # noqa: F401
from test_order_book_token_pg import DELIVERY_CIF, custody_token  # noqa: F401

CLAUSES = (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT)


def _seller_pack(client, cid):
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GSELLER)})
    try:
        return _pack(client, cid)
    finally:
        client.headers.pop("x-test-company", None)


def _items(pack, name=None):
    items = pack["sections"]["deliveries"]["items"]
    return {i["item"]: i for i in items} if name is None else [i for i in items if i["item"] == name]


def test_a_certified_delivered_contract_is_complete_with_no_settlement(custody_token, client):
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))
    _certify(d, GOOD)                                          # PASS, ACCEPTED, then TITLE_TRANSFERRED
    pack = _seller_pack(client, d["contract_id"])
    it = _items(pack)
    assert (it["quality"]["label"], it["quality"]["result"]) == ("VERIFIED", "PASS")
    assert it["quality"]["certificate_sha256"] and it["quality"]["inspector_company_id"]
    assert (it["title_transfer"]["label"], it["title_transfer"]["result"]) == ("VERIFIED", "PASS")
    assert {it["route"]["label"], it["incoterm"]["label"]} == {"DECLARED"}
    assert it["incoterm"]["incoterm"] == "CIF"
    # The token came from the delivery's draw (no settlement exists), and its period is compliant.
    assert pack["sections"]["tokens"]["items"][0]["token_id"] == custody_token["token"]
    assert pack["summary"]["compliance"] == {"VERIFIED": 7, "DECLARED": 0, "MISSING": 0, "FAIL": 0}
    assert pack["summary"]["deliveries_quality_verified"] is True
    assert pack["summary"]["compliance_complete"] is True
    assert pack["pack_version"] == "3"


def test_a_waiver_makes_quality_declared_and_the_pack_incomplete(custody_token, client):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))
    _certify(d, OFF)
    di.propose_waiver(seller, d["id"], _doc(seller, d, "WAIVER"))
    _confirm(d, "WAIVER_CONFIRMED", buyer, _party("g_buyer2", buyer.company_id))
    pack = _seller_pack(client, d["contract_id"])
    q = _items(pack)["quality"]
    assert (q["label"], q["result"], q["certificate_result"]) == ("DECLARED", "FAIL", "FAIL")
    assert pack["summary"]["compliance"]["MISSING"] == 0, "the custody compliance itself is complete"
    assert pack["summary"]["compliance_complete"] is False, "a waived delivery keeps the pack incomplete"


def test_without_a_certificate_quality_and_title_are_missing(custody_token, client):
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))         # in QUALITY_VERIFICATION
    pack = _seller_pack(client, d["contract_id"])
    it = _items(pack)
    assert it["quality"]["label"] == "MISSING" and it["title_transfer"]["label"] == "MISSING"
    assert pack["summary"]["compliance_complete"] is False


def test_settlements_say_they_are_not_linked_to_deliveries(custody_token, client):
    from app.core import market_engine as me

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=100, clauses=CLAUSES))
    with _accounts():
        stl = me.create_settlement(buyer, d["contract_id"], settlement_type="SPOT", volume_kg=100)["settlement_id"]
    pack = _seller_pack(client, d["contract_id"])
    s = next(i for i in pack["sections"]["settlement"]["items"] if i.get("settlement_id") == stl)
    assert s["delivery_id"] is None and "not linked to deliveries" in s["delivery_link"]


def test_the_manifest_is_deterministic_and_moves_with_a_delivery_event(custody_token, client):
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _appoint(_inspection(custody_token, kg=1000, clauses=CLAUSES))
    first, again = _seller_pack(client, d["contract_id"]), _seller_pack(client, d["contract_id"])
    assert first["manifest"]["pack_sha256"] == again["manifest"]["pack_sha256"]
    dr.dispute(seller, d["id"], "TEST")
    moved = _seller_pack(client, d["contract_id"])
    assert moved["manifest"]["sections"]["deliveries"] != first["manifest"]["sections"]["deliveries"]
    assert moved["manifest"]["pack_sha256"] != first["manifest"]["pack_sha256"]
