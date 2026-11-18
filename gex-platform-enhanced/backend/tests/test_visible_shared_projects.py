"""
The project list: shared projects appear; only the owner gets write controls
(JML, 2026-11-18, findings A and B).

A  A project whose owner shared something with this user (a published returns
   case, a DEVEX section) appears in that user's project list, carrying what was
   shared and nothing else: no profile, no other parties (financiers among them),
   no gates. Only ACTIVE shares count, so a revocation takes it out of the list.
   An unreadable share store is 503, never a list silently missing projects.
B  `viewer_is_owner` is true only for the owner company (projects.owner_tenant_id);
   screens show write controls on it alone.

No database: the reads are replaced.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.v1.routes_projects as rp
import app.core.auth as auth
import app.core.entitlements as ent
import app.core.projects_store as ps

OWNER = "hamburgone_com"
BANK = {"user_id": "u_bank", "email": "bank@example.com", "company_id": "nordlb", "company_name": "NORD/LB"}
OWNER_USER = {"user_id": "u_cfo", "email": "cfo@example.com", "company_id": OWNER, "company_name": "HamburgOne"}

RECORDS = {
    "P_OWN": {"project_id": "P_OWN", "project_name": "Own project", "owner_tenant_id": "nordlb"},
    "P_SHARED": {"project_id": "P_SHARED", "project_name": "North Sea", "owner_tenant_id": OWNER},
    "P_ROLE": {"project_id": "P_ROLE", "project_name": "HamburgOne", "owner_tenant_id": OWNER},
}


def _vp(pid):
    return rp.VisibleProject(id=pid, name=RECORDS[pid]["project_name"], molecule="MeOH", location="Hamburg",
                             country="DE", capacity_mtpd=100.0, capacity_mt_year=1, status="development",
                             phase="FEED", owner_company="HamburgOne", associated_companies=["Other Bank AG"],
                             jurisdiction="DE", profile={"capex_note": "x"})


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(payload=dict(BANK), role_ids=["P_ROLE"], grants=[], fail_shares=False)
    monkeypatch.setattr(auth, "get_user_payload_from_token", lambda token: state.payload)
    monkeypatch.setattr(rp, "_visible_ids_from_jwt", lambda payload: list(state.role_ids))
    monkeypatch.setattr(rp, "all_project_profiles",
                        lambda: [SimpleNamespace(project_id=p, owner_company_id=r["owner_tenant_id"],
                                                 owner_company_name="HamburgOne") for p, r in RECORDS.items()])
    monkeypatch.setattr(rp, "_profile_to_visible", lambda profile: _vp(profile.project_id))

    async def bankability(pid, payload, owner):
        return {"evaluated": True, "gates": ["G0"]}
    monkeypatch.setattr(rp, "_engine_bankability", bankability)
    monkeypatch.setattr(ps, "project_owner_record", lambda pid: RECORDS.get(pid))

    def entitlements(user_id=None, project_id=None):
        if state.fail_shares:
            raise RuntimeError("store down")
        return [g for g in state.grants if g["user_id"] == user_id]
    monkeypatch.setattr(ent, "list_entitlements", entitlements)
    return state


def _grant(capability, status="active", project="P_SHARED", user="u_bank"):
    return {"user_id": user, "project_id": project, "capability": capability, "status": status}


def _visible():
    return asyncio.run(rp.get_visible_projects(authorization="Bearer t", x_demo_user=None))


def test_a_shared_project_appears_with_what_was_shared_and_nothing_else(world):
    world.grants = [_grant("RETURNS_SHARE:case_1@LATEST"), _grant("DEVEX_SHARE:SUMMARY")]
    out = {vp.id: vp for vp in _visible()}
    assert set(out) == {"P_ROLE", "P_SHARED"}
    shared = out["P_SHARED"]
    assert shared.name == "North Sea" and shared.owner_company == "HamburgOne"
    assert shared.disclosure == {"basis": "owner_share",
                                 "shared": ["DEVEX brief: SUMMARY", "Published returns case"]}
    # Nothing else: no profile, no other parties, no gates, no figures.
    assert shared.profile is None and shared.associated_companies == []
    assert shared.capex_eur is None and shared.location == "" and shared.molecule == ""
    assert shared.bankability["evaluated"] is False and "gates" not in shared.bankability
    assert shared.viewer_is_owner is False
    assert out["P_ROLE"].disclosure is None                  # its own relationship: unchanged


def test_a_revoked_or_expired_share_takes_the_project_out_of_the_list(world):
    world.grants = [_grant("RETURNS_SHARE:v1", status="revoked"), _grant("DEVEX_SHARE:SUMMARY", status="expired")]
    assert [vp.id for vp in _visible()] == ["P_ROLE"]


def test_other_grants_do_not_list_a_project(world):
    world.grants = [_grant("FINANCE_REVIEW")]
    assert [vp.id for vp in _visible()] == ["P_ROLE"]


def test_a_project_already_listed_is_not_listed_twice(world):
    world.grants = [_grant("RETURNS_SHARE:v1", project="P_ROLE")]
    out = _visible()
    assert [vp.id for vp in out] == ["P_ROLE"] and out[0].disclosure is None


def test_an_unreadable_share_store_is_503_not_a_shorter_list(world):
    world.fail_shares = True
    with pytest.raises(HTTPException) as exc:
        _visible()
    assert exc.value.status_code == 503 and exc.value.detail["code"] == "SHARES_UNAVAILABLE"


def test_only_the_owner_company_is_the_owner(world):
    world.role_ids = ["P_ROLE", "P_OWN"]
    out = {vp.id: vp.viewer_is_owner for vp in _visible()}
    assert out == {"P_ROLE": False, "P_OWN": True}               # the bank owns P_OWN only
    world.payload = dict(OWNER_USER)
    out = {vp.id: vp.viewer_is_owner for vp in _visible()}
    assert out == {"P_ROLE": True, "P_OWN": False}


def test_platform_staff_are_not_the_owner_and_get_no_share_listing(world):
    world.payload = {"user_id": "u_gex", "is_platform_admin": True, "company_id": "greenearthx"}
    world.grants = [_grant("RETURNS_SHARE:v1", user="u_gex")]
    out = _visible()
    assert [vp.id for vp in out] == ["P_ROLE"] and out[0].viewer_is_owner is False
