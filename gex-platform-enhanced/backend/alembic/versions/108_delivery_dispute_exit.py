"""The DISPUTED exit (GreenMesh Phase 2 Step 3, sub-step 4; amendment B3, ruling R4; T2 open).

Revision ID: 108
Revises: 107

A DISPUTED delivery leaves DISPUTED only through a resolution both parties confirm; GEX
arbitrates nothing:

  RESOLUTION_PROPOSED   a party, after the latest dispute: outcome ACCEPTED or REJECTED, with
                        the resolution on file (DISPUTE_RESOLUTION).
  RESOLUTION_CONFIRMED  the OTHER party, four eyes (DELIVERY_CONFIRM, TRADE_CONFIRM's rules).

Then, derived (no party act): ACCEPTED or REJECTED as resolved. R4: a resolution reaches
ACCEPTED only with the agreed inspector's certificate on the delivery — PASS: "resolved",
VERIFIED; FAIL: the confirmed resolution acts as the waiver both parties confirm, DECLARED and
FAIL (D3). With no certificate a dispute resolves only to REJECTED. A REJECTED delivery's
draws are released (107).

Built on 107's trigger text, by checked replacement: 107's file is the base, and every
replacement asserts it found its anchor.
"""
import importlib.util
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "108"
down_revision: Union[str, None] = "107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _m107():
    spec = importlib.util.spec_from_file_location("m107", Path(__file__).with_name("107_delivery_inspection.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


AFTER_DISPUTE = ("e.seq > coalesce((SELECT max(x.seq) FROM tb_contract_event x WHERE x.delivery_id = NEW.delivery_id "
                 "AND x.event_type = 'DELIVERY_DISPUTED'), 0)")
RES = ("(SELECT e.note::jsonb FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id "
       "AND e.event_type = 'DELIVERY_FACT_RESOLUTION_{k}' AND " + AFTER_DISPUTE + " ORDER BY e.seq DESC LIMIT 1)")
RES_COMPANY = ("(SELECT e.company_id FROM tb_contract_event e WHERE e.delivery_id = NEW.delivery_id "
               "AND e.event_type = 'DELIVERY_FACT_RESOLUTION_PROPOSED' AND " + AFTER_DISPUTE +
               " ORDER BY e.seq DESC LIMIT 1)")

RESOLUTION_FACTS = """        IF fact IN ('RESOLUTION_PROPOSED', 'RESOLUTION_CONFIRMED') THEN
          IF prev IS DISTINCT FROM 'DISPUTED' THEN
            RAISE EXCEPTION 'DELIVERY_RESOLUTION_ORDER: a resolution is recorded on a DISPUTED delivery, not %',
              nullif(prev, '') USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.company_id IS DISTINCT FROM d.seller_company_id AND NEW.company_id IS DISTINCT FROM d.buyer_company_id THEN
            RAISE EXCEPTION 'DELIVERY_WRONG_PARTY: a party to the delivery resolves its dispute; GEX arbitrates nothing'
              USING ERRCODE = 'check_violation';
          END IF;
          IF fact = 'RESOLUTION_PROPOSED' THEN
            IF n ->> 'outcome' NOT IN ('ACCEPTED', 'REJECTED') THEN
              RAISE EXCEPTION 'DELIVERY_RESOLUTION_OUTCOME: a dispute resolves to ACCEPTED or REJECTED'
                USING ERRCODE = 'check_violation';
            END IF;
            IF n ->> 'outcome' = 'ACCEPTED' AND cert IS NULL THEN
              RAISE EXCEPTION 'DELIVERY_RESOLUTION_NO_CERTIFICATE: acceptance needs the agreed inspector''s certificate (R4)'
                USING ERRCODE = 'check_violation';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM delivery_document x WHERE x.delivery_id = NEW.delivery_id
                           AND x.kind = 'DISPUTE_RESOLUTION' AND x.sha256 = n ->> 'document_sha256') THEN
              RAISE EXCEPTION 'DELIVERY_DOCUMENT_REQUIRED: the resolution is on file' USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF """ + RES.format(k="PROPOSED") + """ IS NULL
             OR NEW.company_id IS NOT DISTINCT FROM """ + RES_COMPANY + """
             OR (n ->> 'outcome') IS DISTINCT FROM (""" + RES.format(k="PROPOSED") + """ ->> 'outcome') THEN
            RAISE EXCEPTION 'DELIVERY_RESOLUTION_SAME_PARTY: the other party confirms the latest resolution proposed'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END IF;
        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';"""

FROM_DISPUTE = """      IF prev = 'DISPUTED' AND nxt IN ('ACCEPTED', 'REJECTED') THEN
        IF NEW.company_id IS NOT NULL THEN
          RAISE EXCEPTION 'DELIVERY_RESOLUTION_DERIVED: a resolved dispute moves by the confirmed resolution, not a party''s act'
            USING ERRCODE = 'check_violation';
        END IF;
        IF """ + RES.format(k="CONFIRMED") + """ IS NULL OR (""" + RES.format(k="CONFIRMED") + """ ->> 'outcome') IS DISTINCT FROM nxt THEN
          RAISE EXCEPTION 'DELIVERY_NOT_RESOLVED: no confirmed resolution to % since the latest dispute', nxt
            USING ERRCODE = 'check_violation';
        END IF;
        IF nxt = 'ACCEPTED' AND cert IS NULL THEN
          RAISE EXCEPTION 'DELIVERY_RESOLUTION_NO_CERTIFICATE: acceptance needs the agreed inspector''s certificate (R4)'
            USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
      END IF;
      IF nxt = 'ACCEPTED' THEN"""


def _build(m107) -> tuple[str, str]:
    """(108's event check, 108's event-type check)."""
    text = m107.EVENT_CHECK
    replacements = (
        ("        RAISE EXCEPTION 'DELIVERY_FACT_UNKNOWN: %', fact USING ERRCODE = 'check_violation';", RESOLUTION_FACTS),
        ("           OR (prev = 'TITLE_TRANSFERRED' AND nxt = 'SETTLED')",
         "           OR (prev = 'TITLE_TRANSFERRED' AND nxt = 'SETTLED')\n"
         "           OR (prev = 'DISPUTED' AND nxt IN ('ACCEPTED', 'REJECTED'))"),
        ("      IF nxt = 'ACCEPTED' THEN", FROM_DISPUTE),
    )
    for old, new in replacements:
        assert text.count(old) == 1, f"108: anchor not found once in 107's event check: {old[:60]!r}"
        text = text.replace(old, new)
    facts = m107.FACTS + ("RESOLUTION_PROPOSED", "RESOLUTION_CONFIRMED")
    types = m107._event_types(facts)
    return text, "CHECK (event_type IN " + m107._in(types) + ")"


def upgrade() -> None:
    m107 = _m107()
    have = _q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'tb_contract_event_event_type_check'").scalar()
    expected = m107._event_types(m107.FACTS)
    assert have and all(f"'{t}'" in have for t in expected) and have.count("'") == 2 * len(expected), have
    check, types = _build(m107)
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q(f"ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check {types}")
    _q(check)


def downgrade() -> None:
    m107 = _m107()
    n = _q("SELECT count(*) FROM tb_contract_event WHERE event_type LIKE 'DELIVERY\\_FACT\\_RESOLUTION\\_%'").scalar()
    assert n == 0, f"{n} resolution event(s) exist; refusing to downgrade"
    _q("ALTER TABLE tb_contract_event DROP CONSTRAINT tb_contract_event_event_type_check")
    _q("ALTER TABLE tb_contract_event ADD CONSTRAINT tb_contract_event_event_type_check CHECK (event_type IN "
       + m107._in(m107._event_types(m107.FACTS)) + ")")
    _q(m107.EVENT_CHECK)
