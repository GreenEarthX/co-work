"""The quality specification sheet (D2) and its judgement; V16. Pure: no database."""
from __future__ import annotations

import pytest

from app.trading_book import quality, validation
from test_contract_clauses import _terms

SPEC = {"purity_pct": {"min": "99.97", "unit": "%"}, "ghg_intensity_gco2e_mj": {"max": "28.2", "unit": "gCO2e/MJ"}}


def test_a_valid_sheet_passes_v16_and_free_keys_are_untouched():
    t = _terms().model_copy(update={"quality_spec": {"parameters": SPEC, "certification_pathway": "RFNBO"}})
    assert validation.validate(t, "order") == []
    assert quality.sheet({"certification_pathway": "RFNBO"}) is None          # no typed parameters: no sheet


@pytest.mark.parametrize("params", [
    {}, {"purity_pct": {"unit": "%"}}, {"purity_pct": {"min": "x", "unit": "%"}},
    {"purity_pct": {"min": "2", "max": "1", "unit": "%"}}, {"purity_pct": {"min": "1"}},
    {"purity_pct": {"min": "1", "unit": "%", "target": "2"}},
], ids=["empty", "no-limit", "not-decimal", "min-above-max", "no-unit", "unknown-key"])
def test_a_malformed_sheet_fails_v16(params):
    t = _terms().model_copy(update={"quality_spec": {"parameters": params}})
    assert "V16" in validation.validate(t, "order")


def test_judge_is_per_parameter_inclusive_and_decimal():
    r = {x["parameter"]: x["result"] for x in quality.judge(SPEC, {"purity_pct": "99.97", "ghg_intensity_gco2e_mj": "28.2"})}
    assert r == {"purity_pct": "PASS", "ghg_intensity_gco2e_mj": "PASS"}
    r = {x["parameter"]: x["result"] for x in quality.judge(SPEC, {"purity_pct": "99.969", "ghg_intensity_gco2e_mj": "3"})}
    assert r == {"purity_pct": "FAIL", "ghg_intensity_gco2e_mj": "PASS"}


def test_a_parameter_not_measured_is_refused_never_assumed():
    with pytest.raises(ValueError, match="does not measure purity_pct"):
        quality.judge(SPEC, {"ghg_intensity_gco2e_mj": "3"})
    with pytest.raises(ValueError, match="not a measured value"):
        quality.judge(SPEC, {"purity_pct": "n/a", "ghg_intensity_gco2e_mj": "3"})
