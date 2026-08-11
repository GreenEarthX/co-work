"""
Slice 6b-3 guardrails — fuel reference data.
============================================
`fuel_catalog` (10) and `fuel_unit_conversions` (120): the same rows for every
tenant, keyed by fuel rather than project.

The mechanical parts are the copy and the RLS. Two things here are not
mechanical:

1. **A real foreign key.** Unlike `package_evidence` in slice 5 — where no
   constraint existed and inventing one would have made an FK rejection look
   like a copy failure — this one EXISTS in SQLite and had to be carried over,
   CASCADE and all.

2. **A naming collision that must NOT be "reconciled".** Two fields both read
   as "specific energy" and hold different physics. Merging them would corrupt
   either every fuel's energy content or the production formula.
"""
from __future__ import annotations

import os

import pytest

from pg_support import pg_admin as _pg, pg_connect, requires_pg




# ── The naming collision ────────────────────────────────────────────────────

def test_the_two_specific_energy_fields_are_different_quantities():
    """
    ⚠ DO NOT "reconcile" these. They are not two sources for one number.

      fuel_catalog.specific_energy_value
          the FUEL's own energy density (LHV), kWh/kg. VARIES by fuel:
          H2 33.3 · NH3 5.2 · E_METHANOL 5.5 · SAF 11.9 — physically correct.

      FUEL_DEFAULTS[...]["specific_energy_kwh_per_kg_h2"]
          the ELECTROLYSER's electricity consumption per kg of H2 produced.
          CONSTANT at 50.0 across all fuels, because it is a property of the
          electrolyser, not of the downstream product.

    Merging them would corrupt either the energy content of every fuel or the
    production formula corrected on 2026-08-08.
    """
    from app.api.v1.capital_bridge import FUEL_DEFAULTS

    sec = {f.value: d["specific_energy_kwh_per_kg_h2"] for f, d in FUEL_DEFAULTS.items()}
    assert len(set(sec.values())) == 1, (
        f"FUEL_DEFAULTS specific energy now VARIES by fuel ({sec}). It is the "
        "electrolyser's consumption and should be constant — if this became "
        "per-fuel, someone has conflated it with fuel energy density."
    )

    conn, cur = _pg()
    try:
        cur.execute("SELECT fuel_id, specific_energy_value FROM fuel_catalog "
                    "WHERE specific_energy_value IS NOT NULL")
        density = {r["fuel_id"]: r["specific_energy_value"] for r in cur.fetchall()}
    finally:
        conn.close()

    assert len(set(density.values())) > 1, (
        "fuel_catalog specific energy is now the SAME for every fuel — that is "
        "the electrolyser figure, not fuel energy density. The two fields have "
        "been conflated."
    )
    # Spot-check physics: hydrogen is by far the most energy-dense per kg.
    if "H2" in density:
        assert density["H2"] > 30, f"H2 energy density {density['H2']} kWh/kg is wrong"
        others = [v for k, v in density.items() if k != "H2"]
        assert all(v < density["H2"] for v in others), (
            "a fuel is denser per kg than hydrogen — the values are not LHV"
        )


# ── The real foreign key ────────────────────────────────────────────────────

