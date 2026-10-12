"""
Evidence review — separation of duties (Attack A, 2026-09-30).

docs/adversarial/2026-09-30_attack_A_producer_advance.md: a producer walked its
own claims to VERIFIED — 22 writes, no document — and the project moved from
Speculative to Technically plausible with two capital decisions marked
eligible. The audit trail named a certifier who never acted. Four defects:

  1. POST /bankability/evidence with a reviewer status was classified WRITE, so
     R5's verification rule was never reached;
  2. nothing stopped the submitter, or its company, from verifying its claim;
  3. the audit actor was the request body's submitted_by;
  4. VERIFIED needed no document.

Who reviews which gate is the owner's decision of 2026-10-01 (abac.REVIEWER_GATES),
and a reviewer reads the gate screen and its own gates' evidence, nothing else.

These tests drive the REAL ABAC middleware and the REAL bankability router,
against the isolated SQLite store. Stubbed: the project's access profile (the
canonical projects table is PostgreSQL-only), the account directory (no seed
accounts needed) and the engine call — the write path is under test here; the
harness docs/adversarial/harness/run_attack_a.py covers the engine end to end.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.v1 import routes_bankability_proxy as proxy
from app.core import abac_middleware as mw
from app.core import project_registry as reg
from app.core.abac_middleware import ABACMiddleware
from app.core.auth import create_access_token
from app.core.config import settings

PID = "proj_TEST_review_separation"
OWNER = "TEST Review Producer"
OFFTAKER = "TEST Review Offtaker"
BANK = "TEST Review Bank"
ADVISERS = "TEST Review Advisers"
ENGINEERS = "TEST Review Engineers"
CERTIFIER = "TEST Review Certifier"
INSURER_CO = "TEST Review Insurer"
EVIDENCE = "/api/v1/bankability/evidence"

PROFILE = reg.ProjectAccessProfile(project_id=PID, project_name="TEST review separation",
                                   owner_company_name=OWNER,
                                   associated_company_names=(OFFTAKER, BANK),
                                   jurisdiction="DE")

# user_id -> (company, actor types on PID, assigned audits). Reviewers come from
# companies with no stake in the project; R1 lets them in by assignment.
USERS = {
    "u_prod": (OWNER, ["PRODUCER"], []),
    "u_prod_la": (OWNER, ["PRODUCER", "LENDERS_ADVISER"], [PID]),    # owner holding a reviewer role
    "u_offt": (OFFTAKER, ["OFFTAKER"], []),
    "u_offt_la": (OFFTAKER, ["OFFTAKER", "LENDERS_ADVISER"], [PID]), # submitter's colleague
    "u_bank": (BANK, ["COMMERCIAL_BANKER"], []),                    # G4 owner, no reviewer role
    "u_la": (ADVISERS, ["LENDERS_ADVISER"], [PID]),
    "u_ie": (ENGINEERS, ["INDEPENDENT_ENGINEER"], [PID]),
    "u_cert": (CERTIFIER, ["CERTIFIER"], [PID]),
    "u_ins": (INSURER_CO, ["INSURER"], [PID]),
    "u_la_unassigned": (ADVISERS, ["LENDERS_ADVISER"], []),         # the role, not the assignment
}

# One live evidence item per gate, for the table and the read tests.
ITEM = {
    "G0": "zoning_compatibility_memo", "G1": "water_source_plan", "G2": "mrv_plan_v1",
    "G3": "storage_plan", "G4": "hedgeable_pricing_index", "G5": "interface_matrix",
    "G6": "capex_opinion_reasonableness", "G7": "insurance_market_report",
    "G8": "downside_cases", "G9": "operating_permit_pathway", "G10": "dsra_funded",
    "G11": "mrv_reporting_live",
}


def _token(user_id: str) -> str:
    company, actors, audits = USERS[user_id]
    return create_access_token({
        "user_id": user_id, "email": f"{user_id}@test.invalid",
        "company_id": reg.company_slug(company), "company_name": company,
        "company_type": "PRODUCER", "service_type": None, "business_function": "EXECUTIVE",
        "user_name": f"TEST {user_id}", "clearance_level": "STANDARD", "jurisdiction": "DE",
        "kyc_status": "VERIFIED", "nda_signed_with": [], "assigned_audits": audits,
        "actor_type_per_project": {PID: actors},
    })[0]


TOKENS: dict[str, str] = {}


@pytest.fixture(scope="module", autouse=True)
def _store(isolated_store, tmp_path_factory):
    from app.core.db_backend import evidence_is_postgres

    # Guard, not a formality: every write below must land in the throwaway file.
    assert settings.SQLITE_DB_PATH == isolated_store and not evidence_is_postgres()
    conn = proxy._get_db()
    proxy._ensure_tables(conn)
    conn.close()
    TOKENS.update({u: _token(u) for u in USERS})
    docs = tmp_path_factory.mktemp("evidence_docs")
    original = proxy.EVIDENCE_DOCS_DIR
    proxy.EVIDENCE_DOCS_DIR = str(docs)   # the upload route otherwise writes under backend/data
    yield
    proxy.EVIDENCE_DOCS_DIR = original


async def _engine(path, method="GET", json_data=None):
    """Echo the evidence back as one gate, so the platform's own additions
    (can_review, document_hash, the reviewer's scope) can be read from a real response."""
    detail = [{"key": e["key"], "status": e["status"]} for e in (json_data or {}).get("evidence", [])]
    return {"current_state": "SPECULATIVE", "gate_evaluations": [{"gate_id": "G_TEST", "evidence_detail": detail}]}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    profile = lambda pid: PROFILE if reg.normalize_project_id(pid) == PID else None  # noqa: E731
    monkeypatch.setattr(mw, "get_project_profile", profile)
    monkeypatch.setattr(reg, "get_project_profile", profile)
    monkeypatch.setattr(proxy, "_call_engine", _engine)
    monkeypatch.setattr(proxy, "_project_owner", lambda pid: reg.company_slug(OWNER) if pid == PID else None)
    monkeypatch.setattr(proxy, "_physical_payload", lambda pid: {
        "power_model": "GRID_CONNECTED", "project_phase": "FEED", "financing_model": "PROJECT_FINANCE"})
    monkeypatch.setattr(proxy, "_account_directory", lambda ids: {
        u: {"name": f"TEST {u}", "business_function": "EXECUTIVE", "account_state": "ACTIVE",
            "company_id": reg.company_slug(USERS[u][0])} for u in ids if u in USERS})
    api = FastAPI()
    api.include_router(proxy.router, prefix="/api/v1/bankability")
    api.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
    return TestClient(api)


# ── helpers ──────────────────────────────────────────────────────────────────

def _auth(user):
    return {"Authorization": f"Bearer {TOKENS[user]}"}


def _write(client, user, key, status, **extra):
    body = {"project_id": PID, "evidence_key": key, "new_status": status, **extra}
    return client.post(EVIDENCE, json=body, headers=_auth(user))


def _upload(client, user, key, content: bytes) -> str:
    r = client.post(f"{EVIDENCE}/document", data={"project_id": PID, "evidence_key": key},
                    files={"file": ("TEST.pdf", content, "application/pdf")}, headers=_auth(user))
    assert r.status_code == 200, r.text
    return r.json()["sha256"]


def _row(key) -> dict:
    conn = proxy._get_db()
    row = conn.execute("SELECT * FROM bankability_evidence WHERE project_id = ? AND evidence_key = ?",
                       (PID, key)).fetchone()
    conn.close()
    return dict(row) if row else {}


def _events(key) -> list[dict]:
    conn = proxy._get_db()
    rows = conn.execute("SELECT old_status, new_status, actor, document_sha256 FROM evidence_events "
                        "WHERE project_id = ? AND evidence_key = ? ORDER BY id", (PID, key)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _code(r) -> str:
    detail = r.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else detail


REVIEW = ["UNDER_REVIEW", "VERIFIED", "REJECTED", "EXPIRED"]


# ── 1. The classification: a reviewer status is a VERIFY ────────────────────

async def _classify(method, path, body) -> bool:
    raw = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    return await ABACMiddleware._is_evidence_review(
        Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""}, receive))


