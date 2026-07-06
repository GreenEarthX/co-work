"""External Adjacency Corpus — skeleton verification (review item #5).

Synthetic TEST_FIXTURE rows only: this suite proves the MACHINE (quarantine,
census-sign, versioned snapshots, revealed transitions, provenance, the
epistemic leak boundary) without fabricating a seed. Real ingestion is a
drop-in after the licensing sign-off (IEA CC BY 4.0 verified 2026-07-02).
"""
import os, sys, tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # repo root

import app.core.external_corpus as xc  # noqa: E402

V1 = [
    {"source_project_id": "T1", "name": "TEST-PROJECT-A", "fuel": "MEOH-E",
     "technology": "PEM+SYN", "status": "FID taken", "jurisdiction": "FR",
     "capacity_value": 50, "capacity_unit": "kt/y", "announced_year": 2024},
    {"source_project_id": "T2", "name": "TEST-PROJECT-B", "fuel": "MEOH-E",
     "technology": "PEM+SYN", "status": "Concept", "jurisdiction": "DE"},
    {"source_project_id": "T3", "name": "TEST-PROJECT-C", "fuel": "UNKNOWN-FUEL-LABEL",
     "technology": "PEM+SYN", "status": "Concept", "jurisdiction": "ES"},
]
V2 = [dict(V1[0], status="Operational"),      # T1: FID -> operational (revealed outcome)
      dict(V1[1], status="Cancelled"),        # T2: concept -> cancelled
      dict(V1[2])]

LIC = dict(source="TEST_FIXTURE", license="none — synthetic unit fixture",
           attribution="synthetic test rows, not real projects",
           retrieved_at="2026-07-02", imported_by="pytest")


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    tmp = tempfile.mktemp(suffix=".db")
    monkeypatch.setattr(xc, "DB_PATH", tmp)
    xc.init_db()
    yield


def _sign_all():
    for raw, val in [("MEOH-E", "E_METHANOL"), ("UNKNOWN-FUEL-LABEL", "E_METHANOL")]:
        xc.sign_mapping("TEST_FIXTURE", "fuel_id", raw, val, "pytest")
        xc.sign_mapping("TEST_FIXTURE", "pathway_class", raw, "RFNBO", "pytest")
    xc.sign_mapping("TEST_FIXTURE", "technology_class", "PEM+SYN", "PEM_SYNTHESIS", "pytest")
    for raw, val in [("FID taken", "fid"), ("Concept", "concept"),
                     ("Operational", "operational"), ("Cancelled", "cancelled")]:
        xc.sign_mapping("TEST_FIXTURE", "status", raw, val, "pytest")


def test_unmapped_labels_quarantine_never_guess():
    r = xc.import_snapshot(source_version="v1", rows=V1, **LIC)
    assert r["quarantined"] == 3            # nothing signed yet -> all quarantined
    summary = xc.corpus_summary()
    assert summary["unmapped_labels_awaiting_signoff"]          # census sees the labels
    assert xc.density({"fuel_id": "E_METHANOL"})["density"] is None  # quarantined rows never count


def test_census_sign_then_reimport_lifts_quarantine():
    xc.import_snapshot(source_version="v1", rows=V1, **LIC)     # census pass
    _sign_all()
    r = xc.import_snapshot(source_version="v1b", rows=V1, **LIC)
    assert r["quarantined"] == 0
    d = xc.density({"fuel_id": "E_METHANOL", "technology_class": "PEM_SYNTHESIS",
                    "jurisdiction": "FR", "pathway_class": "RFNBO"})
    assert d["density"] is not None and d["n_pool"] == 3
    assert d["provenance_split"]["external"] == 1.0             # provenance always reported
    assert d["provenance"] == "EXTERNAL_PRIOR"


def test_version_diff_yields_revealed_transitions():
    _sign_all()
    xc.import_snapshot(source_version="v1", rows=V1, **LIC)
    r2 = xc.import_snapshot(source_version="v2", rows=V2, **LIC)
    assert r2["status_transitions_observed"] == 2               # fid->operational, concept->cancelled
    rates = xc.base_rates("E_METHANOL")
    pairs = {(t["from_status"], t["to_status"]) for t in rates["revealed_transitions"]}
    assert ("fid", "operational") in pairs and ("concept", "cancelled") in pairs


def test_base_rates_report_counts_and_never_dscr():
    _sign_all()
    xc.import_snapshot(source_version="v2", rows=V2, **LIC)
    rates = xc.base_rates("E_METHANOL")
    assert rates["dscr"] is None                                # NOT observable externally
    assert rates["provenance"] == "EXTERNAL_PRIOR"
    assert rates["status_counts"].get("operational") == 1
    assert rates["sources"][0]["license"].startswith("none — synthetic")


def test_empty_corpus_is_pending_not_fabricated():
    d = xc.density({"fuel_id": "E_SAF"})
    assert d["density"] is None and "PENDING" in d["note"]


def test_import_requires_license_and_attribution():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    import app.api.v1.corpus_routes as cr
    app = FastAPI(); app.include_router(cr.router, prefix="/api/v1/corpus")
    c = TestClient(app)
    bad = dict(source="X", source_version="1", license="  ", attribution="",
               retrieved_at="2026-07-02", imported_by="t", rows=[])
    assert c.post("/api/v1/corpus/import", json=bad).status_code == 422


def test_leak_guard_gates_and_scores_never_import_the_corpus():
    """Ruled epistemic policy: EXTERNAL_PRIOR must never reach gate evaluation
    or bankability scoring. Enforced as an import boundary."""
    root = Path(__file__).resolve().parents[1] / "app"
    forbidden = [
        root / "core" / "bankability_engine.py",
        root / "core" / "gex_project_rating_engine.py",
        root / "api" / "v1" / "routes_verification.py",
        root / "api" / "v1" / "routes_finance_model.py",
    ]
    for f in forbidden:
        if f.exists():
            assert "external_corpus" not in f.read_text(), \
                f"{f.name} must not consume EXTERNAL_PRIOR data"
    # tea_engine gate evaluator too (regime fork)
    tea = Path(__file__).resolve().parents[2] / "tea_engine" / "regimes.py"
    assert "external_corpus" not in tea.read_text()
