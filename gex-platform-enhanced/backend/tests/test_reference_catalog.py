"""
The reference catalog and proposal validation — pure, no database.

The catalog mirrors the frontend's unit families; this file reads
`frontend/src/engine/registry/unitFamilies.ts` so the two cannot drift.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core import reference_registry as reg
from app.core.reference_catalog import (
    MONETARY_FAMILIES, PARAMETERS, UNIT_FAMILIES, pathway_chain, region_chain,
)

UNIT_FAMILIES_TS = (Path(__file__).resolve().parents[2]
                    / "frontend/src/engine/registry/unitFamilies.ts")


def _frontend_families() -> dict[str, set[str]]:
    if not UNIT_FAMILIES_TS.exists():
        pytest.skip("frontend tree not present")
    out = {}
    for m in re.finditer(r"unitFamily:\s*'([A-Z_]+)'.*?allowedUnits:\s*\[([^\]]*)\]",
                         UNIT_FAMILIES_TS.read_text()):
        out[m.group(1)] = set(re.findall(r"'([^']*)'", m.group(2)))
    assert len(out) > 60, "unitFamilies.ts parse found too few families"
    return out


def test_every_registry_family_and_unit_exists_in_the_frontend():
    front = _frontend_families()
    for family, units in UNIT_FAMILIES.items():
        assert family in front, f"{family} is not a frontend unit family"
        missing = set(units) - front[family]
        assert not missing, f"{family}: {missing} not allowed by the frontend"


def test_every_parameter_names_a_known_family():
    for key, pdef in PARAMETERS.items():
        assert pdef.family in UNIT_FAMILIES, key


@pytest.mark.parametrize("pathway, chain", [
    ("H2_PEM", ["H2_PEM", "H2", "ANY"]), ("NH3", ["NH3", "ANY"]), ("ANY", ["ANY"])])
def test_pathway_fallback(pathway, chain):
    assert pathway_chain(pathway) == chain


@pytest.mark.parametrize("region, chain", [
    ("DE", ["DE", "EU", "ROW", "ANY"]), ("US", ["US", "ROW", "ANY"]),
    ("CN", ["CN", "ANY"]), ("EU", ["EU", "ROW", "ANY"]), ("ANY", ["ANY"])])
def test_region_fallback(region, chain):
    assert region_chain(region) == chain


def _p(**over):
    p = dict(parameter_key="h2_price_rfnbo", pathway="H2", region="EU", value_base=8.2,
             unit="EUR/kg", currency="EUR", price_base_date="2025-01-01",
             source_class="public_source", source_name="x")
    p.update(over)
    return p


def test_a_valid_proposal_passes():
    assert reg.validate_proposal(_p())["value_base"] == 8.2


@pytest.mark.parametrize("over, fragment", [
    ({"parameter_key": "hydrogen_price"}, "catalog is closed"),
    ({"unit": "kWh/kg"}, "unit must be one of"),
    ({"currency": "USD"}, "currency must be 'EUR'"),
    ({"price_base_date": None}, "price_base_date is required"),
    ({"price_base_date": "2025"}, "ISO date"),
    ({"value_low": 9.0}, "value_low <= value_base"),
    ({"pathway": "H2_SOEC"}, "pathway must be one of"),
    ({"region": "Europe"}, "region must be"),
    ({"source_class": "vendor_quote"}, "source_class"),
])
def test_bad_proposals_are_refused(over, fragment):
    with pytest.raises(reg.RegistryError, match=re.escape(fragment)):
        reg.validate_proposal(_p(**over))


def test_sec_cannot_be_entered_in_an_lhv_unit_family():
    """kWh/kg is accepted for SEC only because its family is SPECIFIC_POWER;
    MJ/kg (an ENERGY_PER_MASS unit) is refused."""
    base = dict(parameter_key="electrolyser_system_sec", pathway="H2_PEM", value_base=57.0,
                source_class="public_source", source_name="x")
    assert reg.validate_proposal(dict(base, unit="kWh/kg"))
    with pytest.raises(reg.RegistryError):
        reg.validate_proposal(dict(base, unit="MJ/kg"))


def test_a_non_monetary_value_carries_no_currency():
    with pytest.raises(reg.RegistryError, match="not monetary"):
        reg.validate_proposal(dict(parameter_key="stack_life_hours", value_base=40000.0,
                                   unit="h", currency="EUR", source_class="public_source",
                                   source_name="x"))


def test_monetary_families_are_the_cost_families():
    assert MONETARY_FAMILIES == {f for f in UNIT_FAMILIES if f.startswith("COST_")}


def test_fallback_is_marked_model_default_when_the_registry_is_absent(monkeypatch):
    monkeypatch.setattr(reg, "registry_available", lambda: False)
    r = reg.resolve_or_default("h2_price_rfnbo", 3.0, pathway="H2", region="EU")
    assert r == reg.Resolved(3.0, "model_default")


def test_fuel_defaults_without_registry_are_the_code_constants(monkeypatch):
    """WP1 changes no number: with nothing approved for these keys, the routes
    serve FUEL_DEFAULTS exactly, every field marked model_default."""
    import app.api.v1.capital_bridge as cb

    monkeypatch.setattr(reg, "registry_available", lambda: False)
    for fuel in cb.FuelType:
        out = cb._resolved_fuel_defaults(fuel)
        prov = out.pop("provenance")
        assert out.pop("fuel_type") == fuel.value
        assert out == cb.FUEL_DEFAULTS[fuel]
        assert {p["source_class"] for p in prov.values()} == {"model_default"}
