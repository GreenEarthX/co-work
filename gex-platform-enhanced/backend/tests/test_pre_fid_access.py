"""
Pre-FID access (app/core/pre_fid_access.py): ownership from the project record,
shares per section, 503 when either cannot be read, writes never opened by a
share, and nothing cached between requests.

The three reads the module makes are replaced, so no database is needed.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.core.pre_fid_access as pfa
from app.core.request_tenant import reset_current_company, set_current_company

RECORD = {"project_id": "P1", "project_name": "Project One", "owner_tenant_id": "t_owner_0042"}


def _request(**payload):
    return SimpleNamespace(state=SimpleNamespace(user_payload=payload or None, auth_user_payload=None))


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(shares={}, audit=[], record=dict(RECORD))
    monkeypatch.setattr(pfa, "_owner_record", lambda pid: state.record if pid in ("P1", "old_p1") else None)
    monkeypatch.setattr(pfa, "_active_sections", lambda user, pid: list(state.shares.get((user, pid), [])))
    monkeypatch.setattr(pfa, "_audit", lambda **kw: state.audit.append(kw))
    return state


def test_owner_is_the_tenant_on_the_project_record_not_a_name(world):
    a = pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "P1")
    assert (a.basis, a.full, a.owner_tenant) == ("owner", True, "t_owner_0042")
    # a company whose NAME would slug to the same thing is still a different tenant
    assert pfa.resolve(_request(user_id="u2", company_id="acme_fuels"), "P1").basis == "none"


def test_a_retired_project_id_resolves_to_the_current_one(world):
    assert pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "old_p1").project_id == "P1"


def test_platform_staff_by_token_or_by_bound_tenant(world):
    assert pfa.resolve(_request(user_id="s", company_id="gex", is_platform_admin=True), "P1").basis == "platform_admin"
    token = set_current_company(pfa.PLATFORM_ADMIN)
    try:
        assert pfa.resolve(_request(), "P1").basis == "platform_admin"
    finally:
        reset_current_company(token)


def test_the_bound_tenant_is_used_when_no_token_is_at_hand(world):
    token = set_current_company("t_owner_0042")
    try:
        assert pfa.resolve(_request(), "P1").basis == "owner"
    finally:
        reset_current_company(token)
    assert pfa.resolve(_request(), "P1").basis == "none"          # nobody bound, nobody served


@pytest.mark.parametrize("who", [
    dict(user_id="u_bank", company_id="north_bank", service_type="BANK"),
    dict(user_id="u_dfi", company_id="dev_bank", service_type="DFI"),
    dict(user_id="u_assoc", company_id="co_sponsor", business_function="FINANCE_TREASURY"),
])
def test_banks_dfis_and_associated_companies_have_nothing_without_a_share(world, who):
    access = pfa.resolve(_request(**who), "P1")
    assert (access.basis, access.sections) == ("none", ())
    for section in ("SUMMARY", "BREAKDOWN", "FUNDING", "PACKAGES"):
        with pytest.raises(HTTPException) as refused:
            pfa.require(access, section, route="t")
        assert refused.value.status_code == 403 and refused.value.detail["code"] == "PRE_FID_NOT_SHARED"
    assert all(entry["allowed"] is False for entry in world.audit)


def test_a_share_opens_its_own_section_only_and_never_a_write(world):
    world.shares[("u_bank", "P1")] = ["SUMMARY"]
    access = pfa.resolve(_request(user_id="u_bank", company_id="north_bank"), "P1")
    assert pfa.require(access, "SUMMARY", route="t") is access
    for detail in ("PACKAGES", "FUNDING", "BREAKDOWN"):               # a summary does not open the detail
        with pytest.raises(HTTPException):
            pfa.require(access, detail, route="t")
    with pytest.raises(HTTPException) as write:
        pfa.require(access, "SUMMARY", write=True, route="t")
    assert write.value.status_code == 403 and "read-only" in write.value.detail["message"]


def test_no_mandate_is_needed_an_adviser_with_a_share_reads(world):
    world.shares[("u_adviser", "P1")] = ["PACKAGES"]
    access = pfa.resolve(_request(user_id="u_adviser", company_id="dd_advisers", business_function="LEGAL"), "P1")
    assert access.basis == "share" and access.allows("PACKAGES")


def test_revocation_closes_the_path_on_the_next_request(world):
    who = dict(user_id="u_bank", company_id="north_bank")
    world.shares[("u_bank", "P1")] = ["FUNDING"]
    assert pfa.resolve(_request(**who), "P1").allows("FUNDING")
    world.shares[("u_bank", "P1")] = []                                # revoked
    assert not pfa.resolve(_request(**who), "P1").allows("FUNDING")
    assert pfa.withheld(_request(**who), "P1", "FUNDING", route="t") is True


def test_unknown_project_is_404(world):
    with pytest.raises(HTTPException) as e:
        pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "nope")
    assert e.value.status_code == 404


def test_unreadable_ownership_or_shares_is_unavailable_not_empty(world, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("database is down")

    world.record["owner_tenant_id"] = None
    with pytest.raises(HTTPException) as no_owner:
        pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "P1")
    assert no_owner.value.status_code == 503

    world.record["owner_tenant_id"] = "t_owner_0042"
    monkeypatch.setattr(pfa, "_active_sections", boom)
    with pytest.raises(HTTPException) as no_shares:
        pfa.resolve(_request(user_id="u_bank", company_id="north_bank"), "P1")
    assert no_shares.value.status_code == 503

    monkeypatch.setattr(pfa, "_owner_record", boom)
    with pytest.raises(HTTPException) as no_record:
        pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "P1")
    assert no_record.value.status_code == 503
    assert no_record.value.detail["code"] == "PRE_FID_DATA_UNAVAILABLE"
    with pytest.raises(HTTPException):                                 # a mixed answer is unavailable too
        pfa.withheld(_request(user_id="u1", company_id="t_owner_0042"), "P1", "PACKAGES", route="t")


def test_withheld_for_mixed_answers(world):
    owner = _request(user_id="u1", company_id="t_owner_0042")
    bank = _request(user_id="u_bank", company_id="north_bank")
    assert pfa.withheld(None, "P1", "PACKAGES", route="t") is False     # direct internal call
    assert pfa.withheld(owner, "P1", "PACKAGES", route="t") is False
    assert pfa.withheld(bank, "P1", "PACKAGES", route="t") is True
    assert pfa.withheld(owner, "nope", "PACKAGES", route="t") is True   # owner cannot be established
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    assert pfa.withheld(bank, "P1", "PACKAGES", route="t") is False
    assert pfa.withheld(bank, "P1", "FUNDING", route="t") is True


def test_owner_reads_are_not_audited_third_party_attempts_are(world):
    pfa.require(pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "P1"), "PACKAGES", route="t")
    assert world.audit == []
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    pfa.require(pfa.resolve(_request(user_id="u_bank", company_id="north_bank"), "P1"), "PACKAGES", route="packages.list")
    assert world.audit[-1]["allowed"] is True and world.audit[-1]["route"] == "packages.list"


def test_is_pre_fid_takes_strings_and_enums():
    assert pfa.is_pre_fid("FEED") and pfa.is_pre_fid(SimpleNamespace(value="FEL_1"))
    assert not pfa.is_pre_fid("CONSTRUCTION")


def test_a_shared_read_is_made_in_the_owner_tenant_and_everyone_else_reads_as_themselves(world):
    world.shares[("u_adviser", "P1")] = ["PACKAGES"]
    shared = pfa.resolve(_request(user_id="u_adviser", company_id="dd_advisers"), "P1")
    assert pfa.read_tenant(shared) == "t_owner_0042"
    assert pfa.read_tenant(pfa.resolve(_request(user_id="u1", company_id="t_owner_0042"), "P1")) is None
    assert pfa.read_tenant(pfa.resolve(_request(user_id="s", is_platform_admin=True), "P1")) is None


def test_the_package_list_share_does_not_open_evidence(world):
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    access = pfa.resolve(_request(user_id="u_bank", company_id="north_bank"), "P1")
    with pytest.raises(HTTPException):
        pfa.require(access, "EVIDENCE", route="t")
