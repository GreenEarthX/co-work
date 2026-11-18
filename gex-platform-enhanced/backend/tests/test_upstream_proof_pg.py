"""
G-23: cross-company hydrogen carries its RFNBO result through the permissioned upstream proof
(alembic 110; core/upstream_proof.py).

The seller produces hydrogen in a closed, passing custody period; a real order-book trade, an
agreed inspector's PASS certificate and a title transfer put the token with the buyer (109).
The buyer's ammonia period then cites that TOKEN as its hydrogen input, and its correlation
carries the upstream result — while the buyer still cannot read the seller's period, and a
company that does not hold the token gets nothing. Throwaway database (pg_store).
"""
from __future__ import annotations

import uuid

import psycopg2
import pytest

from test_contract_clauses import PAYMENT
from test_delivery_inspection_pg import _accounts, _docs_dir, inspectors  # noqa: F401
from test_delivery_record_pg import _parties, world  # noqa: F401
from test_delivery_record_pg import _row as _row_su
from test_delivery_title_pg import _accepted, _title
from test_evidence_pack_pg import (BASE, GBUYER, GCAP, GPROJECT, GSELLER, OTHER, _su, _superuser,  # noqa: F401
                                   client, scenario, seeded)
from test_order_book_token_pg import DELIVERY_CIF, custody_token  # noqa: F401

AMMONIA = "proj_TEST_g23_ammonia"


@pytest.fixture(scope="module", autouse=True)
def buyer_plant(world):
    from app.core import project_registry as reg

    _su(world, "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
               "(%s, 'TEST G-23 ammonia plant', %s, 'NH3') ON CONFLICT DO NOTHING", (AMMONIA, reg.company_slug(GBUYER)))


@pytest.fixture
def as_buyer(client):
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GBUYER)})
    yield client
    client.headers.pop("x-test-company", None)


def _delivered_token(custody_token):
    """The seller's whole custody token, delivered and title-transferred to the buyer."""
    d = _accepted(custody_token, (DELIVERY_CIF, _title("ON_ACCEPTANCE"), PAYMENT), kg=1000)
    assert d["status"] == "TITLE_TRANSFERRED", d["status"]
    return custody_token["token"]


def _ammonia_period(c):
    r = c.post(f"{BASE}/periods", json={
        "project_id": AMMONIA, "facility_id": f"NH3-{uuid.uuid4().hex[:8]}", "molecule": "NH3",
        "pathway": "HABER_BOSCH", "scheme": "TEST", "period_start": "2026-03-01", "period_end": "2026-03-31"})
    assert r.status_code == 201, r.text
    return r.json()["period_id"]


def _h2_input(c, period, **source):
    return c.post(f"{BASE}/periods/{period}/inputs", json={
        "input_type": "H2", "quantity": source.pop("kg", 500), "unit": "kg", "sustainability_status": "CERTIFIED",
        "received_on": "2026-03-05", "evidence_kind": "POS", "evidence_ref": "POS-H2-G23", **source})


def test_the_buyer_cites_the_hydrogen_it_holds_and_carries_its_rfnbo_result(custody_token, as_buyer):
    token = _delivered_token(custody_token)
    period = _ammonia_period(as_buyer)
    assert _h2_input(as_buyer, period, source_token_id=token).status_code == 201
    c = as_buyer.get(f"{BASE}/periods/{period}/rfnbo-correlation").json()
    up = c["upstream_hydrogen"]
    assert up["status"] == "PASS" and c["status"] == "PASS", c
    one = up["inputs"][0]
    assert (one["via"], one["upstream_period_id"]) == ("token proof", custody_token["period"])
    assert one["upstream_statement_hash"]
    # ... while the buyer still reads none of the seller's custody records.
    assert as_buyer.get(f"{BASE}/periods/{custody_token['period']}").status_code == 404
    proof = as_buyer.get(f"{BASE}/upstream-proof/{token}").json()
    assert (proof["status"], proof["verified"], proof["period_status"]) == ("PASS", True, "CLOSED")
    assert set(proof) <= {"token_id", "root_token_id", "token_state", "molecule", "token_kg", "lot_id", "period_id",
                          "period_status", "statement_hash", "verified", "status", "rfnbo_status", "rules_used",
                          "reason"}, "the proof's fields only, no rows of the seller"


