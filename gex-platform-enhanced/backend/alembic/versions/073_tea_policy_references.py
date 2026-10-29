"""The TEA plausibility band and Monte Carlo sigma become governed references.

Revision ID: 073
Revises: 072
Create Date: 2026-10-26

072 moved the FX rate. These are the rest of the constants that change a published
number or a release gate, and which `tea_engine` held hardcoded:

    PLAUSIBLE_LCOP_EUR_PER_KG = (0.10, 30.0)   -> tea_lcop_plausible_band
    MC_DEFAULT_REL_STD        = 0.10           -> tea_mc_default_rel_std
    MC_MAX_REL_STD            = 0.50           -> tea_mc_max_rel_std

Why these three are worth governing, specifically:
 - The LCOP band decides `result_status = IMPLAUSIBLE`, and the bridge REFUSES to
   promote an IMPLAUSIBLE basis to `verified` (422). The P1 release gate opens only on
   `verified`. So widening this band loosens a release gate — a two-person decision.
 - The default sigma sets the width of every uncertainty band GEX publishes. Changing it
   silently restates how uncertain every project looks.
 - The max sigma is the refusal ceiling for a caller-supplied sigma.

NOT included, deliberately: `OPENPYTEA_TARGET_CEPCI_YEAR = 2024`. It is a CALENDAR year,
and this table fixes a unit family per key. The only year-bearing families are TIME and
LIFETIME, which measure a DURATION — a row saying "2024 years" would be nonsense, and
forcing it there is the vocabulary entropy the registry exists to prevent. The cost year
belongs with the correlation-set pin (one basis = one correlation set + one cost year),
not here.

`tea_lcop_plausible_band` is a BAND: consumers read value_low / value_high. value_base is
the geometric midpoint, recorded only because the table requires low <= base <= high; it
is presentational and nothing reads it. Its family (COST_PER_MASS) also admits EUR/t, so
the engine refuses a band whose unit is not EUR/kg rather than misread a per-tonne band
as per-kilogram — a silent 1000x error.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "073"
down_revision: Union[str, None] = "072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_GEX = "GEX engineering judgement, carried over from tea_engine constants in force since 2026-09"

#   key,                      low,   base,    high,  unit,     currency, price_date
_ROWS = [
    ("tea_lcop_plausible_band", 0.10, 1.7321, 30.0, "EUR/kg", "EUR", "2024-01-01"),
    ("tea_mc_default_rel_std",  0.10, 0.10,   0.10, "-",      None,  None),
    ("tea_mc_max_rel_std",      0.50, 0.50,   0.50, "-",      None,  None),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, low, basev, high, unit, ccy, pdate in _ROWS:
        conn.execute(
            sa.text("""
                INSERT INTO reference_parameter
                    (ref_id, parameter_key, pathway, region,
                     value_low, value_base, value_high, unit, currency, price_base_date,
                     source_class, source_name, retrieved_at, valid_from,
                     state, proposed_by, proposed_at, approved_by, approved_at, note)
                VALUES
                    (:ref_id, :key, 'ANY', 'ANY',
                     :low, :basev, :high, :unit, :ccy, :pdate,
                     'gex_assumption', :src, '2026-09-22', '2024-01-01',
                     'approved', 'MIGRATION_073', now(), 'MIGRATION_073', now(), :note)
            """),
            {"ref_id": str(uuid.uuid4()), "key": key, "low": low, "basev": basev,
             "high": high, "unit": unit, "ccy": ccy, "pdate": pdate, "src": _GEX,
             "note": ("Band: consumers read value_low/value_high; value_base is a "
                      "presentational geometric midpoint and nothing reads it."
                      if key == "tea_lcop_plausible_band" else
                      "Point value: low = base = high. Any change goes through "
                      "propose/approve with a different approver.")},
        )

    for key, low, _b, high, unit, _c, _p in _ROWS:
        got = conn.execute(
            sa.text("SELECT value_low, value_high, unit, state FROM reference_parameter "
                    "WHERE parameter_key = :key"), {"key": key}).fetchone()
        assert got is not None, f"{key} was not inserted"
        assert float(got[0]) == low and float(got[1]) == high, f"{key} band is {got[0]}..{got[1]}"
        assert got[2] == unit, f"{key} unit is {got[2]}, expected {unit}"
        assert got[3] == "approved", f"{key} is {got[3]} — it would not be in force"


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM reference_parameter WHERE parameter_key = ANY(:keys)"),
        {"keys": [r[0] for r in _ROWS]})
