"""Product, carbon-intensity and certificate records (discovery Phase 1; decisions D-C, D-F).

Revision ID: 116
Revises: 115

The GEX product requirement: a token is a defined fuel quantity linked to its molecule, origin,
period, certification documents, environmental attributes and technical qualities, and the
certification ALWAYS has an explicit status. Before 116 a token carried a pathway field that mixed
pathway and scheme, a bare carbon-intensity number, a list of scheme codes, and a
`verification_state` the minter used to set itself (F06, closed in Phase 0).

  tokens + production_pathway, physical_form, specification_standard   (declared at mint)
  product_document            documents on file by GEX-computed sha256, per project; append-only
  token_quality               typed quality parameters, declared or measured; append-only
  token_carbon_intensity      value with method, boundary, calculation date and basis; append-only
  product_certificate         scheme / body / reference, kind (certificate | inspection), SCOPE
                              (organisation | site | batch | sample), validity, document; state in the
                              canonical evidence vocabulary: asserted -> submitted -> verified | rejected.
                              Expiry is derived from valid_until at read time, never stored.
  token_certificate_coverage  which tokens (quantity, period) a batch or sample record covers

Writers: the operator connection only, after core/product_record authorises the caller: the owning
company declares; ONLY an appointed independent reviewer (CERTIFIER, or INDEPENDENT_ENGINEER for an
inspection) of the project decides a certificate (D-F). Readers: GEX, the project's owner, and the
project's appointed reviewers (`app_company_reviews_project`). Market listings expose a status
summary through the market engine's own allowlist, not these tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "116"
down_revision: Union[str, None] = "115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENT = "current_setting('app.current_company_id'::text, true)"
ADMIN = f"({CURRENT} = 'PLATFORM_ADMIN'::text)"
PROJECT_READ = (f"({ADMIN} OR app_company_owns_project(project_id, {CURRENT}) "
                f"OR app_company_reviews_project(project_id, {CURRENT}))")
TOKEN_READ = (f"({ADMIN} OR EXISTS (SELECT 1 FROM tokens t JOIN capacities c ON c.id = t.capacity_id "
              f"WHERE t.id = token_id AND (app_company_owns_project(c.project_id, {CURRENT}) "
              f"OR app_company_reviews_project(c.project_id, {CURRENT}))))")
APPEND_ONLY = ("product_document", "token_quality", "token_carbon_intensity", "token_certificate_coverage")


def _q(sql: str):
    return op.get_bind().execute(sa.text(sql))


def _rls(table: str, read: str) -> None:
    _q(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    _q(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    _q(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING {read}")
    _q(f"CREATE POLICY {table}_operator_insert ON {table} FOR INSERT WITH CHECK {ADMIN}")
    _q(f"REVOKE ALL ON {table} FROM gex_app")


def upgrade() -> None:
    _q("""CREATE OR REPLACE FUNCTION app_company_reviews_project(p_project_id text, p_company_id text)
          RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
          AS $$ SELECT EXISTS (SELECT 1 FROM project_access WHERE project_id = p_project_id
                               AND company_id = p_company_id AND access_role = 'REVIEWER') $$""")
    _q("REVOKE ALL ON FUNCTION app_company_reviews_project(text, text) FROM PUBLIC")
    _q("GRANT EXECUTE ON FUNCTION app_company_reviews_project(text, text) TO gex_app")

    _q("ALTER TABLE tokens ADD COLUMN production_pathway text")
    _q("ALTER TABLE tokens ADD COLUMN physical_form text CHECK (physical_form IS NULL OR physical_form IN "
       "('gas', 'compressed_gas', 'liquid', 'liquefied_gas'))")
    _q("ALTER TABLE tokens ADD COLUMN specification_standard text")

    _q("""CREATE TABLE product_document (
            id bigserial PRIMARY KEY,
            project_id text NOT NULL REFERENCES projects(project_id),
            sha256 character(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            filename text NOT NULL, size_bytes integer NOT NULL CHECK (size_bytes > 0),
            stored_path text NOT NULL, uploaded_by text NOT NULL, company_id text NOT NULL,
            uploaded_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (project_id, sha256))""")
    _rls("product_document", PROJECT_READ)
    _q("GRANT SELECT, INSERT ON product_document TO gex_app")
    _q("GRANT USAGE ON SEQUENCE product_document_id_seq TO gex_app")

    _q("""CREATE TABLE token_quality (
            id bigserial PRIMARY KEY,
            token_id text NOT NULL REFERENCES tokens(id),
            parameter text NOT NULL, value numeric NOT NULL, unit text NOT NULL,
            basis text NOT NULL CHECK (basis IN ('declared', 'measured')),
            document_sha256 character(64) CHECK (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$'),
            recorded_by text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
            CHECK (basis = 'declared' OR document_sha256 IS NOT NULL))""")
    _rls("token_quality", TOKEN_READ)
    _q("GRANT SELECT, INSERT ON token_quality TO gex_app")
    _q("GRANT USAGE ON SEQUENCE token_quality_id_seq TO gex_app")

    _q("""CREATE TABLE token_carbon_intensity (
            id bigserial PRIMARY KEY,
            token_id text NOT NULL REFERENCES tokens(id),
            value_gco2e_mj numeric NOT NULL CHECK (value_gco2e_mj >= 0),
            method text NOT NULL, system_boundary text NOT NULL, calculation_date date NOT NULL,
            basis text NOT NULL CHECK (basis IN ('estimate', 'calculated', 'measured')),
            document_sha256 character(64) CHECK (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$'),
            recorded_by text NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
            CHECK (basis = 'estimate' OR document_sha256 IS NOT NULL))""")
    _rls("token_carbon_intensity", TOKEN_READ)
    _q("GRANT SELECT, INSERT ON token_carbon_intensity TO gex_app")
    _q("GRANT USAGE ON SEQUENCE token_carbon_intensity_id_seq TO gex_app")

    _q("""CREATE TABLE product_certificate (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id text NOT NULL REFERENCES projects(project_id),
            kind text NOT NULL CHECK (kind IN ('certificate', 'inspection')),
            scheme text NOT NULL, body text NOT NULL, reference text NOT NULL,
            scope text NOT NULL CHECK (scope IN ('organisation', 'site', 'batch', 'sample')),
            facility_id text,
            valid_from date NOT NULL, valid_until date,
            document_sha256 character(64) CHECK (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$'),
            state text NOT NULL CHECK (state IN ('asserted', 'submitted', 'verified', 'rejected')),
            submitted_by text NOT NULL, company_id text NOT NULL, submitted_at timestamptz NOT NULL DEFAULT now(),
            decided_by text, decided_company_id text, decided_at timestamptz, decision_note text,
            CHECK (valid_until IS NULL OR valid_until >= valid_from),
            CHECK (state IN ('asserted', 'submitted') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)),
            CHECK (state <> 'verified' OR document_sha256 IS NOT NULL),
            UNIQUE (project_id, scheme, reference))""")
    _rls("product_certificate", PROJECT_READ)
    _q(f"CREATE POLICY product_certificate_operator_update ON product_certificate FOR UPDATE USING {ADMIN} "
       f"WITH CHECK {ADMIN}")
    _q("GRANT SELECT, INSERT ON product_certificate TO gex_app")
    _q("GRANT UPDATE (state, decided_by, decided_company_id, decided_at, decision_note) ON product_certificate TO gex_app")
    _q("""CREATE FUNCTION product_certificate_transition() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF TG_OP = 'DELETE' THEN
              RAISE EXCEPTION 'PRODUCT_CERTIFICATE_KEPT: a certificate record is never deleted' USING ERRCODE = 'check_violation';
            END IF;
            IF NOT ((OLD.state = 'submitted' AND NEW.state IN ('verified', 'rejected'))
                    OR (OLD.state = 'asserted' AND NEW.state = 'rejected')) THEN
              RAISE EXCEPTION 'PRODUCT_CERTIFICATE_STATE: % cannot become %', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END $$""")
    _q("CREATE TRIGGER product_certificate_transition BEFORE UPDATE OR DELETE ON product_certificate "
       "FOR EACH ROW EXECUTE FUNCTION product_certificate_transition()")

    _q("""CREATE TABLE token_certificate_coverage (
            id bigserial PRIMARY KEY,
            certificate_id uuid NOT NULL REFERENCES product_certificate(id),
            token_id text NOT NULL REFERENCES tokens(id),
            quantity_t numeric CHECK (quantity_t IS NULL OR quantity_t > 0),
            period_start date, period_end date,
            created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
            UNIQUE (certificate_id, token_id))""")
    _rls("token_certificate_coverage", TOKEN_READ)
    _q("GRANT SELECT, INSERT ON token_certificate_coverage TO gex_app")
    _q("GRANT USAGE ON SEQUENCE token_certificate_coverage_id_seq TO gex_app")

    for t in APPEND_ONLY:
        _q(f"""CREATE FUNCTION {t}_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN RAISE EXCEPTION 'APPEND_ONLY: {t} is never changed or removed' USING ERRCODE = 'check_violation'; END $$""")
        _q(f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {t}_append_only()")

    forced = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM pg_class WHERE relname = ANY(:t) AND relrowsecurity AND relforcerowsecurity"),
        {"t": list(APPEND_ONLY) + ["product_certificate"]}).scalar()
    assert forced == 5, f"only {forced} of 5 product tables under FORCED RLS"


def downgrade() -> None:
    for t in ("token_certificate_coverage", "product_certificate", "token_carbon_intensity", "token_quality",
              "product_document"):
        _q(f"DROP TABLE IF EXISTS {t}")
    for t in APPEND_ONLY:
        _q(f"DROP FUNCTION IF EXISTS {t}_append_only()")
    _q("DROP FUNCTION IF EXISTS product_certificate_transition()")
    for col in ("specification_standard", "physical_form", "production_pathway"):
        _q(f"ALTER TABLE tokens DROP COLUMN IF EXISTS {col}")
    _q("DROP FUNCTION IF EXISTS app_company_reviews_project(text, text)")
