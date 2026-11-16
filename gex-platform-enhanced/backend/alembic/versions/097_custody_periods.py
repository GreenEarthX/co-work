"""Chain of custody to RED III grade: accounting periods, inputs, conversion factors.

Revision ID: 097
Revises: 096

WHY
---
GreenMesh Phase 1, Step 2. `mass_balance.py` recorded output lots and allocated them to
tokens, with no accounting period, no input consignments, no conversion between the two
and one characteristic per lot — its own docstring listed those gaps. RED III Art. 30 mass
balance is period-based: the sum withdrawn is not greater than the sum added over a
defined accounting period, and characteristics stay assigned to consignments.

WHAT
----
coc_scheme_rule        Per certification scheme: maximum period length, carry-forward,
                       negative interim balance. EMPTY on purpose: the values are the
                       certifier's to confirm (ISCC EU, REDcert and others differ). With
                       no row the ledger applies the conservative reading — no carry-
                       forward, no negative balance — and says the length is unchecked.
coc_period             One accounting period per (project, facility, molecule, pathway).
                       OPEN -> CLOSED once; closing writes the period statement
                       (opening + inputs x conversion - withdrawals = closing) and its
                       hash. Periods of one key never overlap. A CLOSED period never
                       changes; no period is deleted.
coc_input              Input consignments (electricity, CO2, N2, water, hydrogen) with
                       an evidence reference (PPA, GO, supplier PoS ...), hash-chained
                       per period from the period's open hash. Append-only.
coc_conversion_factor  Declared input per kg of output, per facility, pathway, molecule
                       and input type, versioned by valid_from. A DECLARED accounting
                       ratio (from the facility or its engineer), not a process model.
                       Append-only: a new value is a new row.
mass_balance_lots      + period_id, facility_id, characteristics (jsonb), conversion_check,
                       conversion_detail. Lots before 097 keep period_id NULL and stay
                       readable, with carbon_intensity_gco2e_mj as before. A period lot's
                       declaration is fixed once written; it cannot change, move or be
                       deleted, and nothing touches it once its period is closed.
mass_balance_allocations + period_id. Its 043 policy was PLATFORM_ADMIN only (the table
                       has no project_id), so no producer could ever allocate. It now
                       resolves the project through the lot: owner and GEX write, project
                       access reads. Append-only (UPDATE, DELETE, TRUNCATE revoked).

TENANCY
-------
Every new table is FORCED RLS. Project tables: GEX, the owner and project access read;
GEX and the owner write. Scheme rules: everyone reads, GEX writes. Asserted below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "097"
down_revision: Union[str, None] = "096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
READ = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"
WRITE = f"({ADMIN} OR app_company_owns_project(project_id, {ME}))"
INPUT_TYPES = "('ELECTRICITY', 'CO2', 'N2', 'WATER', 'H2')"
PROJECT_TABLES = ("coc_period", "coc_input", "coc_conversion_factor")
APPEND_ONLY = ("coc_input", "coc_conversion_factor", "mass_balance_allocations")


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def upgrade() -> None:
    conn = op.get_bind()

    # ── scheme rules: the certifier's values, none invented ─────────────────
    _q("""CREATE TABLE coc_scheme_rule (
           scheme text PRIMARY KEY,
           max_period_days integer CHECK (max_period_days > 0),
           carry_forward_allowed boolean,
           negative_interim_allowed boolean NOT NULL DEFAULT false,
           source text NOT NULL CHECK (length(source) > 0),
           confirmed_by text,
           confirmed_at timestamptz,
           note text)""")

    # ── periods ─────────────────────────────────────────────────────────────
    _q("""CREATE TABLE coc_period (
           period_id text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           facility_id text NOT NULL CHECK (length(facility_id) > 0),
           molecule text NOT NULL,
           pathway text NOT NULL CHECK (length(pathway) > 0),
           scheme text NOT NULL CHECK (length(scheme) > 0),
           period_start date NOT NULL,
           period_end date NOT NULL,
           status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
           opening_balance_kg double precision NOT NULL DEFAULT 0 CHECK (opening_balance_kg >= 0),
           opening_basis text NOT NULL,
           open_hash text NOT NULL,
           opened_by text NOT NULL,
           opened_at timestamptz NOT NULL DEFAULT now(),
           closing_balance_kg double precision,
           statement jsonb,
           statement_hash text,
           closed_by text,
           closed_at timestamptz,
           CONSTRAINT ck_coc_period_dates CHECK (period_end >= period_start),
           CONSTRAINT ck_coc_period_closed CHECK ((status = 'CLOSED') = (
               statement IS NOT NULL AND statement_hash IS NOT NULL AND closed_by IS NOT NULL
               AND closed_at IS NOT NULL AND closing_balance_kg IS NOT NULL)))""")
    _q("CREATE INDEX ix_coc_period_key ON coc_period (project_id, facility_id, molecule, pathway, period_start)")
    _q("""CREATE FUNCTION coc_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'COC_PERIOD_KEPT: an accounting period is never deleted' USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'OPEN' THEN
              RAISE EXCEPTION 'COC_PERIOD_STARTS_OPEN: a period is opened, then closed' USING ERRCODE = 'check_violation';
            END IF;
            IF EXISTS (SELECT 1 FROM coc_period p WHERE p.project_id = NEW.project_id
                       AND p.facility_id = NEW.facility_id AND p.molecule = NEW.molecule
                       AND p.pathway = NEW.pathway
                       AND p.period_start <= NEW.period_end AND NEW.period_start <= p.period_end) THEN
              RAISE EXCEPTION 'COC_PERIOD_OVERLAP: % overlaps another period of the same facility, molecule and pathway',
                NEW.period_id USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.status = 'CLOSED' THEN
            RAISE EXCEPTION 'COC_PERIOD_CLOSED: period % is closed and never changes', OLD.period_id
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.status <> 'CLOSED' THEN
            RAISE EXCEPTION 'COC_PERIOD_ONLY_CLOSES: an open period changes only by closing'
              USING ERRCODE = 'check_violation';
          END IF;
          IF (NEW.period_id, NEW.project_id, NEW.facility_id, NEW.molecule, NEW.pathway, NEW.scheme,
              NEW.period_start, NEW.period_end, NEW.opening_balance_kg, NEW.opening_basis, NEW.open_hash,
              NEW.opened_by, NEW.opened_at)
             IS DISTINCT FROM
             (OLD.period_id, OLD.project_id, OLD.facility_id, OLD.molecule, OLD.pathway, OLD.scheme,
              OLD.period_start, OLD.period_end, OLD.opening_balance_kg, OLD.opening_basis, OLD.open_hash,
              OLD.opened_by, OLD.opened_at) THEN
            RAISE EXCEPTION 'COC_PERIOD_FIXED: a period''s identity and opening never change'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER coc_period_guard BEFORE INSERT OR UPDATE OR DELETE ON coc_period "
       "FOR EACH ROW EXECUTE FUNCTION coc_period_guard()")

    # ── input consignments ──────────────────────────────────────────────────
    _q(f"""CREATE TABLE coc_input (
           input_id text PRIMARY KEY,
           period_id text NOT NULL REFERENCES coc_period(period_id),
           project_id text NOT NULL,
           input_type text NOT NULL CHECK (input_type IN {INPUT_TYPES}),
           quantity double precision NOT NULL CHECK (quantity > 0),
           unit text NOT NULL,
           quantity_normalised double precision NOT NULL CHECK (quantity_normalised > 0),
           normalised_unit text NOT NULL CHECK (normalised_unit IN ('MWh', 'kg')),
           sustainability_status text NOT NULL CHECK (sustainability_status IN ('CERTIFIED', 'NON_CERTIFIED')),
           received_on date NOT NULL,
           characteristics jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(characteristics) = 'object'),
           evidence_kind text NOT NULL CHECK (evidence_kind IN ('PPA', 'GO', 'POS', 'SUPPLIER_INVOICE', 'METER', 'OTHER')),
           evidence_ref text NOT NULL CHECK (length(evidence_ref) > 0),
           seq integer NOT NULL CHECK (seq > 0),
           prev_hash text NOT NULL,
           entry_hash text NOT NULL UNIQUE,
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           CONSTRAINT uq_coc_input_seq UNIQUE (period_id, seq),
           CONSTRAINT ck_coc_input_unit CHECK (
               (input_type = 'ELECTRICITY') = (normalised_unit = 'MWh')))""")
    _q("""CREATE FUNCTION coc_input_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE p coc_period%ROWTYPE;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'COC_INPUT_APPEND_ONLY: an input consignment is never changed or removed'
              USING ERRCODE = 'check_violation';
          END IF;
          SELECT * INTO p FROM coc_period WHERE period_id = NEW.period_id;
          IF p.status <> 'OPEN' THEN
            RAISE EXCEPTION 'COC_PERIOD_CLOSED: period % is closed', NEW.period_id USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.project_id <> p.project_id THEN
            RAISE EXCEPTION 'COC_INPUT_PROJECT: an input belongs to its period''s project' USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.received_on < p.period_start OR NEW.received_on > p.period_end THEN
            RAISE EXCEPTION 'COC_INPUT_OUTSIDE_PERIOD: % is outside % .. %', NEW.received_on, p.period_start, p.period_end
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER coc_input_guard BEFORE INSERT OR UPDATE OR DELETE ON coc_input "
       "FOR EACH ROW EXECUTE FUNCTION coc_input_guard()")

    # ── conversion factors (declared, versioned) ────────────────────────────
    _q(f"""CREATE TABLE coc_conversion_factor (
           factor_id text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           facility_id text NOT NULL CHECK (length(facility_id) > 0),
           pathway text NOT NULL CHECK (length(pathway) > 0),
           molecule text NOT NULL,
           input_type text NOT NULL CHECK (input_type IN {INPUT_TYPES}),
           input_per_kg_output double precision NOT NULL CHECK (input_per_kg_output > 0),
           input_unit text NOT NULL CHECK (input_unit IN ('MWh', 'kg')),
           stated_value double precision NOT NULL,
           stated_unit text NOT NULL,
           tolerance_fraction double precision CHECK (tolerance_fraction >= 0),
           valid_from date NOT NULL,
           source text NOT NULL CHECK (length(source) > 0),
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           CONSTRAINT ck_coc_factor_unit CHECK ((input_type = 'ELECTRICITY') = (input_unit = 'MWh')),
           CONSTRAINT uq_coc_factor_version UNIQUE (project_id, facility_id, pathway, molecule, input_type, valid_from))""")
    _q("""CREATE FUNCTION coc_append_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'COC_APPEND_ONLY: % rows are never changed or removed; record a new one', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
        END $$""")
    _q("CREATE TRIGGER coc_conversion_factor_guard BEFORE UPDATE OR DELETE ON coc_conversion_factor "
       "FOR EACH ROW EXECUTE FUNCTION coc_append_only_guard()")

    # ── lots: period, characteristics, the conversion check ─────────────────
    _q("ALTER TABLE mass_balance_lots ADD COLUMN period_id text REFERENCES coc_period(period_id)")
    _q("ALTER TABLE mass_balance_lots ADD COLUMN facility_id text")
    _q("ALTER TABLE mass_balance_lots ADD COLUMN characteristics jsonb "
       "CHECK (characteristics IS NULL OR jsonb_typeof(characteristics) = 'object')")
    _q("ALTER TABLE mass_balance_lots ADD COLUMN conversion_check text "
       "CHECK (conversion_check IN ('WITHIN_INPUTS', 'EXCEEDS_INPUTS', 'NO_FACTOR'))")
    _q("ALTER TABLE mass_balance_lots ADD COLUMN conversion_detail jsonb")
    _q("ALTER TABLE mass_balance_lots ADD CONSTRAINT ck_lot_period_fields CHECK ("
       "(period_id IS NULL AND facility_id IS NULL AND characteristics IS NULL AND conversion_check IS NULL) "
       "OR (period_id IS NOT NULL AND facility_id IS NOT NULL AND characteristics IS NOT NULL "
       "AND conversion_check IS NOT NULL))")
    _q("""CREATE FUNCTION mass_balance_lot_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE p coc_period%ROWTYPE; pid text;
        BEGIN
          pid := CASE WHEN TG_OP = 'INSERT' THEN NEW.period_id ELSE OLD.period_id END;
          IF pid IS NULL THEN
            IF TG_OP = 'UPDATE' AND NEW.period_id IS NOT NULL THEN
              RAISE EXCEPTION 'COC_LOT_FIXED: a lot cannot be moved into a period' USING ERRCODE = 'check_violation';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
          END IF;
          SELECT * INTO p FROM coc_period WHERE period_id = pid;
          IF p.status <> 'OPEN' THEN
            RAISE EXCEPTION 'COC_PERIOD_CLOSED: period % is closed', pid USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'COC_LOT_KEPT: a period lot is never deleted' USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF NEW.project_id <> p.project_id OR NEW.molecule <> p.molecule OR NEW.facility_id <> p.facility_id THEN
              RAISE EXCEPTION 'COC_LOT_PERIOD: a lot matches its period''s project, facility and molecule'
                USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.production_date::date < p.period_start OR NEW.production_date::date > p.period_end THEN
              RAISE EXCEPTION 'COC_LOT_OUTSIDE_PERIOD: % is outside % .. %', NEW.production_date, p.period_start, p.period_end
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          IF (NEW.lot_id, NEW.project_id, NEW.molecule, NEW.production_date, NEW.total_volume_kg, NEW.period_id,
              NEW.facility_id, NEW.characteristics, NEW.conversion_check, NEW.conversion_detail,
              NEW.certification_pathway, NEW.carbon_intensity_gco2e_mj, NEW.created_by, NEW.created_at)
             IS DISTINCT FROM
             (OLD.lot_id, OLD.project_id, OLD.molecule, OLD.production_date, OLD.total_volume_kg, OLD.period_id,
              OLD.facility_id, OLD.characteristics, OLD.conversion_check, OLD.conversion_detail,
              OLD.certification_pathway, OLD.carbon_intensity_gco2e_mj, OLD.created_by, OLD.created_at) THEN
            RAISE EXCEPTION 'COC_LOT_FIXED: a period lot''s declaration never changes; only its allocation does'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER mass_balance_lot_period_guard BEFORE INSERT OR UPDATE OR DELETE ON mass_balance_lots "
       "FOR EACH ROW EXECUTE FUNCTION mass_balance_lot_period_guard()")

    # ── allocations: the period, a real tenant policy, append-only ──────────
    _q("ALTER TABLE mass_balance_allocations ADD COLUMN period_id text REFERENCES coc_period(period_id)")
    _q("""CREATE FUNCTION mass_balance_allocation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE lot_period text; st text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'COC_APPEND_ONLY: mass_balance_allocations rows are never changed or removed'
              USING ERRCODE = 'check_violation';
          END IF;
          SELECT period_id INTO lot_period FROM mass_balance_lots WHERE lot_id = NEW.lot_id;
          IF NEW.period_id IS DISTINCT FROM lot_period THEN
            RAISE EXCEPTION 'COC_ALLOCATION_PERIOD: an allocation belongs to its lot''s period'
              USING ERRCODE = 'check_violation';
          END IF;
          IF lot_period IS NOT NULL THEN
            SELECT status INTO st FROM coc_period WHERE period_id = lot_period;
            IF st <> 'OPEN' THEN
              RAISE EXCEPTION 'COC_PERIOD_CLOSED: period % is closed', lot_period USING ERRCODE = 'check_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER mass_balance_allocation_guard BEFORE INSERT OR UPDATE OR DELETE ON mass_balance_allocations "
       "FOR EACH ROW EXECUTE FUNCTION mass_balance_allocation_guard()")
    lot_project = "(SELECT l.project_id FROM mass_balance_lots l WHERE l.lot_id = mass_balance_allocations.lot_id)"
    _q("DROP POLICY mass_balance_allocations_tenant_isolation ON mass_balance_allocations")
    _q(f"CREATE POLICY mass_balance_allocations_read ON mass_balance_allocations FOR SELECT USING ("
       f"{ADMIN} OR app_company_owns_project({lot_project}, {ME}) "
       f"OR app_company_has_project_access({lot_project}, {ME}))")
    _q(f"CREATE POLICY mass_balance_allocations_insert ON mass_balance_allocations FOR INSERT WITH CHECK ("
       f"{ADMIN} OR app_company_owns_project({lot_project}, {ME}))")

    # ── RLS and privileges for the new tables ───────────────────────────────
    for t in PROJECT_TABLES:
        _q(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        _q(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        _q(f"CREATE POLICY {t}_read ON {t} FOR SELECT USING {READ}")
        _q(f"CREATE POLICY {t}_insert ON {t} FOR INSERT WITH CHECK {WRITE}")
        _q(f"REVOKE ALL ON {t} FROM PUBLIC, gex_app")
        _q(f"GRANT SELECT, INSERT ON {t} TO gex_app")
    _q(f"CREATE POLICY coc_period_close ON coc_period FOR UPDATE USING {WRITE} WITH CHECK {WRITE}")
    _q("GRANT UPDATE (status, closing_balance_kg, statement, statement_hash, closed_by, closed_at) "
       "ON coc_period TO gex_app")
    _q("ALTER TABLE coc_scheme_rule ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE coc_scheme_rule FORCE ROW LEVEL SECURITY")
    _q("CREATE POLICY coc_scheme_rule_read ON coc_scheme_rule FOR SELECT USING (true)")
    _q(f"CREATE POLICY coc_scheme_rule_write ON coc_scheme_rule FOR ALL USING ({ADMIN}) WITH CHECK ({ADMIN})")
    _q("REVOKE ALL ON coc_scheme_rule FROM PUBLIC, gex_app")
    _q("GRANT SELECT, INSERT, UPDATE ON coc_scheme_rule TO gex_app")
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON mass_balance_allocations FROM gex_app")

    # ── assert rather than trust ────────────────────────────────────────────
    for t in PROJECT_TABLES + ("coc_scheme_rule", "mass_balance_allocations", "mass_balance_lots"):
        assert conn.execute(sa.text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                                    "WHERE relname = :t"), {"t": t}).scalar(), f"{t} not FORCED"
    for t in APPEND_ONLY:
        held = set(conn.execute(sa.text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'gex_app' AND table_name = :t"), {"t": t}).scalars())
        assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on {t}"
    cols = set(conn.execute(sa.text(
        "SELECT column_name FROM information_schema.column_privileges WHERE grantee = 'gex_app' "
        "AND table_name = 'coc_period' AND privilege_type = 'UPDATE'")).scalars())
    assert cols == {"status", "closing_balance_kg", "statement", "statement_hash", "closed_by", "closed_at"}, cols


def downgrade() -> None:
    for t in ("coc_period", "coc_input", "coc_conversion_factor"):
        n = _q(f"SELECT count(*) FROM {t}").scalar()
        assert n == 0, f"{t} holds {n} row(s); refusing to drop custody records"
    _q("DROP TRIGGER IF EXISTS mass_balance_allocation_guard ON mass_balance_allocations")
    _q("DROP FUNCTION IF EXISTS mass_balance_allocation_guard()")
    _q("DROP POLICY IF EXISTS mass_balance_allocations_read ON mass_balance_allocations")
    _q("DROP POLICY IF EXISTS mass_balance_allocations_insert ON mass_balance_allocations")
    _q(f"CREATE POLICY mass_balance_allocations_tenant_isolation ON mass_balance_allocations "
       f"FOR ALL USING ({ADMIN})")
    _q("GRANT UPDATE, DELETE ON mass_balance_allocations TO gex_app")
    _q("ALTER TABLE mass_balance_allocations DROP COLUMN IF EXISTS period_id")
    _q("DROP TRIGGER IF EXISTS mass_balance_lot_period_guard ON mass_balance_lots")
    _q("DROP FUNCTION IF EXISTS mass_balance_lot_period_guard()")
    _q("ALTER TABLE mass_balance_lots DROP CONSTRAINT IF EXISTS ck_lot_period_fields")
    for col in ("conversion_detail", "conversion_check", "characteristics", "facility_id", "period_id"):
        _q(f"ALTER TABLE mass_balance_lots DROP COLUMN IF EXISTS {col}")
    _q("DROP TABLE IF EXISTS coc_conversion_factor")
    _q("DROP TABLE IF EXISTS coc_input")
    _q("DROP TABLE IF EXISTS coc_period")
    _q("DROP TABLE IF EXISTS coc_scheme_rule")
    for fn in ("coc_append_only_guard", "coc_input_guard", "coc_period_guard"):
        _q(f"DROP FUNCTION IF EXISTS {fn}()")
