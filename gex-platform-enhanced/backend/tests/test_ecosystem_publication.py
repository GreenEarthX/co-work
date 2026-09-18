"""
Ecosystem map publication — server-side store.

Pins the three rules the review document set for this table: attach rather than
overwrite, withdraw is a soft delete, and the publisher's confidentiality choice
binds every other viewer including a platform admin.

Uses `isolated_store`, so nothing here writes the development database.
"""
from __future__ import annotations

import pytest

from app.core import ecosystem_store as store


@pytest.fixture(scope="module", autouse=True)
def _schema(isolated_store):
    store.init_db()


@pytest.fixture(autouse=True)
def _clean():
    conn = store._conn()
    try:
        conn.execute("DELETE FROM ecosystem_published_projects")
        conn.execute("DELETE FROM ecosystem_enrichments")
        conn.commit()
    finally:
        conn.close()


def _publish(tenant="t_alpha", slug="mv2", name="Maasvlakte H2",
             status="planned", **kw):
    return store.publish_project(
        tenant_id=tenant, user_id="u1", slug=slug, name=name,
        lat=51.95, lng=4.05, status=status, country="Netherlands",
        molecule_type="hydrogen", owner_name="Shell Nederland", **kw)


def _eco(name: str) -> dict:
    """One published marker as another tenant sees it, found by name.
    `list_published` returns map records, which carry no slug."""
    rec = next(p for p in store.list_published() if p["name"] == name)
    return store.redact_for_viewer(rec, "t_beta")


# ── it actually persists, which localStorage never did ──────────────────────

def test_a_published_project_is_visible_to_another_tenant():
    _publish()
    seen = [store.redact_for_viewer(p, "t_beta") for p in store.list_published()]
    assert [p["name"] for p in seen] == ["Maasvlakte H2"]
    assert seen[0]["owned"] is False


def test_republishing_the_same_slug_updates_rather_than_duplicating():
    first = _publish()
    again = _publish(name="Maasvlakte H2 Renamed")
    assert first["id"] == again["id"]
    assert len(store.list_published()) == 1
    assert store.list_published()[0]["name"] == "Maasvlakte H2 Renamed"


def test_coordinates_are_required_to_place_a_marker():
    with pytest.raises(ValueError):
        store.publish_project(tenant_id="t_alpha", user_id="u1", slug="nowhere",
                              name="Nowhere", lat=None, lng=None, status="planned")


# ── attach, never overwrite ─────────────────────────────────────────────────

def test_two_tenants_enriching_one_project_both_survive():
    target = _publish()["id"]
    store.attach_enrichment(tenant_id="t_beta", user_id="u2",
                            target_eco_id=target, payload={"capacity": "20 kt/yr"})
    store.attach_enrichment(tenant_id="t_gamma", user_id="u3",
                            target_eco_id=target, payload={"capacity": "60 kt/yr"})
    rows = store.list_enrichments(target)
    assert len(rows) == 2
    # The disagreement is retained, not resolved. That is the point.
    assert {r["payload"]["capacity"] for r in rows} == {"20 kt/yr", "60 kt/yr"}


def test_a_tenant_re_enriching_replaces_only_its_own_reading():
    target = _publish()["id"]
    store.attach_enrichment(tenant_id="t_beta", user_id="u2",
                            target_eco_id=target, payload={"capacity": "20 kt/yr"})
    store.attach_enrichment(tenant_id="t_gamma", user_id="u3",
                            target_eco_id=target, payload={"capacity": "60 kt/yr"})
    store.attach_enrichment(tenant_id="t_beta", user_id="u2",
                            target_eco_id=target, payload={"capacity": "25 kt/yr"})
    rows = {r["tenant_id"]: r["payload"]["capacity"]
            for r in store.list_enrichments(target)}
    assert rows == {"t_beta": "25 kt/yr", "t_gamma": "60 kt/yr"}


# ── withdrawal is soft ──────────────────────────────────────────────────────

def test_withdrawing_hides_the_marker_but_keeps_the_row():
    _publish()
    assert store.withdraw_project(tenant_id="t_alpha", slug="mv2") is True
    assert store.list_published() == []
    conn = store._conn()
    try:
        row = conn.execute("SELECT withdrawn_at FROM ecosystem_published_projects "
                           "WHERE slug = 'mv2'").fetchone()
    finally:
        conn.close()
    assert row is not None and row["withdrawn_at"] is not None


def test_withdrawing_someone_elses_marker_does_nothing():
    _publish(tenant="t_alpha")
    assert store.withdraw_project(tenant_id="t_beta", slug="mv2") is False
    assert len(store.list_published()) == 1


# ── publisher confidentiality ───────────────────────────────────────────────

def test_gated_extras_are_hidden_from_other_tenants():
    _publish(extras={"website": "https://example.com", "offtakers": "Maersk"},
             visible_fields=["website"])
    rec = store.list_published()[0]
    other = store.redact_for_viewer(rec, "t_beta")
    assert other["website"] == "https://example.com"   # publisher opted in
    assert "offtakers" not in other                    # publisher did not
    mine = store.redact_for_viewer(rec, "t_alpha")
    assert mine["offtakers"] == "Maersk"               # own record, whole


