"""
Chain-of-Custody ledger — naming truth and project anchoring.
=============================================================
This module was called the "Mass Balance Ledger". It is not one. It performs
two arithmetic operations — `allocated += volume` and `remaining = total -
allocated` — and contains no yield, conversion, recycle, utility, loss,
efficiency, stream or stoichiometry logic of any kind.

Engineering mass balance DOES exist in GEX, in the frontend equation engine
(`src/engine/`): conservation residual r = Σṁ_in − Σṁ_out, electrolysis
stoichiometry, splitter and separator balances, recycle and purge. Different
layer, different file, not a duplicate. These tests exist so the two never get
merged and the backend never re-acquires the engineering claim.

The load-bearing behaviour under test is the 503/404 distinction. `fetch_project`
returns None both for "no such project" and for "the database was unreachable",
because projects_store fails soft to keep ABAC hot paths alive. Reporting an
outage as 404 would tell an operator their project_id is wrong, and they would
"fix" it by inventing a different one — writing custody records anchored to a
project that does not exist.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
MODULE = BACKEND / "app" / "api" / "v1" / "mass_balance.py"

LOT = {
    "project_id": "proj_etf_pecos1",
    "molecule": "E_METHANOL",
    "production_date": "2026-07-14",
    "total_volume_kg": 12_000_000,
    "certification_pathway": "RFNBO",
    "carbon_intensity_gco2e_mj": 18.4,
    "created_by": "test",
}


@pytest.fixture()
def client(isolated_store):
    """`isolated_store` is not optional. Without it this fixture drove the
    DEVELOPMENT store: three `created_by='test'` lots from earlier runs are
    still in `backend/gex_platform.db`, and once DOMAIN_DB_BACKEND became
    `postgres` the same tests would have written the real PostgreSQL."""
    from app.api.v1.mass_balance import init_db, router

    init_db()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── The product surface is Chain of Custody ─────────────────────────────────

def test_the_route_prefix_is_chain_of_custody(client):
    """"Mass balance" names the RED III chain-of-custody METHOD correctly, but
    it is the wrong name for a product: an engineer reads it as conservation of
    mass and energy, which this module does not perform."""
    paths = {r.path for r in client.app.routes}
    assert any(p.startswith("/api/v1/chain-of-custody") for p in paths), paths
    assert not any(p.startswith("/api/v1/mass-balance") for p in paths), (
        "the old prefix is still served — domain_authorization maps the path to "
        "a domain, so two prefixes means one of them is unauthorised"
    )


def test_the_authorization_map_follows_the_rename():
    src = (BACKEND / "app" / "core" / "domain_authorization.py").read_text()
    assert '"/api/v1/chain-of-custody"' in src, (
        "domain_authorization still maps the old path — the renamed routes would "
        "fall outside the sustainability domain"
    )


def test_the_module_does_not_claim_engineering_balance():
    """Guards the docstring against re-acquiring a physics claim. Matched on the
    module docstring only, so ordinary code comments are not caught."""
    doc = ast.get_docstring(ast.parse(MODULE.read_text())) or ""
    assert "does not" in doc.lower() and "equipment sizing" in doc.lower(), (
        "the docstring no longer states what this module does NOT validate"
    )
    for claim in ("verifies the plant", "validates the process", "solves the mass balance"):
        assert claim not in doc.lower(), f"docstring claims to {claim}"


def test_the_module_still_performs_no_physics():
    """The original finding, pinned. If any of these appear, either real process
    logic arrived here (wrong layer — it belongs in src/engine) or the module is
    drifting back toward the claim its old name made."""
    src = MODULE.read_text().lower()
    body = src[src.index('"""', src.index('"""') + 3) + 3:]      # strip docstring
    for term in ("recycle", "stoichiom", "utilit", "conversion_factor", "purge"):
        assert term not in body, (
            f"'{term}' appeared in the custody ledger. Engineering balance lives "
            "in the frontend equation engine, not here."
        )


# ── A lot must be anchored to a real project ────────────────────────────────

def test_an_unknown_project_is_rejected_as_404(client, monkeypatch):
    import app.core.projects_store as ps

    monkeypatch.setattr(ps, "fetch_project", lambda pid: None)
    monkeypatch.setattr(ps, "_engine", lambda: _ReachableEngine())

    r = client.post("/api/v1/chain-of-custody/lots", json={**LOT, "project_id": "nope"})
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()


def test_an_unreachable_store_is_503_not_404(client, monkeypatch):
    """THE test. An outage must not be reported as an invalid project."""
    import app.core.projects_store as ps

    monkeypatch.setattr(ps, "fetch_project", lambda pid: None)

    def _down():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ps, "_engine", _down)

    r = client.post("/api/v1/chain-of-custody/lots", json={**LOT, "project_id": "nope"})
    assert r.status_code == 503, (
        f"got {r.status_code}: an unreachable projects store was reported as an "
        "invalid project. An operator would 'fix' that by inventing a different "
        "project_id and anchoring custody to nothing."
    )


def test_a_real_project_is_accepted_and_recorded(client, monkeypatch):
    import app.core.projects_store as ps

    monkeypatch.setattr(
        ps, "fetch_project",
        lambda pid: {"project_id": pid, "project_name": "ETFuels Pecos I"},
    )
    r = client.post("/api/v1/chain-of-custody/lots", json=LOT)
    assert r.status_code == 201, r.text
    lot = r.json()
    assert lot["project_id"] == LOT["project_id"]
    assert lot["remaining_volume_kg"] == LOT["total_volume_kg"]

    # and the exhaustion guard still holds on the created lot
    over = client.post("/api/v1/chain-of-custody/allocate", json={
        "lot_id": lot["lot_id"], "token_id": "TKN-TEST",
        "volume_kg": LOT["total_volume_kg"] + 1, "allocated_by": "test",
    })
    assert over.status_code >= 400, "over-allocation was accepted"


class _ReachableEngine:
    """Stands in for a live SQLAlchemy engine: connect() works, so the 404
    branch is reached rather than the 503 branch."""

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *_a, **_k):
        return None
