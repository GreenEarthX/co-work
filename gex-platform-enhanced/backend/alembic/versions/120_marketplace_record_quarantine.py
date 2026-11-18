"""D-A: no confirmation without evidence; the unprovenanced confirmations withdrawn (R6, F07).

Revision ID: 120
Revises: 119

On 2026-10-25 the Marketplace records moved from frontend constants (`source` = "MarketplacePage.tsx
constant ...") were set CONFIRMED by decision, with no document and no source: 8 sales records,
33 input lines (naming real suppliers and buyers) and 10 input classifications. D-A (JML,
2026-11-16): remove the unsupported certainty, keep the history, and allow confirmation again only
against recorded evidence.

  marketplace_record_history  every change of verification_state on the three tables, written by
                              trigger: from, to, the confirmation it replaced, who, when, why.
                              Append-only for every role.
  evidence_sha256             the document a confirmation rests on.
  quarantine_reason           why a record's certainty was withdrawn; screens say so.
  guard (trigger)             CONFIRMED or AUDITED needs evidence_sha256 AND a confirmer other than
                              the row's importer (created_by).

Data: every CONFIRMED/AUDITED row with no evidence goes back to UNVERIFIED with a quarantine reason;
the history keeps who confirmed it and when. The 5 spot prices (F08) are reference-registry rows
whose approval is JML's recorded decision of 2026-10-25; the registry has no withdrawal, so they are
NOT touched here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "120"
down_revision: Union[str, None] = "119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = {"project_sales_detail": "jsonb_build_object('project_id', NEW.project_id)",
          "project_input_line": "jsonb_build_object('id', NEW.id, 'project_id', NEW.project_id)",
          "input_classification": "jsonb_build_object('feedstock', NEW.feedstock)"}
REASON = ("Source not recorded: moved from a frontend constant and confirmed without evidence. "
          "Confirmation withdrawn 2026-11-16 (decision D-A); it returns only against a recorded document.")
CURRENT = "current_setting('app.current_company_id'::text, true)"


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    _q("""CREATE TABLE marketplace_record_history (
            id bigserial PRIMARY KEY,
            table_name text NOT NULL,
            record_key jsonb NOT NULL,
            from_state text NOT NULL,
            to_state text NOT NULL,
            prior_verified_by text,
            prior_verified_at timestamptz,
            verified_by text,
            evidence_sha256 text,
            reason text,
            actor text NOT NULL DEFAULT current_user,
            at timestamptz NOT NULL DEFAULT now())""")
    _q("ALTER TABLE marketplace_record_history ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE marketplace_record_history FORCE ROW LEVEL SECURITY")
    # GEX reads the history; the owner reads its project's (the records themselves are owner-only, 112).
    _q(f"""CREATE POLICY marketplace_record_history_read ON marketplace_record_history FOR SELECT USING (
             {CURRENT} = 'PLATFORM_ADMIN' OR (record_key ? 'project_id'
             AND app_company_owns_project(record_key->>'project_id', {CURRENT})))""")
    # Only the guard trigger writes history (SECURITY DEFINER, below); the runtime reads it.
    _q("REVOKE ALL ON marketplace_record_history FROM gex_app")
    _q("GRANT SELECT ON marketplace_record_history TO gex_app")
    _q("""CREATE FUNCTION marketplace_record_history_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'APPEND_ONLY: record history is never changed or removed' USING ERRCODE = 'check_violation'; END $$""")
    _q("CREATE TRIGGER marketplace_record_history_append_only BEFORE UPDATE OR DELETE ON marketplace_record_history "
       "FOR EACH ROW EXECUTE FUNCTION marketplace_record_history_append_only()")

    for t, key in TABLES.items():
        _q(f"ALTER TABLE {t} ADD COLUMN evidence_sha256 text CHECK (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{{64}}$')")
        _q(f"ALTER TABLE {t} ADD COLUMN quarantine_reason text")
        _q(f"""CREATE FUNCTION {t}_verification_guard() RETURNS trigger LANGUAGE plpgsql
              SECURITY DEFINER SET search_path = public, pg_temp AS $$
              BEGIN
                IF NEW.verification_state IN ('CONFIRMED', 'AUDITED') AND (
                     NEW.evidence_sha256 IS NULL OR NEW.verified_by IS NULL
                     OR NEW.verified_by IS NOT DISTINCT FROM NEW.created_by) THEN
                  RAISE EXCEPTION 'CONFIRMATION_NEEDS_EVIDENCE: % needs a recorded document and a confirmer other than its importer',
                    NEW.verification_state USING ERRCODE = 'check_violation';
                END IF;
                IF TG_OP = 'UPDATE' AND NEW.verification_state IS DISTINCT FROM OLD.verification_state THEN
                  INSERT INTO marketplace_record_history (table_name, record_key, from_state, to_state, prior_verified_by,
                         prior_verified_at, verified_by, evidence_sha256, reason)
                  VALUES ('{t}', {key}, OLD.verification_state::text, NEW.verification_state::text, OLD.verified_by,
                          OLD.verified_at, NEW.verified_by, NEW.evidence_sha256, NEW.quarantine_reason);
                END IF;
                RETURN NEW;
              END $$""")
        _q(f"CREATE TRIGGER {t}_verification_guard BEFORE INSERT OR UPDATE ON {t} "
           f"FOR EACH ROW EXECUTE FUNCTION {t}_verification_guard()")
        # Withdraw every confirmation that rests on nothing. The trigger records what it replaces.
        _q(f"UPDATE {t} SET verification_state = 'UNVERIFIED', verified_by = NULL, verified_at = NULL, "
           f"quarantine_reason = :reason WHERE verification_state IN ('CONFIRMED', 'AUDITED') AND evidence_sha256 IS NULL",
           {"reason": REASON})
    left = _q("SELECT (SELECT count(*) FROM project_sales_detail WHERE verification_state IN ('CONFIRMED','AUDITED')) "
              "+ (SELECT count(*) FROM project_input_line WHERE verification_state IN ('CONFIRMED','AUDITED')) "
              "+ (SELECT count(*) FROM input_classification WHERE verification_state IN ('CONFIRMED','AUDITED'))").scalar()
    assert left == 0, f"{left} confirmations without evidence remain"
    bad = _q("SELECT string_agg(privilege_type, ',') FROM information_schema.role_table_grants WHERE grantee = 'gex_app' "
             "AND table_name = 'marketplace_record_history' AND privilege_type <> 'SELECT'").scalar()
    assert not bad, f"gex_app must only read marketplace_record_history, holds {bad}"


def downgrade() -> None:
    # Put back exactly the confirmations 120 withdrew, from its own history, then remove what 120 added.
    for t in TABLES:
        _q(f"DROP TRIGGER IF EXISTS {t}_verification_guard ON {t}")
        _q(f"DROP FUNCTION IF EXISTS {t}_verification_guard()")
    for t, where in (("project_sales_detail", "x.project_id = h.record_key->>'project_id'"),
                     ("project_input_line", "x.id::text = h.record_key->>'id'"),
                     ("input_classification", "x.feedstock = h.record_key->>'feedstock'")):
        _q(f"""UPDATE {t} x SET verification_state = h.from_state::tb_verification_state,
                 verified_by = h.prior_verified_by, verified_at = h.prior_verified_at
               FROM marketplace_record_history h
               WHERE h.table_name = '{t}' AND h.to_state = 'UNVERIFIED' AND h.reason = :reason AND {where}""",
           {"reason": REASON})
        _q(f"ALTER TABLE {t} DROP COLUMN IF EXISTS quarantine_reason, DROP COLUMN IF EXISTS evidence_sha256")
    _q("DROP TABLE IF EXISTS marketplace_record_history")
    _q("DROP FUNCTION IF EXISTS marketplace_record_history_append_only()")
