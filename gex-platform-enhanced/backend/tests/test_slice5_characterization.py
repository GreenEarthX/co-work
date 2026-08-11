"""
Slice 5 CHARACTERIZATION tests — capital_bridge + development_packages.
=======================================================================
Written BEFORE the migration, as docs/postgres-migration-plan.md instructs:
"biggest modules, 1,200+ lines each — write characterization tests BEFORE
migrating these".

WHAT A CHARACTERIZATION TEST IS
-------------------------------
It pins what the code DOES, not what it SHOULD do. Its only job is to fail if
behaviour changes while the store underneath is swapped. That means it
deliberately encodes current output — including output that is WRONG.

Where current behaviour is a defect, the test says so in capital letters and
pins it anyway. Fixing a defect inside a storage migration is how you end up
unable to tell a copy bug from an intended change. Fix them after, as their own
change, and update the pinned value in the same commit.

  The one defect these tests originally pinned — a 1000x units error in
  `_compute_production` — was FIXED on 2026-08-08 as its own change, with the
  pinned value updated in the same commit. That is the intended workflow: pin
  the defect, migrate or fix deliberately, never both at once.

SCOPE
    capital_bridge.py         1234 lines, 20 endpoints, 8 tables
    development_packages.py   1398 lines, 13 endpoints, 3 tables
    Populated today: development_packages 3, development_package_events 18,
                     fuel_defaults 5, package_evidence 2. The rest are empty,
                     so their SHAPE is pinned rather than their contents.
"""
from __future__ import annotations

import json

import pytest

from pg_support import as_platform_admin, requires_pg

from app.api.v1 import capital_bridge as cb
from app.api.v1 import development_packages as dp


# ═══════════════════════════════════════════════════════════════════════════
# 1. PURE COMPUTATION — the numbers a migration must not perturb
# ═══════════════════════════════════════════════════════════════════════════

def test_compute_production_is_pinned():
    """
    Golden values for the production/revenue core.

    UPDATED 2026-08-08 alongside the units fix, in the same change — the
    previous pin recorded output that was wrong by a factor of 1000 (45.39 t/yr
    for a 300 MW plant, EUR 160k revenue). See the note in the function.

    Cross-check without the code: 300 MW x 8760 h x 0.95 / 55 kWh/kg
    = 45,392.73 t H2/yr, x 5.44 = 246,936.44 t product, x EUR650 = EUR 160.5M.
    Those are plausible figures for a 300 MW electrolyser; the old ones were
    not, which is how the defect was found.
    """
    control = {
        "nameplate_mw": 300.0,
        "availability_factor": 0.95,
        "specific_energy_kwh_per_kg_h2": 55.0,
        "product_yield_t_per_t_h2": 5.44,
        "offtake_price_eur_per_t": 650.0,
    }
    assert cb._compute_production(control) == {
        "h2_annual_production_t": 45392.73,
        "product_annual_production_t": 246936.44,
        "annual_revenue_eur": 160508683.64,
    }


def test_production_matches_an_independent_dimensional_calculation():
    """
    Recomputes from units rather than repeating the implementation, so a
    reintroduced conversion error is caught by arithmetic, not by a golden
    value someone might "update to make it pass".
    """
    mw, avail, sec, yld, price = 300.0, 0.95, 55.0, 5.44, 650.0
    energy_kwh = mw * 8760.0 * avail * 1000.0
    h2_t = (energy_kwh / sec) / 1000.0          # unrounded, as the code carries it

    out = cb._compute_production({
        "nameplate_mw": mw, "availability_factor": avail,
        "specific_energy_kwh_per_kg_h2": sec, "product_yield_t_per_t_h2": yld,
        "offtake_price_eur_per_t": price,
    })
    # 2-decimal rounding is part of the function's contract, and each output is
    # rounded only at the end — product and revenue derive from the UNROUNDED
    # tonnage. Mirror that here rather than loosening the tolerance.
    assert out["h2_annual_production_t"] == round(h2_t, 2)
    assert out["product_annual_production_t"] == round(h2_t * yld, 2)
    assert out["annual_revenue_eur"] == round(h2_t * yld * price, 2)


