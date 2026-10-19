"""Reference data registry — versioned, dated, sourced, approved reference values.

Revision ID: 061
Revises: 060
Create Date: 2026-10-19

Price and technology knowledge lived in code constants
(`capital_bridge.FUEL_DEFAULTS`, `tea_engine/models/tea.py`). Changing one needed
a release, and no project learned that a reference had moved. These two tables
make the database the single source; the constants become a last-resort fallback
marked `model_default` (app/core/reference_registry.py).

REFERENCE DATA, NOT PROJECT DATA
--------------------------------
The same rows for every tenant, as `fuel_catalog` (041): read-open, and written
only under `app.current_company_id = 'PLATFORM_ADMIN'`. A tenant can read a
reference and can never write one. Project values stay in the project; when a
reference moves, a project is flagged (WP2), never rewritten.

APPEND-ONLY, WITH A LIFECYCLE
-----------------------------
A value is never updated in place: a new row supersedes the old one, and the old
row stays readable through `as_of`. The row still has a lifecycle
(proposed -> approved | rejected, approved -> superseded), so "append-only" here
means precisely:

  · the VALUE columns are immutable once written — a trigger refuses any change
    to them, whoever the role is;
  · only the lifecycle columns may change, only along those transitions, and
    `gex_app` holds UPDATE on those columns alone (column-level grant);
  · nothing is deleted — no DELETE/TRUNCATE for `gex_app`, and a trigger refuses
    DELETE for every role. A wrong proposal is REJECTED, not removed.

`reference_version` is a named snapshot (the full list of approved ref_ids at
that moment) that projects pin. It is insert-only.

031's DEFAULT PRIVILEGES hand every new table full DML to `gex_app`, so a GRANT
restricts nothing — the REVOKE ALL below is what makes these grants true.

ONE QUANTITY PER NAME
---------------------
041 records that `fuel_catalog.specific_energy_value` (fuel LHV) and electrolyser
specific energy consumption (kWh per kg H2 PRODUCED) are different quantities.
The registry keeps them apart by key AND by unit family: `electrolyser_system_sec`
is SPECIFIC_POWER, never ENERGY_PER_MASS. The parameter catalog is closed
(app/core/reference_catalog.py); the guardrail is in tests/test_fuel_reference_slice.py.

SEED — reviewed 2026-10-19, each source opened before seeding
-------------------------------------------------------------
Rows whose figure was confirmed against the source are seeded APPROVED and form
version 1. Rows that could NOT be confirmed are seeded PROPOSED, so they reach a
project only after a PLATFORM_ADMIN approves them; their `note` says what is
missing. A seed row's actor is `MIGRATION_061`, the marker that finds them.

`price_base_date` is an ISO date; where a source gives a period ("2024",
"Q2 2026") it holds the FIRST day of that period, and the note names the period.
"""
from typing import Sequence, Union
import json
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "061"
down_revision: Union[str, None] = "060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
TABLES = ("reference_parameter", "reference_version")

# Lifecycle columns — the only ones gex_app may UPDATE, and only these may change.
LIFECYCLE = ("state", "supersedes_ref_id", "approved_by", "approved_at",
             "rejected_by", "rejected_at")

SEED_ACTOR = "MIGRATION_061"
SEED_DATE = "2026-10-19"
_NS = uuid.UUID("6f1c2b0e-7d3a-4c51-9a61-0c5e2f8a0611")

IEA = ("IEA Global Hydrogen Review 2025",
       "https://www.iea.org/reports/global-hydrogen-review-2025")
DOE = ("US DOE Hydrogen Program Record 24005 (2024-05-20): Clean Hydrogen Production "
       "Cost Scenarios with PEM Electrolyzer Technology",
       "https://www.hydrogen.energy.gov/docs/hydrogenprogramlibraries/pdfs/"
       "24005-clean-hydrogen-production-cost-pem-electrolyzer.pdf")
ACER = ("ACER European hydrogen markets monitoring 2025",
        "https://acer.europa.eu/monitoring/European-hydrogen-markets-2025")
LEVELTEN = ("LevelTen European PPA Price Index Q2 2026",
            "https://www.leveltenenergy.com/post/levelten-european-ppa-price-index-q2-2026")
