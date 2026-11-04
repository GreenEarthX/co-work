"""GEX's equipment-train assumptions are governed (migration 075) — point 5.

The last hole in "all TEA variables in PostgreSQL, editable, four-eye". 39 specs across
E_METHANOL (12), E_SAF (13) and BIO_SAF_HEFA (14): what size each unit is at the
50,000 t/yr reference and the exponent used to scale it. They move every capex directly
and were changeable with nobody's approval and no record.

NOT in reference_parameter, deliberately: that table fixes one unit family per
parameter_key, and `base_param` carries eight different units across these rows —
measured area m^2 (9), volume m^3 (7), driver power kW (6), shell mass kg (6), shaft
power kW (3), capacity m^3 (3), flow L/s (3), electric power MWe (2). The unit belongs
to the OpenPyTEA correlation, so it has to live per row.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tea_engine.process_functions as pfx            # noqa: E402
from tea_engine.compute import run_tea                # noqa: E402
from tea_engine.models import TEAComputeRequest       # noqa: E402

_CAPEX = 175_255_929.06


def _req(**over):
    base = dict(project_id="t5", pathway_id="t", fuel_id="E_METHANOL",
                nameplate_capacity=50000.0, nameplate_unit="t_per_year")
    base.update(over)
    return TEAComputeRequest(**base)


def _code_train(fuel="E_METHANOL"):
    return [{"role": e.role, "node": e.node, "category": e.category,
             "equipment_type": e.type, "material": e.material,
             "base_param": e.base_param, "scale_exp": e.scale_exp}
            for e in pfx.REGISTRY[fuel].equipment]


def test_a_governed_train_equal_to_the_code_values_reproduces_the_number_exactly():
    """If the governed path did not reproduce the code path, adopting it would silently
    restate every basis — so this is the precondition for the whole increment."""
    a = run_tea(_req())
    b = run_tea(_req(governed_train=_code_train(), governed_train_version="v1"))
    assert a.plant_summary.capex_eur == b.plant_summary.capex_eur == _CAPEX
    assert a.process_function["train_basis"] == "canonical_code"
    assert b.process_function["train_basis"] == "governed"
    assert b.process_function["governed_train_version"] == "v1"


def test_changing_one_governed_base_param_reprices_and_rehashes():
    base = run_tea(_req(governed_train=_code_train(), governed_train_version="v1"))
    train = _code_train()
    train[0]["base_param"] = train[0]["base_param"] * 2
    changed = run_tea(_req(governed_train=train, governed_train_version="v2"))
    assert changed.plant_summary.capex_eur > base.plant_summary.capex_eur
    assert changed.cost_basis_hash != base.cost_basis_hash, (
        "an approved change to a base_param must reprice VISIBLY")


def test_changing_only_the_scale_exponent_also_reprices():
    """scale_exp only bites away from the reference nameplate, so test off-reference."""
    off = dict(nameplate_capacity=150_000.0, nameplate_unit="t_per_year")
    train = _code_train()
    a = run_tea(_req(**off, governed_train=train, governed_train_version="v1"))
    train2 = [dict(x) for x in train]
    for x in train2:
        x["scale_exp"] = 0.80
    b = run_tea(_req(**off, governed_train=train2, governed_train_version="v2"))
    assert b.plant_summary.capex_eur != a.plant_summary.capex_eur
    assert b.cost_basis_hash != a.cost_basis_hash


def test_no_governed_train_falls_back_to_the_code_registry():
    r = run_tea(_req())
    assert r.process_function["train_basis"] == "canonical_code"
    assert r.process_function["governed_train_version"] is None
    assert r.plant_summary.capex_eur == _CAPEX, "fallback must not change the number"


def test_all_39_specs_are_seeded_approved_with_their_own_unit():
    from pg_support import pg_admin
    conn, cur = pg_admin()
    try:
        cur.execute("SELECT fuel_id, count(*) n FROM tea_equipment_spec "
                    "WHERE state='approved' GROUP BY 1 ORDER BY 1")
        per = {r["fuel_id"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT count(DISTINCT base_param_unit) u, count(*) n "
                    "FROM tea_equipment_spec WHERE state='approved'")
        spread = cur.fetchone()
    finally:
        conn.close()
    assert per == {"BIO_SAF_HEFA": 14, "E_METHANOL": 12, "E_SAF": 13}
    assert sum(per.values()) == 39
    assert spread["u"] == 8, (
        "eight distinct base_param units is why these cannot live in "
        "reference_parameter, which fixes one unit family per key")


def test_four_eye_is_enforced_by_the_database_not_only_by_code():
    """reference_parameter checks this in reference_registry.approve alone, which any
    other writer bypasses. Here the constraint makes it impossible."""
    from pg_support import pg_admin
    conn, cur = pg_admin()
    try:
        with pytest.raises(Exception) as exc:
            cur.execute("UPDATE tea_equipment_spec SET approved_by = proposed_by "
                        "WHERE state='approved' AND fuel_id='E_METHANOL'")
        assert "four_eyes" in str(exc.value) or "CheckViolation" in type(exc.value).__name__
    finally:
        conn.rollback()
        conn.close()


def test_only_one_spec_per_fuel_and_role_may_be_approved():
    """Two approved rows for one (fuel, role) would silently double a unit in the train."""
    from pg_support import pg_admin
    conn, cur = pg_admin()
    try:
        with pytest.raises(Exception) as exc:
            cur.execute(
                "INSERT INTO tea_equipment_spec (spec_id, fuel_id, role, node, category,"
                " equipment_type, material, base_param, scale_exp,"
                " reference_nameplate_t_per_year, state, proposed_by, proposed_at,"
                " approved_by, approved_at) "
                "SELECT gen_random_uuid()::text, fuel_id, role, node, category,"
                " equipment_type, material, base_param, scale_exp,"
                " reference_nameplate_t_per_year, 'approved', 'a', now()::text,"
                " 'b', now()::text FROM tea_equipment_spec "
                "WHERE state='approved' LIMIT 1")
        assert "uq_tes_fuel_role_approved" in str(exc.value) or "UniqueViolation" in type(exc.value).__name__
    finally:
        conn.rollback()
        conn.close()


def test_the_bridge_resolves_the_approved_train_and_versions_the_set():
    import app.api.v1.routes_tea as rt
    g = rt._tea_governed_train("E_METHANOL")
    assert len(g["governed_train"]) == 12
    assert g["governed_train_version"].startswith("sha256:")
    assert rt._tea_governed_train("NO_SUCH_FUEL") == {}, (
        "an unknown molecule must not fabricate a train")
    # the version is a content hash: the same set must version identically
    assert rt._tea_governed_train("E_METHANOL")["governed_train_version"] == \
        g["governed_train_version"]
