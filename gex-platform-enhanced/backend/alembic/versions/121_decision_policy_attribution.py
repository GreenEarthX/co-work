"""Decision-test policy attribution on reference_parameter (handoff v4, task 6).

Revision ID: 121
Revises: 120
Create Date: 2026-11-17

JML, 2026-11-17: the twelve gates certify facts; metric thresholds are DECISION
TESTS, each attributed to its actual policy source, with that source's context
and effective date. A lender floor is the lender's policy once established;
until then it is a "GEX proposed" value. JML's approval establishes GEX
defaults; it never stands in for an institution's own policy.

The registry (061) already carries the source, the effective date (valid_from)
and the lifecycle. This adds what it lacks:

  policy_party      whose policy the value is: GEX, or the institution (EIB,
                    KfW, a named lender …). NULL for ordinary reference data.
  policy_context    JSON: the instrument, stage and scenario the value applies to.
  policy_reference  for an institution's ESTABLISHED policy: the document or
                    letter that establishes it. Without it an institution's
                    value can only ever be proposed.

The three are VALUE columns: immutable once written, like 061's (the guard
function is replaced with one that includes them). The one-approved-row index
now includes the party, so EIB's and KfW's hurdles are separate rows of one key.

Status shown to users is DERIVED, never stored (app/core/decision_policy.py):
  proposed                                  -> "GEX proposed"
  approved, party GEX                       -> "GEX default (approved by JML)"
  approved, party not GEX, with reference   -> "institution policy (established)"
No row is approved by this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "121"
down_revision: Union[str, None] = "120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALUE_COLS_061 = [
    "ref_id", "parameter_key", "pathway", "region", "value_low", "value_base",
    "value_high", "unit", "currency", "price_base_date", "source_class",
    "source_name", "source_url", "retrieved_at", "valid_from", "proposed_by",
    "proposed_at", "note"]
NEW_COLS = ["policy_party", "policy_context", "policy_reference"]


def _guard(conn, value_cols):
    changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in value_cols)
    conn.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION reference_parameter_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'reference_parameter is append-only: reject a row, never delete it';
          END IF;
          IF {changed} THEN
            RAISE EXCEPTION 'reference_parameter value columns are immutable: propose a new row';
          END IF;
          IF OLD.state = 'proposed' AND NEW.state IN ('approved', 'rejected') THEN
            RETURN NEW;
          END IF;
          IF OLD.state = 'approved' AND NEW.state = 'superseded'
             AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
             AND NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at
             AND NEW.supersedes_ref_id IS NOT DISTINCT FROM OLD.supersedes_ref_id
             AND NEW.rejected_by IS NULL AND NEW.rejected_at IS NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'illegal reference_parameter transition % -> %', OLD.state, NEW.state;
        END $$
    """))


def upgrade() -> None:
    conn = op.get_bind()
    for col in NEW_COLS:
        op.add_column("reference_parameter", sa.Column(col, sa.Text()))
    _guard(conn, VALUE_COLS_061 + NEW_COLS)
    conn.execute(sa.text(
        "ALTER TABLE reference_parameter ADD CONSTRAINT refparam_policy_context_json "
        "CHECK (policy_context IS NULL OR (policy_context::jsonb IS NOT NULL))"))
    # An institution's policy is established only with a reference; GEX's own
    # values never claim one (they are approved by JML, not established elsewhere).
    conn.execute(sa.text(
        "ALTER TABLE reference_parameter ADD CONSTRAINT refparam_policy_reference_party "
        "CHECK (policy_reference IS NULL OR (policy_party IS NOT NULL AND policy_party <> 'GEX'))"))
    op.drop_index("uq_refparam_one_approved", table_name="reference_parameter")
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX uq_refparam_one_approved ON reference_parameter "
        "(parameter_key, pathway, region, COALESCE(policy_party, '')) WHERE state = 'approved'"))
    # gex_app keeps no UPDATE on the new value columns: 061 granted UPDATE on the
    # lifecycle columns only, and a column-level grant does not extend to new columns.
    rows = conn.execute(sa.text(
        "SELECT privilege_type FROM information_schema.column_privileges "
        "WHERE grantee = 'gex_app' AND table_name = 'reference_parameter' "
        "AND column_name = ANY(:cols) AND privilege_type = 'UPDATE'"), {"cols": NEW_COLS}).fetchall()
    if rows:
        raise RuntimeError("gex_app must not hold UPDATE on the policy attribution columns")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS uq_refparam_one_approved"))
    op.create_index("uq_refparam_one_approved", "reference_parameter",
                    ["parameter_key", "pathway", "region"], unique=True,
                    postgresql_where=sa.text("state = 'approved'"))
    conn.execute(sa.text("ALTER TABLE reference_parameter DROP CONSTRAINT refparam_policy_reference_party"))
    conn.execute(sa.text("ALTER TABLE reference_parameter DROP CONSTRAINT refparam_policy_context_json"))
    _guard(conn, VALUE_COLS_061)
    for col in reversed(NEW_COLS):
        op.drop_column("reference_parameter", col)