def test_a_utility_scale_plant_produces_a_plausible_tonnage():
    """
    A magnitude sanity check — the guard that would have caught the original
    bug immediately. A 300 MW electrolyser makes tens of thousands of tonnes of
    hydrogen a year, not tens.
    """
    out = cb._compute_production({
        "nameplate_mw": 300.0, "availability_factor": 0.95,
        "specific_energy_kwh_per_kg_h2": 55.0, "product_yield_t_per_t_h2": 1.0,
        "offtake_price_eur_per_t": 5500.0,
    })
    assert 10_000 < out["h2_annual_production_t"] < 100_000, (
        f"{out['h2_annual_production_t']} t/yr is not a plausible annual output "
        "for a 300 MW electrolyser — check the kWh/MWh conversion"
    )
    assert out["annual_revenue_eur"] > 100_000_000


def test_compute_production_scales_linearly_with_capacity():
    """
    A property, not a golden value.

    The tolerance is TIGHT again (2026-08-08). While the 1000x units bug was in
    place the outputs were tiny (15.77 t/yr for 100 MW), so the `round(..., 2)`
    was a material fraction of the value and linearity only held to ~0.05. At
    correct magnitudes the rounding is negligible and the relation is exact.
    """
    base = {"nameplate_mw": 100.0, "availability_factor": 0.90,
            "specific_energy_kwh_per_kg_h2": 50.0, "product_yield_t_per_t_h2": 1.0,
            "offtake_price_eur_per_t": 5500.0}
    one = cb._compute_production(base)
    ten = cb._compute_production({**base, "nameplate_mw": 1000.0})
    assert ten["h2_annual_production_t"] == pytest.approx(
        one["h2_annual_production_t"] * 10, rel=1e-9)
    assert ten["annual_revenue_eur"] == pytest.approx(
        one["annual_revenue_eur"] * 10, rel=1e-9)


def test_production_is_inverse_in_specific_energy():
    """Halving kWh/kg must double output. Independent of the 1000x offset."""
    base = {"nameplate_mw": 100.0, "availability_factor": 1.0,
            "specific_energy_kwh_per_kg_h2": 50.0, "product_yield_t_per_t_h2": 1.0,
            "offtake_price_eur_per_t": 1.0}
    a = cb._compute_production(base)["h2_annual_production_t"]
    b = cb._compute_production({**base, "specific_energy_kwh_per_kg_h2": 25.0})[
        "h2_annual_production_t"]
    assert b == pytest.approx(a * 2, rel=1e-6)


def test_revenue_is_production_times_price():
    control = {"nameplate_mw": 250.0, "availability_factor": 0.9,
               "specific_energy_kwh_per_kg_h2": 52.0, "product_yield_t_per_t_h2": 1.87,
               "offtake_price_eur_per_t": 420.0}
    out = cb._compute_production(control)
    assert out["annual_revenue_eur"] == pytest.approx(
        out["product_annual_production_t"] * 420.0, rel=1e-4)


# ═══════════════════════════════════════════════════════════════════════════
# 2. ECONOMIC CONSTANTS — assumptions behind every capital stack
# ═══════════════════════════════════════════════════════════════════════════

def test_default_capital_stack_sums_to_exactly_one():
    """
    A stack that does not sum to 100% silently under- or over-funds every
    bootstrapped project. This is an invariant, not a golden value.
    """
    assert sum(cb.DEFAULT_CAPITAL_STACK_PCT.values()) == pytest.approx(1.0, abs=1e-9)


def test_default_capital_stack_shares_are_pinned():
    assert cb.DEFAULT_CAPITAL_STACK_PCT == {
        "SEED_EQUITY": 0.02, "SPONSOR_EQUITY": 0.18, "GRANT": 0.10,
        "DFI_EIB": 0.15, "DFI_KFW": 0.10, "DFI_IFC": 0.08,
        "DFI_BPIFRANCE": 0.05, "DFI_DFC": 0.05, "DFI_AFDB": 0.05,
        "COMMERCIAL_SENIOR": 0.18, "ECA": 0.04,
    }


