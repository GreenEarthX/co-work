"""M5 — capacities feed the position view (spec §3.5, §8 M5; Phase 3 of "One contract record").

Revision ID: 086
Revises: 085

capacities gains commodity_id, asset_id, owner_id (tb_counterparty), period_start,
period_end, quantity and unit, backfilled by app/trading_book/migrate/capacities_m5.py.
What cannot be determined is printed and left NULL, never guessed: on 2026-11-10 the
asset of all five rows (tb_asset is empty).

v_position (065: "planned joins at M5") now has three status classes:
  contracted  current contract versions (065, unchanged)
  planned     a producer's capacity, LONG product, month by month (JML 2026-10-23)
  ordered     open firm orders, signed by side through the §2 convention; a partly
              filled order counts only its unfilled share, so nothing is both
              ordered and contracted
security_invoker as before, so every caller sees the rows its RLS allows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "086"
down_revision: Union[str, None] = "085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTRACTED = """
    SELECT pf.party_company_id, t.commodity_id, pf.index_id,
           date_trunc('month', pf.period_start)::date AS period, 'contracted'::text AS status_class,
           sum(pf.signed_quantity) FILTER (WHERE pf.flow_type = 'physical') AS physical_qty,
           sum(pf.signed_fixed_amount) AS fixed_cash_amount,
           sum(pf.signed_quantity * pf.index_multiplier) FILTER (WHERE pf.flow_type = 'float_cash')
               AS index_exposure_qty
    FROM v_party_flow pf JOIN tb_contract_version v ON v.contract_id = pf.contract_id
         AND v.superseded_at IS NULL
    JOIN tb_terms t ON t.id = v.terms_id
    GROUP BY 1, 2, 3, 4"""
PLANNED = """
    SELECT cp.company_id AS party_company_id, c.commodity_id, NULL::uuid AS index_id,
           m.month::date AS period, 'planned'::text AS status_class,
           sum(c.capacity_mtpd::numeric * ((LEAST(c.period_end, (m.month + interval '1 month - 1 day')::date)
               - GREATEST(c.period_start, m.month::date)) + 1)) AS physical_qty,
           NULL::numeric AS fixed_cash_amount, NULL::numeric AS index_exposure_qty
    FROM capacities c
    JOIN tb_counterparty cp ON cp.id = c.owner_id
    CROSS JOIN LATERAL generate_series(date_trunc('month', c.period_start), c.period_end::timestamp,
                                       interval '1 month') AS m(month)
    WHERE c.period_start IS NOT NULL AND c.period_end IS NOT NULL AND c.commodity_id IS NOT NULL
    GROUP BY 1, 2, 3, 4"""
ORDERED = """
    SELECT cp.company_id AS party_company_id, t.commodity_id, f.index_id,
           date_trunc('month', f.period_start)::date AS period, 'ordered'::text AS status_class,
           sum(d.dir * f.quantity * r.share) FILTER (WHERE f.flow_type = 'physical') AS physical_qty,
           sum(d.dir * f.quantity * r.share * (f.unit_price + f.spread)) FILTER (WHERE f.flow_type = 'fixed_cash')
               AS fixed_cash_amount,
           sum(d.dir * f.quantity * r.share * f.index_multiplier) FILTER (WHERE f.flow_type = 'float_cash')
               AS index_exposure_qty
    FROM tb_order o
    JOIN tb_counterparty cp ON cp.id = o.owner_id
    JOIN tb_terms t ON t.id = o.terms_id
    JOIN tb_leg l ON l.terms_id = t.id
    JOIN tb_flow f ON f.leg_id = l.id
    CROSS JOIN LATERAL (SELECT CASE WHEN (l.leg_role IN ('product', 'floating') AND o.side = 'sell')
                                      OR (l.leg_role IN ('payment', 'fixed') AND o.side = 'buy')
                                    THEN -1 ELSE 1 END AS dir) d
    CROSS JOIN LATERAL (
        SELECT coalesce(1 - coalesce((SELECT sum(x.quantity) FROM tb_fill x
                                      WHERE x.buy_order_id = o.id OR x.sell_order_id = o.id), 0)
                          / NULLIF((SELECT sum(pf.quantity) FROM tb_leg pl JOIN tb_flow pf ON pf.leg_id = pl.id
                                    WHERE pl.terms_id = t.id AND pf.flow_type = 'physical'), 0), 1) AS share) r
    WHERE o.status IN ('open', 'partially_filled') AND o.order_type = 'firm'
    GROUP BY 1, 2, 3, 4"""


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def _view(*parts: str) -> None:
    _q("DROP VIEW IF EXISTS v_position")
    _q("CREATE VIEW v_position WITH (security_invoker = true) AS " + " UNION ALL ".join(parts))


def upgrade() -> None:
    for col, kind in (("commodity_id", "uuid REFERENCES tb_commodity(id)"), ("asset_id", "uuid REFERENCES tb_asset(id)"),
                      ("owner_id", "uuid REFERENCES tb_counterparty(id)"), ("period_start", "date"),
                      ("period_end", "date"), ("quantity", "numeric(20,6) CHECK (quantity IS NULL OR quantity > 0)"),
                      ("unit", "tb_unit")):
        _q(f"ALTER TABLE capacities ADD COLUMN {col} {kind}")
    _q("ALTER TABLE capacities ADD CONSTRAINT ck_capacities_period CHECK "
       "(period_start IS NULL OR period_end IS NULL OR period_start <= period_end)")
    from app.trading_book.migrate.capacities_m5 import fill
    from app.trading_book.migrate.fold_contract_tokens import SAConnection

    report = fill(SAConnection(op.get_bind()))
    for capacity, missing in report.items():
        print(f"  086: capacity {capacity}: not determined, left NULL: {'; '.join(missing)}")
    _view(CONTRACTED, PLANNED, ORDERED)


def downgrade() -> None:
    _view(CONTRACTED)
    _q("ALTER TABLE capacities DROP CONSTRAINT IF EXISTS ck_capacities_period")
    for col in ("unit", "quantity", "period_end", "period_start", "owner_id", "asset_id", "commodity_id"):
        _q(f"ALTER TABLE capacities DROP COLUMN IF EXISTS {col}")