def test_the_conversion_fk_survived_the_migration():
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT confdeltype FROM pg_constraint
            WHERE conname = 'fk_fuc_fuel' AND contype = 'f'
        """)
        row = cur.fetchone()
        assert row, "fuel_unit_conversions lost its FK to fuel_catalog"
        assert row["confdeltype"] == "c", (
            f"ON DELETE is {row['confdeltype']!r}, expected 'c' (CASCADE) — the "
            "SQLite constraint cascaded and that behaviour must be preserved"
        )
    finally:
        conn.close()


def test_the_fk_actually_rejects_an_orphan():
    """A declared constraint that does not fire is decoration."""
    conn, cur = _pg()
    try:
        with pytest.raises(Exception):
            cur.execute("""
                INSERT INTO fuel_unit_conversions
                    (fuel_id, from_unit, to_unit, multiplier, dimension,
                     created_at, updated_at)
                VALUES ('NO_SUCH_FUEL','kg','t',0.001,'mass','x','x')
            """)
        conn.rollback()
    finally:
        conn.close()


def test_duplicate_conversion_rules_are_rejected():
    """UNIQUE(fuel_id, from_unit, to_unit) — two multipliers for one conversion
    would make unit maths non-deterministic."""
    conn, cur = _pg()
    try:
        cur.execute("SELECT fuel_id, from_unit, to_unit FROM fuel_unit_conversions "
                    "LIMIT 1")
        row = cur.fetchone()
        if not row:
            pytest.skip("no conversions to duplicate")
        with pytest.raises(Exception):
            cur.execute("""
                INSERT INTO fuel_unit_conversions
                    (fuel_id, from_unit, to_unit, multiplier, dimension,
                     created_at, updated_at)
                VALUES (%s,%s,%s, 999.0, 'mass', 'x','x')
            """, (row["fuel_id"], row["from_unit"], row["to_unit"]))
        conn.rollback()
    finally:
        conn.close()


def test_no_conversion_references_a_missing_fuel():
    conn, cur = _pg()
    try:
        cur.execute("""
            SELECT count(*) AS n FROM fuel_unit_conversions c
            WHERE NOT EXISTS (SELECT 1 FROM fuel_catalog f WHERE f.fuel_id = c.fuel_id)
        """)
        assert cur.fetchone()["n"] == 0
    finally:
        conn.close()


# ── Reference data is readable by everyone, writable by nobody but admin ────

def test_reference_data_is_readable_by_any_tenant():
    """
    Deliberately NOT tenant-isolated — a conversion factor is not anyone's
    secret. Locking it down would break unit maths for every tenant.
    """
    import psycopg2

    requires_pg()
    conn = pg_connect()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id='acme_totally_unrelated'")
        cur.execute("SELECT count(*) FROM fuel_catalog")
        assert cur.fetchone()[0] == 10, "reference data is hidden from a tenant"
        cur.execute("SELECT count(*) FROM fuel_unit_conversions")
        assert cur.fetchone()[0] == 120
    finally:
        conn.rollback()
        conn.close()


def test_rls_is_enabled_so_the_openness_is_deliberate():
    """
    RLS ON with a permissive read policy, not RLS OFF. The difference is
    legibility: "deliberately public" must be distinguishable from "forgotten".
    """
    conn, cur = _pg()
    try:
        cur.execute("SELECT relname, relrowsecurity FROM pg_class "
                    "WHERE relname IN ('fuel_catalog','fuel_unit_conversions')")
        for r in cur.fetchall():
            assert r["relrowsecurity"], (
                f"{r['relname']}: RLS is OFF — indistinguishable from an oversight"
            )
        cur.execute("SELECT tablename, policyname FROM pg_policies "
                    "WHERE tablename IN ('fuel_catalog','fuel_unit_conversions')")
        by_table = {}
        for r in cur.fetchall():
            by_table.setdefault(r["tablename"], []).append(r["policyname"])
        for t in ("fuel_catalog", "fuel_unit_conversions"):
            assert any("reference_data" in p for p in by_table.get(t, [])), (
                f"{t} has no explicit reference-data policy"
            )
    finally:
        conn.close()


# ── Backends agree, and schema ownership ────────────────────────────────────

def test_both_backends_return_the_same_reference_data(monkeypatch):
    requires_pg()

    def snapshot(backend):
        monkeypatch.setenv("FUELREF_DB_BACKEND", backend)
        from app.core.fuel_catalog import _get_conn

        conn = _get_conn()
        try:
            cat = {r["fuel_id"]: r["specific_energy_value"] for r in conn.execute(
                "SELECT fuel_id, specific_energy_value FROM fuel_catalog").fetchall()}
            n = conn.execute(
                "SELECT count(*) AS n FROM fuel_unit_conversions").fetchone()["n"]
            return cat, n
        finally:
            conn.close()

    try:
        lite, pg = snapshot("sqlite"), snapshot("postgres")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend unavailable: {exc}")
    assert lite == pg, f"backends disagree:\n  sqlite={lite}\n  postgres={pg}"


def test_ensure_tables_does_not_run_sqlite_ddl_on_postgres():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "core" /
           "fuel_catalog.py").read_text()
    fn = src[src.index("def _ensure_tables("):]
    fn = fn[:fn.index("\ndef ") if "\ndef " in fn else len(fn)]
    assert "fuelref_is_postgres" in fn and "return" in fn