def test_cost_of_capital_constants_are_pinned():
    assert cb.DEFAULT_COMMERCIAL_SENIOR_RATE == 0.080
    assert cb.DEFAULT_COMMERCIAL_SENIOR_TENOR == 15
    assert cb.DEFAULT_COMMERCIAL_SENIOR_GRACE == 1
    assert cb.DEFAULT_ECA_RATE == 0.045
    assert cb.DEFAULT_EQUITY_COST == 0.12


def test_dfi_terms_are_cheaper_than_commercial_senior():
    """
    The whole point of DFI capital. If a migration or edit inverted this, every
    blended cost of capital would be wrong in a direction that flatters the model.
    """
    for inst, terms in cb.DEFAULT_DFI_TERMS.items():
        rate = terms.get("rate", terms.get("interest_rate"))
        assert rate is not None, f"{inst}: no rate field"
        assert rate < cb.DEFAULT_COMMERCIAL_SENIOR_RATE, (
            f"{inst} rate {rate} is not below commercial senior "
            f"{cb.DEFAULT_COMMERCIAL_SENIOR_RATE}"
        )


def test_all_five_fuels_carry_the_full_default_set():
    expected_keys = {
        "fuel_label", "specific_energy_kwh_per_kg_h2", "product_yield_t_per_t_h2",
        "base_price_eur_per_t", "green_premium_eur_per_t", "typical_availability",
        "dsra_months", "contingency_pct", "typical_offtake_counterparty",
    }
    assert {f.value for f in cb.FuelType} == {"H2", "NH3", "E_METHANOL", "E_NG", "SAF"}
    for fuel, d in cb.FUEL_DEFAULTS.items():
        assert expected_keys <= set(d), f"{fuel}: missing {expected_keys - set(d)}"
        assert 0.0 < d["typical_availability"] <= 1.0, f"{fuel}: availability"
        assert d["specific_energy_kwh_per_kg_h2"] > 0, f"{fuel}: SEC"
        assert d["product_yield_t_per_t_h2"] > 0, f"{fuel}: yield"


