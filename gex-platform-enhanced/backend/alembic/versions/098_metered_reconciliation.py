"""Metered production and power: explicit units, a facility, an interval; meter tolerances.

Revision ID: 098
Revises: 097

WHY
---
GreenMesh Phase 1, Step 3: a lot's declared volume is compared with what the plant's
meters recorded for the same facility and window, so a declared tonne is RECONCILED,
shows a VARIANCE, or is UNVERIFIED — never passed silently. Until now `plant_data` held a
free-text payload ("m³/h H2, t/day NH3"), no facility, no interval, and the ingest route
took `project_id` from the body without checking it against the gateway.

WHAT
----
gateway_registry   + facility_id: a meter belongs to one facility of its project.
plant_data         + facility_id, molecule, interval_start, interval_end,
                   quantity_normalised, normalised_unit (kg | MWh). Required for
                   PRODUCTION_VOLUME and POWER_CONSUMPTION (CHECK). By trigger: a reading's
                   project is its gateway's project, a metered reading's facility is its
                   gateway's facility, and two readings of one gateway, type and molecule
                   never overlap in time (a duplicate push would count twice). Append-only:
                   UPDATE/DELETE/TRUNCATE revoked from gex_app and refused by trigger.
coc_meter_tolerance  The agreed tolerance between declared and metered quantities, per
                   facility and measure (PRODUCTION of a molecule, or ELECTRICITY), versioned
                   by valid_from, with its source. EMPTY: the value is the certifier's or the
                   independent engineer's to give. With no row the tolerance is ZERO.
mass_balance_lots  + meter_check, meter_detail: the reconciliation known when the lot was
                   created, required on a period lot and fixed with its declaration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "098"
down_revision: Union[str, None] = "097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
READ = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"
WRITE = f"({ADMIN} OR app_company_owns_project(project_id, {ME}))"
METERED = "('PRODUCTION_VOLUME', 'POWER_CONSUMPTION')"


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def _lot_guard(fixed_extra: str) -> str:
    """097's lot guard, with `fixed_extra` columns added to the fixed declaration."""
    return f"""CREATE OR REPLACE FUNCTION mass_balance_lot_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
              NEW.certification_pathway, NEW.carbon_intensity_gco2e_mj, NEW.created_by, NEW.created_at{fixed_extra.replace('X.', 'NEW.')})
             IS DISTINCT FROM
             (OLD.lot_id, OLD.project_id, OLD.molecule, OLD.production_date, OLD.total_volume_kg, OLD.period_id,
              OLD.facility_id, OLD.characteristics, OLD.conversion_check, OLD.conversion_detail,
              OLD.certification_pathway, OLD.carbon_intensity_gco2e_mj, OLD.created_by, OLD.created_at{fixed_extra.replace('X.', 'OLD.')}) THEN
            RAISE EXCEPTION 'COC_LOT_FIXED: a period lot''s declaration never changes; only its allocation does'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$"""


