"""
Commitment cards (rules 4.0.0) — validation, ownership, audit, and delivery to
the engine.

The engine grades offtake (O0–O7) and EPC (E0–E6) and runs ten coherence checks
from these cards. A card that accepted nonsense would grade nonsense; a card any
company could write would let a counterparty state what the producer promised;
a card that never reached the engine would make every check NOT_EVALUABLE and
every gate look coherent.

Runs in the throwaway PostgreSQL database (conftest.pg_store); never touches the
development database. Since Phase 2 of "One contract record" (2026-11-06) a card
save and its contract version are ONE transaction in PostgreSQL (Phase 0 Q9),
so these tests left the SQLite isolated_store: on SQLite a card can no longer be
saved without its contract record.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1 import routes_bankability_proxy as proxy
from app.core.bankability_engine import COMMITMENT_CARD_FIELDS, TERMS_CARD_GATE
from app.core.commitment_terms import TermsValidationError, validate_card

PROJECT = "proj_terms_test"
OWNER = "acme_fuels"


# ── validation ──────────────────────────────────────────────────────────────

def test_a_valid_card_is_cleaned_and_empty_values_are_dropped():
    clean = validate_card("offtake", {
        "commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80, "tenor_years": 15,
        "buyer_investment_grade": True, "longstop_date": "2028-06-30T00:00:00",
        "compliance_regime": ["REFUELEU", " "], "counterparty_name": "  Uniper ",
        "product_spec_standard": "", "delay_ld_cap_eur": None,
    })
    assert clean == {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 80.0, "tenor_years": 15.0,
                     "buyer_investment_grade": True, "longstop_date": "2028-06-30",
                     "compliance_regime": ["REFUELEU"], "counterparty_name": "Uniper"}


@pytest.mark.parametrize("card, terms, fragment", [
    ("offtake", {"volume": 1}, "not a field of the offtake card"),
    ("offtake", {"commitment_form": "TAKE_OR_MAYBE"}, "must be one of"),
    ("offtake", {"take_or_pay_pct": 120}, "cannot exceed 100"),
    ("offtake", {"tenor_years": -1}, "zero or more"),
    ("offtake", {"tenor_years": True}, "must be a number"),
    ("offtake", {"longstop_date": "30/06/2028"}, "YYYY-MM-DD"),
    ("offtake", {"cps_satisfied": "yes"}, "true or false"),
    ("offtake", {"compliance_regime": "REFUELEU"}, "list of text"),
    ("epc", {"expected_availability_pct": 101}, "cannot exceed 100"),
    ("schedule", {"construction_months_p80": float("inf")}, "finite"),
])
def test_invalid_values_are_refused_with_the_reason(card, terms, fragment):
    with pytest.raises(TermsValidationError) as exc:
        validate_card(card, terms)
    assert fragment in str(exc.value)


def test_every_problem_is_reported_not_just_the_first():
    with pytest.raises(TermsValidationError) as exc:
        validate_card("offtake", {"volume": 1, "take_or_pay_pct": 500, "cps_satisfied": "no"})
    assert len(exc.value.problems) == 3


def test_an_unknown_card_is_refused():
    with pytest.raises(TermsValidationError):
        validate_card("dreams", {})


def test_every_card_has_a_gate_for_authorisation():
    from app.core.abac import gate_for_terms_card

    for card in COMMITMENT_CARD_FIELDS:
        assert gate_for_terms_card(card) == TERMS_CARD_GATE[card]
    assert gate_for_terms_card("dreams") is None and gate_for_terms_card(None) is None


# ── the endpoints ───────────────────────────────────────────────────────────

def _owner_sql(pg_store, *statements):
    """As the throwaway database's owner: the audit and record tables are append-only
    for the runtime role (and the record's by trigger), so cleaning up needs both."""
    import os

    from pg_support import connect_dsn

    conn = connect_dsn(os.environ["ALEMBIC_DATABASE_URL"].rsplit("/", 1)[0] + "/" + pg_store.rsplit("/", 1)[1])
    try:
        cur = conn.cursor()
        cur.execute("SET session_replication_role = replica")
        for sql in statements:
            cur.execute(sql, (PROJECT,) if "%s" in sql else ())
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="module")
def _seeded(pg_store):
    from app.db import session

    # projects_store caches ONE SQLAlchemy engine for the process: built here on the
    # throwaway URL, it would serve every later module the wrong database. Restore it.
    saved = session._sync_engine
    session._sync_engine = None
    _owner_sql(pg_store,
               f"INSERT INTO tenants (company_id, company_name, company_type) VALUES ('{OWNER}', 'TEST Acme', "
               "'PRODUCER') ON CONFLICT DO NOTHING",
               "INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule) VALUES "
               f"(%s, 'TEST terms plant', '{OWNER}', 'H2') ON CONFLICT DO NOTHING")
    yield pg_store
    if session._sync_engine is not None:
        session._sync_engine.dispose()
    session._sync_engine = saved