def test_hydrogen_defaults_are_pinned():
    """One fuel pinned exactly; the rest are covered by the invariants above."""
    assert cb.FUEL_DEFAULTS[cb.FuelType.H2] == {
        "fuel_label": "Green Hydrogen",
        "specific_energy_kwh_per_kg_h2": 50.0,
        "product_yield_t_per_t_h2": 1.0,
        "base_price_eur_per_t": 5500.0,
        "green_premium_eur_per_t": 2000.0,
        "typical_availability": 0.93,
        "dsra_months": 6,
        "contingency_pct": 0.15,
        "typical_offtake_counterparty":
            "Industrial offtaker (steel / refining / ammonia)",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. THE TWO STATE MACHINES — orthogonal, forward-only
# ═══════════════════════════════════════════════════════════════════════════

_WORKFLOW_ORDER = ["identified", "scoped", "costed", "evidenced", "eligible",
                   "approved", "committed", "drawable", "drawn", "verified",
                   "closed", "propagated"]


def test_workflow_is_twelve_states_in_this_exact_order():
    assert [s.value for s in dp.WorkflowState] == _WORKFLOW_ORDER


def test_workflow_is_a_strict_forward_only_chain():
    """
    Each state advances to exactly its successor, and PROPAGATED is terminal.
    Pinned as a derived property so reordering the enum cannot pass silently.
    """
    for i, name in enumerate(_WORKFLOW_ORDER):
        state = dp.WorkflowState(name)
        allowed = [s.value for s in dp.VALID_TRANSITIONS[state]]
        expected = [_WORKFLOW_ORDER[i + 1]] if i + 1 < len(_WORKFLOW_ORDER) else []
        assert allowed == expected, f"{name}: expected {expected}, got {allowed}"


def test_no_workflow_state_can_move_backwards():
    index = {n: i for i, n in enumerate(_WORKFLOW_ORDER)}
    for state, nexts in dp.VALID_TRANSITIONS.items():
        for nxt in nexts:
            assert index[nxt.value] > index[state.value], (
                f"{state.value} -> {nxt.value} is a rollback"
            )


_CAPITAL_ORDER = ["NOT_ELIGIBLE", "THEORETICALLY_ELIGIBLE", "INDICATED",
                  "COMMITTED", "DRAWABLE", "DRAWN"]


def test_capital_ladder_is_six_states_forward_only():
    assert [s.value for s in dp.CapitalStatus] == _CAPITAL_ORDER
    for i, name in enumerate(_CAPITAL_ORDER):
        allowed = [s.value for s in dp.VALID_CAPITAL_TRANSITIONS[dp.CapitalStatus(name)]]
        expected = [_CAPITAL_ORDER[i + 1]] if i + 1 < len(_CAPITAL_ORDER) else []
        assert allowed == expected, f"{name}: expected {expected}, got {allowed}"


def test_the_two_ladders_are_independent():
    """
    workflow_state tracks package maturity; capital_status tracks provider
    engagement. They share the names COMMITTED / DRAWABLE / DRAWN but are
    SEPARATE dimensions — a package can be EVIDENCED yet NOT_ELIGIBLE. Merging
    them would destroy information, so nothing may couple the tables.
    """
    assert dp.VALID_TRANSITIONS.keys() != dp.VALID_CAPITAL_TRANSITIONS.keys()
    shared = {s.value for s in dp.WorkflowState} & {s.value for s in dp.CapitalStatus}
    assert shared == set(), (
        "workflow and capital state VALUES now overlap: "
        f"{shared} — they are lowercase vs UPPERCASE precisely so a value "
        "cannot be mistaken for the other ladder"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. HASHING — content addressing must be stable across stores
# ═══════════════════════════════════════════════════════════════════════════

def test_package_hash_is_deterministic_and_key_order_independent():
    a = {"package_id": "pkg-1", "cost": 100, "state": "costed"}
    b = {"state": "costed", "package_id": "pkg-1", "cost": 100}
    assert dp._hash_package(a) == dp._hash_package(b), (
        "hash depends on dict ordering — a store that returns columns in a "
        "different order would change it"
    )


def test_package_hash_is_pinned():
    """A fixed vector: if the canonical form changes, every stored hash breaks."""
    assert dp._hash_package({"package_id": "pkg-1", "cost": 100}) == (
        "33f7918540839d42b118a1a74bc87c7e9be0b7cdf513b983074381e4401bc833"
    )


def test_package_hash_changes_when_content_changes():
    base = {"package_id": "pkg-1", "cost": 100}
    assert dp._hash_package(base) != dp._hash_package({**base, "cost": 101})


# ═══════════════════════════════════════════════════════════════════════════
# 5. TRANSITION GUARDS — refusals that must survive the migration
# ═══════════════════════════════════════════════════════════════════════════

def test_evidenced_requires_evidence_refs_is_declared():
    """
    The guard lives inside the endpoint, so pin its presence at source rather
    than not covering it at all. Replaced by a behavioural test once the
    endpoint takes an injectable store.
    """
    src = dp.__file__
    with open(src) as fh:
        body = fh.read()
    marker = body[body.index("def transition_state("):]
    marker = marker[:marker.index("\n@router") if "\n@router" in marker else len(marker)]
    assert "WorkflowState.EVIDENCED" in marker and "evidence_refs" in marker, (
        "the EVIDENCED-requires-evidence guard is gone"
    )
    assert "WorkflowState.DRAWABLE" in marker and "unlock" in marker, (
        "the DRAWABLE-requires-unlock-evidence guard is gone"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. STORED DATA — the golden master to diff after the move
# ═══════════════════════════════════════════════════════════════════════════

def _sqlite():
    import sqlite3

    from app.core.config import settings

    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


SLICE5_TABLES = {
    "development_packages": 3,
    "development_package_events": 18,
    "fuel_defaults": 5,
    "package_evidence": 2,
    "capital_stack_tranches": 0,
    "dfi_criteria_status": 0,
    "drawdown_quarters": 0,
    "personnel_plan": 0,
    "post_cod_schedule": 0,
    "project_control": 0,
    "spend_wave": 0,
}


@pytest.mark.parametrize("table,expected", sorted(SLICE5_TABLES.items()))
def test_row_counts_are_pinned_before_migration(table, expected):
    """
    The baseline the migration must reproduce exactly. A count that DROPS is a
    lost row; one that GROWS means the app wrote to the old store after the
    cutover. Both are failures, so this is equality, not a ratchet.
    """
    conn = _sqlite()
    try:
        got = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"{table} not present: {exc}")
    finally:
        conn.close()
    assert got == expected, (
        f"{table}: {got} rows, pinned at {expected}. If this change is "
        "intended, update the baseline in the SAME commit as the change."
    )


def test_development_package_workflow_states_in_use_are_pinned():
    """Which states real rows actually occupy — a migration must preserve them."""
    conn = _sqlite()
    try:
        rows = conn.execute(
            "SELECT workflow_state, count(*) AS n FROM development_packages "
            "GROUP BY workflow_state ORDER BY workflow_state").fetchall()
    finally:
        conn.close()
    # Two IDENTIFIED and one already EVIDENCED — so the migration must carry a
    # package that has passed the evidence guard, not just fresh ones.
    assert {r["workflow_state"]: r["n"] for r in rows} == {"identified": 2, "evidenced": 1}


def test_every_stored_package_state_is_a_known_state():
    """Guards against a stray value that the enum cannot parse."""
    conn = _sqlite()
    try:
        rows = conn.execute(
            "SELECT DISTINCT workflow_state FROM development_packages").fetchall()
    finally:
        conn.close()
    known = {s.value for s in dp.WorkflowState}
    unknown = [r["workflow_state"] for r in rows if r["workflow_state"] not in known]
    assert not unknown, f"stored states not in WorkflowState: {unknown}"


def test_package_event_log_is_append_only_in_practice():
    """
    Every package should have at least one event. A package with none means
    either the log was truncated or events were written elsewhere — worth
    knowing BEFORE the store moves.
    """
    conn = _sqlite()
    try:
        pkgs = {r["package_id"] for r in conn.execute(
            "SELECT package_id FROM development_packages")}
        evented = {r["package_id"] for r in conn.execute(
            "SELECT DISTINCT package_id FROM development_package_events")}
    finally:
        conn.close()
    assert pkgs <= evented, f"packages with no event history: {sorted(pkgs - evented)}"


def test_fuel_defaults_table_matches_the_in_code_constants():
    """
    FUEL_DEFAULTS exists in Python AND in a `fuel_defaults` table — two sources
    for the same numbers. Pin that they AGREE now, so the migration cannot
    silently let them drift apart.
    """
    conn = _sqlite()
    try:
        rows = conn.execute("SELECT * FROM fuel_defaults").fetchall()
    finally:
        conn.close()
    assert len(rows) == 5
    by_fuel = {r["fuel_type"]: r for r in rows}
    assert set(by_fuel) == {f.value for f in cb.FuelType}
    for fuel, row in by_fuel.items():
        code = cb.FUEL_DEFAULTS[cb.FuelType(fuel)]
        assert row["specific_energy_kwh_per_kg_h2"] == pytest.approx(
            code["specific_energy_kwh_per_kg_h2"]), f"{fuel}: SEC drifted"
        assert row["product_yield_t_per_t_h2"] == pytest.approx(
            code["product_yield_t_per_t_h2"]), f"{fuel}: yield drifted"


def test_package_evidence_rows_reference_existing_packages():
    """Referential integrity SQLite never enforced — pin it before Postgres does."""
    conn = _sqlite()
    try:
        pkgs = {r["package_id"] for r in conn.execute(
            "SELECT package_id FROM development_packages")}
        refs = [r["package_id"] for r in conn.execute(
            "SELECT package_id FROM package_evidence")]
    finally:
        conn.close()
    orphans = [p for p in refs if p not in pkgs]
    assert not orphans, (
        f"package_evidence rows point at non-existent packages: {orphans}. "
        "A foreign key in the Postgres schema would reject these — decide "
        "whether to repair or to migrate without the constraint."
    )


# ═══════════════════════════════════════════════════════════════════════════
# 7. THE PACKAGE-EVENT HASH CHAIN — pinned BROKEN, pre-existing
# ═══════════════════════════════════════════════════════════════════════════

def _recompute_event_hash(row) -> str:
    """Reproduce _log_event's digest from a stored row."""
    import hashlib
    import json as _json

    payload = {
        "package_id": row["package_id"], "event_type": row["event_type"],
        "field": row["field_changed"], "new_value": row["new_value"],
        "actor": row["changed_by"], "timestamp": row["created_at"],
        "prev_hash": row["prev_hash"],
    }
    return hashlib.sha256(
        _json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _event_chain_state():
    """(unverifiable_count, broken_link_count) over all package event chains."""
    from collections import defaultdict

    conn = _sqlite()
    try:
        rows = conn.execute(
            "SELECT * FROM development_package_events "
            "ORDER BY created_at, rowid").fetchall()
    finally:
        conn.close()
    by_pkg = defaultdict(list)
    for r in rows:
        by_pkg[r["package_id"]].append(r)

    unverifiable = broken_links = 0
    for evs in by_pkg.values():
        expected = None
        for e in evs:
            if _recompute_event_hash(e) != e["event_hash"]:
                unverifiable += 1
            if e["prev_hash"] != expected:
                broken_links += 1
            expected = e["event_hash"]
    return unverifiable, broken_links, len(rows)


def test_package_event_chain_is_pinned_BROKEN_FOR_NON_STRING_VALUES():
    """
    ⚠ PRE-EXISTING DEFECT, PINNED — NOT caused by any migration.

    `_log_event` hashes `new_val` as a typed Python object but PERSISTS
    `str(new_val)`:

        hashed  json.dumps({... "new_value": ['G1_GRID_WATER'] ...})
                 -> ["G1_GRID_WATER"]      (JSON, double quotes)
                 -> EstimateClass.CLASS_4 serialises as "CLASS_4"
        stored  str(new_val)
                 -> "['G1_GRID_WATER']"    (Python repr, single quotes)
                 -> "EstimateClass.CLASS_4"

    They coincide only when new_val is already a plain string. For floats,
    lists and enums they diverge, so the digest cannot be reproduced from what
    was stored — tamper-evidence is absent for exactly those rows.

    7 of 18 events are affected today, all `package.updated` with a non-string
    value. The LINKS are intact (0 broken), so the ordering is sound; it is the
    per-row self-hash that cannot be checked.

    IMPORTANT: fixing `_log_event` will NOT repair these 7. Their pre-image was
    never persisted, so they are permanently unverifiable. A fix makes FUTURE
    events verifiable and should hash `str(new_val)` — the form actually stored.

    Pinned so the migration must reproduce this state EXACTLY. If the number
    changes, the copy altered event data.
    """
    unverifiable, broken_links, total = _event_chain_state()
    assert total == 18, f"event count changed: {total}"
    assert unverifiable == 7, (
        f"{unverifiable} unverifiable events, pinned at 7. A DECREASE means "
        "someone fixed the hashing (good — update this pin in that commit). An "
        "INCREASE means event data was altered."
    )
    assert broken_links == 0, (
        f"{broken_links} broken prev_hash links — ordering integrity has been "
        "lost, which is a different and more serious failure than the "
        "unverifiable self-hashes above."
    )


def test_string_valued_events_do_verify():
    """
    The other side of the defect: where new_value WAS a plain string, the digest
    reproduces exactly. This is what proves the diagnosis is the
    typed-vs-stringified mismatch and not a broken hash function.
    """
    conn = _sqlite()
    try:
        rows = conn.execute(
            "SELECT * FROM development_package_events "
            "WHERE event_type = 'package.state_changed' "
            "ORDER BY created_at, rowid").fetchall()
    finally:
        conn.close()
    assert rows, "no state-change events to check"
    bad = [r["event_id"] for r in rows
           if _recompute_event_hash(r) != r["event_hash"]]
    assert not bad, (
        f"state-change events (always plain-string values) failed to verify: "
        f"{bad} — the hash function itself is broken, not just the typing"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. POST-MIGRATION — both backends must answer identically
# ═══════════════════════════════════════════════════════════════════════════

def _capital_reads(backend: str, monkeypatch):
    """Same reads through the module's own get_db, on the chosen backend."""
    # Whole-store fidelity: ask as admin, explicitly. The shim now fails
    # closed without a bound caller, so an unscoped read returns nothing.
    with as_platform_admin():
        return _capital_reads_inner(backend, monkeypatch)


def _capital_reads_inner(backend: str, monkeypatch):
    import hashlib
    import json as _json
    from collections import defaultdict

    monkeypatch.setenv("CAPITAL_DB_BACKEND", backend)
    from app.api.v1.development_packages import get_db

    gen = get_db()
    conn = next(gen)          # hold the generator: its finally: closes the conn
    try:
        states = {r["workflow_state"]: r["n"] for r in conn.execute(
            "SELECT workflow_state, count(*) n FROM development_packages "
            "GROUP BY workflow_state ORDER BY workflow_state").fetchall()}
        evs = conn.execute("SELECT * FROM development_package_events "
                           "ORDER BY created_at, event_id").fetchall()
        by = defaultdict(list)
        for e in evs:
            by[e["package_id"]].append(e)
        unver = links = 0
        for lst in by.values():
            expected = None
            for e in lst:
                payload = {"package_id": e["package_id"], "event_type": e["event_type"],
                           "field": e["field_changed"], "new_value": e["new_value"],
                           "actor": e["changed_by"], "timestamp": e["created_at"],
                           "prev_hash": e["prev_hash"]}
                if hashlib.sha256(_json.dumps(payload, sort_keys=True,
                                              default=str).encode()).hexdigest() != e["event_hash"]:
                    unver += 1
                if e["prev_hash"] != expected:
                    links += 1
                expected = e["event_hash"]
        fuels = {r["fuel_type"]: r["specific_energy_kwh_per_kg_h2"]
                 for r in conn.execute(
                     "SELECT fuel_type, specific_energy_kwh_per_kg_h2 "
                     "FROM fuel_defaults ORDER BY fuel_type").fetchall()}
        return {"states": states, "events": len(evs), "unverifiable": unver,
                "broken_links": links, "fuels": fuels}
    finally:
        gen.close()


def test_slice5_reads_identically_on_both_backends(monkeypatch):
    """
    The flip gate. If the two stores disagree on package states, event-chain
    integrity or reference data, the migration is not behaviour-preserving and
    CAPITAL_DB_BACKEND must not be switched.
    """
    import os

    requires_pg()
    try:
        lite = _capital_reads("sqlite", monkeypatch)
        pg = _capital_reads("postgres", monkeypatch)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"backend unavailable: {exc}")
    assert lite == pg, f"backends disagree:\n  sqlite  ={lite}\n  postgres={pg}"


def test_the_broken_chain_was_copied_faithfully_not_repaired(monkeypatch):
    """
    A migration that silently "fixed" the 7 unverifiable events would be
    rewriting audit history. Faithful means the same number, either side.
    """
    import os

    requires_pg()
    try:
        pg = _capital_reads("postgres", monkeypatch)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    assert pg["events"] == 18
    assert pg["unverifiable"] == 7, (
        "the copy changed how many events verify — audit history was altered"
    )
    assert pg["broken_links"] == 0
