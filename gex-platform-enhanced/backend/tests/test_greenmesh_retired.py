"""
GreenMesh Phase 1, Step 1 (G-12, JML 2026-11-12): one name, one meaning.

GreenMesh is kept only as the future physical-delivery and clearing extension of the market
engine and the chain-of-custody ledger. The separate engine is retired:

  * the stub router `api/v1/greenmesh.py` (imported, never mounted, every handler TODO),
  * `core/greenmesh_engine.py` (called by nothing; its certification premiums now live in
    the reference registry as INDICATIVE `proposed` rows),
  * `core/greenmesh_bankable.py` (moved to docs/design as the Phase 2 reference, not wired).

These tests keep them retired and pin the port of the premiums. The PostgreSQL test runs in
a transaction that is always rolled back.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
SCRIPT = BACKEND / "scripts" / "load_certification_premiums_20261112.py"
DATA = BACKEND / "scripts" / "data" / "certification_premiums_20261112.json"

PREMIUM_KEYS = {"certification_premium_rfnbo", "certification_premium_red_iii",
                "certification_premium_45v", "certification_premium_certifhy",
                "certification_premium_corsia"}


def _loader():
    import importlib.util

    spec = importlib.util.spec_from_file_location("load_certification_premiums", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── the retired modules stay retired ──────────────────────────────────────────

@pytest.mark.parametrize("rel", ["api/v1/greenmesh.py", "core/greenmesh_engine.py",
                                 "core/greenmesh_bankable.py"])
def test_the_retired_greenmesh_module_is_gone(rel):
    assert not (APP / rel).exists(), f"app/{rel} was retired on 2026-11-12 (G-12)"


def test_no_module_imports_anything_named_greenmesh():
    offenders = []
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            if any("greenmesh" in n.lower() for n in names):
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert not offenders, offenders


def test_the_app_mounts_no_greenmesh_route():
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if "greenmesh" in p.lower()]


# ── the premiums: ported, labelled, and not in force ──────────────────────────

def test_each_regime_has_its_own_mass_priced_key_marked_indicative():
    from app.core.reference_catalog import PARAMETERS

    for key in PREMIUM_KEYS:
        assert PARAMETERS[key].family == "COST_PER_MASS", key
        assert PARAMETERS[key].description.startswith("INDICATIVE"), key


def test_the_proposals_carry_the_cited_sources_and_say_indicative():
    from app.core import reference_registry as reg

    loader = _loader()
    rows = loader.proposals(json.loads(DATA.read_text()))
    assert len(rows) == 13
    assert {r["parameter_key"] for r in rows} == PREMIUM_KEYS
    for r in rows:
        reg.validate_proposal(r)                      # the closed catalog accepts every row
        assert r["unit"] == "EUR/t" and r["currency"] == "EUR"
        assert r["source_class"] == "gex_assumption"  # a citation nobody has checked
        assert "BNEF" in r["source_name"] and "ICIS" in r["source_name"]
        assert r["note"].startswith("INDICATIVE")
    v45 = [r for r in rows if r["parameter_key"] == "certification_premium_45v"]
    assert [(r["pathway"], r["region"]) for r in v45] == [("H2", "US")]
    assert "subsidy_45v_max" in v45[0]["note"]


class _Tx:
    """The slice of the shim's connection the registry uses, over a test connection
    whose transaction is always rolled back (as in test_reference_registry_pg)."""

    def __init__(self, company: str) -> None:
        import psycopg2.extras
        from pg_support import pg_connect

        self._conn = pg_connect()
        self._factory = psycopg2.extras.RealDictCursor
        cur = self._conn.cursor()
        cur.execute("SELECT to_regclass('public.reference_parameter')")
        if cur.fetchone()[0] is None:
            self._conn.close()
            pytest.skip("migration 061 not applied")
        cur.execute("SET LOCAL ROLE gex_app")
        cur.execute("SET LOCAL app.current_company_id = %s", (company,))

    def execute(self, sql, params=()):
        from app.core.db_backend import _PgCursor, _to_pg

        cur = self._conn.cursor(cursor_factory=self._factory)
        cur.execute(_to_pg(sql), tuple(params))
        return _PgCursor(cur)

    def close(self) -> None:
        self._conn.rollback()
        self._conn.close()


@pytest.fixture
def admin():
    tx = _Tx("PLATFORM_ADMIN")
    yield tx
    tx.close()


def test_loading_proposes_thirteen_rows_once_and_puts_none_in_force(admin):
    from app.core import reference_registry as reg

    loader = _loader()
    data = json.loads(DATA.read_text())
    already = admin.execute("SELECT count(*) AS n FROM reference_parameter WHERE proposed_by = ?",
                            (loader.PROPOSER,)).fetchone()["n"]
    first = loader.load(admin, data)
    assert first == (13 - already, already)
    assert loader.load(admin, data) == (0, 13)        # idempotent

    rows = admin.execute("SELECT * FROM reference_parameter WHERE proposed_by = ?",
                         (loader.PROPOSER,)).fetchall()
    assert len(rows) == 13
    assert {r["state"] for r in rows} == {"proposed"}
    for r in rows:
        assert reg.in_force(admin, r["parameter_key"], r["pathway"], r["region"]) is None
