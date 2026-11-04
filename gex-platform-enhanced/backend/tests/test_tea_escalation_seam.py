"""The escalation basis is pluggable, and a change to it is visible.

Point 3 of the 2026-10-26 plan. Two defects this seam fixes:

1. `integrity.OPENPYTEA_TARGET_CEPCI_YEAR = 2024` LABELLED the cost basis but was never
   passed to `Equipment`, which used OpenPyTEA's own default of 2024. They agreed by
   coincidence, so moving the GEX constant would have moved the label while the
   arithmetic stood still. `escalation.target_year()` is now the single answer.

2. Escalation stopped dead at 2024 — the free CEPCI series ends there and is now behind
   a subscription, so a 2025 cost base raised from deep inside `inflation_adjustment`
   naming neither the year nor the reason.

The GreenEarthX index (paper 2026-10-07) is the intended provider but is INERT until a
governed annual-average snapshot of its factor series exists. These tests use a
deliberately illustrative snapshot — they prove the seam, not the index.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tea_engine import escalation                      # noqa: E402
from tea_engine.compute import run_tea                 # noqa: E402
from tea_engine.models import TEAComputeRequest        # noqa: E402

_CAPEX_2024 = 175_255_929.06


def _req():
    return TEAComputeRequest(project_id="esc", pathway_id="e", fuel_id="E_METHANOL",
                             nameplate_capacity=50000.0, nameplate_unit="t_per_year")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GEX_ESCALATION_PROVIDER", raising=False)
    monkeypatch.delenv("GEX_TEA_TARGET_YEAR", raising=False)


def test_cepci_is_the_default_and_the_target_year_is_explicit():
    assert escalation.active_provider().name == "cepci"
    assert escalation.target_year() == escalation.DEFAULT_TARGET_YEAR == 2024
    d = escalation.describe()
    assert d["provider"] == "cepci" and d["covers_beyond_2024"] is False
    assert d["gex_supplied_years"] == [1987], "cepci_extension must still be in force"


def test_passing_the_target_year_explicitly_changes_no_number():
    """It was previously left to OpenPyTEA's default. Making it explicit must be a
    no-op at 2024, or the fix would silently restate every basis."""
    assert run_tea(_req()).plant_summary.capex_eur == _CAPEX_2024


def test_a_cost_base_the_series_cannot_cover_is_refused_by_name(monkeypatch):
    monkeypatch.setenv("GEX_TEA_TARGET_YEAR", "2025")
    with pytest.raises(ValueError, match="2025 is not available"):
        run_tea(_req())
    # and the message must name the real reason, not just the year
    with pytest.raises(ValueError, match="free CEPCI series ends at 2024"):
        escalation.target_year()


def test_a_provider_enables_a_later_cost_base_and_the_hash_follows(monkeypatch):
    """The whole point: 2025 is impossible on CEPCI, possible with a provider, and the
    difference is VISIBLE — capex moves and so does cost_basis_hash."""
    base = run_tea(_req())
    escalation.register(escalation.GexIndexProvider(
        snapshot={2025: 825.6}, provenance={"basis": "illustrative test snapshot"}))
    monkeypatch.setenv("GEX_ESCALATION_PROVIDER", "gex_index")
    monkeypatch.setenv("GEX_TEA_TARGET_YEAR", "2025")

    later = run_tea(_req())
    assert escalation.active_provider().name == "gex_index"
    # 825.6 / 800.0 = exactly +3.2%
    assert abs(later.plant_summary.capex_eur / base.plant_summary.capex_eur - 1.032) < 1e-6
    assert later.cost_basis["cost_year"] == 2025
    assert later.cost_basis_hash != base.cost_basis_hash, (
        "a different escalation basis must rehash — measured 2026-10-26 it did NOT, "
        "because the fingerprint was lru_cached and the target year was unhashed")
    assert later.cost_basis["correlation_set"]["cepci_year_range"] == [1987, 2025], (
        "the pin must pick up the provider-supplied year, not report a stale series")


def test_the_fingerprint_is_not_cached_across_a_series_change(monkeypatch):
    """It was @lru_cache(maxsize=1) on a false assumption: apply() mutates the series
    in-process, and the cached pin then described data that no longer priced anything."""
    from tea_engine.correlation_set import fingerprint
    before = fingerprint()["cepci_year_range"]
    escalation.register(escalation.GexIndexProvider(snapshot={2031: 900.0}))
    monkeypatch.setenv("GEX_ESCALATION_PROVIDER", "gex_index")
    escalation.apply()
    assert fingerprint()["cepci_year_range"] != before, "the pin went stale"
    assert fingerprint()["cepci_year_range"][1] == 2031


def test_a_provider_extends_and_never_overwrites_published_history():
    """A provider must not quietly restate a published year."""
    from openpytea.equipment import CEPCI_DF
    published_2024 = float(CEPCI_DF.loc[2024, "cepci"])
    added = escalation.apply(escalation.GexIndexProvider(snapshot={2024: 1.0}))
    assert added == [], "an existing year must not be touched"
    assert float(CEPCI_DF.loc[2024, "cepci"]) == published_2024


def test_an_unusable_provider_falls_back_to_cepci_rather_than_failing(monkeypatch):
    """An escalation provider that cannot deliver must not take TEA offline."""
    monkeypatch.setenv("GEX_ESCALATION_PROVIDER", "no_such_provider")
    assert escalation.active_provider().name == "cepci"
    escalation.register(escalation.GexIndexProvider(snapshot={}))     # empty = unusable
    monkeypatch.setenv("GEX_ESCALATION_PROVIDER", "gex_index")
    assert escalation.active_provider().name == "cepci"
    assert run_tea(_req()).plant_summary.capex_eur == _CAPEX_2024


def test_the_gex_index_provider_is_inert_until_a_snapshot_is_loaded():
    p = escalation.GexIndexProvider()
    assert p.available is False and p.series() == {}
    d = p.describe()
    assert d["available"] is False and d["years"] == []
    assert "deterministic" in d["note"], "a spot feed must be refused by design"