@pytest.mark.parametrize("status", REVIEW)
def test_a_reviewer_status_on_the_evidence_write_is_a_verify(status):
    import asyncio
    assert asyncio.run(_classify("POST", EVIDENCE, {"new_status": status})) is True


def test_the_classified_path_is_the_real_evidence_route():
    """The middleware recognises the evidence write, and the gate screen, by
    path. Mounted anywhere else, both would silently stop applying — and the
    tests below would not notice, since they mount the router themselves."""
    from app.main import app

    routes = {(getattr(r, "path", None), m) for r in app.routes for m in (getattr(r, "methods", None) or ())}
    assert (mw.EVIDENCE_WRITE_PATH, "POST") in routes
    assert (mw.EVALUATION_PATH, "GET") in routes


@pytest.mark.parametrize("method,path,body", [
    ("POST", EVIDENCE, {"new_status": "SUBMITTED"}),
    ("POST", EVIDENCE, {"new_status": "IN_PROGRESS"}),
    ("POST", EVIDENCE, {"new_status": ["VERIFIED"]}),              # not a string: the handler refuses it
    ("POST", "/api/v1/bankability/evidence/assign", {"new_status": "VERIFIED"}),
    ("GET", EVIDENCE, {"new_status": "VERIFIED"}),
])
def test_everything_else_keeps_its_classification(method, path, body):
    import asyncio
    assert asyncio.run(_classify(method, path, body)) is False


