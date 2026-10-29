"""tea_fx_usd_to_eur — the TEA cost basis FX rate becomes a governed reference.

Revision ID: 072
Revises: 071
Create Date: 2026-10-26

OpenPyTEA's 417 cost correlations are in USD. `tea_engine/integrity.py` multiplied
them into the project's base currency with a hardcoded `USD_TO_BASE = {"EUR": 0.924}`,
and used that same number as the midpoint of the +/-5% band a CFO FX override must sit
inside. So one edit to a Python constant moved every priced capex on the platform, with
nobody proposing it and nobody approving it.

Measured 2026-09-24 and the reason this row exists: setting that constant to 0.88 moved
e-methanol capex -4.8% (175,255,929 -> 166,910,409) while `cost_basis_hash` stayed
BYTE-IDENTICAL. An adversarial review called that "hardening, not a defect" on the
grounds that the constant could not drift independently of the code that hashed it.
Moving it into the registry makes it able to drift, so the hash must now cover it — the
bridge resolves this row and passes the value in the TEA request, which the hash
already covers (see `cost_basis_hash`).

Seeded `approved` because it is the value in force today, not a proposal: 0.924 is what
has priced every basis to date. `proposed_by`/`approved_by` are both MIGRATION_072 —
the registry's own four-eye (`reference_registry.approve` refuses `proposed_by ==
actor`) governs every CHANGE from here, which is the point. Not monetary: EXCHANGE_RATE
is a ratio, so `currency` is NULL and no `price_base_date` —
ck_refparam_monetary_dated allows NULL but rejects '' (it is NOT NULL and does
not match ^[A-Z]{3}$), which is how this was first written and why it failed.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "072"
down_revision: Union[str, None] = "071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_KEY = "tea_fx_usd_to_eur"
_RATE = 0.924


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO reference_parameter
                (ref_id, parameter_key, pathway, region,
                 value_low, value_base, value_high, unit, currency,
                 source_class, source_name, source_url, retrieved_at, valid_from,
                 state, proposed_by, proposed_at, approved_by, approved_at, note)
            VALUES
                (:ref_id, :key, 'ANY', 'ANY',
                 :rate, :rate, :rate, 'EUR/USD', NULL,
                 'public_source',
                 'ECB euro reference exchange rate, 2024 annual average',
                 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html',
                 '2026-09-22', '2024-01-01',
                 'approved', 'MIGRATION_072', now(), 'MIGRATION_072', now(),
                 :note)
        """),
        {"ref_id": str(uuid.uuid4()), "key": _KEY, "rate": _RATE,
         "note": "In force since before the registry existed: the value hardcoded in "
                 "tea_engine/integrity.py USD_TO_BASE. Fixed, not spot — a spot rate "
                 "would make cost_basis_hash non-deterministic. Any change goes through "
                 "propose/approve with a different approver."},
    )

    # The row must be resolvable and in force, or the engine silently keeps using its
    # code default and this migration has achieved nothing.
    got = conn.execute(
        sa.text("SELECT value_base, state, unit FROM reference_parameter "
                "WHERE parameter_key = :key"), {"key": _KEY}).fetchone()
    assert got is not None, f"{_KEY} was not inserted"
    assert float(got[0]) == _RATE, f"{_KEY} value_base is {got[0]}, expected {_RATE}"
    assert got[1] == "approved", f"{_KEY} is {got[1]}, not approved — it would not be in force"
    assert got[2] == "EUR/USD", f"{_KEY} unit is {got[2]}"


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM reference_parameter WHERE parameter_key = :key"),
        {"key": _KEY})
