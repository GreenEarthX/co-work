"""
Quality before title (GreenMesh Phase 2 Step 3, sub-step 3; alembic 107; D1, D2, D3, B4).

On REAL confirmed order-book trades (G-25) carrying a quality specification sheet:
  * an inspector is proposed by one party and agreed by the other with four eyes;
    never the seller's, the buyer's, GEX or an inactive company; proposed-but-unagreed
    cannot certify;
  * the agreed inspector certifies against the sheet; PASS accepts (derived, VERIFIED);
  * off-spec: not accepted; either a waiver both parties confirm (DECLARED, FAIL) or the
    buyer rejects, which releases the draw with the certificate untouched (B4);
  * no sheet, no certificate (D2). Throwaway database (pg_store).
"""
from __future__ import annotations

import contextlib

import psycopg2
import pytest

from test_delivery_record_pg import JAN, NOW, _parties, _refused, world  # noqa: F401
from test_delivery_record_pg import _row as _row_su
from test_evidence_pack_pg import _su, client, seeded  # noqa: F401
from test_order_book_token_pg import confirmed_order_book_trade, custody_token  # noqa: F401

SPEC = {"purity_pct": {"min": "99.97", "unit": "%"}, "ghg_intensity_gco2e_mj": {"max": "28.2", "unit": "gCO2e/MJ"}}
GOOD = {"purity_pct": "99.98", "ghg_intensity_gco2e_mj": "3.0"}
OFF = {"purity_pct": "99.90", "ghg_intensity_gco2e_mj": "3.0"}
INSPECTOR, IDLE, DORMANT = "test_insp_co", "test_insp_idle", "test_insp_dormant"


@pytest.fixture(scope="module", autouse=True)
def inspectors(world):
    for company, active in ((INSPECTOR, True), (IDLE, True), (DORMANT, False)):
        _su(world, "INSERT INTO tenants (company_id, company_name, company_type, jurisdiction, is_active) VALUES "
                   "(%s, %s, 'THIRD_PARTY', 'CH', %s) ON CONFLICT DO NOTHING", (company, f"TEST {company}", active))
    from app.core import project_registry as reg
    from test_evidence_pack_pg import GBUYER

    _su(world, "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
               "business_function, user_name, account_state, is_active) VALUES ('g_buyer3','g_buyer3@test.invalid','x',"
               "%s,%s,'PRODUCER','COMMERCIAL','TEST g_buyer3','ACTIVE',1) ON CONFLICT DO NOTHING",
        (reg.company_slug(GBUYER), GBUYER))
    for uid, company, admin in (("u_insp", INSPECTOR, False), ("u_insp_dormant", DORMANT, False),
                                ("u_gex_test", "greenearthx", True)):
        _su(world, "INSERT INTO tenants (company_id, company_name, company_type) VALUES (%s, %s, 'THIRD_PARTY') "
                   "ON CONFLICT DO NOTHING", (company, f"TEST {company}"))
        _su(world, "INSERT INTO auth_users (user_id, email, password_hash, company_id, company_name, company_type, "
                   "business_function, user_name, account_state, is_active, is_platform_admin) VALUES "
                   "(%s,%s,'x',%s,%s,'THIRD_PARTY','EXECUTIVE',%s,'ACTIVE',1,%s) ON CONFLICT DO NOTHING",
            (uid, f"{uid}@test.invalid", company, f"TEST {company}", f"TEST {uid}", int(admin)))


@contextlib.contextmanager
def _accounts():
    """Account lookups (four eyes) read the throwaway database."""
    from app.db import session

    saved = session._sync_engine
    session._sync_engine = None
    try:
        yield
    finally:
        if session._sync_engine is not None:
            session._sync_engine.dispose()
        session._sync_engine = saved


def _party(uid, company):
    from app.core import market_engine as me

    return me.Party(business_function="COMMERCIAL", user_id=uid, company_id=company)


def _inspection(custody_token, spec=SPEC, kg=100, clauses=None, **trade):
    """A delivery in QUALITY_VERIFICATION on a confirmed trade carrying `spec` (and `clauses`)."""
    from app.core import delivery_record as dr

    # No title clause by default: these tests stop at ACCEPTED. Title (109) passes its own clauses.
    from test_contract_clauses import PAYMENT
    from test_order_book_token_pg import DELIVERY_CIF

    clauses = (DELIVERY_CIF, PAYMENT) if clauses is None else clauses
    t = confirmed_order_book_trade(custody_token["url"], custody_token["token"], spec=spec, clauses=clauses, **trade)
    seller, buyer = _parties()
    d = dr.schedule(seller, t["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": custody_token["token"], "kg": kg}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": "SHIP",
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})
    dr.dispatch(seller, d["id"], kg, NOW())
    dr.receive(buyer, d["id"], kg, NOW())
    return dr.request_inspection(buyer, d["id"])


def _doc(party, d, kind, body=b"TEST document"):
    from app.core import delivery_documents as docs

    return docs.file_document(party, d["id"], kind, f"{kind.lower()}.pdf", body + kind.encode())["sha256"]


