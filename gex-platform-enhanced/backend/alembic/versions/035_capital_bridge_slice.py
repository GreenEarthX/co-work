"""Capital bridge + development packages — slice 5.

Revision ID: 035
Revises: 034

The plan's largest slice: capital_bridge.py (1234 lines) and
development_packages.py (1398). Gated by 39 characterization tests written
first — see tests/test_slice5_characterization.py.

TWO KINDS OF TABLE HERE
-----------------------
Ten are PROJECT-SCOPED and get tenant-isolation policies delegating to the 032
SECURITY DEFINER helpers, exactly as slices 3 and 4 do.

`fuel_defaults` is REFERENCE DATA — keyed by fuel_type, no project_id, the same
five rows for everyone. It gets RLS enabled with a read-open policy rather than
being left unprotected: a table with RLS off in a schema where everything else
has it on reads as an oversight, and the next person cannot tell "deliberately
public" from "forgotten". Writes still require the app role.

NOTE ON fuel_defaults: it duplicates the in-code `FUEL_DEFAULTS` dict. The
characterization tests pin that the two AGREE today; this migration does not
resolve the duplication, it preserves it. Collapsing to one source is a separate
change.

A SECOND HASH CHAIN — AND IT IS ALREADY BROKEN
----------------------------------------------
`development_package_events` carries event_hash/prev_hash, like evidence_ledger.
Unlike that one it has real rows (18), and **7 of them cannot be verified from
stored data** — a defect that PREDATES this migration:

    _log_event hashes new_val as a typed object, but stores str(new_val).
    They coincide only for plain strings; floats, lists and enums diverge.

Pinned at exactly 7 in the characterization tests so the copy must reproduce the
state precisely. This migration deliberately changes nothing about it — a
faithful copy of broken data is correct here, because "fix" and "move" must stay
separable. Fixing _log_event will not repair the 7 (their pre-image was never
persisted); it makes future events verifiable.

TYPE FIDELITY: timestamps stay TEXT, as in 030/034, for the same reason.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "gex_app"

PROJECT_SCOPED = (
    "project_control",
    "capital_stack_tranches",
    "spend_wave",
    "drawdown_quarters",
    "personnel_plan",
    "post_cod_schedule",
    "dfi_criteria_status",
    "development_packages",
    "development_package_events",
    "package_evidence",
)


def upgrade() -> None:
    # ── Reference data ──────────────────────────────────────────────────────
    op.create_table(
        "fuel_defaults",
        sa.Column("fuel_type", sa.Text(), primary_key=True),
        sa.Column("fuel_label", sa.Text(), nullable=False),
        sa.Column("specific_energy_kwh_per_kg_h2", sa.Float(), nullable=False),
        sa.Column("product_yield_t_per_t_h2", sa.Float(), nullable=False),
        sa.Column("base_price_eur_per_t", sa.Float(), nullable=False),
        sa.Column("green_premium_eur_per_t", sa.Float(), nullable=False),
        sa.Column("typical_availability", sa.Float(), nullable=False),
        sa.Column("dsra_months", sa.Integer(), nullable=False),
        sa.Column("contingency_pct", sa.Float(), nullable=False),
        sa.Column("typical_offtake_counterparty", sa.Text()),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    # ── CONTROL sheet ───────────────────────────────────────────────────────
    op.create_table(
        "project_control",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("fuel_type", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text()),
        sa.Column("base_currency", sa.Text()),
        sa.Column("nameplate_mw", sa.Float(), nullable=False),
        sa.Column("availability_factor", sa.Float(), nullable=False),
        sa.Column("specific_energy_kwh_per_kg_h2", sa.Float(), nullable=False),
        sa.Column("product_yield_t_per_t_h2", sa.Float(), nullable=False),
        sa.Column("first_year_ramp_factor", sa.Float()),
        sa.Column("offtake_price_eur_per_t", sa.Float(), nullable=False),
        sa.Column("green_premium_eur_per_t", sa.Float()),
        sa.Column("offtake_duration_years", sa.Integer()),
        sa.Column("target_counterparty", sa.Text()),
        sa.Column("fel_1_year", sa.Integer(), nullable=False),
        sa.Column("fel_2_year", sa.Integer(), nullable=False),
        sa.Column("feed_year", sa.Integer(), nullable=False),
        sa.Column("fid_year", sa.Integer(), nullable=False),
        sa.Column("cod_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("total_capex_eur", sa.Float()),
        sa.Column("contingency_pct", sa.Float()),
        sa.Column("dsra_months", sa.Integer()),
        sa.Column("fixed_om_eur_per_yr", sa.Float()),
        sa.Column("variable_opex_eur_per_t", sa.Float()),
        sa.Column("ga_eur_per_yr", sa.Float()),
        sa.Column("insurance_pct_of_capex", sa.Float()),
        sa.Column("cert_advisory_eur_per_yr", sa.Float()),
        sa.Column("owner_user_id", sa.Text()),
        sa.Column("company_id", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text()),
    )

    # ── Capital stack ───────────────────────────────────────────────────────
    op.create_table(
        "capital_stack_tranches",
        sa.Column("tranche_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("tranche_type", sa.Text(), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("pct_of_capex", sa.Float(), nullable=False),
        sa.Column("rate_pct", sa.Float()),
        sa.Column("tenor_years", sa.Integer()),
        sa.Column("grace_years", sa.Integer()),
        sa.Column("drawdown_method", sa.Text()),
        sa.Column("first_repay_year", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_cst_project", "capital_stack_tranches", ["project_id"])

    op.create_table(
        "spend_wave",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("tranche_id", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_spend_project", "spend_wave", ["project_id"])

    op.create_table(
        "drawdown_quarters",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("tranche_id", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("amount_eur", sa.Float(), nullable=False),
        sa.Column("milestone_trigger", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_ddq_project", "drawdown_quarters", ["project_id"])

    op.create_table(
        "personnel_plan",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("role_name", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("fte_count", sa.Float(), nullable=False),
        sa.Column("daily_rate_eur", sa.Float(), nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_pers_project", "personnel_plan", ["project_id"])

    op.create_table(
        "post_cod_schedule",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("production_t", sa.Float()),
        sa.Column("revenue_eur", sa.Float()),
        sa.Column("opex_eur", sa.Float()),
        sa.Column("ebitda_eur", sa.Float()),
        sa.Column("debt_service_eur", sa.Float()),
        sa.Column("cfads_eur", sa.Float()),
        sa.Column("dscr", sa.Float()),
        sa.Column("dscr_covenant_min", sa.Float()),
        sa.Column("cash_after_ds_eur", sa.Float()),
        sa.Column("dsra_topup_eur", sa.Float()),
        sa.Column("available_for_dist_eur", sa.Float()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_pcs_project", "post_cod_schedule", ["project_id"])

    op.create_table(
        "dfi_criteria_status",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("criterion_name", sa.Text(), nullable=False),
        sa.Column("dfi_requirement", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("gex_note", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_dfi_project", "dfi_criteria_status", ["project_id"])

    # ── Development packages ────────────────────────────────────────────────
    op.create_table(
        "development_packages",
        sa.Column("package_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("package_name", sa.Text(), nullable=False),
        sa.Column("package_type", sa.Text(), nullable=False),
        sa.Column("phase_required", sa.Text(), nullable=False),
        sa.Column("discipline_owner", sa.Text(), nullable=False),
        sa.Column("cost_amount", sa.Float(), nullable=False),
        sa.Column("cost_p10", sa.Float()),
        sa.Column("cost_p90", sa.Float()),
        sa.Column("estimate_class", sa.Text(), nullable=False),
        sa.Column("risk_removed", sa.Text(), nullable=False),
        sa.Column("capital_eligible", sa.Text(), nullable=False),
        sa.Column("unlock_condition", sa.Text(), nullable=False),
        sa.Column("drawdown_method", sa.Text(), nullable=False),
        sa.Column("downstream_effect", sa.Text(), nullable=False),
        sa.Column("gex_gate", sa.Text()),
        sa.Column("evidence_refs", sa.Text(), nullable=False),
        sa.Column("workflow_state", sa.Text(), nullable=False),
        sa.Column("concessional_tranche_id", sa.Text()),
        sa.Column("debt_swap_id", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("currency", sa.Text()),
        sa.Column("fx_hedge_id", sa.Text()),
        sa.Column("aace_class_history", sa.Text(), nullable=False),
        sa.Column("personnel_breakdown", sa.Text(), nullable=False),
        sa.Column("verification_state", sa.Text(), nullable=False),
        sa.Column("capital_status", sa.Text(), nullable=False),
        sa.Column("opex_effect", sa.Float()),
        sa.Column("opex_effect_tag", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_changed_by", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        # The two ORTHOGONAL ladders. Constrained here so a bad value cannot be
        # written at all — the characterization tests pin the transition tables,
        # this pins the domain.
        sa.CheckConstraint(
            "workflow_state IN ('identified','scoped','costed','evidenced',"
            "'eligible','approved','committed','drawable','drawn','verified',"
            "'closed','propagated')", name="ck_dev_pkg_workflow_state"),
        sa.CheckConstraint(
            "capital_status IN ('NOT_ELIGIBLE','THEORETICALLY_ELIGIBLE',"
            "'INDICATED','COMMITTED','DRAWABLE','DRAWN')",
            name="ck_dev_pkg_capital_status"),
    )
    op.create_index("idx_devpkg_project", "development_packages", ["project_id"])
    op.create_index("idx_devpkg_state", "development_packages", ["workflow_state"])

    op.create_table(
        "development_package_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("package_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("field_changed", sa.Text()),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("event_hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    # The chain is walked per package in insertion order — see _log_event.
    op.create_index("idx_devpkgev_chain", "development_package_events",
                    ["package_id", "created_at"])
    op.create_index("idx_devpkgev_project", "development_package_events", ["project_id"])

    op.create_table(
        "package_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("package_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column("uploaded_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_pkgev_package", "package_evidence", ["package_id"])
    op.create_index("idx_pkgev_project", "package_evidence", ["project_id"])

    # NOTE: no FK from package_evidence.package_id to development_packages.
    # SQLite never enforced it and the characterization test confirms there are
    # no orphans today, but adding the constraint in the same change as the move
    # would make an FK rejection look like a copy failure. Separate change.

    conn = op.get_bind()
    for table in PROJECT_SCOPED:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_isolation
            ON {table}
            FOR ALL
            USING (
                current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'
                OR app_company_owns_project(
                       project_id, current_setting('app.current_company_id', true))
                OR app_company_has_project_access(
                       project_id, current_setting('app.current_company_id', true))
            )
        """))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}"))

    # Reference data: readable by any tenant, RLS ON so it is visibly
    # deliberate rather than apparently forgotten.
    conn.execute(sa.text("ALTER TABLE fuel_defaults ENABLE ROW LEVEL SECURITY"))
    conn.execute(sa.text("ALTER TABLE fuel_defaults FORCE ROW LEVEL SECURITY"))
    conn.execute(sa.text("""
        CREATE POLICY fuel_defaults_reference_data
        ON fuel_defaults
        FOR SELECT
        USING (true)
    """))
    conn.execute(sa.text(f"GRANT SELECT ON fuel_defaults TO {APP_ROLE}"))
    conn.execute(sa.text(
        f"GRANT USAGE, SELECT ON SEQUENCE package_evidence_id_seq TO {APP_ROLE}"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in PROJECT_SCOPED:
        conn.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    conn.execute(sa.text(
        "DROP POLICY IF EXISTS fuel_defaults_reference_data ON fuel_defaults"))
    for table in ("package_evidence", "development_package_events",
                  "development_packages", "dfi_criteria_status", "post_cod_schedule",
                  "personnel_plan", "drawdown_quarters", "spend_wave",
                  "capital_stack_tranches", "project_control", "fuel_defaults"):
        op.drop_table(table)