def upgrade() -> None:
    conn = op.get_bind()

    # ── a meter belongs to a facility ───────────────────────────────────────
    _q("ALTER TABLE gateway_registry ADD COLUMN facility_id text")

    # ── metered readings: explicit, normalised, one interval each ───────────
    for col, typ in (("facility_id", "text"), ("molecule", "text"), ("interval_start", "timestamptz"),
                     ("interval_end", "timestamptz"), ("quantity_normalised", "double precision"),
                     ("normalised_unit", "text")):
        _q(f"ALTER TABLE plant_data ADD COLUMN {col} {typ}")
    _q("ALTER TABLE plant_data ADD CONSTRAINT ck_plant_data_normalised_unit "
       "CHECK (normalised_unit IS NULL OR normalised_unit IN ('kg', 'MWh'))")
    _q("ALTER TABLE plant_data ADD CONSTRAINT ck_plant_data_quantity "
       "CHECK (quantity_normalised IS NULL OR quantity_normalised >= 0)")
    _q(f"""ALTER TABLE plant_data ADD CONSTRAINT ck_plant_data_metered CHECK (
           data_type NOT IN {METERED} OR (
             facility_id IS NOT NULL AND interval_start IS NOT NULL AND interval_end IS NOT NULL
             AND interval_end > interval_start AND quantity_normalised IS NOT NULL
             AND (data_type = 'POWER_CONSUMPTION') = (normalised_unit = 'MWh')
             AND (data_type <> 'PRODUCTION_VOLUME' OR molecule IS NOT NULL))) NOT VALID""")
    legacy = _q(f"SELECT count(*) FROM plant_data WHERE data_type IN {METERED}").scalar()
    if legacy == 0:
        _q("ALTER TABLE plant_data VALIDATE CONSTRAINT ck_plant_data_metered")
    _q("CREATE INDEX ix_plant_data_metered ON plant_data (project_id, facility_id, data_type, interval_start)")
    _q("""CREATE FUNCTION plant_data_guard() RETURNS trigger LANGUAGE plpgsql
          SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DECLARE g gateway_registry%ROWTYPE;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'PLANT_DATA_APPEND_ONLY: a meter reading is never changed or removed'
              USING ERRCODE = 'check_violation';
          END IF;
          SELECT * INTO g FROM gateway_registry WHERE id = NEW.gateway_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'PLANT_DATA_GATEWAY: % is not a registered gateway', NEW.gateway_id
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.project_id IS DISTINCT FROM g.project_id THEN
            RAISE EXCEPTION 'PLANT_DATA_PROJECT: gateway % reports for project %, not %', g.id, g.project_id, NEW.project_id
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.data_type IN ('PRODUCTION_VOLUME', 'POWER_CONSUMPTION') THEN
            IF g.facility_id IS NULL OR NEW.facility_id IS DISTINCT FROM g.facility_id THEN
              RAISE EXCEPTION 'PLANT_DATA_FACILITY: gateway % meters facility %, not %', g.id, g.facility_id, NEW.facility_id
                USING ERRCODE = 'check_violation';
            END IF;
            IF EXISTS (SELECT 1 FROM plant_data d WHERE d.gateway_id = NEW.gateway_id
                       AND d.data_type = NEW.data_type
                       AND COALESCE(d.molecule, '') = COALESCE(NEW.molecule, '')
                       AND d.interval_start < NEW.interval_end AND NEW.interval_start < d.interval_end) THEN
              RAISE EXCEPTION 'PLANT_DATA_OVERLAP: gateway % already reported % for part of % .. %',
                NEW.gateway_id, NEW.data_type, NEW.interval_start, NEW.interval_end USING ERRCODE = 'check_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$""")
    _q("CREATE TRIGGER plant_data_guard BEFORE INSERT OR UPDATE OR DELETE ON plant_data "
       "FOR EACH ROW EXECUTE FUNCTION plant_data_guard()")
    _q("REVOKE UPDATE, DELETE, TRUNCATE ON plant_data FROM gex_app")

    # ── agreed meter tolerances (none invented) ─────────────────────────────
    _q("""CREATE TABLE coc_meter_tolerance (
           tolerance_id text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           facility_id text NOT NULL CHECK (length(facility_id) > 0),
           measure text NOT NULL CHECK (measure IN ('PRODUCTION', 'ELECTRICITY')),
           molecule text,
           tolerance_fraction double precision NOT NULL CHECK (tolerance_fraction >= 0),
           valid_from date NOT NULL,
           source text NOT NULL CHECK (length(source) > 0),
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           CONSTRAINT ck_coc_meter_tolerance_molecule CHECK ((measure = 'PRODUCTION') = (molecule IS NOT NULL)))""")
    _q("CREATE UNIQUE INDEX uq_coc_meter_tolerance_version ON coc_meter_tolerance "
       "(project_id, facility_id, measure, COALESCE(molecule, ''), valid_from)")
    _q("CREATE TRIGGER coc_meter_tolerance_guard BEFORE UPDATE OR DELETE ON coc_meter_tolerance "
       "FOR EACH ROW EXECUTE FUNCTION coc_append_only_guard()")
    _q("ALTER TABLE coc_meter_tolerance ENABLE ROW LEVEL SECURITY")
    _q("ALTER TABLE coc_meter_tolerance FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY coc_meter_tolerance_read ON coc_meter_tolerance FOR SELECT USING {READ}")
    _q(f"CREATE POLICY coc_meter_tolerance_insert ON coc_meter_tolerance FOR INSERT WITH CHECK {WRITE}")
    _q("REVOKE ALL ON coc_meter_tolerance FROM PUBLIC, gex_app")
    _q("GRANT SELECT, INSERT ON coc_meter_tolerance TO gex_app")

    # ── the lot's reconciliation at creation, fixed with its declaration ────
    _q("ALTER TABLE mass_balance_lots ADD COLUMN meter_check text "
       "CHECK (meter_check IN ('RECONCILED', 'VARIANCE', 'UNVERIFIED'))")
    _q("ALTER TABLE mass_balance_lots ADD COLUMN meter_detail jsonb")
    _q("ALTER TABLE mass_balance_lots DROP CONSTRAINT ck_lot_period_fields")
    _q("ALTER TABLE mass_balance_lots ADD CONSTRAINT ck_lot_period_fields CHECK ("
       "(period_id IS NULL AND facility_id IS NULL AND characteristics IS NULL AND conversion_check IS NULL "
       " AND meter_check IS NULL) "
       "OR (period_id IS NOT NULL AND facility_id IS NOT NULL AND characteristics IS NOT NULL "
       " AND conversion_check IS NOT NULL AND meter_check IS NOT NULL))")
    _q(_lot_guard(", X.meter_check, X.meter_detail"))

    # ── assert rather than trust ────────────────────────────────────────────
    for t in ("plant_data", "coc_meter_tolerance"):
        assert conn.execute(sa.text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                                    "WHERE relname = :t"), {"t": t}).scalar(), f"{t} not FORCED"
        held = set(conn.execute(sa.text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'gex_app' AND table_name = :t"), {"t": t}).scalars())
        assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on {t}"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM coc_meter_tolerance").scalar()
    assert n == 0, f"coc_meter_tolerance holds {n} row(s); refusing to drop it"
    n = _q("SELECT count(*) FROM mass_balance_lots WHERE meter_check IS NOT NULL").scalar()
    assert n == 0, f"{n} lot(s) carry a meter check; refusing to drop it"
    _q(_lot_guard(""))
    _q("ALTER TABLE mass_balance_lots DROP CONSTRAINT ck_lot_period_fields")
    _q("ALTER TABLE mass_balance_lots ADD CONSTRAINT ck_lot_period_fields CHECK ("
       "(period_id IS NULL AND facility_id IS NULL AND characteristics IS NULL AND conversion_check IS NULL) "
       "OR (period_id IS NOT NULL AND facility_id IS NOT NULL AND characteristics IS NOT NULL "
       "AND conversion_check IS NOT NULL))")
    _q("ALTER TABLE mass_balance_lots DROP COLUMN IF EXISTS meter_detail")
    _q("ALTER TABLE mass_balance_lots DROP COLUMN IF EXISTS meter_check")
    _q("DROP TABLE IF EXISTS coc_meter_tolerance")
    _q("DROP TRIGGER IF EXISTS plant_data_guard ON plant_data")
    _q("DROP FUNCTION IF EXISTS plant_data_guard()")
    _q("GRANT UPDATE, DELETE ON plant_data TO gex_app")
    _q("DROP INDEX IF EXISTS ix_plant_data_metered")
    for c in ("ck_plant_data_metered", "ck_plant_data_quantity", "ck_plant_data_normalised_unit"):
        _q(f"ALTER TABLE plant_data DROP CONSTRAINT IF EXISTS {c}")
    for col in ("normalised_unit", "quantity_normalised", "interval_end", "interval_start", "molecule", "facility_id"):
        _q(f"ALTER TABLE plant_data DROP COLUMN IF EXISTS {col}")
    _q("ALTER TABLE gateway_registry DROP COLUMN IF EXISTS facility_id")