def _confirm(d, act, first, second):
    from app.core import delivery_inspection as di

    with _accounts():
        req = di.request_confirmation(first, d["id"], act)["request_id"]
        return di.approve_confirmation(second, d["id"], req)


def _appoint(d, inspector=INSPECTOR):
    """The seller proposes, the buyer agrees with four eyes."""
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    di.propose_inspector(seller, d["id"], inspector, _doc(seller, d, "INSPECTOR_APPOINTMENT"))
    return _confirm(d, "INSPECTOR_AGREED", buyer, _party("g_buyer2", buyer.company_id))


def _certify(d, measured):
    from app.core import delivery_inspection as di

    insp = _party("u_insp", INSPECTOR)
    return di.certify(insp, d["id"], _doc(insp, d, "INSPECTION_CERTIFICATE"), measured)


@pytest.fixture(autouse=True)
def _docs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GEX_DELIVERY_DOCS_DIR", str(tmp_path))


def _types(d):
    return [e["event_type"] for e in d["events"]]


def test_a_pass_certificate_from_the_agreed_inspector_accepts_the_delivery(custody_token):
    from app.core import delivery_record as dr

    seller, _ = _parties()
    d = _appoint(_inspection(custody_token))
    assert d["inspector_company_id"] == INSPECTOR and d["quality"]["inspector_company_id"] == INSPECTOR
    _certify(d, GOOD)
    d = dr.get_delivery(seller, d["id"])
    assert d["status"] == "ACCEPTED"
    accepted = next(e for e in d["events"] if e["event_type"] == "DELIVERY_ACCEPTED")
    assert (accepted["company_id"], accepted["actor"]) == (None, "system:inspection"), "derived, no party act"
    assert d["quality"]["acceptance"] == {"basis": "CERTIFICATE", "label": "VERIFIED", "result": "PASS"}
    assert d["quality"]["certificate"]["result"] == "PASS"


def test_an_off_spec_cargo_is_not_accepted_and_the_buyer_rejects_it(custody_token):
    import psycopg2  # noqa: F811

    from app.core import delivery_inspection as di
    from app.core import delivery_record as dr

    url, token = custody_token["url"], custody_token["token"]
    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token, kg=1000))                 # draws ALL the token's 1000 kg
    before = _row_su(url, "SELECT compliance_certifications, carbon_intensity_gco2e_mj, mass_balance_lot_id, "
                          "lifecycle_state FROM tokens WHERE id = %s", (token,))
    _certify(d, OFF)
    d = dr.get_delivery(seller, d["id"])
    assert d["status"] == "QUALITY_VERIFICATION" and d["quality"]["certificate"]["result"] == "FAIL"
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record
    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        with pytest.raises(psycopg2.Error, match="DELIVERY_NOT_ACCEPTABLE"):
            record.append_event(shim, d["contract_id"], "DELIVERY_ACCEPTED", "test", None, delivery_id=d["id"])
    finally:
        shim.rollback()
        shim.close()
    _refused(lambda: di.reject(seller, d["id"], "TEST"), status=403)
    _refused(lambda: di.reject(buyer, d["id"], " "), status=422, code="REJECTION_REASON")
    d = di.reject(buyer, d["id"], "TEST purity below the sheet")
    assert d["status"] == "REJECTED"
    # B4: the draw is released, with the certificate untouched and no split.
    after = _row_su(url, "SELECT compliance_certifications, carbon_intensity_gco2e_mj, mass_balance_lot_id, "
                         "lifecycle_state FROM tokens WHERE id = %s", (token,))
    assert after == before
    again = dr.schedule(seller, d["contract_id"], {
        "flow": {"leg_seq": 1, "flow_seq": 1}, "draws": [{"token_id": token, "kg": 1000}],
        "window_start": JAN[0], "window_end": JAN[1], "transport_mode": "SHIP",
        "origin": {"facility_id": custody_token["facility"]}, "destination": {"locode": "NLRTM"}})
    assert again["nominated_kg"] == "1000", "the rejected delivery's 1000 kg are drawn again"