EHB = ("European Hydrogen Bank, second auction results (general topic)",
       "https://www.iea.org/policies/27897-second-auction-of-european-hydrogen-bank-ehb")
H45V = ("IRC section 45V as amended by the One Big Beautiful Bill Act (2025-07-04)",
        "https://www.troutman.com/insights/navigating-the-one-big-beautiful-bill-act-a-practical-guide/")
OIES = ("OIES ET21", None)

# (key, pathway, region, low, base, high, unit, currency, price_base_date,
#  source_class, (source_name, url), state, note)
SEED = [
    ("electrolyser_installed_capex", "ANY", "ROW", 2000.0, 2300.0, 2600.0, "USD/kW", "USD",
     "2024-01-01", "public_source", IEA, "proposed",
     "Price year 2024, installed system outside China. NOT CONFIRMED: the IEA report "
     "page carries no cost figure and the PDF could not be retrieved on 2026-10-19. "
     "Secondary coverage of the 2026 edition gives USD 1,900-2,500/kW for 2025."),
    ("electrolyser_installed_capex", "ANY", "CN", 600.0, 900.0, 1200.0, "USD/kW", "USD",
     "2024-01-01", "public_source", IEA, "proposed",
     "Price year 2024, Chinese-made system installed in China. NOT CONFIRMED (as the "
     "ROW row). Secondary coverage of the 2026 edition gives USD 500-1,100/kW for 2025."),
    ("electrolyser_installed_capex", "H2_PEM", "US", 1500.0, 2000.0, 2500.0, "USD/kW", "USD",
     "2022-01-01", "public_source", DOE, "approved",
     "2022 dollars; low/base/high are the record's three capex cases. Confirmed."),
    ("electrolyser_system_sec", "H2_PEM", "ANY", 55.2, 57.0, 57.5, "kWh/kg", None,
     None, "public_source", DOE, "approved",
     "Electricity per kg H2 PRODUCED (system: stack + balance of plant). NOT the fuel's "
     "LHV. 55.2 beginning of life, 57.5 lifetime average, ~57 in the record's summary "
     "table. Confirmed."),
    ("stack_life_hours", "H2_PEM", "ANY", None, 40000.0, None, "h", None,
     None, "public_source", DOE, "approved",
     "Replacement interval in operating hours. Confirmed."),
    ("stack_replacement_pct_capex", "H2_PEM", "ANY", None, 0.11, None, "fraction", None,
     None, "public_source", DOE, "approved",
     "Fraction of TOTAL INSTALLED capex per replacement (mainly stacks). Confirmed."),
    ("output_degradation_pct_per_year", "ANY", "ANY", None, 0.01, None, "fraction/yr", None,
     None, "gex_assumption", ("GEX assumption, Hydrogen FM review 2026-10-19", None),
     "approved",
     "To be sourced. DOE Record 24005 gives 4.8 mV/khr stack voltage degradation, which "
     "is not an output rate."),
    ("h2_price_rfnbo", "H2", "EU", 7.0, 8.2, 10.0, "EUR/kg", "EUR",
     "2025-01-01", "public_source", ACER, "approved",
     "Period 2025. Base = HYDRIX 2025 average; range = RFNBO price by origin country. "
     "Figures confirmed via the report's press coverage (pv-magazine, 2025-12-03); "
     "the ACER page itself states an ~8 EUR/kg average production cost."),
    ("h2_price_grey", "H2", "EU", None, 2.0, None, "EUR/kg", "EUR",
     "2025-01-01", "public_source", ACER, "approved",
     "Period January-October 2025, conventional SMR hydrogen. Confirmed as the RFNBO row."),
    ("ppa_price_solar", "ANY", "EU", None, 56.59, None, "EUR/MWh", "EUR",
     "2026-04-01", "public_source", LEVELTEN, "approved",
     "Period Q2 2026, European average of signed deals (PV Tech). NOT LevelTen's P25 "
     "headline index, which is the 25th percentile of offers."),
    ("ehb_premium", "H2", "EU", 0.20, 0.40, 0.60, "EUR/kg", "EUR",
     "2025-01-01", "public_source", EHB, "approved",
     "Fixed premium, round 2 general topic, winners' bid range 0.20-0.60 (clearing "
     "0.60). The source gives a range only: base is its MIDPOINT, not a published value."),
    ("subsidy_45v_max", "H2", "US", None, 3.28, None, "USD/kg", "USD",
     "2026-01-01", "public_source", H45V, "proposed",
     "Top tier. Construction must begin before 2028-01-01 (confirmed). The 3.28 "
     "inflation-adjusted amount is NOT CONFIRMED; the statute's base amount is 3.00."),
    ("debt_gearing", "ANY", "ANY", 0.60, 0.65, 0.70, "fraction", None,
     None, "public_source", OIES, "proposed",
     "Senior debt share of capex. NOT CONFIRMED: OIES ET21 was not located. The source "
     "gives a range only: base is its MIDPOINT."),
]


