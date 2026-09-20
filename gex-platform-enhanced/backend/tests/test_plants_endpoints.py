"""
A plant belongs to one account, and the caller cannot name another.

`docs/supabase-cutover-endpoints.md` increment 2. The Supabase table took
`user_id` from the browser and PostgREST honoured it, so anyone could read or
overwrite anyone's portfolio by naming their id — and the live ids are
`admin-001`, `demo-user`, `user-003`, guessable strings rather than uuids.

Two defects are pinned here as well:
  - §8.15, the portfolio wipe: delete-then-insert with no transaction.
  - the deletion guard, so an empty body from a half-loaded client cannot mean
    "delete everything".

Uses `isolated_store`, so nothing touches the development database.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_plants
from app.core import plants_store

_IDENTITY: dict[str, Any] = {"payload": None}

ALICE = {"user_id": "alice_example_com", "email": "alice@example.com"}
BOB = {"user_id": "bob_example_com", "email": "bob@example.com"}
ADMIN = {"user_id": "admin_gex", "email": "admin@gex.example",
         "is_platform_admin": True}


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    plants_store.init_db()


@pytest.fixture()
def client() -> TestClient:
    api = FastAPI()

    @api.middleware("http")
    async def _bind_identity(request, call_next):
        payload = _IDENTITY["payload"]
        if payload is not None:
            request.state.auth_user_payload = payload
        return await call_next(request)

    api.include_router(routes_plants.router, prefix="/api/v1/plants")
    return TestClient(api)


@pytest.fixture(autouse=True)
def _clean():
    _IDENTITY["payload"] = None
    for owner in (ALICE, BOB, ADMIN):
        plants_store.replace_all(owner["user_id"], [])
    yield
    _IDENTITY["payload"] = None


def _as(identity: dict[str, Any]) -> None:
    _IDENTITY["payload"] = identity


def _plant(slug: str, name: str = "Plant") -> dict[str, Any]:
    return {"slug": slug, "data": {"id": slug, "name": name}}


# ── ownership ────────────────────────────────────────────────────────────────

def test_an_anonymous_caller_gets_nothing(client):
    assert client.get("/api/v1/plants").status_code == 401
    assert client.put("/api/v1/plants/x", json={"data": {}}).status_code == 401


def test_a_token_with_no_subject_does_not_land_in_a_shared_bucket(client):
    _as({"email": "nobody@example.com"})  # authenticated shape, no user_id
    assert client.get("/api/v1/plants").status_code == 401


def test_each_caller_sees_only_their_own_portfolio(client):
    _as(ALICE)
    client.put("/api/v1/plants/alice-1", json={"data": {"id": "alice-1"}})
    _as(BOB)
    client.put("/api/v1/plants/bob-1", json={"data": {"id": "bob-1"}})

    _as(ALICE)
    assert [p["slug"] for p in client.get("/api/v1/plants").json()] == ["alice-1"]
    _as(BOB)
    assert [p["slug"] for p in client.get("/api/v1/plants").json()] == ["bob-1"]


def test_another_owners_plant_is_404_not_403(client):
    """A 403 would confirm the slug exists and that somebody owns it."""
    _as(ALICE)
    client.put("/api/v1/plants/secret-site", json={"data": {"id": "secret-site"}})

    _as(BOB)
    assert client.get("/api/v1/plants/secret-site").status_code == 404
    assert client.delete("/api/v1/plants/secret-site").status_code == 404
    assert client.post("/api/v1/plants/secret-site/touch").status_code == 404

    # …and Bob's 404 did not delete it.
    _as(ALICE)
    assert client.get("/api/v1/plants/secret-site").status_code == 200


def test_writing_the_same_slug_does_not_touch_the_other_owners_row(client):
    _as(ALICE)
    client.put("/api/v1/plants/shared-name", json={"data": {"id": "a"}})
    _as(BOB)
    client.put("/api/v1/plants/shared-name", json={"data": {"id": "b"}})

    _as(ALICE)
    assert client.get("/api/v1/plants/shared-name").json()["data"]["id"] == "a"


def test_a_platform_admin_does_not_see_other_portfolios(client):
    """No implicit support bypass. GEX grants such access explicitly or not
    at all — an admin who can silently read a customer's work is a decision
    nobody took."""
    _as(ALICE)
    client.put("/api/v1/plants/alice-only", json={"data": {"id": "alice-only"}})

    _as(ADMIN)
    assert client.get("/api/v1/plants").json() == []
    assert client.get("/api/v1/plants/alice-only").status_code == 404


def test_the_route_offers_no_way_to_name_an_owner(client):
    """A query parameter that is ignored is worse than one that does not
    exist — it reads as supported. Nothing here accepts an owner."""
    _as(ALICE)
    client.put("/api/v1/plants/mine", json={"data": {"id": "mine"}})
    _as(BOB)
    assert client.get("/api/v1/plants?user_id=alice_example_com").json() == []


# ── the write paths ──────────────────────────────────────────────────────────

def test_upsert_then_read_round_trips_the_record(client):
    _as(ALICE)
    body = {"data": {"id": "rotterdam", "name": "Rotterdam RFNBO", "nodes": [1, 2]}}
    put = client.put("/api/v1/plants/rotterdam", json=body)
    assert put.status_code == 200
    assert put.json()["data"] == body["data"]
    assert client.get("/api/v1/plants/rotterdam").json()["data"]["nodes"] == [1, 2]


def test_touch_moves_only_this_plants_timestamp(client):
    _as(ALICE)
    client.put("/api/v1/plants/one", json={"data": {}})
    client.put("/api/v1/plants/two", json={"data": {}})
    before = {p["slug"]: p["updated_at"] for p in client.get("/api/v1/plants").json()}

    client.post("/api/v1/plants/one/touch")
    after = {p["slug"]: p["updated_at"] for p in client.get("/api/v1/plants").json()}

    assert after["one"] >= before["one"]
    assert after["two"] == before["two"]


def test_delete_removes_one_plant_and_leaves_the_rest(client):
    _as(ALICE)
    client.put("/api/v1/plants/keep", json={"data": {}})
    client.put("/api/v1/plants/drop", json={"data": {}})

    assert client.delete("/api/v1/plants/drop").status_code == 204
    assert [p["slug"] for p in client.get("/api/v1/plants").json()] == ["keep"]


# ── §8.15: the wipe ──────────────────────────────────────────────────────────

def test_a_failed_bulk_replace_leaves_the_portfolio_intact(monkeypatch):
    """
    THE DEFECT THIS CLOSES. The browser deleted every row then inserted the
    new set, unwrapped: a failure in between left the user with nothing.
    Here the delete and the insert are one transaction, so a failure rolls
    back to the portfolio the caller started with.
    """
    plants_store.replace_all(ALICE["user_id"], [_plant("a"), _plant("b")])
    assert plants_store.count_for_owner(ALICE["user_id"]) == 2

    real_dumps = plants_store.json.dumps
    calls = {"n": 0}

    def explode(obj, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:            # fail partway through the insert loop
            raise RuntimeError("network died mid-write")
        return real_dumps(obj, *a, **kw)

    monkeypatch.setattr(plants_store.json, "dumps", explode)
    with pytest.raises(RuntimeError):
        plants_store.replace_all(ALICE["user_id"], [_plant("c"), _plant("d")])

    monkeypatch.undo()
    survivors = sorted(p["slug"] for p in plants_store.list_plants(ALICE["user_id"]))
    assert survivors == ["a", "b"], "the original portfolio must survive a failed replace"


def test_an_empty_body_cannot_silently_empty_the_portfolio(client):
    """A half-initialised client sending `[]` means "I have nothing loaded",
    not "delete my work". The caller must state the deletion count."""
    _as(ALICE)
    client.put("/api/v1/plants/p1", json={"data": {}})
    client.put("/api/v1/plants/p2", json={"data": {}})

    res = client.put("/api/v1/plants?confirm_delete=0", json={"plants": []})
    assert res.status_code == 409
    assert "would delete 2" in res.json()["detail"]
    assert len(client.get("/api/v1/plants").json()) == 2


def test_a_bulk_replace_that_states_its_deletions_is_accepted(client):
    _as(ALICE)
    client.put("/api/v1/plants/p1", json={"data": {}})
    client.put("/api/v1/plants/p2", json={"data": {}})

    res = client.put("/api/v1/plants?confirm_delete=1",
                     json={"plants": [_plant("p1"), _plant("p3")]})
    assert res.status_code == 200
    assert sorted(p["slug"] for p in res.json()) == ["p1", "p3"]


def test_a_replaced_plant_keeps_its_original_created_at(client):
    _as(ALICE)
    client.put("/api/v1/plants/persistent", json={"data": {}})
    created = client.get("/api/v1/plants/persistent").json()["created_at"]

    client.put("/api/v1/plants", json={"plants": [_plant("persistent")]})
    assert client.get("/api/v1/plants/persistent").json()["created_at"] == created


# ── the store ────────────────────────────────────────────────────────────────

def test_postgres_is_refused_rather_than_created_unprotected(monkeypatch):
    from app.core.ecosystem_store import PostgresMigrationRequired

    monkeypatch.setattr(plants_store, "_plants_is_postgres", lambda: True)
    with pytest.raises(PostgresMigrationRequired):
        plants_store.init_db()