# ── 2. The owner's table: who reviews which gate ────────────────────────────

DECIDED = {   # owner decision 2026-10-02 — change it here and in abac.REVIEWER_GATES, deliberately
    "CERTIFIER": {"G2", "G11"},
    "INDEPENDENT_ENGINEER": {"G0", "G1", "G3", "G5", "G6", "G11"},
    "LENDERS_ADVISER": {"G0", "G4", "G7", "G8", "G9", "G10"},
    "INSURER": {"G7"},
}


@pytest.mark.parametrize("role", sorted(DECIDED))
def test_the_reviewer_table_is_the_owners_decision(role):
    from app.core.abac import ActorType, ResourceAttributes, UserAttributes, gate_for_evidence, verification_refusal

    reviewer = UserAttributes(user_id="u", company_id="independent_co",
                              actor_type_per_project={PID: [ActorType(role)]}, assigned_audits={PID})
    covered = set()
    for gate, key in ITEM.items():
        assert gate_for_evidence(key).split("_")[0] == gate, key
        resource = ResourceAttributes(project_id=PID, data_owner_company_id="owner_co",
                                      gate_id=gate_for_evidence(key))
        if verification_refusal(reviewer, resource) is None:
            covered.add(gate)
    assert covered == DECIDED[role]


# ── 3. The attack itself: the producer reviews its own claims ───────────────

@pytest.mark.parametrize("status", REVIEW)
def test_the_producer_cannot_review_its_own_claims(client, status):
    key = "land_option_or_lease_executed"
    sha = _upload(client, "u_prod", key, f"TEST land option {status}".encode())
    r = _write(client, "u_prod", key, status, document_sha256=sha,
               submitted_by="TEST Independent Certifier (spoofed name)")
    assert r.status_code == 403, r.text
    assert "R5" in r.json()["rules_evaluated"]
    assert _row(key)["status"] == "SUBMITTED"


def test_the_owners_company_cannot_verify_even_with_a_reviewer_role(client):
    key = "zoning_compatibility_memo"                  # G0: a lenders' adviser's gate
    sha = _upload(client, "u_prod", key, b"TEST zoning memo")
    r = _write(client, "u_prod_la", key, "VERIFIED", document_sha256=sha)
    assert r.status_code == 403
    assert r.json()["reason"] == "The company that owns the project cannot review its own evidence"


