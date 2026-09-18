"""Term-curve tenor labels must be unique and must not round partial years.

Regression (2026-09-14): tenor_label used integer division, so the 18M point was
labelled "1Y" and 30M "2Y". /pricing-curves showed two "1Y" and two "2Y" rows
with different prices for every molecule.
"""
from __future__ import annotations

import math

import pytest

from pf_engine.api.routes_pricing import TERM_CURVE_TENORS_MONTHS
from pf_engine.core.gabillon import SEED_PARAMS, get_gabillon_model, tenor_label


@pytest.mark.parametrize(
    "months, label",
    [(1, "1M"), (9, "9M"), (12, "1Y"), (18, "18M"), (24, "2Y"), (30, "30M"), (60, "5Y")],
)
def test_tenor_label_convention(months, label):
    assert tenor_label(months) == label


@pytest.mark.parametrize("molecule", sorted(SEED_PARAMS))
def test_term_curve_labels_unique_and_partial_years_not_whole(molecule):
    params = SEED_PARAMS[molecule]
    curve = get_gabillon_model().term_structure(
        params, math.exp(params.mu_base), params.theta_0, TERM_CURVE_TENORS_MONTHS
    )
    labels = [pt["tenor_label"] for pt in curve]

    assert len(labels) == len(set(labels)), f"duplicate tenor labels: {labels}"
    by_months = {pt["tenor_months"]: pt["tenor_label"] for pt in curve}
    assert 18 in by_months and 30 in by_months, "route no longer requests 18M/30M"
    assert by_months[18] not in {"1Y", "2Y"} and not by_months[18].endswith("Y")
    assert by_months[30] not in {"2Y", "3Y"} and not by_months[30].endswith("Y")
