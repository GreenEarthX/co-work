"""
Plant Builder energy arithmetic — the invariants that a catalogue literal broke.

The defect these guard against reached a registered route (/api/v1/plant-builder,
main.py) and every LCOH and subsidy figure it produced:

  * EQUIPMENT_CATALOG carried `annual_power_mwh` and `capacity_tonnes_year` as
    two independent literals. Their RATIO is a specific energy consumption that
    nothing stated and nothing checked. Every PEM row implied 200.00 kWh/kg
    while its own `description` said "55 kWh/kg specific energy"; SOEC implied
    132.76 against a stated "~37"; all four alkaline rows implied 204.65.
  * The alkaline rows implied 8,800 full-load hours in a year that contains
    8,760 — proof the numbers were invented rather than derived.
  * At the default EUR 45/MWh that is EUR 9.00/kg of power in LCOH instead of
    EUR 2.48: levelised cost and `subsidy_needed_total_eur_yr` overstated by
    roughly EUR 6,500 per tonne of H2.
  * The error differed by technology (PEM 200.00, ALK 204.65, SOEC 132.76), so
    the tool also ranked the technologies against each other on an artefact.
  * `capacity_factor`, `availability`, `load_factor` and `8760` appeared ZERO
    times in the engine, so 100% uptime was asserted and never priced.

A failure here means one of those is back.
"""

from __future__ import annotations

import pytest

from app.core.plant_builder import (
    EQUIPMENT_CATALOG,
    HOURS_PER_YEAR,
    CapacityFactorRequired,
    PlantConfiguration,
    get_plant_builder,
)

DERIVED = [i for i in EQUIPMENT_CATALOG if i.rated_mw > 0 and i.sec_kwh_per_kg > 0]


def _config(equipment, capacity_factor=None, power_price=45.0):
    return PlantConfiguration(
        project_id="test",
        molecule="H2",
        location_jurisdiction="FR",
        equipment=equipment,
        power_price_eur_mwh=power_price,
        water_price_eur_m3=2.50,
        labour_count=10,
        labour_cost_eur_year=65_000,
        insurance_pct_capex=0.005,
        contingency_pct=0.10,
        target_market_price_eur_t=5_000,
        capacity_factor=capacity_factor,
    )


def test_every_electrolyser_is_a_derived_converter():
    """No electrolyser may reintroduce a standalone annual literal."""
    offenders = [
        f"{i.id}: power={i.annual_power_mwh} output={i.capacity_tonnes_year} "
        f"water={i.annual_water_m3}"
        for i in EQUIPMENT_CATALOG
        if i.category == "ELECTROLYSER"
        and (i.annual_power_mwh or i.capacity_tonnes_year or i.annual_water_m3)
    ]
    assert not offenders, (
        "an electrolyser carries a hardcoded annual figure again; its ratio to "
        "the others is an unstated SEC: " + "; ".join(offenders)
    )
    assert len(DERIVED) >= 9, "the derived-converter catalogue shrank unexpectedly"


@pytest.mark.parametrize("item", DERIVED, ids=lambda i: i.id)
def test_declared_sec_is_physically_plausible(item):
    """
    A water-electrolysis SEC below ~32 kWh/kg is below the thermodynamic floor
    (HHV of H2 is 39.4 kWh/kg); above ~70 is worse than any commercial stack.
    200 kWh/kg — the value the catalogue used to imply — is far outside this.
    """
    assert 32.0 <= item.sec_kwh_per_kg <= 70.0, (
        f"{item.id} declares {item.sec_kwh_per_kg} kWh/kg, outside the plausible "
        f"range for water electrolysis"
    )


@pytest.mark.parametrize("item", DERIVED, ids=lambda i: i.id)
def test_declared_sec_matches_the_items_own_description(item):
    """
    The catalogue's prose used to contradict its arithmetic by 3.6x. Where a
    description states a kWh/kg figure, the declared SEC must agree with it.
    """
    import re

    m = re.search(r"~?(\d+(?:\.\d+)?)\s*kWh/kg", item.description)
    if not m:
        pytest.skip(f"{item.id} description states no SEC")
    stated = float(m.group(1))
    assert item.sec_kwh_per_kg == pytest.approx(stated, rel=0.10), (
        f"{item.id} description says {stated} kWh/kg but declares "
        f"{item.sec_kwh_per_kg}"
    )


