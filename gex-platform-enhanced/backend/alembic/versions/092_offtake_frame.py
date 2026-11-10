"""The offtake frame: one sub-leg per buyer, confirmed by that buyer (Phase 3 of "One contract record", step 4).

Revision ID: 092
Revises: 091

Phase 0 Q2 (JML 2026-11-05) and Q3: a project's offtake is ONE record — the frame —
holding the shared terms (specification, certification, force majeure, change in
law) and one sub-leg per buyer (volume, tenor, take-or-pay, commitment form,
credit). Each part is hashed on its own and the version hash is their Merkle root
(083). A `card` frame has no legs, so a buyer's sub-leg names its buyer
(tb_sub_leg.buyer_id) and carries that buyer's own projection here, inside its
sub_leg_hash and frozen with the terms (the 083 trigger covers every column).

Confirmation is per buyer: a CONFIRMED event naming the buyer's sub-leg
(tb_contract_event.sub_leg_id, 083) confirms that sub-leg's hash together with the
shared hash of its version. Only buyers whose part changed re-confirm (Q2): a
confirmation stays in force while the buyer's current sub-leg and the current
shared terms are the ones it confirmed — the comparison is the application's,
against the card, as for every other kind.

  v_engine_offtake_buyers   per (project, buyer company): the sub-leg named by that
                            buyer's last CONFIRMED with no DISPUTED of its own after
                            it — its projection, hash, and its version's shared
                            projection and hash
  v_engine_contract_terms   unchanged, except that a sub-leg's CONFIRMED or DISPUTED
                            is no longer read as the whole contract's

Both views are security_invoker; the engine reads them on the operator connection.

Q5 on a frame: a buyer reads the shared terms and ITS OWN sub-leg, never another
buyer's. tb_sub_leg's read policy keeps 085's rule for every other sub-leg and,
for a frame buyer's card sub-leg, admits the terms' owner, that sub-leg's buyer,
and any company that may read the terms and is not itself a buyer on them
(lenders, reviewers). app_tb_card_sub_leg_readable is SECURITY DEFINER with a
pinned search_path, as every cross-table lookup here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "092"
down_revision: Union[str, None] = "091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTRACT_TERMS = """
CREATE OR REPLACE VIEW v_engine_contract_terms WITH (security_invoker = true) AS
WITH decisive AS (
    SELECT DISTINCT ON (e.contract_id) e.contract_id, e.event_type, e.version_id
    FROM tb_contract_event e
    WHERE (e.event_type = 'DISPUTED' OR (e.event_type = 'CONFIRMED' AND e.version_id IS NOT NULL)){sub_leg}
    ORDER BY e.contract_id, e.seq DESC
)
SELECT c.project_id, c.kind, c.id AS contract_id, v.version, v.legacy_terms_sha256, t.card_projection AS terms
FROM decisive d
JOIN tb_contract c ON c.id = d.contract_id
JOIN tb_contract_version v ON v.id = d.version_id
JOIN tb_terms t ON t.id = v.terms_id
WHERE d.event_type = 'CONFIRMED' AND c.contract_type = 'terms' AND c.kind <> 'trade'
  AND c.project_id IS NOT NULL AND t.profile = 'card'
"""

BUYERS = """
CREATE VIEW v_engine_offtake_buyers WITH (security_invoker = true) AS
WITH decisive AS (
    SELECT DISTINCT ON (e.contract_id, cp.company_id)
           e.contract_id, cp.company_id AS buyer_company_id, e.event_type, e.sub_leg_id, e.seq
    FROM tb_contract_event e
    JOIN tb_sub_leg s ON s.id = e.sub_leg_id
    JOIN tb_counterparty cp ON cp.id = s.buyer_id
    WHERE e.event_type IN ('CONFIRMED', 'DISPUTED') AND e.sub_leg_id IS NOT NULL
    ORDER BY e.contract_id, cp.company_id, e.seq DESC
)
SELECT c.project_id, c.id AS contract_id, d.buyer_company_id, s.seq AS sub_leg_seq,
       s.sub_leg_hash, s.card_projection AS sub_leg_terms, t.shared_hash, t.card_projection AS shared_terms,
       d.seq AS confirmed_seq
FROM decisive d
JOIN tb_contract c ON c.id = d.contract_id
JOIN tb_sub_leg s ON s.id = d.sub_leg_id
JOIN tb_terms t ON t.id = s.terms_id
WHERE d.event_type = 'CONFIRMED' AND c.kind = 'offtake' AND c.contract_type = 'terms'
  AND c.project_id IS NOT NULL AND t.profile = 'card'
"""


def _q(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


CO = "current_setting('app.current_company_id', true)"
OLD_READ = f"({CO} = 'PLATFORM_ADMIN') OR app_tb_terms_readable(terms_id, {CO})"
NEW_READ = (f"({CO} = 'PLATFORM_ADMIN') OR (card_projection IS NULL AND app_tb_terms_readable(terms_id, {CO})) "
            f"OR (card_projection IS NOT NULL AND app_tb_card_sub_leg_readable(id, {CO}))")
READABLE = """
CREATE FUNCTION app_tb_card_sub_leg_readable(p_sub_leg uuid, p_company text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM tb_sub_leg s JOIN tb_terms t ON t.id = s.terms_id
        WHERE s.id = p_sub_leg AND (
            t.owner_company_id = p_company
            OR EXISTS (SELECT 1 FROM tb_counterparty cp WHERE cp.id = s.buyer_id AND cp.company_id = p_company)
            OR (app_tb_terms_readable(t.id, p_company) AND NOT EXISTS (
                SELECT 1 FROM tb_sub_leg o JOIN tb_counterparty ocp ON ocp.id = o.buyer_id
                WHERE o.terms_id = t.id AND ocp.company_id = p_company))))
$$"""


def _read_policy(rule: str) -> None:
    _q("DROP POLICY tb_sub_leg_read ON tb_sub_leg")
    _q(f"CREATE POLICY tb_sub_leg_read ON tb_sub_leg FOR SELECT USING ({rule})")


def upgrade() -> None:
    _q("ALTER TABLE tb_sub_leg ADD COLUMN card_projection jsonb")
    _q(READABLE)
    _read_policy(NEW_READ)
    _q(CONTRACT_TERMS.format(sub_leg=" AND e.sub_leg_id IS NULL"))
    _q(BUYERS)
    # 031's DEFAULT PRIVILEGES hand a new relation full DML; the runtime only reads it.
    _q("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON v_engine_offtake_buyers FROM gex_app")
    _q("GRANT SELECT ON v_engine_offtake_buyers TO gex_app")


def downgrade() -> None:
    n = op.get_bind().execute(sa.text("SELECT count(*) FROM tb_sub_leg WHERE card_projection IS NOT NULL")).scalar()
    assert n == 0, f"{n} frame sub-leg(s) carry a buyer's projection; 091 has nowhere to keep them"
    _q("DROP VIEW v_engine_offtake_buyers")
    _q(CONTRACT_TERMS.format(sub_leg=""))
    _read_policy(OLD_READ)
    _q("DROP FUNCTION app_tb_card_sub_leg_readable(uuid, text)")
    _q("ALTER TABLE tb_sub_leg DROP COLUMN card_projection")