# ── 4. Separation from the submitter ─────────────────────────────────────────

def test_submitter_cannot_verify_own_evidence(client):
    """A reviewer who supplied the document is its submitter, and cannot verify it."""
    key = "stakeholder_map_v1"                          # G0: the engineer's gate
    sha = _upload(client, "u_ie", key, b"TEST stakeholder map uploaded by the engineer")
    r = _write(client, "u_ie", key, "VERIFIED", document_sha256=sha)
    assert r.status_code == 403 and _code(r) == "SUBMITTER_CANNOT_REVIEW"
    assert _row(key)["verified_by"] is None


def test_same_company_cannot_verify_its_own_claim(client):
    key = "binding_offtake_contract_executed"          # G4: the offtaker submits, an adviser reviews
    sha = _upload(client, "u_offt", key, b"TEST offtake contract")
    r = _write(client, "u_offt_la", key, "VERIFIED", document_sha256=sha)
    assert r.status_code == 403 and _code(r) == "SUBMITTING_COMPANY_CANNOT_REVIEW"
    assert _row(key)["status"] == "SUBMITTED"


def test_nothing_submitted_cannot_be_reviewed(client):
    r = _write(client, "u_ie", "site_technical_suitability", "UNDER_REVIEW")
    assert r.status_code == 409 and _code(r) == "NOTHING_SUBMITTED"


def test_a_submission_naming_no_account_cannot_be_reviewed(client):
    """Legacy rows carry display names; independence from them cannot be checked."""
    key = "grid_interconnection_study"
    conn = proxy._get_db()
    conn.execute("INSERT INTO bankability_evidence (project_id, evidence_key, status, submitted_by) "
                 "VALUES (?, ?, 'SUBMITTED', 'Anna Keller')", (PID, key))
    conn.commit()
    conn.close()
    r = _write(client, "u_ie", key, "UNDER_REVIEW")
    assert r.status_code == 409 and _code(r) == "SUBMITTER_NOT_IDENTIFIED"


# ── 5. The reviewer role, for the gate ───────────────────────────────────────

@pytest.mark.parametrize("status", REVIEW)
def test_verification_requires_reviewer_role_for_the_gate(client, status):
    """The bank OWNS G4 for writing and is independent of the offtaker who
    submitted — and still may not review: owning a gate is not reviewing it.
    Before the fix this was a WRITE on a gate the bank owns, and went through.
    A certifier is a reviewer, but not of G4."""
    key = "offtake_credit_assessment"
    sha = _upload(client, "u_offt", key, f"TEST credit assessment {status}".encode())
    r = _write(client, "u_bank", key, status, document_sha256=sha)
    assert r.status_code == 403, r.text
    assert r.json()["reason"] == "Only an assigned reviewer can verify evidence"
    r = _write(client, "u_cert", key, status, document_sha256=sha)
    assert r.status_code == 403 and r.json()["reason"] == "Your reviewer role does not cover G4"
    assert _row(key)["status"] == "SUBMITTED"


def test_a_reviewer_must_be_assigned_to_the_project(client):
    """The role alone is not an assignment: an unassigned adviser is a stranger."""
    key = "termination_payment_formula"
    sha = _upload(client, "u_offt", key, b"TEST termination formula, unassigned")
    r = _write(client, "u_la_unassigned", key, "VERIFIED", document_sha256=sha)
    assert r.status_code == 403 and r.json()["rules_evaluated"] == ["R1"]


@pytest.mark.parametrize("reviewer,submitter,key", [
    ("u_la", "u_offt", "credit_support_package"),      # G4
    ("u_ie", "u_prod", "interface_matrix"),            # G5
    ("u_cert", "u_prod", "mrv_plan_v1"),               # G2
    ("u_ins", "u_prod", "insurance_market_report"),    # G7
])
def test_each_reviewer_verifies_its_own_gates(client, reviewer, submitter, key):
    sha = _upload(client, submitter, key, f"TEST {key}".encode())
    r = _write(client, reviewer, key, "VERIFIED", document_sha256=sha)
    assert r.status_code == 200, r.text
    row = _row(key)
    assert (row["status"], row["submitted_by"], row["verified_by"], row["document_hash"]) == \
        ("VERIFIED", submitter, reviewer, sha)
    assert row["verified_at"]