@pytest.fixture
def wired(_seeded, monkeypatch):
    from app.core.request_tenant import reset_current_company, set_current_company

    _owner_sql(_seeded,
               "DELETE FROM tb_contract_event WHERE contract_id IN (SELECT id FROM tb_contract WHERE project_id = %s)",
               "DELETE FROM tb_contract_version WHERE contract_id IN (SELECT id FROM tb_contract WHERE project_id = %s)",
               "DELETE FROM tb_contract WHERE project_id = %s",
               "DELETE FROM commitment_terms WHERE project_id = %s",
               "DELETE FROM commitment_terms_events WHERE project_id = %s")
    # The routes' own authorisation (_owner_gate) is what these tests exercise; the
    # tenant context is the operator's, as for the expiry sweep.
    token = set_current_company("PLATFORM_ADMIN")
    yield from _wired(monkeypatch)
    reset_current_company(token)


def _wired(monkeypatch):
    actor = {"user_id": "u_exec", "company_id": OWNER, "is_platform_admin": False}
    monkeypatch.setattr(proxy, "_require_actor", lambda authorization: actor)
    # Saving a card re-evaluates the project (2026-10-28): no live engine in tests.
    async def _engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "test", "persona_gates": {"PRODUCER": ["G4_OFFTAKE_BANKABLE"],
                                                               "EXECUTIVE": ["G4_OFFTAKE_BANKABLE"]}}
        return {"current_state": "SPECULATIVE", "gate_evaluations": []}
    monkeypatch.setattr(proxy, "_call_engine", _engine)
    proxy._RULES_CACHE.update(at=0.0, rules=None)
    monkeypatch.setattr(proxy, "_project_owner", lambda pid: OWNER if pid == PROJECT else None)
    yield actor


def _put(card, terms):
    return asyncio.run(proxy.put_commitment_terms(
        proxy.TermsWriteRequest(project_id=PROJECT, card_type=card, terms=terms), authorization="Bearer x"))


def _get():
    return asyncio.run(proxy.get_commitment_terms(project_id=PROJECT, authorization="Bearer x"))


def _events():
    return asyncio.run(proxy.list_commitment_terms_events(project_id=PROJECT, authorization="Bearer x"))["events"]


def test_the_owner_saves_a_card_and_reads_it_back_with_the_spec(wired):
    out = _put("offtake", {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 70})
    assert out["changed"] and out["terms"]["take_or_pay_pct"] == 70.0
    got = _get()
    assert got["cards"]["offtake"]["terms"] == {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 70.0}
    assert got["cards"]["offtake"]["updated_by"] == "u_exec"
    assert got["card_fields"] == COMMITMENT_CARD_FIELDS


def test_every_change_is_audited_with_old_and_new(wired):
    _put("epc", {"contracting_model": "LSTK"})
    _put("epc", {"contracting_model": "EPCM"})
    first, second = reversed(_events())
    assert first["old_json"] is None and '"LSTK"' in first["new_json"]
    assert '"LSTK"' in second["old_json"] and '"EPCM"' in second["new_json"]


def test_saving_the_same_card_again_changes_nothing(wired):
    _put("model", {"debt_tenor_years": 12})
    out = _put("model", {"debt_tenor_years": 12})
    assert out["changed"] is False
    assert len(_events()) == 1


def test_an_empty_card_clears_it_and_is_audited(wired):
    _put("schedule", {"construction_months_p80": 36})
    _put("schedule", {})
    assert _get()["cards"]["schedule"]["terms"] == {}
    assert _events()[0]["new_json"] == "{}"


def test_another_company_cannot_write_the_producers_cards(wired):
    wired.update(company_id="rival_co", user_id="u_other")
    with pytest.raises(HTTPException) as exc:
        _put("offtake", {"commitment_form": "TAKE_OR_PAY"})
    assert exc.value.status_code == 403


def test_the_read_tells_the_screen_who_may_edit(wired):
    """can_edit must follow the write rule exactly, or the screen offers a form
    the write then refuses (or hides one it would accept)."""
    assert _get()["can_edit"] is True
    wired.update(company_id="rival_co", user_id="u_other")
    assert _get()["can_edit"] is False
    wired.update(is_platform_admin=True)
    assert _get()["can_edit"] is True
    ownerless = asyncio.run(proxy.get_commitment_terms(project_id="default", authorization="Bearer x"))
    assert ownerless["can_edit"] is False


