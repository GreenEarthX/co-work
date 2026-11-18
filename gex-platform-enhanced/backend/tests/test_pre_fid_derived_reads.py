"""
Derived pre-FID disclosures (handoff v4, task 9; Part C test 15).

CEC, FRI and the capital gap are computed from development packages; the
lineage identity and the capital-bridge one-shot view read them too. The rule
(pre_fid_access) must hold on each: the owner gets everything; anyone else gets
the post-FID figures only, labelled, unless the owner shared the section; a
shared read is made in the owner's tenant. No database: connections and the
access reads are replaced.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.v1.development_packages as devp
import app.api.v1.pre_cod_metrics as pcm
import app.core.pre_fid_access as pfa

OWNER = "t_owner_0042"
DEV = {"package_id": "dev", "project_id": "P1", "phase_required": "FEL_2", "cost_amount": 4_000_000.0,
       "workflow_state": "identified", "estimate_class": "CLASS_5", "package_name": "Owner's secret FEED name"}
EPC = {"package_id": "epc", "project_id": "P1", "phase_required": "CONSTRUCTION", "cost_amount": 6_000_000.0,
       "workflow_state": "evidenced", "estimate_class": "CLASS_3", "package_name": "EPC"}


def _request(**payload):
    return SimpleNamespace(state=SimpleNamespace(user_payload=payload or None, auth_user_payload=None))


OWNER_REQ = dict(user_id="u_cfo", company_id=OWNER)
BANK_REQ = dict(user_id="u_bank", company_id="north_bank", service_type="BANK")


class FakeConn:
    def __init__(self, tenant, rows=None, spend=None):
        self.tenant, self.rows, self.spend, self.sql = tenant, rows or [], spend or [], []

    def execute(self, sql, *_a, **_k):
        self.sql.append(sql)
        rows = self.spend if "spend_wave" in sql else ([] if "INSERT" in sql else self.rows)
        return SimpleNamespace(fetchall=lambda: [dict(r) for r in rows],
                               fetchone=lambda: dict(rows[0]) if rows else None)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(shares={}, audit=[], opened=[])
    record = {"project_id": "P1", "project_name": "Project One", "owner_tenant_id": OWNER}
    monkeypatch.setattr(pfa, "_owner_record", lambda pid: record if pid == "P1" else None)
    monkeypatch.setattr(pfa, "_active_sections", lambda user, pid: list(state.shares.get((user, pid), [])))
    monkeypatch.setattr(pfa, "_audit", lambda **kw: state.audit.append(kw))

    def connection(tenant=None):
        state.opened.append(tenant)
        return FakeConn(tenant, [DEV, EPC] if tenant in (OWNER, None) else [])

    monkeypatch.setattr(devp, "_connection", connection)
    return state


def _cec(who, rows=(DEV, EPC), **body):
    return pcm.compute_pre_cod_metrics("P1", pcm.PreCODRequest(project_id="P1", **body),
                                       request=_request(**who), db=FakeConn(who.get("company_id"), list(rows)))


# ── CEC ──────────────────────────────────────────────────────────────────────

def test_the_owner_gets_cec_on_every_package(world):
    r = _cec(OWNER_REQ)
    assert r.cec_basis == pcm.CEC_ALL and r.cec_basis_label is None
    assert r.cec.value == pytest.approx(0.6)                  # 6M evidenced of 10M


def test_a_bank_without_summary_gets_post_fid_cec_only_labelled(world):
    r = _cec(BANK_REQ)
    assert r.cec_basis == pcm.CEC_POST_FID and r.cec.value == pytest.approx(1.0)   # EPC only
    assert "post-FID packages only" in r.cec.formatted
    assert r.cec_basis_label == pcm.CEC_POST_FID_LABEL == r.cec.known_limitation
    assert r.capital_gap_eur == 0.0 and r.blocked_packages == 0                     # DEV is not counted


def test_a_summary_share_opens_cec_and_reads_pre_fid_rows_in_the_owner_tenant(world):
    world.shares[("u_bank", "P1")] = ["SUMMARY"]
    r = _cec(BANK_REQ, rows=[EPC])
    assert r.cec_basis == pcm.CEC_ALL and r.cec.value == pytest.approx(0.6)
    assert world.opened == [OWNER]


def test_a_packages_share_does_not_open_cec(world):
    """A section opens only itself."""
    world.shares[("u_bank", "P1")] = ["PACKAGES"]
    assert _cec(BANK_REQ).cec_basis == pcm.CEC_POST_FID


def test_no_post_fid_package_and_no_share_is_a_refusal_not_an_empty_figure(world):
    with pytest.raises(HTTPException) as exc:
        _cec(BANK_REQ, rows=[DEV])
    assert exc.value.status_code == 403 and exc.value.detail["section"] == "SUMMARY"


def test_a_share_never_saves_a_snapshot_and_history_needs_summary(world):
    world.shares[("u_bank", "P1")] = ["SUMMARY"]
    with pytest.raises(HTTPException) as exc:
        _cec(BANK_REQ, save_snapshot=True)
    assert exc.value.status_code == 403
    world.shares[("u_bank", "P1")] = []
    with pytest.raises(HTTPException) as exc:
        pcm.get_metric_history("P1", limit=5, request=_request(**BANK_REQ), db=FakeConn("north_bank", []))
    assert exc.value.status_code == 403


def test_the_portfolio_summary_labels_post_fid_projects(world):
    out = pcm.portfolio_summary("P1", request=_request(**BANK_REQ), db=FakeConn("north_bank", [DEV, EPC]))
    p = out["projects"][0]
    assert p["cec_basis"] == pcm.CEC_POST_FID and p["cec"] == 1.0 and p["cec_basis_label"]
    assert out["portfolio_basis"].startswith("MIXED")
    own = pcm.portfolio_summary("P1", request=_request(**OWNER_REQ), db=FakeConn(OWNER, [DEV, EPC]))
    assert own["projects"][0]["cec"] == 0.6 and own["portfolio_basis"] == pcm.CEC_ALL


# ── Lineage ──────────────────────────────────────────────────────────────────

def test_lineage_never_names_a_project_after_a_package():
    from app.api.v1 import lineage

    class Conn:
        def execute(self, sql, *a):
            rows = [] if "FROM projects" in sql else [DEV]
            return SimpleNamespace(fetchone=lambda: (SimpleNamespace(keys=lambda: DEV.keys(), **DEV) if rows else None),
                                   fetchall=lambda: rows)

    ident = lineage._fetch_identity(Conn(), "P1")
    assert ident.project_name == "P1" and "secret" not in ident.model_dump_json()


# ── Capital-bridge one-shot view ─────────────────────────────────────────────

def _full(who, monkeypatch, world, spend_owner=({"year": 2026, "amount_eur": 1.0},)):
    import app.api.v1.capital_bridge as cb
    import app.core.db_backend as dbb

    def capital_connection(company_id=None):
        world.opened.append(company_id)
        return FakeConn(company_id, [DEV, EPC], spend=list(spend_owner) if company_id == OWNER else [])

    monkeypatch.setattr(dbb, "capital_connection", capital_connection)
    project = {"project_id": "P1"}

    class Db(FakeConn):
        def execute(self, sql, *a, **k):
            if "FROM projects" in sql:
                return SimpleNamespace(fetchone=lambda: project, fetchall=lambda: [project])
            if "development_packages" in sql:
                return SimpleNamespace(fetchall=lambda: [EPC], fetchone=lambda: EPC)   # RLS: caller sees post-FID
            return SimpleNamespace(fetchall=lambda: [], fetchone=lambda: None)

    return cb.get_full_project("P1", db=Db(who.get("company_id")), request=_request(**who))


def test_the_one_shot_view_withholds_without_a_share(world, monkeypatch):
    out = _full(BANK_REQ, monkeypatch, world)
    assert [p["package_id"] for p in out["packages"]] == ["epc"] and out["spend_wave"] == []
    assert out["pre_fid_withheld"] == {"packages": True, "spend_wave": True}


def test_the_one_shot_view_reads_shared_rows_in_the_owner_tenant(world, monkeypatch):
    world.shares[("u_bank", "P1")] = ["PACKAGES", "FUNDING"]
    out = _full(BANK_REQ, monkeypatch, world)
    assert sorted(p["package_id"] for p in out["packages"]) == ["dev", "epc"]
    assert out["spend_wave"] == [{"year": 2026, "amount_eur": 1.0}]
    assert out["pre_fid_withheld"] == {"packages": False, "spend_wave": False}
    assert OWNER in world.opened


def test_a_register_whose_packages_are_all_withheld_refuses_rather_than_reporting_none(world):
    """A bank without PACKAGES on a project with only pre-FID packages is told they are not
    shared — a 404 "no packages" would read as nothing recorded (handoff v4 task 9)."""
    with pytest.raises(HTTPException) as exc:
        devp.project_summary("P1", db=FakeConn("north_bank", [DEV]), request=_request(**BANK_REQ))
    assert exc.value.status_code == 403 and exc.value.detail["code"] == "PRE_FID_NOT_SHARED"


def test_the_portfolio_names_a_wholly_withheld_project_instead_of_dropping_it(world):
    out = pcm.portfolio_summary("P1", request=_request(**BANK_REQ), db=FakeConn("north_bank", [DEV]))
    assert out["projects"] == [] and out["withheld_projects"][0]["project_id"] == "P1"
    assert out["withheld_projects"][0]["cec"] is None and out["portfolio_basis"].startswith("MIXED")