def test_a_review_that_names_no_project_is_refused(client):
    """With no project_id the middleware resolves no resource and used to wave
    the request through to a handler that defaults the project to 'default'."""
    r = client.post(EVIDENCE, json={"evidence_key": "take_or_pay_floor", "new_status": "VERIFIED"},
                    headers=_auth("u_la"))
    assert r.status_code == 403
    assert proxy._load_evidence("default") == []


# ── 6. The audit actor is the token's user ──────────────────────────────────

def test_evidence_event_actor_is_the_authenticated_user(client):
    key = "legal_opinion_on_appeal_risk"               # G9: the producer submits, an adviser reviews
    spoof = "TEST Independent Certifier (spoofed name)"
    assert _write(client, "u_prod", key, "SUBMITTED", submitted_by=spoof).status_code == 200
    sha = _upload(client, "u_prod", key, b"TEST appeal-risk opinion")
    assert _write(client, "u_la", key, "VERIFIED", document_sha256=sha,
                  submitted_by="TEST someone else").status_code == 200
    events = _events(key)
    assert [e["actor"] for e in events] == ["u_prod", "u_prod", "u_la"]
    row = _row(key)
    assert (row["submitted_by"], row["verified_by"]) == ("u_prod", "u_la")
    assert spoof not in json.dumps(events) + json.dumps(row)


def test_the_handler_itself_takes_the_actor_from_a_token():
    """Not only the middleware: without a bearer the handler has no one to record
    as the actor, so it refuses — whatever submitted_by says."""
    import asyncio
    from fastapi import HTTPException

    req = proxy.EvidenceUpdateRequest(project_id=PID, evidence_key="assignment_rights",
                                      new_status="SUBMITTED", submitted_by="u_offt")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(proxy.update_evidence(req, authorization=None))
    assert exc.value.status_code == 401


# ── 7. VERIFIED attests to a document on file ───────────────────────────────

def test_verified_requires_a_document_hash(client):
    key = "step_in_rights"
    assert _write(client, "u_offt", key, "SUBMITTED").status_code == 200

    r = _write(client, "u_la", key, "VERIFIED")
    assert r.status_code == 422 and _code(r) == "VERIFIED_REQUIRES_A_DOCUMENT"

    r = _write(client, "u_la", key, "VERIFIED", document_sha256=hashlib.sha256(b"never uploaded").hexdigest())
    assert r.status_code == 422 and _code(r) == "DOCUMENT_NOT_ON_FILE"

    elsewhere = _upload(client, "u_offt", "price_review_mechanism_memo", b"TEST a document for another item")
    r = _write(client, "u_la", key, "VERIFIED", document_sha256=elsewhere)
    assert r.status_code == 422 and _code(r) == "DOCUMENT_NOT_ON_FILE"
    assert _row(key)["status"] == "SUBMITTED"

    sha = _upload(client, "u_offt", key, b"TEST step-in rights")
    assert _write(client, "u_la", key, "VERIFIED", document_sha256=sha.upper()).status_code == 200
    assert _events(key)[-1] == {"old_status": "SUBMITTED", "new_status": "VERIFIED",
                                "actor": "u_la", "document_sha256": sha}


def test_rejecting_needs_no_document(client):
    """A missing document is a reason to reject, so rejection cannot require one."""
    key = "offtake_seller_obligations"
    assert _write(client, "u_offt", key, "SUBMITTED").status_code == 200
    assert _write(client, "u_la", key, "REJECTED").status_code == 200
    assert _row(key)["status"] == "REJECTED"


# ── 8. Maturity is declared by the submitter, never raised at review ────────