def test_platform_admin_does_not_bypass_publisher_confidentiality():
    # Publisher confidentiality is security, not a viewer preference, so the
    # admin tier does not lift it.
    _publish(extras={"offtakers": "Maersk"}, visible_fields=[])
    rec = store.list_published()[0]
    assert "offtakers" not in store.redact_for_viewer(rec, "PLATFORM_ADMIN")


def test_an_unauthenticated_viewer_sees_no_gated_extras_and_owns_nothing():
    _publish(extras={"offtakers": "Maersk"}, visible_fields=[])
    rec = store.list_published()[0]
    out = store.redact_for_viewer(rec, None)
    assert out["owned"] is False and "offtakers" not in out


def test_internal_columns_never_leave_the_store():
    _publish()
    out = store.redact_for_viewer(store.list_published()[0], "t_beta")
    assert not [k for k in out if k.startswith("_")]


# ── postgres guard ──────────────────────────────────────────────────────────

def test_init_refuses_to_create_unprotected_tenant_tables_on_postgres(monkeypatch):
    monkeypatch.setenv("ECOSYSTEM_DB_BACKEND", "postgres")
    with pytest.raises(store.PostgresMigrationRequired):
        store.init_db()


# ── lifecycle: phase and status are two fields (Data Structure v4.2) ─────────

def test_phase_and_status_are_recorded_separately():
    """The point of the split: a project is cancelled AT a phase."""
    _publish(slug="split", name="Cancelled At FEED", phase="feed", status="cancelled")
    eco = _eco("Cancelled At FEED")
    assert (eco["phase"], eco["status"]) == ("feed", "cancelled")


def test_a_legacy_status_is_split_on_write():
    """Older clients still send one value. Refusing them would drop publications."""
    cases = {
        "planned": ("unknown", "active"),
        "concept": ("concept", "active"),
        "construction": ("construction", "active"),
        "operational": ("operation", "active"),
        "cancelled": ("unknown", "cancelled"),
    }
    for legacy, expected in cases.items():
        _publish(slug=f"legacy_{legacy}", name=f"Legacy {legacy}", status=legacy)
        eco = _eco(f"Legacy {legacy}")
        assert (eco["phase"], eco["status"]) == expected, legacy


def test_a_row_written_before_the_column_existed_still_reads_as_a_pair():
    """The additive migration defaults `phase` to 'unknown'; the legacy status
    is what carries the meaning, and it is resolved on read."""
    _publish(slug="old_row", name="Pre-split Row", status="operational")
    conn = store._conn()
    try:
        # What a pre-split row looks like once ALTER TABLE has run: the legacy
        # status untouched, the new column holding only its default. Writing
        # both by hand matters — publish_project normalises on write, so
        # resetting the phase alone would not reproduce the row.
        conn.execute("UPDATE ecosystem_published_projects "
                     "SET phase = 'unknown', status = 'operational' "
                     "WHERE slug = 'old_row'")
        conn.commit()
    finally:
        conn.close()
    eco = _eco("Pre-split Row")
    assert (eco["phase"], eco["status"]) == ("operation", "active")


def test_rubbish_lifecycle_values_fail_closed_rather_than_raising():
    _publish(slug="junk", name="Junk Values", phase="banana", status="nonsense")
    eco = _eco("Junk Values")
    assert (eco["phase"], eco["status"]) == ("unknown", "active")


def test_the_lifecycle_vocabulary_matches_the_frontend():
    """Two copies of one vocabulary exist — here and in
    `frontend/src/lib/ecosystem/types.ts` — because both ends must read a legacy
    row the same way. This test is what keeps them from drifting apart."""
    import re
    from pathlib import Path

    types_ts = (Path(__file__).resolve().parents[2]
                / "frontend" / "src" / "lib" / "ecosystem" / "types.ts")
    if not types_ts.exists():                       # frontend not checked out
        pytest.skip("frontend/src/lib/ecosystem/types.ts not present")
    src = types_ts.read_text()

    def union(name: str) -> set[str]:
        block = re.search(rf"export type {name} =(.+?);", src, re.S)
        assert block, f"{name} not found in types.ts"
        return set(re.findall(r'"([a-z_]+)"', block.group(1)))

    assert union("ProjectPhase") == set(store.PHASES)
    assert union("ProjectStatus") == set(store.STATUSES)

    legacy_block = re.search(r"const LEGACY_LIFECYCLE[^{]*\{(.+?)\n\};", src, re.S)
    assert legacy_block, "LEGACY_LIFECYCLE not found in types.ts"
    ts_legacy = {
        m.group(1): (m.group(2), m.group(3))
        for m in re.finditer(r'(\w+):\s*\{\s*phase:\s*"(\w+)",\s*status:\s*"(\w+)"\s*\}',
                             legacy_block.group(1))
    }
    assert ts_legacy == store._LEGACY_LIFECYCLE