def test_a_platform_admin_can_write_them(wired):
    wired.update(company_id="greenearthx", user_id="u_admin", is_platform_admin=True)
    assert _put("offtake", {"commitment_form": "FRAMEWORK"})["changed"]


def test_a_project_without_an_owner_has_no_cards_to_write(wired):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(proxy.put_commitment_terms(
            proxy.TermsWriteRequest(project_id="default", card_type="offtake", terms={}), authorization="Bearer x"))
    assert exc.value.detail["code"] == "PROJECT_HAS_NO_OWNER"


def test_an_invalid_card_is_refused_whole_and_nothing_is_saved(wired):
    with pytest.raises(HTTPException) as exc:
        _put("offtake", {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 150})
    assert exc.value.status_code == 422 and exc.value.detail["code"] == "TERMS_INVALID"
    assert "offtake" not in _get()["cards"] and _events() == []


# ── delivery to the engine ──────────────────────────────────────────────────

def test_every_evaluation_sends_the_cards_to_the_engine(wired, monkeypatch):
    _put("offtake", {"commitment_form": "TAKE_IF_TENDERED"})
    _put("epc", {"contracting_model": "LSTK"})
    sent = []

    async def fake_engine(path, method="GET", json_data=None):
        if path == "/rules":
            return {"rules_version": "test", "persona_gates": {"PRODUCER": ["G4_OFFTAKE_BANKABLE"],
                                                               "EXECUTIVE": ["G4_OFFTAKE_BANKABLE"]}}
        sent.append((path, json_data))
        return {"current_state": "SPECULATIVE", "gate_evaluations": []}

    monkeypatch.setattr(proxy, "_call_engine", fake_engine)
    monkeypatch.setattr(proxy, "_store_snapshot", lambda *a, **k: None)
    asyncio.run(proxy.evaluate_project(project_id=PROJECT, authorization=None))
    proxy._RULES_CACHE.update(at=0.0, rules=None)
    # The persona is the caller's own now (the token decides), not a parameter.
    asyncio.run(proxy.evaluate_for_persona(project_id=PROJECT, persona=None, authorization="Bearer x"))
    asyncio.run(proxy.check_regression(project_id=PROJECT))
    # Since 2026-10-28 only terms CONFIRMED on their contract token reach the
    # engine (app/core/contract_tokens.py). These cards were typed by the owner
    # and confirmed by nobody, so every evaluation sends none of them.
    expected = {}
    assert [p for p, _ in sent] == ["/evaluate", "/evaluate/persona", "/regression/check"]
    for _, payload in sent:
        assert payload["terms"] == expected


def test_an_item_without_a_request_can_still_be_assigned_by_the_owner(wired):
    snap = {"gate_evaluations": [{"evidence_detail": [
        {"key": "technology_maturity_dossier", "status": "NOT_STARTED"},
        {"key": "credit_support_package", "status": "NOT_APPLICABLE"},
    ]}]}
    items = proxy._attach_assignments(snap, [], wired, PROJECT)["gate_evaluations"][0]["evidence_detail"]
    assert items[0]["can_assign"] is True and items[0]["commitment"] == "UNASSIGNED"
    assert items[1]["can_assign"] is False


# ── Q9 (2026-11-06): the card and its contract version are one transaction ──

def test_a_saved_card_records_its_contract_version_in_the_same_save(wired):
    from app.core import contract_tokens as ct

    _put("offtake", {"commitment_form": "TAKE_OR_PAY", "take_or_pay_pct": 70})
    c = ct.contract(PROJECT, "offtake", create=False)
    assert c is not None
    last = ct.latest_version(c["id"])
    assert last["terms_json"] == {"offtake.commitment_form": "TAKE_OR_PAY", "offtake.take_or_pay_pct": 70.0}


def test_if_the_version_cannot_be_recorded_the_card_is_not_saved(wired, monkeypatch):
    from app.core import contract_tokens as ct

    def broken(*args, **kwargs):
        raise RuntimeError("TEST: the contract record is unavailable")

    monkeypatch.setattr(ct, "record_versions", broken)
    with pytest.raises(HTTPException) as exc:
        _put("epc", {"contracting_model": "LSTK"})
    assert exc.value.status_code == 503 and exc.value.detail["code"] == "CONTRACT_RECORD_UNAVAILABLE"
    assert "epc" not in _get()["cards"] and _events() == []          # nothing saved, nothing audited
