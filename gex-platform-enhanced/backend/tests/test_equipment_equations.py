"""
An equation can only be deleted by the person who owns it.

`docs/supabase-cutover-endpoints.md` increment 4, closing CLAUDE_HANDOFF
§8.16. The browser's delete was:

    supabase.from("equipment_equations").delete().eq("id", id)

— no user scoping, while every other query in the same hook filtered on
`user_id`. Under the bundled anon key that removed any row by id, for anybody.

So the delete tests are the point of this file, and the 404-not-403 rule
matters as much as the refusal: a 403 would confirm the id exists.

Uses `isolated_store`, so nothing touches the development database.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_equipment_equations
from app.core import equations_store

_IDENTITY: dict[str, Any] = {"payload": None}

ALICE = {"user_id": "alice_example_com", "email": "alice@example.com"}
BOB = {"user_id": "bob_example_com", "email": "bob@example.com"}
ADMIN = {"user_id": "admin_gex", "email": "a@gex.example", "is_platform_admin": True}

PLANT, NODE = "rotterdam-rfnbo", "e-electrolyzer"


def _body(**over: Any) -> dict[str, Any]:
    payload = {
        "plant_slug": PLANT,
        "equipment_node_id": NODE,
        "equipment_label": "Electrolyzer",
        "equation_id": "EQ351",
        "equation_expression": "n_H2 = m_H2 / M_H2",
        "output_param": "n_H2",
        "variable_bindings": {"m_H2": {"source": "node", "ref": "x"}},
    }
    payload.update(over)
    return payload


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    equations_store.init_db()


@pytest.fixture()
def client() -> TestClient:
    api = FastAPI()

    @api.middleware("http")
    async def _bind_identity(request, call_next):
        payload = _IDENTITY["payload"]
        if payload is not None:
            request.state.auth_user_payload = payload
        return await call_next(request)

    api.include_router(routes_equipment_equations.router,
                       prefix="/api/v1/equipment-equations")
    return TestClient(api)


@pytest.fixture(autouse=True)
def _clean():
    _IDENTITY["payload"] = None
    import sqlite3
    from app.core.config import settings
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    try:
        conn.execute("DELETE FROM equipment_equations")
        conn.commit()
    finally:
        conn.close()
    yield
    _IDENTITY["payload"] = None


def _as(identity: dict[str, Any]) -> None:
    _IDENTITY["payload"] = identity


def _q(plant: str = PLANT, node: str = NODE) -> str:
    return f"/api/v1/equipment-equations?plant_slug={plant}&node_id={node}"


# ── the defect this closes ───────────────────────────────────────────────────

def test_one_owner_cannot_delete_anothers_equation(client):
    """§8.16. The whole reason this increment exists."""
    _as(ALICE)
    created = client.put("/api/v1/equipment-equations", json=_body()).json()

    _as(BOB)
    assert client.delete(f"/api/v1/equipment-equations/{created['id']}").status_code == 404

    _as(ALICE)
    assert [e["id"] for e in client.get(_q()).json()] == [created["id"]], \
        "Alice's equation must survive Bob's delete"


def test_a_platform_admin_cannot_either(client):
    """No implicit support bypass, the same rule as plants and canvases."""
    _as(ALICE)
    created = client.put("/api/v1/equipment-equations", json=_body()).json()
    _as(ADMIN)
    assert client.delete(f"/api/v1/equipment-equations/{created['id']}").status_code == 404
    _as(ALICE)
    assert len(client.get(_q()).json()) == 1


def test_a_missing_and_a_foreign_row_answer_identically(client):
    """404 either way: the status code must not reveal that an id exists."""
    _as(ALICE)
    created = client.put("/api/v1/equipment-equations", json=_body()).json()
    _as(BOB)
    foreign = client.delete(f"/api/v1/equipment-equations/{created['id']}")
    absent = client.delete("/api/v1/equipment-equations/00000000-0000-0000-0000-000000000000")
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()


def test_an_owner_can_delete_their_own(client):
    _as(ALICE)
    created = client.put("/api/v1/equipment-equations", json=_body()).json()
    assert client.delete(f"/api/v1/equipment-equations/{created['id']}").status_code == 204
    assert client.get(_q()).json() == []


# ── ownership on the read and write paths ────────────────────────────────────

def test_an_anonymous_caller_gets_nothing(client):
    assert client.get(_q()).status_code == 401
    assert client.put("/api/v1/equipment-equations", json=_body()).status_code == 401
    assert client.delete("/api/v1/equipment-equations/x").status_code == 401


def test_each_caller_sees_only_their_own_equations(client):
    _as(ALICE)
    client.put("/api/v1/equipment-equations", json=_body())
    _as(BOB)
    assert client.get(_q()).json() == []
    client.put("/api/v1/equipment-equations", json=_body(equation_id="EQ9"))
    assert [e["equation_id"] for e in client.get(_q()).json()] == ["EQ9"]
    _as(ALICE)
    assert [e["equation_id"] for e in client.get(_q()).json()] == ["EQ351"]


# ── the contract the hook expects ────────────────────────────────────────────

def test_the_row_shape_is_StoredEquipmentEquation(client):
    _as(ALICE)
    created = client.put("/api/v1/equipment-equations", json=_body()).json()
    assert set(created) == {"id", "equation_id", "equation_expression",
                            "output_param", "variable_bindings"}
    assert created["variable_bindings"] == {"m_H2": {"source": "node", "ref": "x"}}


def test_resaving_the_same_equation_updates_rather_than_duplicates(client):
    """Same conflict target the browser used: (owner, plant, node, equation)."""
    _as(ALICE)
    first = client.put("/api/v1/equipment-equations", json=_body()).json()
    second = client.put("/api/v1/equipment-equations",
                        json=_body(equation_expression="n_H2 = 2 * m_H2")).json()
    assert first["id"] == second["id"]
    rows = client.get(_q()).json()
    assert len(rows) == 1
    assert rows[0]["equation_expression"] == "n_H2 = 2 * m_H2"


def test_equations_are_scoped_to_the_node_not_just_the_plant(client):
    _as(ALICE)
    client.put("/api/v1/equipment-equations", json=_body())
    client.put("/api/v1/equipment-equations",
               json=_body(equipment_node_id="e-wtu", equation_id="EQ8"))
    assert len(client.get(_q()).json()) == 1
    assert len(client.get(_q(node="e-wtu")).json()) == 1


def test_two_owners_may_hold_the_same_equation_id(client):
    """The uniqueness constraint includes the owner; it must not collide."""
    _as(ALICE)
    a = client.put("/api/v1/equipment-equations", json=_body()).json()
    _as(BOB)
    b = client.put("/api/v1/equipment-equations", json=_body()).json()
    assert a["id"] != b["id"]


# ── the store ────────────────────────────────────────────────────────────────

def test_postgres_is_refused_rather_than_created_unprotected(monkeypatch):
    from app.core.ecosystem_store import PostgresMigrationRequired

    monkeypatch.setattr(equations_store, "_equations_is_postgres", lambda: True)
    with pytest.raises(PostgresMigrationRequired):
        equations_store.init_db()