def test_water_intensity_is_near_stoichiometric():
    """
    Electrolysis consumes 9 kg H2O per kg H2 (mass_balance.py states this).
    The catalogue used to imply 400-465 kg/kg, putting ~EUR 1,000/t of water
    into LCOH against a true ~EUR 25/t.
    """
    for item in DERIVED:
        assert 9.0 <= item.water_kg_per_kg <= 15.0, (
            f"{item.id} declares {item.water_kg_per_kg} kg water per kg H2"
        )


def test_a_derived_converter_cannot_be_costed_without_a_capacity_factor():
    """
    Run hours follow from the power contract. Refusing is the point: the engine
    previously asserted 8,760 h (and, for alkaline, 8,800) silently.
    """
    builder = get_plant_builder()
    cfg = _config([{"equipment_id": "PEM_ELEC_10MW", "quantity": 1}])
    with pytest.raises(CapacityFactorRequired):
        builder.build(cfg)


def test_capacity_factor_must_be_a_fraction():
    builder = get_plant_builder()
    for bad in (0.0, -0.2, 1.5, 8760):
        cfg = _config(
            [{"equipment_id": "PEM_ELEC_10MW", "quantity": 1}], capacity_factor=bad
        )
        with pytest.raises(ValueError):
            builder.build(cfg)


def test_no_configuration_can_draw_more_hours_than_a_year_contains():
    """
    At capacity_factor=1.0 a 10 MW unit draws exactly 10 x 8760 MWh. The
    alkaline rows used to claim 8,800 h — 40 hours that do not exist.
    """
    builder = get_plant_builder()
    for item in DERIVED:
        cfg = _config([{"equipment_id": item.id, "quantity": 1}], capacity_factor=1.0)
        result = builder.build(cfg)
        implied_hours = result.total_annual_power_mwh / item.rated_mw
        assert implied_hours <= HOURS_PER_YEAR + 1, (
            f"{item.id} implies {implied_hours:.0f} full-load hours"
        )


@pytest.mark.parametrize("item", DERIVED, ids=lambda i: i.id)
def test_power_and_output_cannot_drift_into_an_unstated_sec(item):
    """
    The core invariant. Whatever the capacity factor, annual power divided by
    annual output must reproduce the ONE declared SEC. This is what makes the
    original defect unrepresentable.
    """
    builder = get_plant_builder()
    for cf in (0.25, 0.55, 0.92):
        result = builder.build(
            _config([{"equipment_id": item.id, "quantity": 1}], capacity_factor=cf)
        )
        implied_sec = (
            result.total_annual_power_mwh * 1_000
        ) / (result.annual_output_tonnes * 1_000)
        assert implied_sec == pytest.approx(item.sec_kwh_per_kg, rel=0.01), (
            f"{item.id} at cf={cf} implies {implied_sec:.2f} kWh/kg but declares "
            f"{item.sec_kwh_per_kg}"
        )


def test_output_scales_with_capacity_factor():
    """Negative verification: if capacity_factor were ignored, these would match."""
    builder = get_plant_builder()
    eq = [{"equipment_id": "PEM_ELEC_10MW", "quantity": 1}]
    low = builder.build(_config(eq, capacity_factor=0.30)).annual_output_tonnes
    high = builder.build(_config(eq, capacity_factor=0.90)).annual_output_tonnes
    assert high == pytest.approx(low * 3, rel=0.02), (
        "capacity_factor does not reach the output calculation"
    )


def test_the_power_term_of_lcoh_is_now_the_declared_sec():
    """
    End to end, in money. A 10 MW PEM at 55 kWh/kg and EUR 45/MWh must put
    55 x 45 / 1000 = EUR 2.475/kg (EUR 2,475/t) of power into LCOH. The old
    implied 200 kWh/kg made that EUR 9,000/t.
    """
    builder = get_plant_builder()
    result = builder.build(
        _config(
            [{"equipment_id": "PEM_ELEC_10MW", "quantity": 1}],
            capacity_factor=0.50,
            power_price=45.0,
        )
    )
    power_eur_per_tonne = result.annual_power_eur / result.annual_output_tonnes
    assert power_eur_per_tonne == pytest.approx(2_475, rel=0.01), (
        f"power term is EUR {power_eur_per_tonne:.0f}/t, expected EUR 2,475/t"
    )
