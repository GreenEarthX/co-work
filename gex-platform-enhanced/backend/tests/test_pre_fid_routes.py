"""
Pre-FID access on the package and spend-wave APIs.
==================================================
The rule is tested in test_pre_fid_access.py. This pins how the two APIs apply
it: which section each read needs, that a shared read is made in the owner's
tenant, that writes need the owner, and that non-pre-FID packages are not
affected. The connections and the access reads are replaced; no database.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.api.v1.development_packages as dp  # noqa: E402
import app.api.v1.spend_wave as sw  # noqa: E402
import app.core.pre_fid_access as pfa  # noqa: E402

OWNER = "t_owner_0042"
ROWS = [{"package_id": "dev", "project_id": "P1", "phase_required": "FEL_2"},
        {"package_id": "epc", "project_id": "P1", "phase_required": "CONSTRUCTION"}]


def _request(**payload):
    return SimpleNamespace(state=SimpleNamespace(user_payload=payload or None, auth_user_payload=None))


OWNER_REQ = dict(user_id="u_cfo", company_id=OWNER, business_function="FINANCE_TREASURY")
BANK_REQ = dict(user_id="u_bank", company_id="north_bank", service_type="BANK")


class FakeConn:
    def __init__(self, tenant, rows):
        self.tenant, self.rows, self.closed = tenant, rows, False

    def execute(self, *_a, **_k):
        return SimpleNamespace(fetchall=lambda: list(self.rows), fetchone=lambda: self.rows[0] if self.rows else None)

    def close(self):
        self.closed = True


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(shares={}, audit=[], opened=[])
    record = {"project_id": "P1", "project_name": "Project One", "owner_tenant_id": OWNER}
    monkeypatch.setattr(pfa, "_owner_record", lambda pid: record if pid == "P1" else None)
    monkeypatch.setattr(pfa, "_active_sections", lambda user, pid: list(state.shares.get((user, pid), [])))
    monkeypatch.setattr(pfa, "_audit", lambda **kw: state.audit.append(kw))

    def connection(tenant=None):
        # the owner's tenant sees every row; a caller outside it sees the post-FID row only
        conn = FakeConn(tenant, ROWS if tenant in (OWNER, None) else [])
        state.opened.append(tenant)
        return conn

    monkeypatch.setattr(dp, "_connection", connection)
    monkeypatch.setattr(dp, "_package_ref", lambda pid: next(
        ({"project_id": r["project_id"], "phase_required": r["phase_required"]} for r in ROWS
         if r["package_id"] == pid), None))
    return state


def _ids(rows):
    return [r["package_id"] for r in rows]


# ── project-level reads ──────────────────────────────────────────────────────

def test_the_owner_sees_every_package(world):
    rows, withheld = dp._project_rows("P1", FakeConn(OWNER, ROWS), _request(**OWNER_REQ), "t")
    assert (_ids(rows), withheld) == (["dev", "epc"], False)


def test_a_bank_without_a_share_loses_the_pre_fid_package_and_is_told(world):
    caller_rows = ROWS          # RLS lets a related bank see both rows; the rule removes one
    rows, withheld = dp._project_rows("P1", FakeConn("north_bank", caller_rows), _request(**BANK_REQ), "t")
    assert (_ids(rows), withheld) == (["epc"], True)
    assert world.audit[-1]["allowed"] is False


def test_a_shared_read_takes_the_pre_fid_rows_from_the_owner_tenant(world):
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    rows, withheld = dp._project_rows("P1", FakeConn("north_bank", [ROWS[1]]), _request(**BANK_REQ), "t")
    assert (_ids(rows), withheld) == (["epc", "dev"], False)
    assert world.opened == [OWNER]


def test_an_adviser_with_no_project_relationship_still_gets_what_was_shared(world):
    world.shares[("u_adv", "P1")] = ["PACKAGES"]
    adviser = _request(user_id="u_adv", company_id="dd_advisers")
    rows, withheld = dp._project_rows("P1", FakeConn("dd_advisers", []), adviser, "t")   # RLS shows nothing
    assert (_ids(rows), withheld) == (["dev"], False)


def test_a_direct_internal_call_is_unchanged(world):
    rows, withheld = dp._project_rows("P1", FakeConn(None, ROWS), None, "t")
    assert (_ids(rows), withheld) == (["dev", "epc"], False)


# ── item reads: the section each one needs ───────────────────────────────────

def _open(section, package_id, who):
    gen = dp._package_db(section, "t")(package_id, _request(**who))
    return gen, next(gen)


def test_item_reads_need_their_own_section(world):
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    _, conn = _open("PACKAGES", "dev", BANK_REQ)
    assert conn.tenant == OWNER                                      # shared read, owner tenant
    with pytest.raises(HTTPException) as refused:                    # the list does not open the evidence
        _open("EVIDENCE", "dev", BANK_REQ)
    assert refused.value.status_code == 403
    world.shares[("u_bank", "P1")] = ["PACKAGES", "EVIDENCE"]
    assert _open("EVIDENCE", "dev", BANK_REQ)[1].tenant == OWNER


def test_post_fid_packages_and_the_owner_read_as_themselves(world):
    assert _open("EVIDENCE", "epc", BANK_REQ)[1].tenant is None      # not pre-FID: no change
    assert _open("EVIDENCE", "dev", OWNER_REQ)[1].tenant is None


def test_the_connection_is_closed_after_the_request(world):
    gen, conn = _open("PACKAGES", "dev", OWNER_REQ)
    with pytest.raises(StopIteration):
        next(gen)
    assert conn.closed


def test_a_share_never_opens_a_write(world):
    world.shares[("u_bank", "P1")] = ["PACKAGES", "EVIDENCE"]
    with pytest.raises(HTTPException) as refused:
        dp._pre_fid_write("dev", _request(**BANK_REQ))
    assert refused.value.status_code == 403
    dp._pre_fid_write("dev", _request(**OWNER_REQ))                  # the owner may
    dp._pre_fid_write("epc", _request(**BANK_REQ))                   # post-FID: not this rule's business


# ── spend wave ───────────────────────────────────────────────────────────────

def test_spend_wave_reads_need_funding_and_a_shared_read_uses_the_owner_tenant(world, monkeypatch):
    opened = []
    monkeypatch.setattr(sw, "domain_connection", lambda company_id=None: opened.append(company_id) or FakeConn(company_id, []))
    monkeypatch.setattr(sw, "domain_is_postgres", lambda: True)

    with pytest.raises(HTTPException) as refused:
        next(sw._funding_db("P1", _request(**BANK_REQ)))
    assert refused.value.status_code == 403
    world.shares[("u_bank", "P1")] = ["SUMMARY"]                       # a summary does not open the spend wave
    with pytest.raises(HTTPException):
        next(sw._funding_db("P1", _request(**BANK_REQ)))
    world.shares[("u_bank", "P1")] = ["FUNDING"]
    next(sw._funding_db("P1", _request(**BANK_REQ)))
    next(sw._funding_db("P1", _request(**OWNER_REQ)))
    assert opened == [OWNER, None]