def test_verification_cannot_raise_maturity(client):
    key = "take_or_pay_floor"
    sha = _upload(client, "u_offt", key, b"TEST take-or-pay term sheet")
    assert _write(client, "u_offt", key, "SUBMITTED", maturity="INDICATIVE").status_code == 200
    r = _write(client, "u_la", key, "VERIFIED", maturity="EXECUTED", document_sha256=sha)
    assert r.status_code == 422 and _code(r) == "VERIFICATION_CANNOT_RAISE_MATURITY"
    assert _write(client, "u_la", key, "VERIFIED", maturity="INDICATIVE",
                  document_sha256=sha).status_code == 200


# ── 9. The screen offers review exactly where the write accepts it ──────────

def test_can_review_is_offered_only_where_the_write_accepts_it(client):
    """_attach_assignments is what /evaluate and the evidence write return to
    the screen; called directly so every user, stakeholder or not, is asked."""
    from app.core.auth import get_user_payload_from_token

    key = "assignment_rights"                          # G4
    sha = _upload(client, "u_offt", key, b"TEST assignment rights")
    evidence = proxy._load_evidence(PID)

    def offered(user):
        snapshot = {"gate_evaluations": [{"evidence_detail": [{"key": key, "status": "SUBMITTED"}]}]}
        actor = get_user_payload_from_token(TOKENS[user])
        items = proxy._attach_assignments(snapshot, evidence, actor, PID)["gate_evaluations"][0]["evidence_detail"]
        if not items:
            return False   # withheld: a reviewer whose role does not cover G4 never sees it
        (item,) = items
        assert item["document_hash"] == sha
        return item["can_review"]

    assert {u for u in USERS if offered(u)} == {"u_la"}
    # And the write agrees with the one it offered.
    assert _write(client, "u_bank", key, "VERIFIED", document_sha256=sha).status_code == 403
    assert _write(client, "u_la", key, "VERIFIED", document_sha256=sha).status_code == 200


# ── 10. What a reviewer may read: the screen, and its own gates ─────────────

@pytest.fixture
def one_item_per_gate(client):
    for gate, key in ITEM.items():
        _upload(client, "u_prod" if gate != "G4" else "u_offt", key, f"TEST read {gate}".encode())


def _screen(client, user) -> set:
    r = client.get("/api/v1/bankability/evaluate", params={"project_id": PID}, headers=_auth(user))
    assert r.status_code == 200, r.text
    return {i["key"] for g in r.json()["gate_evaluations"] for i in g["evidence_detail"]}


def test_a_reviewer_reads_the_gate_screen_with_only_its_own_gates(client, one_item_per_gate):
    seen = _screen(client, "u_ins")
    assert {ITEM[g] for g in ("G7",)} <= seen
    assert not seen & {ITEM[g] for g in ITEM if g not in ("G7",)}
    # A stakeholder's view is untouched.
    assert set(ITEM.values()) <= _screen(client, "u_prod")


def test_a_reviewer_reads_documents_only_on_its_gates(client, one_item_per_gate):
    def documents(user, gate):
        return client.get(f"{EVIDENCE}/documents", params={"project_id": PID, "evidence_key": ITEM[gate]},
                          headers=_auth(user)).status_code

    assert documents("u_ins", "G7") == 200
    assert documents("u_ins", "G4") == 403
    assert documents("u_la", "G4") == 200
    assert documents("u_cert", "G4") == 403


@pytest.mark.parametrize("path,params", [
    (EVIDENCE, {"project_id": PID}),                                  # every item's row
    (f"{EVIDENCE}/events", {"project_id": PID}),                      # the whole audit trail
    (f"{EVIDENCE}/documents", {"project_id": PID}),                   # every document
    ("/api/v1/bankability/evaluate/persona", {"project_id": PID, "persona": "EXECUTIVE"}),
])
def test_a_reviewer_reads_nothing_else(client, path, params):
    assert client.get(path, params=params, headers=_auth("u_ins")).status_code == 403
    assert client.get(path, params=params, headers=_auth("u_prod")).status_code == 200