def test_no_proof_and_no_citation_for_a_token_the_company_does_not_hold(custody_token, client, as_buyer):
    from app.core import project_registry as reg

    token = _delivered_token(custody_token)
    for company in (reg.company_slug(GSELLER), OTHER):            # the seller no longer holds it; a stranger never did
        client.headers.update({"x-test-company": company})
        assert client.get(f"{BASE}/upstream-proof/{token}").status_code == 404
    client.headers.update({"x-test-company": reg.company_slug(GBUYER)})
    assert client.get(f"{BASE}/upstream-proof/TKN-NO-SUCH").status_code == 404
    period = _ammonia_period(as_buyer)
    r = _h2_input(as_buyer, period, source_token_id=custody_token["token"] + "-x")
    assert r.status_code == 422 and "NOT_HELD" in r.text, r.text


def test_cited_hydrogen_is_used_once_and_never_retired(custody_token, as_buyer):
    url = custody_token["url"]
    token = _delivered_token(custody_token)
    period = _ammonia_period(as_buyer)
    assert _h2_input(as_buyer, period, source_token_id=token, kg=600).status_code == 201
    r = _h2_input(as_buyer, period, source_token_id=token, kg=401)          # 600 + 401 > 1000
    assert r.status_code == 409 and "EXHAUSTED" in r.text, r.text
    assert _h2_input(as_buyer, period, source_token_id=token, kg=400).status_code == 201   # exactly the rest
    conn = _superuser(url)
    try:
        with pytest.raises(psycopg2.Error, match="TOKEN_CONSUMED_DOWNSTREAM"):
            conn.cursor().execute("UPDATE tokens SET lifecycle_state = 'RETIRED' WHERE id = %s", (token,))
    finally:
        conn.rollback()
        conn.close()
    assert _row_su(url, "SELECT lifecycle_state FROM tokens WHERE id = %s", (token,))["lifecycle_state"] == "SETTLED"


def test_the_database_refuses_a_citation_past_the_application(custody_token, as_buyer):
    """110's trigger, below the API: a token not held by the consuming project's company."""
    url = custody_token["url"]
    period = _ammonia_period(as_buyer)
    conn = _superuser(url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT open_hash, project_id FROM coc_period WHERE period_id = %s", (period,))
        p = cur.fetchone()
        with pytest.raises(psycopg2.Error, match="COC_SOURCE_TOKEN_NOT_HELD"):
            cur.execute("INSERT INTO coc_input (input_id, period_id, project_id, input_type, quantity, unit, "
                        "quantity_normalised, normalised_unit, sustainability_status, received_on, characteristics, "
                        "evidence_kind, evidence_ref, recorded_by, seq, prev_hash, entry_hash, source_token_id) VALUES "
                        "(%s, %s, %s, 'H2', 1, 'kg', 1, 'kg', 'CERTIFIED', '2026-03-05', '{}', 'POS', 'x', 'raw', 1, "
                        "%s, 'h', %s)", (str(uuid.uuid4()), period, p["project_id"], p["open_hash"], custody_token["token"]))
    finally:
        conn.rollback()
        conn.close()


def test_one_source_only_and_only_for_hydrogen(custody_token, as_buyer):
    token = _delivered_token(custody_token)
    period = _ammonia_period(as_buyer)
    r = _h2_input(as_buyer, period, source_token_id=token, source_lot_id="LOT-X")
    assert r.status_code == 422 and "not both" in r.text, r.text
    r = as_buyer.post(f"{BASE}/periods/{period}/inputs", json={
        "input_type": "ELECTRICITY", "quantity": 5, "unit": "MWh", "sustainability_status": "CERTIFIED",
        "received_on": "2026-03-05", "evidence_kind": "PPA", "evidence_ref": "PPA-X", "source_token_id": token})
    assert r.status_code == 422 and "hydrogen" in r.text, r.text


def test_hydrogen_from_an_open_upstream_period_is_never_assumed_rfnbo(world, client, as_buyer, monkeypatch):
    """The seller's period is left OPEN: the token travels, but its proof is UNVERIFIED."""
    from app.core import project_registry as reg

    client.headers.update({"x-test-company": reg.company_slug(GSELLER)})
    try:
        s = scenario(client, world, project=GPROJECT, capacity=GCAP, synthetic=False, close=False)
    finally:
        client.headers.update({"x-test-company": reg.company_slug(GBUYER)})
    fac = _row_su(world, "SELECT facility_id FROM coc_period WHERE period_id = %s", (s["period"],))["facility_id"]
    token = _delivered_token({"token": s["token"], "facility": fac, "period": s["period"], "url": world})
    period = _ammonia_period(as_buyer)
    assert _h2_input(as_buyer, period, source_token_id=token).status_code == 201
    up = as_buyer.get(f"{BASE}/periods/{period}/rfnbo-correlation").json()["upstream_hydrogen"]
    assert up["status"] == "UNVERIFIED" and "still open" in up["inputs"][0]["reason"], up
