"""RFNBO correlation, computed: a versioned rule table, facility profiles, PPAs, generation.

Revision ID: 099
Revises: 098

WHY
---
GreenMesh Phase 1, Step 4. `decision_twin.evaluate_red_iii` took temporal matching and
geographical correlation as caller-supplied flags, and accepted "monthly" with no date
limit. RFNBO correlation must be COMPUTED from consumption and contracted generation, and
the rules belong in data, versioned, because Delegated Regulation (EU) 2023/1184 is under
targeted review (autumn 2026).

WHAT
----
rfnbo_rule           Versioned rules (valid_from / valid_to), append-only, readable by all,
                     written by GEX. Seeded AS WRITTEN in 2023/1184 — temporal correlation
                     monthly until 31 Dec 2029 and hourly from 1 Jan 2030 (Art. 6);
                     additionality: a generator in operation no earlier than 36 months
                     before the electrolyser (Art. 5), with the exemption to 31 Dec 2037 for
                     electrolysers in operation before 1 Jan 2028 (Art. 11); geographic
                     correlation by the same bidding zone (Art. 7; its alternatives are not
                     evaluated). Each row says: confirm with counsel or the certifier.
coc_facility_profile The facility's bidding zone and electrolyser commissioning date.
coc_ppa              A power purchase agreement of a facility: generator, its bidding zone,
                     commissioning date, evidence.
plant_data           + ppa_id; new metered type PPA_GENERATION (MWh per interval, one PPA).
                     The PPA must belong to the gateway's project and facility (trigger).
All new tables FORCED RLS and append-only for gex_app. Asserted below.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "099"
down_revision: Union[str, None] = "098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ME = "current_setting('app.current_company_id', true)"
ADMIN = f"({ME} = 'PLATFORM_ADMIN')"
READ = f"({ADMIN} OR app_company_owns_project(project_id, {ME}) OR app_company_has_project_access(project_id, {ME}))"
WRITE = f"({ADMIN} OR app_company_owns_project(project_id, {ME}))"
NOTE = ("As written in Delegated Regulation (EU) 2023/1184, under targeted review (autumn 2026). "
        "Confirm with counsel or the certifier before relying on it.")
SEED = [
    ("rfnbo-temporal-monthly", "TEMPORAL_CORRELATION", '{"granularity": "MONTHLY"}', None, "2029-12-31", "2023/1184 Art. 6"),
    ("rfnbo-temporal-hourly", "TEMPORAL_CORRELATION", '{"granularity": "HOURLY"}', "2030-01-01", None, "2023/1184 Art. 6"),
    ("rfnbo-additionality-new", "ADDITIONALITY_NEW_INSTALLATION", '{"max_months_before_electrolyser": 36}', None, None,
     "2023/1184 Art. 5"),
    ("rfnbo-additionality-transition", "ADDITIONALITY_TRANSITION",
     '{"electrolyser_in_operation_before": "2028-01-01", "exempt_until": "2037-12-31"}', None, None, "2023/1184 Art. 11"),
    ("rfnbo-geographic-zone", "GEOGRAPHIC_CORRELATION", '{"same_bidding_zone": true}', None, None,
     "2023/1184 Art. 7 (alternatives not evaluated)"),
]


def _q(sql: str, params: dict | None = None):
    return op.get_bind().execute(sa.text(sql), params or {})


def _plant_data_guard(metered: str, key: str) -> str:
    return f"""CREATE OR REPLACE FUNCTION plant_data_guard() RETURNS trigger LANGUAGE plpgsql
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
          IF NEW.data_type IN {metered} THEN
            IF g.facility_id IS NULL OR NEW.facility_id IS DISTINCT FROM g.facility_id THEN
              RAISE EXCEPTION 'PLANT_DATA_FACILITY: gateway % meters facility %, not %', g.id, g.facility_id, NEW.facility_id
                USING ERRCODE = 'check_violation';
            END IF;
            {"IF NEW.ppa_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM coc_ppa a WHERE a.ppa_id = NEW.ppa_id AND a.project_id = NEW.project_id AND a.facility_id = NEW.facility_id) THEN RAISE EXCEPTION 'PLANT_DATA_PPA: % is not a PPA of this facility', NEW.ppa_id USING ERRCODE = 'check_violation'; END IF;" if 'ppa' in key else ''}
            IF EXISTS (SELECT 1 FROM plant_data d WHERE d.gateway_id = NEW.gateway_id
                       AND d.data_type = NEW.data_type
                       AND {key.replace('X.', 'd.')} = {key.replace('X.', 'NEW.')}
                       AND d.interval_start < NEW.interval_end AND NEW.interval_start < d.interval_end) THEN
              RAISE EXCEPTION 'PLANT_DATA_OVERLAP: gateway % already reported % for part of % .. %',
                NEW.gateway_id, NEW.data_type, NEW.interval_start, NEW.interval_end USING ERRCODE = 'check_violation';
            END IF;
          END IF;
          RETURN NEW;
        END $$"""


def _metered_check(with_ppa: bool) -> str:
    types = "('PRODUCTION_VOLUME', 'POWER_CONSUMPTION', 'PPA_GENERATION')" if with_ppa \
        else "('PRODUCTION_VOLUME', 'POWER_CONSUMPTION')"
    mwh = "(data_type IN ('POWER_CONSUMPTION', 'PPA_GENERATION'))" if with_ppa else "(data_type = 'POWER_CONSUMPTION')"
    ppa = " AND (data_type = 'PPA_GENERATION') = (ppa_id IS NOT NULL)" if with_ppa else ""
    return f"""ALTER TABLE plant_data ADD CONSTRAINT ck_plant_data_metered CHECK (
           data_type NOT IN {types} OR (
             facility_id IS NOT NULL AND interval_start IS NOT NULL AND interval_end IS NOT NULL
             AND interval_end > interval_start AND quantity_normalised IS NOT NULL
             AND {mwh} = (normalised_unit = 'MWh')
             AND (data_type <> 'PRODUCTION_VOLUME' OR molecule IS NOT NULL){ppa}))"""


def _rls(table: str, read: str, write: str) -> None:
    _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({read})")
    _q(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({write})")
    _q(f"REVOKE ALL ON {table} FROM PUBLIC, gex_app")
    _q(f"GRANT SELECT, INSERT ON {table} TO gex_app")
    _q(f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} "
       "FOR EACH ROW EXECUTE FUNCTION coc_append_only_guard()")


def upgrade() -> None:
    conn = op.get_bind()
    _q("""CREATE TABLE rfnbo_rule (
           rule_id text PRIMARY KEY,
           rule_key text NOT NULL CHECK (rule_key IN ('TEMPORAL_CORRELATION', 'ADDITIONALITY_NEW_INSTALLATION',
                                                      'ADDITIONALITY_TRANSITION', 'GEOGRAPHIC_CORRELATION')),
           value jsonb NOT NULL CHECK (jsonb_typeof(value) = 'object'),
           valid_from date,
           valid_to date,
           legal_basis text NOT NULL,
           note text,
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           CONSTRAINT ck_rfnbo_rule_dates CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from))""")
    for rid, key, value, vf, vt, basis in SEED:
        _q("INSERT INTO rfnbo_rule (rule_id, rule_key, value, valid_from, valid_to, legal_basis, note, recorded_by) "
           "VALUES (:r, :k, CAST(:v AS jsonb), CAST(:f AS date), CAST(:t AS date), :b, :n, 'MIGRATION_099')",
           {"r": rid, "k": key, "v": value, "f": vf, "t": vt, "b": basis, "n": NOTE})
    _rls("rfnbo_rule", "true", ADMIN)

    _q("""CREATE TABLE coc_facility_profile (
           project_id text NOT NULL REFERENCES projects(project_id),
           facility_id text NOT NULL CHECK (length(facility_id) > 0),
           bidding_zone text NOT NULL CHECK (length(bidding_zone) > 0),
           electrolyser_commissioning_date date,
           source text NOT NULL CHECK (length(source) > 0),
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           PRIMARY KEY (project_id, facility_id))""")
    _rls("coc_facility_profile", READ, WRITE)

    _q("""CREATE TABLE coc_ppa (
           ppa_id text PRIMARY KEY,
           project_id text NOT NULL REFERENCES projects(project_id),
           facility_id text NOT NULL CHECK (length(facility_id) > 0),
           ppa_ref text NOT NULL CHECK (length(ppa_ref) > 0),
           generator_id text NOT NULL CHECK (length(generator_id) > 0),
           generator_bidding_zone text NOT NULL CHECK (length(generator_bidding_zone) > 0),
           generator_commissioning_date date,
           technology text,
           evidence_ref text NOT NULL CHECK (length(evidence_ref) > 0),
           recorded_by text NOT NULL,
           recorded_at timestamptz NOT NULL DEFAULT now(),
           CONSTRAINT uq_coc_ppa_ref UNIQUE (project_id, ppa_ref))""")
    _rls("coc_ppa", READ, WRITE)

    _q("ALTER TABLE plant_data ADD COLUMN ppa_id text REFERENCES coc_ppa(ppa_id)")
    _q("ALTER TABLE plant_data DROP CONSTRAINT ck_plant_data_metered")
    _q(_metered_check(True))
    _q(_plant_data_guard("('PRODUCTION_VOLUME', 'POWER_CONSUMPTION', 'PPA_GENERATION')",
                         "(COALESCE(X.molecule, '') || '|' || COALESCE(X.ppa_id, ''))"))

    for t in ("rfnbo_rule", "coc_facility_profile", "coc_ppa"):
        assert conn.execute(sa.text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                                    "WHERE relname = :t"), {"t": t}).scalar(), f"{t} not FORCED"
        held = set(conn.execute(sa.text("SELECT privilege_type FROM information_schema.role_table_grants "
                                        "WHERE grantee = 'gex_app' AND table_name = :t"), {"t": t}).scalars())
        assert held == {"SELECT", "INSERT"}, f"gex_app holds {sorted(held)} on {t}"


def downgrade() -> None:
    n = _q("SELECT count(*) FROM plant_data WHERE data_type = 'PPA_GENERATION'").scalar()
    assert n == 0, f"{n} PPA_GENERATION reading(s); refusing to drop them"
    _q(_plant_data_guard("('PRODUCTION_VOLUME', 'POWER_CONSUMPTION')", "COALESCE(X.molecule, '')"))
    _q("ALTER TABLE plant_data DROP CONSTRAINT ck_plant_data_metered")
    _q(_metered_check(False))
    _q("ALTER TABLE plant_data DROP COLUMN IF EXISTS ppa_id")
    for t in ("coc_ppa", "coc_facility_profile", "rfnbo_rule"):
        _q(f"DROP TABLE IF EXISTS {t}")
