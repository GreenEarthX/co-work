"""OpenPyTEA 3.2 category names in tea_equipment_spec (20 Nov 2026).

Revision ID: 129
Revises: 128

OpenPyTEA 3.2.0 renamed three cost-correlation categories. The correlations under them
are unchanged (coefficients identical to 3.1.0's, measured 20 Nov 2026), so this is a LABEL
change only: no base_param, scale_exp or state moves, and no approval is re-made. The two
approved CO2 feed compressor rows (E_METHANOL, E_SAF) carried "Compressors & blowers".

The engine also translates the old names (tea_engine/correlation_set.RENAMED_CATEGORIES)
and lists the translation in a run's defaults_used, so a request sent with an old name
still prices and says so. After this migration no stored row needs it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "129"
down_revision: Union[str, None] = "128"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

RENAMED = {
    "Compressors & blowers": "Compressors, fans, & blowers",
    "Adsorption & membrane separation": "Absorption, adsorption, & membrane separation",
    "CO2 capture": "Absorption, adsorption, & membrane separation",
}
# Downgrade: the 3.1.0 home of each type that moved (from 3.1.0's CSV).
_OLD_HOME_TYPES = {
    "Compressors & blowers": ("CO2 compressor", "H2 compressor", "Air blower"),
    "CO2 capture": ("MEA CCS technology",),
}


def upgrade() -> None:
    conn = op.get_bind()
    for old, new in RENAMED.items():
        conn.execute(sa.text("UPDATE tea_equipment_spec SET category = :new WHERE category = :old"),
                     {"old": old, "new": new})
    left = conn.execute(sa.text("SELECT count(*) FROM tea_equipment_spec WHERE category = ANY(:o)"),
                        {"o": list(RENAMED)}).scalar()
    assert left == 0, f"{left} tea_equipment_spec rows still carry a retired OpenPyTEA category"


def downgrade() -> None:
    conn = op.get_bind()
    for old, types in _OLD_HOME_TYPES.items():
        conn.execute(sa.text("UPDATE tea_equipment_spec SET category = :old "
                             "WHERE category = :new AND equipment_type = ANY(:t)"),
                     {"old": old, "new": RENAMED[old], "t": list(types)})