def test_a_waiver_both_parties_confirm_accepts_it_labelled_declared_and_fail(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _appoint(_inspection(custody_token))
    _certify(d, OFF)
    d = di.propose_waiver(seller, d["id"], _doc(seller, d, "WAIVER"))
    with _accounts():
        _refused(lambda: di.request_confirmation(seller, d["id"], "WAIVER_CONFIRMED"), status=403,
                 code="DELIVERY_SAME_PARTY")
    d = _confirm(d, "WAIVER_CONFIRMED", buyer, _party("g_buyer2", buyer.company_id))
    assert d["status"] == "ACCEPTED"
    assert d["quality"]["acceptance"] == {"basis": "WAIVER", "label": "DECLARED", "result": "FAIL"}
    assert d["quality"]["waiver_confirmed"] is True
    _refused(lambda: di.reject(buyer, d["id"], "TEST"), status=409)


def test_a_non_independent_inspector_is_refused(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _inspection(custody_token)
    doc = _doc(seller, d, "INSPECTOR_APPOINTMENT")
    for company in (seller.company_id, buyer.company_id, "greenearthx", DORMANT, IDLE, "test_no_such_co"):
        _refused(lambda c=company: di.propose_inspector(seller, d["id"], c, doc), status=422,
                 code="DELIVERY_INSPECTOR_NOT_INDEPENDENT")
    from app.core.db_backend import PLATFORM_ADMIN, market_connection
    from app.trading_book import record
    shim = market_connection(company_id=PLATFORM_ADMIN)
    try:
        with pytest.raises(psycopg2.Error, match="DELIVERY_INSPECTOR_NOT_INDEPENDENT"):
            record.append_event(shim, d["contract_id"], "DELIVERY_FACT_INSPECTOR_PROPOSED", "g_seller", seller.company_id,
                                delivery_id=d["id"], note=f'{{"document_sha256":"{doc}","inspector_company_id":"{buyer.company_id}"}}')
    finally:
        shim.rollback()
        shim.close()


def test_an_inspector_proposed_but_not_agreed_cannot_certify(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _inspection(custody_token)
    di.propose_inspector(seller, d["id"], INSPECTOR, _doc(seller, d, "INSPECTOR_APPOINTMENT"))
    insp = _party("u_insp", INSPECTOR)
    _refused(lambda: di.certify(insp, d["id"], "0" * 64, GOOD), status=403, code="DELIVERY_NOT_THE_AGREED_INSPECTOR")
    from app.core import delivery_documents as docs
    _refused(lambda: docs.file_document(insp, d["id"], "INSPECTION_CERTIFICATE", "c.pdf", b"x"), status=404)
    with _accounts():
        _refused(lambda: di.request_confirmation(seller, d["id"], "INSPECTOR_AGREED"), status=403,
                 code="DELIVERY_SAME_PARTY")                        # the proposer cannot agree its own
        req = di.request_confirmation(buyer, d["id"], "INSPECTOR_AGREED")["request_id"]
        di.propose_inspector(seller, d["id"], INSPECTOR, _doc(seller, d, "INSPECTOR_APPOINTMENT", b"TEST v2 "))
        _refused(lambda: di.approve_confirmation(_party("g_buyer2", buyer.company_id), d["id"], req), status=409,
                 code="DELIVERY_PROPOSAL_CHANGED")                  # a newer proposal voids the older agreement


def test_four_eyes_inside_the_agreeing_party(custody_token):
    from app.core import delivery_inspection as di

    seller, buyer = _parties()
    d = _inspection(custody_token)
    di.propose_inspector(seller, d["id"], INSPECTOR, _doc(seller, d, "INSPECTOR_APPOINTMENT"))
    with _accounts():
        # Two non-executives of the buyer cannot agree it between them (TRADE_CONFIRM's rule).
        weak = di.request_confirmation(_party("g_buyer", buyer.company_id), d["id"], "INSPECTOR_AGREED")["request_id"]  # D-B swap: g_buyer is Commercial
        _refused(lambda: di.approve_confirmation(_party("g_buyer3", buyer.company_id), d["id"], weak), status=403,
                 code="EXECUTIVE_REQUIRED")
        req = di.request_confirmation(buyer, d["id"], "INSPECTOR_AGREED")["request_id"]
        _refused(lambda: di.approve_confirmation(buyer, d["id"], req), status=403, code="SOD_SELF_APPROVAL")
        _refused(lambda: di.approve_confirmation(_party("g_seller2", seller.company_id), d["id"], req), status=404)
        assert di.approve_confirmation(_party("g_buyer2", buyer.company_id), d["id"], req)["inspector_company_id"] == INSPECTOR


def test_no_confirmed_sheet_no_certificate_and_every_parameter_is_measured(custody_token):
    from app.core import delivery_inspection as di

    d = _appoint(_inspection(custody_token, spec=None))
    insp = _party("u_insp", INSPECTOR)
    doc = _doc(insp, d, "INSPECTION_CERTIFICATE")
    _refused(lambda: di.certify(insp, d["id"], doc, GOOD), status=409, code="DELIVERY_NO_CONFIRMED_SPEC")


def test_a_certificate_measures_every_parameter_of_the_sheet(custody_token):
    from app.core import delivery_inspection as di

    d = _appoint(_inspection(custody_token))
    insp = _party("u_insp", INSPECTOR)
    doc = _doc(insp, d, "INSPECTION_CERTIFICATE")
    _refused(lambda: di.certify(insp, d["id"], doc, {"purity_pct": "99.99"}), status=422,
             code="DELIVERY_CERTIFICATE_INCOMPLETE")
    _refused(lambda: di.certify(insp, d["id"], "f" * 64, GOOD), status=422, code="DELIVERY_DOCUMENT_NOT_ON_FILE")
