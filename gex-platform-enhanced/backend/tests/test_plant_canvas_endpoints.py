"""
Canvas documents belong to one account, and slugs come from a URL.

`docs/supabase-cutover-endpoints.md` increment 3. The Supabase bucket was
listable and readable with the bundled anon key, and the path that scoped a
document — `users/{userId}/{slug}.json` — was composed by the browser, so
naming another id read their canvas.

Two hazards get pinned here:
  - cross-owner access, which must be 404 rather than 403;
  - path traversal, because `slug` reaches a filesystem path and arrives from
    a URL. A `..` that escaped would read or overwrite arbitrary files.

Uses `isolated_store` and a temporary blob directory, so neither the dev
database nor the real `data/` tree is touched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import routes_plant_canvas
from app.core import canvas_store

_IDENTITY: dict[str, Any] = {"payload": None}

ALICE = {"user_id": "alice_example_com", "email": "alice@example.com"}
BOB = {"user_id": "bob_example_com", "email": "bob@example.com"}
ADMIN = {"user_id": "admin_gex", "email": "a@gex.example", "is_platform_admin": True}

CANVAS = {"nodes": [{"id": "electrolyser"}], "edges": []}


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store, tmp_path_factory):
    blobs = tmp_path_factory.mktemp("canvas_blobs")
    original = canvas_store.CANVAS_BLOBS_DIR
    canvas_store.CANVAS_BLOBS_DIR = str(blobs)
    canvas_store.init_db()
    yield blobs
    canvas_store.CANVAS_BLOBS_DIR = original


@pytest.fixture()
def client() -> TestClient:
    api = FastAPI()

    @api.middleware("http")
    async def _bind_identity(request, call_next):
        payload = _IDENTITY["payload"]
        if payload is not None:
            request.state.auth_user_payload = payload
        return await call_next(request)

    api.include_router(routes_plant_canvas.router, prefix="/api/v1/plant-canvas")
    return TestClient(api)


@pytest.fixture(autouse=True)
def _clean():
    _IDENTITY["payload"] = None
    for owner in (ALICE, BOB, ADMIN):
        for kind, slug in (("canvas", "p1"), ("canvas", "shared"), ("site", "p1"),
                           ("library", "")):
            try:
                canvas_store.delete_document(owner["user_id"], kind, slug)
            except canvas_store.BlobNotFound:
                pass
    yield
    _IDENTITY["payload"] = None


def _as(identity: dict[str, Any]) -> None:
    _IDENTITY["payload"] = identity


# ── ownership ────────────────────────────────────────────────────────────────

def test_an_anonymous_caller_gets_nothing(client):
    assert client.get("/api/v1/plant-canvas/canvas/p1").status_code == 401
    assert client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS).status_code == 401
    assert client.get("/api/v1/plant-canvas/library").status_code == 401


def test_a_canvas_round_trips_for_its_owner(client):
    _as(ALICE)
    put = client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS)
    assert put.status_code == 200
    assert put.json()["size_bytes"] > 0

    got = client.get("/api/v1/plant-canvas/canvas/p1")
    assert got.status_code == 200
    assert got.json() == CANVAS
    assert got.headers["content-type"].startswith("application/json")
    assert got.headers["X-Content-Sha256"] == put.json()["sha256"]


def test_another_owners_canvas_is_404_not_403(client):
    _as(ALICE)
    client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS)

    _as(BOB)
    assert client.get("/api/v1/plant-canvas/canvas/p1").status_code == 404
    assert client.delete("/api/v1/plant-canvas/canvas/p1").status_code == 404
    assert client.get("/api/v1/plant-canvas/canvas/p1/versions").json() == []

    _as(ALICE)
    assert client.get("/api/v1/plant-canvas/canvas/p1").json() == CANVAS


def test_two_owners_may_hold_the_same_slug_without_collision(client):
    _as(ALICE)
    client.put("/api/v1/plant-canvas/canvas/shared", json={"nodes": ["a"], "edges": []})
    _as(BOB)
    client.put("/api/v1/plant-canvas/canvas/shared", json={"nodes": ["b"], "edges": []})

    _as(ALICE)
    assert client.get("/api/v1/plant-canvas/canvas/shared").json()["nodes"] == ["a"]
    _as(BOB)
    assert client.get("/api/v1/plant-canvas/canvas/shared").json()["nodes"] == ["b"]


def test_a_platform_admin_does_not_read_other_canvases(client):
    """Same rule as the plant rows: no implicit support bypass."""
    _as(ALICE)
    client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS)
    _as(ADMIN)
    assert client.get("/api/v1/plant-canvas/canvas/p1").status_code == 404


def test_the_library_is_per_user(client):
    _as(ALICE)
    client.put("/api/v1/plant-canvas/library", json={"items": ["alice-pump"]})
    _as(BOB)
    assert client.get("/api/v1/plant-canvas/library").status_code == 404
    client.put("/api/v1/plant-canvas/library", json={"items": ["bob-pump"]})
    assert client.get("/api/v1/plant-canvas/library").json()["items"] == ["bob-pump"]
    _as(ALICE)
    assert client.get("/api/v1/plant-canvas/library").json()["items"] == ["alice-pump"]


# ── path traversal ───────────────────────────────────────────────────────────

def test_the_route_refuses_an_encoded_traversal_outright(_schema, client):
    """Encoded slashes do not match a single path segment, so these never reach
    the handler. Worth pinning: it is the first of two layers, and if routing
    ever changed to accept them the second layer below is what holds."""
    _as(ALICE)
    for attempt in ("..%2F..%2F..%2Fescaped", "..%2Fescaped2"):
        res = client.put(f"/api/v1/plant-canvas/canvas/{attempt}", json=CANVAS)
        assert res.status_code >= 400, f"{attempt} was accepted"

    root = Path(_schema).resolve()
    assert not (root.parent / "escaped.json").exists()
    assert not (root.parent / "escaped2.json").exists()


@pytest.mark.parametrize("hostile", [
    "../../../escaped", "....//escaped", "/etc/passwd", "..", ".", "a/../../b",
    "\x00null", "../" * 12 + "root",
])
def test_a_hostile_slug_cannot_escape_the_blob_root(_schema, hostile):
    """
    The second layer, tested where it lives. `_safe()` is what stands between a
    slug and the filesystem; the route is not the only possible caller, and a
    migration script passes slugs straight from an export.
    """
    owner = ALICE["user_id"]
    root = Path(_schema).resolve()

    # Check the path the store INTENDS to use, not just what landed inside the
    # root: a file written outside would be invisible to an rglob of the root,
    # so scanning alone would pass vacuously for the traversal cases.
    intended = canvas_store._disk_path(owner, "canvas", hostile, "0" * 64).resolve()
    assert root in intended.parents, f"{intended} escapes {root}"

    canvas_store.put_blob(owner, "canvas", hostile, json.dumps(CANVAS).encode())
    for path in root.rglob("*.json"):
        assert root in path.resolve().parents, f"{path} escaped {root}"
    # Readable back under the same hostile key, so sanitising is deterministic
    # rather than lossy in a way that strands documents.
    content, _ = canvas_store.get_blob(owner, "canvas", hostile)
    assert json.loads(content) == CANVAS


def test_a_traversal_slug_cannot_reach_another_owners_document(client):
    _as(ALICE)
    client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS)
    _as(BOB)
    for attempt in ("..%2Falice_example_com%2Fcanvas%2Fp1", "..%2F..%2Fp1"):
        assert client.get(f"/api/v1/plant-canvas/canvas/{attempt}").status_code == 404


# ── versions ─────────────────────────────────────────────────────────────────

def test_versions_are_listed_newest_first_and_readable(client):
    _as(ALICE)
    for stamp, node in (("2026-09-20T10-00-00", "a"), ("2026-09-20T11-00-00", "b")):
        client.put(f"/api/v1/plant-canvas/canvas/p1/versions/{stamp}",
                   json={"nodes": [node], "edges": []})

    listed = client.get("/api/v1/plant-canvas/canvas/p1/versions").json()
    assert [v["version_id"] for v in listed] == [
        "2026-09-20T11-00-00", "2026-09-20T10-00-00"]

    old = client.get("/api/v1/plant-canvas/canvas/p1/versions/2026-09-20T10-00-00")
    assert old.json()["nodes"] == ["a"]


def test_history_is_pruned_to_the_retention_limit(client):
    """Matches MAX_VERSIONS_KEPT in useCanvasData, so the cutover changes no
    behaviour — the limit just moves to where it can be enforced."""
    _as(ALICE)
    keep = canvas_store.MAX_VERSIONS_KEPT
    for i in range(keep + 5):
        client.put(f"/api/v1/plant-canvas/canvas/p1/versions/v{i:03d}",
                   json={"nodes": [i], "edges": []})

    listed = client.get("/api/v1/plant-canvas/canvas/p1/versions").json()
    assert len(listed) == keep
    assert listed[0]["version_id"] == f"v{keep + 4:03d}"      # newest kept
    assert client.get("/api/v1/plant-canvas/canvas/p1/versions/v000").status_code == 404


def test_deleting_a_canvas_takes_its_history_with_it(client):
    _as(ALICE)
    client.put("/api/v1/plant-canvas/canvas/p1", json=CANVAS)
    client.put("/api/v1/plant-canvas/canvas/p1/versions/v1", json=CANVAS)

    assert client.delete("/api/v1/plant-canvas/canvas/p1").status_code == 204
    assert client.get("/api/v1/plant-canvas/canvas/p1").status_code == 404
    assert client.get("/api/v1/plant-canvas/canvas/p1/versions").json() == []


# ── the store ────────────────────────────────────────────────────────────────

def test_identical_content_is_stored_once_and_survives_a_sibling_delete(_schema):
    """Content addressing means two versions can share a file. Deleting one
    must not blank the other — the bug a naive unlink would introduce."""
    owner = ALICE["user_id"]
    body = json.dumps(CANVAS).encode()
    canvas_store.put_blob(owner, "canvas", "p1", body, version_id="v1")
    canvas_store.put_blob(owner, "canvas", "p1", body, version_id="v2")

    files = list((Path(_schema) / owner / "canvas" / "p1").glob("*.json"))
    assert len(files) == 1, "identical content should be written once"

    canvas_store.prune_versions(owner, "canvas", "p1", keep=1)
    content, _ = canvas_store.get_blob(owner, "canvas", "p1", version_id="v2")
    assert json.loads(content) == CANVAS


def test_an_oversized_document_is_refused(client):
    _as(ALICE)
    payload = {"nodes": ["x" * (canvas_store.MAX_BLOB_BYTES + 1024)]}
    res = client.put("/api/v1/plant-canvas/canvas/p1", json=payload)
    assert res.status_code == 413


def test_an_empty_body_is_refused_rather_than_stored(client):
    """An empty save would silently destroy a canvas on the next read."""
    _as(ALICE)
    assert client.put("/api/v1/plant-canvas/canvas/p1", content=b"").status_code == 422


def test_missing_content_reports_absence_rather_than_an_empty_canvas(_schema):
    """If the row outlives its bytes, saying "here is nothing" would invite the
    canvas to overwrite itself with it."""
    owner = ALICE["user_id"]
    canvas_store.put_blob(owner, "canvas", "p1", json.dumps(CANVAS).encode())
    _, meta = canvas_store.get_blob(owner, "canvas", "p1")
    for path in (Path(_schema) / owner / "canvas" / "p1").glob("*.json"):
        path.unlink()
    with pytest.raises(canvas_store.BlobNotFound):
        canvas_store.get_blob(owner, "canvas", "p1")


def test_stored_paths_are_absolute(_schema):
    """
    A relative path resolves against the working directory, so a service
    started from elsewhere would find no bytes for any row and every canvas
    would read as "content missing" while the files sat safely on disk. Caught
    live on 2026-09-20; pinned so it cannot come back.
    """
    owner = ALICE["user_id"]
    canvas_store.put_blob(owner, "canvas", "p1", json.dumps(CANVAS).encode())
    stored = canvas_store._disk_path(owner, "canvas", "p1", "0" * 64)
    assert stored.is_absolute(), f"{stored} is relative"


def test_the_store_never_creates_canvas_blobs_on_postgres(monkeypatch):
    """`canvas_blobs` belongs to migration 050, policy included.

    This module used to RAISE on PostgreSQL, because the only alternative then
    was creating an owner-scoped table with no policy at all. 050 creates it
    WITH an owner-only policy (no admin clause), so raising would now only stop
    the app booting against a database that already has the table. What must
    not change is who creates it: the runtime never does. If anyone
    reintroduces DDL here, the table would be created unprotected and every
    owner's rows would be readable by everyone.
    """
    def _explode(*a, **kw):
        raise AssertionError(
            "init_db() opened a PostgreSQL connection — canvas_blobs belongs to "
            "migration 050, not to the runtime")

    monkeypatch.setattr(canvas_store, "_canvas_is_postgres", lambda: True)
    monkeypatch.setattr(canvas_store, "workspace_connection", _explode)
    canvas_store.init_db()