def _ref_id(key: str, pathway: str, region: str) -> str:
    """Deterministic, so a rebuild reproduces the same ids and version 1."""
    return str(uuid.uuid5(_NS, f"{key}|{pathway}|{region}|seed"))


def upgrade() -> None:
    op.create_table(
        "reference_parameter",
        sa.Column("ref_id", sa.Text(), primary_key=True),
        sa.Column("parameter_key", sa.Text(), nullable=False),
        sa.Column("pathway", sa.Text(), nullable=False, server_default="ANY"),
        sa.Column("region", sa.Text(), nullable=False, server_default="ANY"),
        sa.Column("value_low", sa.Float()),
        sa.Column("value_base", sa.Float(), nullable=False),
        sa.Column("value_high", sa.Float()),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text()),
        sa.Column("price_base_date", sa.Text()),
        sa.Column("source_class", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("retrieved_at", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("supersedes_ref_id", sa.Text()),
        sa.Column("state", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("proposed_by", sa.Text(), nullable=False),
        sa.Column("proposed_at", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text()),
        sa.Column("approved_at", sa.Text()),
        sa.Column("rejected_by", sa.Text()),
        sa.Column("rejected_at", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.ForeignKeyConstraint(["supersedes_ref_id"], ["reference_parameter.ref_id"],
                                name="fk_refparam_supersedes"),
        sa.CheckConstraint(
            "state IN ('proposed', 'approved', 'rejected', 'superseded')",
            name="ck_refparam_state"),
        sa.CheckConstraint(
            "source_class IN ('public_source', 'gex_cohort', 'gex_assumption')",
            name="ck_refparam_source_class"),
        sa.CheckConstraint(
            "pathway IN ('H2', 'H2_PEM', 'H2_ALK', 'NH3', 'E_METHANOL', 'E_NG', 'SAF', 'ANY')",
            name="ck_refparam_pathway"),
        sa.CheckConstraint(
            "region ~ '^[A-Z]{2}$' OR region IN ('EU', 'ROW', 'ANY')",
            name="ck_refparam_region"),
        sa.CheckConstraint(
            "(value_low IS NULL OR value_low <= value_base) AND "
            "(value_high IS NULL OR value_base <= value_high)",
            name="ck_refparam_band"),
        sa.CheckConstraint(
            "currency IS NULL OR (currency ~ '^[A-Z]{3}$' AND price_base_date IS NOT NULL)",
            name="ck_refparam_monetary_dated"),
        sa.CheckConstraint(
            "state NOT IN ('approved', 'superseded') OR "
            "(approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_refparam_approval_recorded"),
        sa.CheckConstraint(
            "state <> 'rejected' OR (rejected_by IS NOT NULL AND rejected_at IS NOT NULL)",
            name="ck_refparam_rejection_recorded"),
    )
    op.create_index("idx_refparam_key", "reference_parameter",
                    ["parameter_key", "pathway", "region", "valid_from"])
    # One approved row per (key, pathway, region) at a time.
    op.create_index("uq_refparam_one_approved", "reference_parameter",
                    ["parameter_key", "pathway", "region"], unique=True,
                    postgresql_where=sa.text("state = 'approved'"))

    op.create_table(
        "reference_version",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column("version_number", sa.Integer(), nullable=False, unique=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("ref_ids_json", sa.Text(), nullable=False),
    )

    conn = op.get_bind()
    value_cols = [
        "ref_id", "parameter_key", "pathway", "region", "value_low", "value_base",
        "value_high", "unit", "currency", "price_base_date", "source_class",
        "source_name", "source_url", "retrieved_at", "valid_from", "proposed_by",
        "proposed_at", "note"]
    changed = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in value_cols)
    conn.execute(sa.text(f"""
        CREATE FUNCTION reference_parameter_guard() RETURNS trigger
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
    conn.execute(sa.text("""
        CREATE TRIGGER reference_parameter_guard
        BEFORE UPDATE OR DELETE ON reference_parameter
        FOR EACH ROW EXECUTE FUNCTION reference_parameter_guard()
    """))
    conn.execute(sa.text("""
        CREATE FUNCTION reference_version_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'reference_version is insert-only: create a new version';
        END $$
    """))
    conn.execute(sa.text("""
        CREATE TRIGGER reference_version_guard
        BEFORE UPDATE OR DELETE ON reference_version
        FOR EACH ROW EXECUTE FUNCTION reference_version_guard()
    """))

    for table in TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(
            f"CREATE POLICY {table}_reference_data ON {table} FOR SELECT USING (true)"))
        # Writes are admin-only: reference data is curated, not tenant-authored.
        conn.execute(sa.text(
            f"CREATE POLICY {table}_admin_writes ON {table} "
            f"FOR ALL USING ({ADMIN}) WITH CHECK ({ADMIN})"))
        conn.execute(sa.text(f"REVOKE ALL ON {table} FROM gex_app"))
        conn.execute(sa.text(f"GRANT SELECT, INSERT ON {table} TO gex_app"))
    conn.execute(sa.text(
        f"GRANT UPDATE ({', '.join(LIFECYCLE)}) ON reference_parameter TO gex_app"))

    # ── Seed ────────────────────────────────────────────────────────────────
    insert = sa.text("""
        INSERT INTO reference_parameter
          (ref_id, parameter_key, pathway, region, value_low, value_base, value_high,
           unit, currency, price_base_date, source_class, source_name, source_url,
           retrieved_at, valid_from, state, proposed_by, proposed_at,
           approved_by, approved_at, note)
        VALUES
          (:ref_id, :key, :pathway, :region, :low, :base, :high,
           :unit, :currency, :price_date, :source_class, :source_name, :source_url,
           :retrieved, :valid_from, :state, :actor, :retrieved,
           :approved_by, :approved_at, :note)
    """)
    approved = []
    for (key, pathway, region, low, base, high, unit, currency, price_date,
         source_class, (source_name, source_url), state, note) in SEED:
        ref_id = _ref_id(key, pathway, region)
        conn.execute(insert, dict(
            ref_id=ref_id, key=key, pathway=pathway, region=region, low=low, base=base,
            high=high, unit=unit, currency=currency, price_date=price_date,
            source_class=source_class, source_name=source_name, source_url=source_url,
            retrieved=SEED_DATE, valid_from=SEED_DATE, state=state, actor=SEED_ACTOR,
            approved_by=SEED_ACTOR if state == "approved" else None,
            approved_at=SEED_DATE if state == "approved" else None, note=note))
        if state == "approved":
            approved.append(ref_id)

    conn.execute(sa.text("""
        INSERT INTO reference_version
          (version_id, version_number, created_at, created_by, reason, ref_ids_json)
        VALUES (:vid, 1, :at, :actor, :reason, :ids)
    """), dict(vid=str(uuid.uuid5(_NS, "version-1")), at=SEED_DATE, actor=SEED_ACTOR,
               reason="Seed: values confirmed in the Hydrogen FM review of 2026-10-19",
               ids=json.dumps(sorted(approved))))


def downgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_reference_data ON {table}"))
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_admin_writes ON {table}"))
    conn.execute(sa.text("DROP TRIGGER IF EXISTS reference_version_guard ON reference_version"))
    conn.execute(sa.text(
        "DROP TRIGGER IF EXISTS reference_parameter_guard ON reference_parameter"))
    op.drop_table("reference_version")
    op.drop_table("reference_parameter")
    conn.execute(sa.text("DROP FUNCTION IF EXISTS reference_version_guard()"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS reference_parameter_guard()"))
