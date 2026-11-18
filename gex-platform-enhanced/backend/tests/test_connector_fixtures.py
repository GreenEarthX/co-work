"""Offline connector fixtures: synthetic, internally consistent, and shaped on the published schemas.

No extraction or matching code exists yet (docs/GREENMESH_CONNECTOR_FIELD_MAPPING.md v0.2 awaits
JML's approval). These tests keep the fixtures honest until it does:
  * every case names files that exist, and every fixture file is used;
  * every expected outcome is in the manifest's vocabulary and cites the mapping's section;
  * everything is synthetic (TEST markers, the 9999999 certificate prefix, TEST- identifiers);
  * UDB fixtures validate against the vendored v3.5 XSDs, whose sha256 is pinned;
  * AIB fixtures carry SD03 9.1's v81 mandatory elements for their energy carrier (no AIB XSD obtained);
  * the scenarios agree with the files (the overlap really overlaps, the lineage really over-draws);
  * nothing under app/ reads these fixtures.
No database, no network.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

ROOT = pathlib.Path(__file__).parent / "fixtures" / "connectors"
APP = pathlib.Path(__file__).parent.parent / "app"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
CASES = MANIFEST["cases"]
VOCAB = MANIFEST["vocabulary"]
AIB_NS = {"r": "http://system.aib-net.org"}
TEST_MARK = "GEX TEST FIXTURE"
TEST_PREFIX = "9999999"

# SD03 9.1, B4.3 (v81): elements mandatory (M) for every carrier, plus those mandatory for one.
AIB_V81_MANDATORY = [
    "r:StartCertificateNumber", "r:EndCertificateNumber", "r:IssuingBody", "r:CountryOfIssue",
    "r:DateOfIssue", "r:ProductionPeriod", "r:EnergyCarrier", "r:Conversion", "r:Storage", "r:Product",
    "r:Product/r:Purpose", "r:Product/r:CompetentAuthority", "r:Product/r:ProductType",
    "r:ProductionDeviceID", "r:DateOperational", "r:ProductionTechnology", "r:EnergySource",
    "r:SupportFlag", "r:DisseminationLevel",
]
AIB_V81_MANDATORY_BY_CARRIER = {
    "Electricity": ["r:Capacity/r:ElectricalCapacity"],
    "Hydrogen": ["r:Capacity/r:GasProductionCapacity", "r:Gas", "r:CalorificValue"],
}


def _fixture_files() -> set[str]:
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.xml")}


def _aib(rel: str) -> ET.Element:
    return ET.parse(ROOT / rel).getroot()


def _bundles(rel: str):
    return _aib(rel).findall("r:Body/r:Certificates", AIB_NS)


def _interval(bundle) -> tuple[int, int]:
    s = bundle.find("r:StartCertificateNumber", AIB_NS).text.strip()
    e = bundle.find("r:EndCertificateNumber", AIB_NS).text.strip()
    return int(s), int(e)


def _udb_transactions(rel: str):
    return ET.parse(ROOT / rel).getroot().findall("EO_TRANS_HEADER/EO_TRANSACTION")


# ── manifest coherence ──────────────────────────────────────────────────────

def test_every_case_file_exists_and_every_fixture_is_used():
    named = {f for c in CASES for f in c["files"]}
    assert named - _fixture_files() == set(), "a case names a missing file"
    unused = {f for f in _fixture_files() if not f.startswith("udb/xsd_")} - named
    assert unused == set(), f"fixture files no case uses: {sorted(unused)}"


def test_case_ids_are_unique_and_each_cites_the_mapping():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        assert c["section"].startswith("§"), c["id"]
    assert MANIFEST["mapping_doc_version"] == "0.3"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_expected_outcomes_use_the_vocabulary(case):
    flat = {k: v for group in VOCAB.values() for k, v in group.items()}
    for key, outcome in case["expected"].items():
        assert outcome in flat, f"{case['id']}: {key}={outcome} is not in the vocabulary"
        if key in VOCAB:
            assert outcome in VOCAB[key], f"{case['id']}: {outcome} is not a {key} outcome"
    for unit, u in case.get("units", {}).items():
        assert u["outcome"] in VOCAB["unit_outcome"], unit


def test_every_offline_case_stays_declared():
    """Offline evidence is never VERIFIED: only registry confirmation could make it so."""
    for c in CASES:
        assert c["expected"]["label"] == "DECLARED", c["id"]


def test_test_rules_are_marked_synthetic_and_proposed_rows_are_not_in_force():
    for r in MANIFEST["test_rules"]:
        assert r["rule_id"].startswith("TEST-RULE-") and r["intended_use"].startswith("TEST_USE_")
        assert "Synthetic" in r["note"]
    proposed = {r["intended_use"] for r in MANIFEST["test_rules"] if r["status"] != "approved"}
    for c in CASES:
        if c.get("gex", {}).get("intended_use") in proposed:
            assert c["expected"]["eligibility"] == "NOT_ESTABLISHED", c["id"]
            assert c["expected"]["confirmation"] == "NOT_CONFIRMABLE", c["id"]


def test_no_rule_means_not_established_never_permission():
    known = {r["intended_use"] for r in MANIFEST["test_rules"]}
    for c in CASES:
        use = c.get("gex", {}).get("intended_use")
        if use and use not in known:
            assert c["expected"]["eligibility"] == "NOT_ESTABLISHED", c["id"]
            assert c["expected"]["confirmation"] != "CONFIRMABLE", c["id"]


# ── synthetic only ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", sorted(f for f in _fixture_files() if not f.startswith("udb/xsd_")))
def test_every_fixture_is_marked_test(rel):
    assert TEST_MARK in (ROOT / rel).read_text(), rel


def test_aib_identifiers_are_synthetic():
    for rel in (f for f in _fixture_files() if f.startswith("aib/")):
        root = _aib(rel)
        for reg in root.findall("r:Header/r:FromRegistry", AIB_NS) + root.findall("r:Header/r:ToRegistry", AIB_NS):
            assert reg.text.startswith(TEST_PREFIX), rel
        for b in _bundles(rel):
            for tag in ("r:StartCertificateNumber", "r:EndCertificateNumber"):
                n = b.find(tag, AIB_NS).text.strip()
                assert len(n) == 30 and n.isdigit() and n.startswith(TEST_PREFIX), (rel, n)
            assert b.find("r:IssuingBody", AIB_NS).text == "99", rel
            assert b.find("r:CountryOfIssue", AIB_NS).text == "ZZ", rel


def test_udb_identifiers_are_synthetic():
    for rel in (f for f in _fixture_files() if f.startswith("udb/") and not f.startswith("udb/xsd_")):
        for t in _udb_transactions(rel):
            for tag in ("POS_ID", "TRANSACTION_ID", "EO_TRANS_DETAIL_MATERIALS/ORIGINAL_POS",
                        "EO_TRANS_DETAIL_MATERIALS/PREVIOUS_POS"):
                assert t.find(tag).text.startswith("TEST-"), (rel, tag)
            for tag in ("SELLER_ECONOMIC_OPERATOR_NUMBER", "BUYER_ECONOMIC_OPERATOR_NUMBER"):
                assert t.find(tag).text.startswith("EOTEST"), (rel, tag)


# ── shapes against the published specifications ─────────────────────────────

def test_vendored_udb_xsds_are_the_retrieved_files():
    for rel, digest in MANIFEST["sources"]["udb_xsd"]["files_sha256"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest, rel


@pytest.mark.parametrize("rel", sorted(f for f in _fixture_files() if f.startswith("udb/") and not f.startswith("udb/xsd_")))
def test_udb_fixture_validates_against_the_v35_xsd(rel):
    # lxml is declared in requirements.txt (2026-11-16): without it this FAILS, it does not skip.
    from lxml import etree
    schema = etree.XMLSchema(etree.parse(str(ROOT / MANIFEST["sources"]["udb_xsd"]["root_schema"])))
    ok = schema.validate(etree.parse(str(ROOT / rel)))
    assert ok, [e.message for e in schema.error_log][:5]


@pytest.mark.parametrize("rel", sorted(f for f in _fixture_files() if f.startswith("aib/")))
def test_aib_fixture_carries_the_v81_mandatory_elements(rel):
    root = _aib(rel)
    assert root.tag == "{http://system.aib-net.org}Env"
    header = root.find("r:Header", AIB_NS)
    assert header.get("MessageTransmissionTime")
    for tag in ("r:MessageID", "r:FromRegistry", "r:ToRegistry", "r:Context"):
        assert header.find(tag, AIB_NS) is not None, (rel, tag)
    body = root.find("r:Body", AIB_NS)
    for tag in ("r:SendingAccountID", "r:ReceivingAccountID", "r:NumberOfCertificates"):
        assert body.find(tag, AIB_NS) is not None, (rel, tag)
    total = 0
    for b in _bundles(rel):
        carrier = b.find("r:EnergyCarrier", AIB_NS).text
        assert carrier in ("Electricity", "EnergyGas", "Hydrogen")
        for tag in AIB_V81_MANDATORY + AIB_V81_MANDATORY_BY_CARRIER.get(carrier, []):
            assert b.find(tag, AIB_NS) is not None, (rel, tag)
        loc = b.find("r:ProductionDeviceLocation", AIB_NS)
        assert loc is not None and (loc.find("r:Coordinates", AIB_NS) is not None
                                    or loc.find("r:Address", AIB_NS) is not None), rel
        pp = b.find("r:ProductionPeriod", AIB_NS)
        start, end = datetime.fromisoformat(pp.get("start")), datetime.fromisoformat(pp.get("end"))
        assert pp.get("length") in ("month", "day", "hour", "30min", "15min")
        if pp.get("length") == "month":   # SD03 B4.6.6: start and end in the same calendar month
            assert (start.year, start.month) == (end.year, end.month), rel
        s, e = _interval(b)
        assert s <= e, rel
        total += e - s + 1
    # Inference, flagged in the mapping (§2): one certificate per number in a range.
    assert int(body.find("r:NumberOfCertificates", AIB_NS).text) == total, rel


# ── the scenarios agree with the files ──────────────────────────────────────

@pytest.mark.parametrize("case", [c for c in CASES if "overlap" in c], ids=lambda c: c["id"])
def test_overlap_cases_really_overlap(case):
    o = case["overlap"]
    (a0, a1), = [_interval(b) for b in _bundles(o["first"])]
    (b0, b1), = [_interval(b) for b in _bundles(o["second"])]
    assert str(a0).startswith(o["registry"]) and str(b0).startswith(o["registry"])
    assert max(0, min(a1, b1) - max(a0, b0) + 1) == o["certificates"]


def test_cross_tenant_overlap_documents_name_different_holders():
    c = next(c for c in CASES if c["id"] == "aib_allocation_overlap_cross_tenant")
    parties = MANIFEST["test_parties"]
    for step in c["gex"]["steps"]:
        holder = _aib(step["file"]).find("r:Body/r:ReceivingAccountID", AIB_NS).text
        assert holder == parties[step["company"]]["aib_account"], step


def _udb_pos_quantities(rel: str) -> dict[str, tuple[str, float, str]]:
    out = {}
    for t in _udb_transactions(rel):
        m = t.find("EO_TRANS_DETAIL_MATERIALS")
        out[t.find("POS_ID").text] = (m.find("ORIGINAL_POS").text, float(m.find("QUANTITY").text),
                                      t.find("BUYER_ECONOMIC_OPERATOR_NUMBER").text)
    return out


def test_lineage_cases_match_the_file():
    parties = MANIFEST["test_parties"]
    for cid, over in (("udb_parent_child_reference", False), ("udb_lineage_overdraw", True)):
        c = next(c for c in CASES if c["id"] == cid)
        pos = _udb_pos_quantities(c["files"][0])
        root = c["lineage"]["root"]
        for child in c["lineage"]["children"]:
            assert pos[child][0] == root, (cid, child)
        for step in c["gex"]["steps"]:
            assert pos[step["pos"]][2] == parties[step["company"]]["udb_eo"], (cid, step)
            assert pos[step["pos"]][1] == step["quantity_t"], (cid, step)
        drawn = sum(pos[ch][1] for ch in c["lineage"]["children"])
        assert (drawn > pos[root][1]) is over, cid


def test_units_case_covers_the_whole_measuring_unit_enum():
    c = next(c for c in CASES if c["id"] == "udb_units")
    in_file = {t.find("EO_TRANS_DETAIL_MATERIALS/MEASURE_UNIT").text for t in _udb_transactions(c["files"][0])}
    xsd = (ROOT / "udb/xsd_v3.5/udbModel/udbModel_v1.0.xsd").read_text()
    block = xsd.split('name="MeasuringUnitEnum"', 1)[1].split("</xs:simpleType>", 1)[0]
    enum = {v.split('"', 1)[0] for v in block.split('value="')[1:]}
    assert in_file == enum == set(c["units"]), (in_file ^ enum, enum ^ set(c["units"]))


def test_quantity_match_case_agrees_with_the_file():
    c = next(c for c in CASES if c["id"] == "udb_quantity_match")
    (t,) = _udb_transactions(c["files"][0])
    qty = float(t.find("EO_TRANS_DETAIL_MATERIALS/QUANTITY").text)
    factor = next(u["factor"] for k, u in next(x for x in CASES if x["id"] == "udb_units")["units"].items()
                  if k == t.find("EO_TRANS_DETAIL_MATERIALS/MEASURE_UNIT").text)
    assert qty * factor == c["gex"]["quantity"]
    assert t.find("BUYER_ECONOMIC_OPERATOR_NUMBER").text == MANIFEST["test_parties"][c["gex"]["company"]]["udb_eo"]


# ── fixtures stay out of the application ────────────────────────────────────

def test_nothing_under_app_reads_the_connector_fixtures():
    hits = [p.relative_to(APP).as_posix() for p in APP.rglob("*.py")
            if "fixtures/connectors" in p.read_text(errors="ignore")]
    assert hits == []


# ── acceptance cases (mapping v0.3 §10): the manifest agrees with itself, its files and the doc ──
# These check the SPECIFICATION's internal consistency, not an implementation (none exists yet).

DOC = (pathlib.Path(__file__).parent.parent.parent / MANIFEST["mapping_doc"]).read_text()
RULES = {r["intended_use"]: r for r in MANIFEST["test_rules"]}
BY_ID = {c["id"]: c for c in CASES}


def _d(s: str):
    return datetime.fromisoformat(s).date()


def _certificates_in(rel: str) -> int:
    return sum(e - s + 1 for s, e in map(_interval, _bundles(rel)))


def test_every_acceptance_case_in_the_doc_has_its_fixture_and_back():
    section = DOC.split("## 10. Acceptance cases", 1)[1].split("## Change log", 1)[0]
    rows = [r for r in section.splitlines() if r.startswith("| AC-")]
    assert len(rows) == 20
    named = {cell.strip().strip("`") for r in rows for cell in [r.rstrip(" |").rsplit("|", 1)[1]]
             if cell.strip().startswith("`")}
    assert named <= set(BY_ID), named - set(BY_ID)
    ac_cases = {c for c in BY_ID if c.startswith("ac")}
    assert ac_cases <= named, ac_cases - named
    assert len(named) == 17


@pytest.mark.parametrize("cid", ["ac01_partial_allocation_divisible", "ac04_conflict_same_tenant"])
def test_sequential_requests_respect_the_eligible_quantity(cid):
    c = BY_ID[cid]
    total, taken = _certificates_in(c["files"][0]), 0
    assert RULES[c["gex"]["intended_use"]]["divisibility"] == "whole_certificate"
    for step in c["gex"]["steps"]:
        fits = taken + step["quantity"] <= total
        assert (step["expected_confirmation"] == "CONFIRMABLE") is fits, step
        if fits:
            taken += step["quantity"]
        if "expected_request" in step:   # flagged when provisional requests together exceed it
            before = sum(s["quantity"] for s in c["gex"]["steps"][:c["gex"]["steps"].index(step)])
            flagged = before + step["quantity"] > total
            assert (step["expected_request"] == "PROVISIONAL_OVERLAP_FLAGGED") is flagged, step


def test_without_divisibility_only_the_whole_quantity_is_confirmable():
    c = BY_ID["ac02_partial_without_divisibility"]
    assert RULES[c["gex"]["intended_use"]]["divisibility"] is None
    total = _certificates_in(c["files"][0])
    for alt in c["gex"]["alternatives"]:
        assert (alt["expected_confirmation"] == "CONFIRMABLE") is (alt["quantity"] == total), alt


def test_below_the_unit_and_concurrent_cases_are_what_they_claim():
    c3 = BY_ID["ac03_below_unit"]
    assert c3["gex"]["quantity"] != int(c3["gex"]["quantity"])           # a fraction of a certificate
    c6 = BY_ID["ac06_concurrent_confirmation"]
    both = c6["gex"]["simultaneous"]
    assert sum(both) > _certificates_in(c6["files"][0]) and all(q <= _certificates_in(c6["files"][0]) for q in both)


def _valid_at(cert: dict, day, event: dict | None = None) -> bool:
    ok = _d(cert["valid_from"]) <= day <= _d(cert["valid_until"])
    if event and event["kind"] in ("withdrawal", "suspension") and day >= _d(event["effective"]):
        ok = False
    return ok


@pytest.mark.parametrize("cid", ["ac07_historical_expiry", "ac09_retrospective_withdrawal",
                                 "ac10_withdrawal_prospective", "ac11_suspension_prospective"])
def test_validity_cases_follow_event_date_rules(cid):
    c, g = BY_ID[cid], BY_ID[cid]["gex"]
    rule = RULES[g["intended_use"]]
    assert rule["validity_test"] == {"kind": "at_event", "event": "dispatch"}
    cert, event = g["certificate"], g.get("event")
    dispatch = _d(g["decision"]["event_dispatch"])
    exp = c["expected"]
    assert exp.get("historical_decision", "PRESERVED") == "PRESERVED"          # never rewritten
    if cid == "ac07_historical_expiry":                                       # expiry is not retroactive
        assert _d(g["reassessed_on"]) > _d(cert["valid_until"]) and _valid_at(cert, dispatch)
        assert exp["validity"] == "VALID_AT_EVENT"
    if event:
        reaches_back = _d(event["effective"]) <= dispatch
        assert (exp["reassessment"] == "REQUIRED") is reaches_back, cid
        assert (exp["downstream"] == "REASSESSMENT_PENDING") is reaches_back, cid
        if reaches_back:
            assert exp["quantity_state"] == "RESTRICTED"
    if "new_request" in g:
        valid = _valid_at(cert, _d(g["new_request"]["event_dispatch"]), event)
        assert (exp["new_request_validity"] == "VALID_AT_EVENT") is valid, cid
        assert exp["new_request_confirmation"] == ("CONFIRMABLE" if valid else "NOT_CONFIRMABLE"), cid


def test_historical_expiry_case_uses_the_files_dispatch_and_certificate():
    c = BY_ID["ac07_historical_expiry"]
    (t,) = _udb_transactions(c["files"][0])
    assert t.find("DELIVERY_DATE").text[:10] == c["gex"]["decision"]["event_dispatch"]
    assert t.find("SELLER_CERTIFICATE_NUMBER").text == c["gex"]["certificate"]["reference"]


def test_continuing_condition_is_not_met_by_one_favourable_date():
    c = BY_ID["ac08_continuing_condition"]
    assert RULES[c["gex"]["intended_use"]]["validity_test"]["kind"] == "over_period"
    cert, (p0, p1) = c["gex"]["certificate"], map(_d, c["gex"]["production_period"])
    assert _valid_at(cert, p0)                                   # valid at the start ...
    assert _d(cert["valid_until"]) < p1                          # ... but not over the period
    assert c["expected"]["validity"] == "NOT_VALID_OVER_PERIOD"


@pytest.mark.parametrize("cid", ["ac12_correction_no_dependents", "ac13_correction_with_dependents",
                                 "ac14_correction_draft_export", "ac15_correction_submitted_export"])
def test_correction_cases_follow_the_dependency_rules(cid):
    c, g = BY_ID[cid], BY_ID[cid]["gex"]
    exp, deps, rf = c["expected"], g["dependents"], g.get("registry_file")
    if "reversal" in g and g["reversal"]["material"]:
        assert g["reversal"]["proposed_by"] != g["reversal"]["approved_by"]
    if not deps:
        assert exp["correction"] == "REVERSED" and exp["quantity_state"] == "RESTORED"
    elif rf is not None:
        assert rf["downloaded"] is True                                     # a download alone ...
        submitted = rf["submission_evidence"] is not None                   # ... is not submission
        assert exp["correction"] == ("PENDING_EXTERNALLY" if submitted else "SUPERSEDED_DRAFT")
        assert exp["external_ack"] == ("REQUIRED" if submitted else "NOT_REQUIRED")
        if submitted:
            assert exp["quantity_state"] == "RESTRICTED"
    else:
        assert exp["correction"] == "REFUSED_DEPENDENTS_ACTIVE" and exp["quantity_state"] == "RESTRICTED"


def test_free_text_assertion_belongs_to_another_tenant_and_grants_nothing():
    c = BY_ID["ac16_free_text_assertion"]
    g = c["gex"]
    assert g["registered_elsewhere"]["company"] != g["company"]
    assert g["registered_elsewhere"]["statement_id"] == g["evidence_ref_typed"]
    assert c["expected"]["reference"] == "UNRESOLVED_ASSERTION"
    assert c["expected"]["disclosure"] == "INDISTINGUISHABLE_FROM_UNKNOWN"
    assert "allocation_request" not in c["expected"] and "confirmation" not in c["expected"]


# ── cross-company disclosure (mapping v0.3 §5.11, JML 16 Nov) ───────────────

NEUTRAL = MANIFEST["neutral_refusal_text"]


def test_the_neutral_refusal_text_is_the_decided_wording_in_doc_and_manifest():
    assert NEUTRAL == "This allocation cannot be confirmed. Request an evidence review."
    s511 = DOC.split("### 5.11", 1)[1].split("\n## ", 1)[0]
    assert f'"{NEUTRAL}"' in s511
    ac20 = next(l for l in DOC.splitlines() if l.startswith("| AC-20 "))
    assert NEUTRAL in ac20


def test_every_cross_company_refusal_is_neutral_and_shows_only_review_pending():
    for c in CASES:
        steps = c.get("gex", {}).get("steps", [])
        companies = {s["company"] for s in steps if "company" in s} | {c.get("gex", {}).get("company")} - {None}
        if c["expected"].get("confirmation") == "REFUSED_NEUTRAL":
            assert len(companies) > 1, c["id"]                         # only an outside cause is neutral
            assert c["expected"]["requester_sees"] == "REVIEW_PENDING", c["id"]
        if c["expected"].get("confirmation") in ("REFUSED_WITH_DETAIL", "REFUSED_OWN_DATA_DETAIL"):
            assert c["expected"].get("requester_sees", "DETAIL") == "DETAIL", c["id"]


def test_shared_reference_case_gives_detail_only_from_the_requesters_own_upload():
    c = BY_ID["ac19_shared_reference_no_priority"]
    parties, req = MANIFEST["test_parties"], c["gex"]["allocation_request"]
    holder = _aib(c["files"][0]).find("r:Body/r:ReceivingAccountID", AIB_NS).text
    assert holder == parties["TEST_CO_A"]["aib_account"] != parties[req["company"]]["aib_account"]
    assert [u["company"] for u in sorted(c["gex"]["uploads"], key=lambda u: u["order"])] == ["TEST_CO_A", "TEST_CO_B"]
    assert c["expected"]["priority"] == "NONE" and c["expected"]["evidence_records"] == "ONE_PER_COMPANY"
    assert c["expected"]["confirmation"] == "REFUSED_OWN_DATA_DETAIL"   # the holder is readable in B's own upload
