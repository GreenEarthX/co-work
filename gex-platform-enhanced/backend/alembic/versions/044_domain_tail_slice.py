"""Domain tail — slice 6b-6.

Revision ID: 044
Revises: 043

The bulk: 35 live domain tables, all but three empty
(gateway_registry 1, pre_cod_snapshots 2, risk_flag_status 1, risk_flag_events 2).

26 are project-scoped and get the standard delegation. The 9 without a
project_id get admin-only, for the reason stated in the loop below.

GENERATED FROM THE LIVE SQLITE SCHEMAS, then reviewed. Hand-writing 35 tables
invites transcription errors; the generator reads PRAGMA table_info and the
stored DDL, so column names, NOT NULLs, composite primary keys, AUTOINCREMENT
and UNIQUE(...) constraints come from the source rather than from memory.

Type fidelity as in every prior slice: timestamps stay TEXT, booleans stay
INTEGER. Storage moves; the type system does not, so a failure cannot be both.

EXCLUDED — the 12 tables with no reference anywhere in app/ (no DDL, no query):
covenant_compliance, drawdown_tranches, equity_contributions, financial_metrics,
pre_cod_metric_snapshots, project_events, project_stakeholders, project_states,
reserve_accounts, service_calls, state_transitions, workflow_checkpoints.
Migrating a dead table makes it look alive. They are slice 6b-7's decision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN = "current_setting('app.current_company_id', true) = 'PLATFORM_ADMIN'"
ME = "current_setting('app.current_company_id', true)"

PROJECT_SCOPED = ['additionality_assessments', 'adjacency_cache', 'adversarial_reviews', 'availability_reports', 'carbon_attribution_events', 'commitment_records', 'deliveries', 'dfi_criteria', 'dfi_impact_kpis', 'drawdown_schedules', 'gateway_registry', 'mass_balance_lots', 'matrix_events', 'matrix_rooms', 'model_base_case', 'offtake_contracts', 'pathway_claims', 'plant_data', 'pre_cod_snapshots', 'production_readings', 'quality_certificates', 'risk_flag_events', 'risk_flag_status', 'settlement_events', 'sovereign_instruments', 'spend_waves']
ALL_TABLES = ['additionality_assessments', 'adjacency_cache', 'admin_log', 'adversarial_findings', 'adversarial_handoffs', 'adversarial_reviews', 'approval_decisions', 'availability_reports', 'carbon_attribution_events', 'commitment_records', 'corpus_status_transitions', 'corpus_taxonomy_map', 'corpus_versions', 'deliveries', 'dfi_criteria', 'dfi_impact_kpis', 'drawdown_schedules', 'external_projects', 'gateway_registry', 'mass_balance_lots', 'matrix_events', 'matrix_members', 'matrix_rooms', 'model_base_case', 'offtake_contracts', 'pathway_claims', 'plant_data', 'pre_cod_snapshots', 'production_readings', 'quality_certificates', 'risk_flag_events', 'risk_flag_status', 'settlement_events', 'sovereign_instruments', 'spend_waves']
SEQUENCES = ['admin_log', 'matrix_events', 'risk_flag_events']


def upgrade() -> None:
    op.create_table(
        "additionality_assessments",
        sa.Column("assessment_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("dfi_institution", sa.Text(), nullable=False),
        sa.Column("tranche_amount_eur", sa.Float(), nullable=False),
        sa.Column("total_capex_eur", sa.Float(), nullable=False),
        sa.Column("irr_with_dfi", sa.Float(), nullable=False),
        sa.Column("irr_without_dfi", sa.Float(), nullable=False),
        sa.Column("commercial_hurdle_rate", sa.Float(), nullable=False),
        sa.Column("blended_wacc", sa.Float(), nullable=False),
        sa.Column("all_commercial_wacc", sa.Float(), nullable=False),
        sa.Column("commercial_debt_pct", sa.Float(), nullable=False),
        sa.Column("total_concessional_pct", sa.Float(), nullable=False),
        sa.Column("grant_pct", sa.Float(), nullable=False),
        sa.Column("jobs_construction", sa.Integer()),
        sa.Column("jobs_operational", sa.Integer()),
        sa.Column("emissions_avoided_tco2e", sa.Float()),
        sa.Column("energy_access_mwh", sa.Float()),
        sa.Column("host_nation_gdp_eur", sa.Float()),
        sa.Column("female_workforce_pct", sa.Float()),
        sa.Column("local_procurement_pct", sa.Float()),
        sa.Column("debt_swap_id", sa.Text()),
        sa.Column("sovereign_debt_retired_usd", sa.Float()),
        sa.Column("carbon_attribution_pct", sa.Float()),
        sa.Column("additionality_status", sa.Text(), nullable=False),
        sa.Column("overall_verdict", sa.Text(), nullable=False),
        sa.Column("impact_score", sa.Float()),
        sa.Column("g10_pre_condition_met", sa.Integer()),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("assessed_by", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "adjacency_cache",
        sa.Column("project_id", sa.Text(), primary_key=True),
        sa.Column("density_score", sa.Float(), nullable=False),
        sa.Column("cohort_n", sa.Integer(), nullable=False),
        sa.Column("cohort_dscr_p25", sa.Float(), nullable=False),
        sa.Column("cohort_dscr_p50", sa.Float(), nullable=False),
        sa.Column("cohort_dscr_p75", sa.Float(), nullable=False),
        sa.Column("cohort_completion_rate", sa.Float(), nullable=False),
        sa.Column("cohort_tie_p50", sa.Float(), nullable=False),
        sa.Column("confidence_flag", sa.Integer(), nullable=False),
        sa.Column("fuel_pathway", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("certifier_ecosystem", sa.Text(), nullable=False),
        sa.Column("dimension_matches", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "admin_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("admin_user_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text()),
        sa.Column("target_user_id", sa.Text()),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("before_state", sa.Text()),
        sa.Column("after_state", sa.Text()),
    )

    op.create_table(
        "adversarial_findings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("review_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("owner_role", sa.Text()),
        sa.Column("blocking", sa.Integer(), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "adversarial_handoffs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("review_id", sa.Text(), nullable=False),
        sa.Column("from_role", sa.Text()),
        sa.Column("to_role", sa.Text(), nullable=False),
        sa.Column("plain_language", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at", sa.Text()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "adversarial_reviews",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text()),
        sa.Column("target_id", sa.Text()),
        sa.Column("target_route", sa.Text()),
        sa.Column("screen_title", sa.Text()),
        sa.Column("prompt_preset_id", sa.Text()),
        sa.Column("prompt_card_id", sa.Text()),
        sa.Column("agent_id", sa.Text()),
        sa.Column("employee_name", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("subtype", sa.Text()),
        sa.Column("sophistication", sa.Integer()),
        sa.Column("summary", sa.Text()),
        sa.Column("what_it_seems_to_do", sa.Text()),
        sa.Column("what_it_gets_wrong", sa.Text()),
        sa.Column("what_is_missing", sa.Text()),
        sa.Column("what_feels_dangerous", sa.Text()),
        sa.Column("cooperation_risk", sa.Text()),
        sa.Column("trust_increase_needed", sa.Text()),
        sa.Column("clean_handoff_note", sa.Text()),
        sa.Column("final_stance", sa.Text(), nullable=False),
        sa.Column("trust_delta", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by", sa.Text()),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text()),
    )

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("approver_user_id", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("reason_text", sa.Text()),
        sa.Column("decided_at", sa.Text()),
    )

    op.create_table(
        "availability_reports",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Text(), nullable=False),
        sa.Column("period_end", sa.Text(), nullable=False),
        sa.Column("availability_pct", sa.Float(), nullable=False),
        sa.Column("guaranteed_availability_pct", sa.Float(), nullable=False),
        sa.Column("penalty_triggered", sa.Integer()),
        sa.Column("penalty_amount", sa.Float()),
        sa.Column("is_material_breach", sa.Integer()),
    )

    op.create_table(
        "carbon_attribution_events",
        sa.Column("attribution_id", sa.Text(), primary_key=True),
        sa.Column("settlement_id", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("host_nation", sa.Text(), nullable=False),
        sa.Column("host_nation_share_pct", sa.Float(), nullable=False),
        sa.Column("buyer_share_pct", sa.Float(), nullable=False),
        sa.Column("carbon_volume_tonnes", sa.Float(), nullable=False),
        sa.Column("sovereign_certifier", sa.Text(), nullable=False),
        sa.Column("debt_swap_id", sa.Text()),
        sa.Column("attribution_methodology", sa.Text()),
        sa.Column("attribution_status", sa.Text(), nullable=False),
        sa.Column("registry_ref", sa.Text()),
        sa.Column("audit_hash", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "commitment_records",
        sa.Column("commitment_id", sa.Text(), primary_key=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("initiator_user_id", sa.Text(), nullable=False),
        sa.Column("initiator_company_id", sa.Text(), nullable=False),
        sa.Column("initiator_timestamp", sa.Text(), nullable=False),
        sa.Column("initiator_signature", sa.Text(), nullable=False),
        sa.Column("approvers_json", sa.Text(), nullable=False),
        sa.Column("counterparty_user_id", sa.Text()),
        sa.Column("counterparty_company_id", sa.Text()),
        sa.Column("counterparty_timestamp", sa.Text()),
        sa.Column("counterparty_signature", sa.Text()),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("record_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text()),
        sa.Column("created_at", sa.Text()),
    )

    op.create_table(
        "corpus_status_transitions",
        sa.Column("transition_id", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_project_id", sa.Text(), nullable=False),
        sa.Column("from_version", sa.Text(), nullable=False),
        sa.Column("to_version", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text()),
        sa.Column("to_status", sa.Text()),
        sa.Column("fuel_id", sa.Text()),
        sa.Column("jurisdiction", sa.Text()),
        sa.Column("observed_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "corpus_taxonomy_map",
        sa.Column("source", sa.Text()),
        sa.Column("field", sa.Text()),
        sa.Column("raw_label", sa.Text()),
        sa.Column("gex_value", sa.Text()),
        sa.Column("mapped_by", sa.Text()),
        sa.Column("mapped_at", sa.Text()),
        sa.PrimaryKeyConstraint("source", "field", "raw_label"),
    )

    op.create_table(
        "corpus_versions",
        sa.Column("version_id", sa.Text(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.Text(), nullable=False),
        sa.Column("imported_by", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("quarantined", sa.Integer(), nullable=False),
        sa.UniqueConstraint("source", "source_version"),
    )

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("volume_mt", sa.Float(), nullable=False),
        sa.Column("quality_verified", sa.Integer()),
        sa.Column("verified_ghg_intensity", sa.Float()),
        sa.Column("quality_certificate_number", sa.Text()),
        sa.Column("title_transferred", sa.Integer()),
        sa.Column("title_transfer_date", sa.Text()),
        sa.Column("delivery_status", sa.Text(), nullable=False),
        sa.Column("invoice_amount", sa.Float()),
        sa.Column("payment_received", sa.Integer()),
    )

    op.create_table(
        "dfi_criteria",
        sa.Column("criterion_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("criterion_code", sa.Text(), nullable=False),
        sa.Column("criterion_name", sa.Text(), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("evidence_ref", sa.Text()),
        sa.Column("responsible_actor", sa.Text(), nullable=False),
        sa.Column("target_date", sa.Text()),
        sa.Column("blocks_drawdown", sa.Integer(), nullable=False),
        sa.Column("last_reviewed", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "dfi_impact_kpis",
        sa.Column("kpi_id", sa.Text(), primary_key=True),
        sa.Column("assessment_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("dfi_institution", sa.Text(), nullable=False),
        sa.Column("reporting_period", sa.Text(), nullable=False),
        sa.Column("jobs_construction", sa.Integer()),
        sa.Column("jobs_operational", sa.Integer()),
        sa.Column("emissions_avoided", sa.Float()),
        sa.Column("energy_access_mwh", sa.Float()),
        sa.Column("female_pct", sa.Float()),
        sa.Column("local_procurement_pct", sa.Float()),
        sa.Column("host_nation_gdp_eur", sa.Float()),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "drawdown_schedules",
        sa.Column("drawdown_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("tranche_id", sa.Text(), nullable=False),
        sa.Column("quarter", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("amount_native", sa.Float()),
        sa.Column("fx_rate_used", sa.Float()),
        sa.Column("milestone_trigger", sa.Text(), nullable=False),
        sa.Column("milestone_evidence_ref", sa.Text()),
        sa.Column("ie_signoff_ref", sa.Text()),
        sa.Column("cps_satisfied", sa.Text(), nullable=False),
        sa.Column("drawdown_status", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "external_projects",
        sa.Column("row_id", sa.Text(), primary_key=True),
        sa.Column("version_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_project_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("fuel_id", sa.Text()),
        sa.Column("pathway_class", sa.Text()),
        sa.Column("technology_class", sa.Text()),
        sa.Column("jurisdiction", sa.Text()),
        sa.Column("capacity_value", sa.Float()),
        sa.Column("capacity_unit", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("announced_year", sa.Integer()),
        sa.Column("fid_year", sa.Integer()),
        sa.Column("cod_year", sa.Integer()),
        sa.Column("quarantined", sa.Integer(), nullable=False),
        sa.Column("quarantine_reason", sa.Text()),
        sa.Column("raw", sa.Text(), nullable=False),
    )

    op.create_table(
        "gateway_registry",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("gateway_name", sa.Text(), nullable=False),
        sa.Column("cert_fingerprint", sa.Text()),
        sa.Column("ip_allowlist", sa.Text()),
        sa.Column("active", sa.Integer()),
        sa.Column("registered_at", sa.Text()),
        sa.Column("last_seen", sa.Text()),
    )

    op.create_table(
        "mass_balance_lots",
        sa.Column("lot_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("molecule", sa.Text(), nullable=False),
        sa.Column("production_date", sa.Text(), nullable=False),
        sa.Column("total_volume_kg", sa.Float(), nullable=False),
        sa.Column("allocated_volume_kg", sa.Float(), nullable=False),
        sa.Column("remaining_volume_kg", sa.Float(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("certification_pathway", sa.Text()),
        sa.Column("carbon_intensity_gco2e_mj", sa.Float()),
        sa.Column("audit_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "matrix_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text()),
        sa.Column("project_id", sa.Text()),
        sa.Column("gate_id", sa.Text()),
        sa.Column("actor_user_id", sa.Text()),
        sa.Column("company_id", sa.Text()),
        sa.Column("metadata", sa.Text()),
        sa.Column("abac_decision", sa.Text()),
    )

    op.create_table(
        "matrix_members",
        sa.Column("room_id", sa.Text()),
        sa.Column("user_id", sa.Text()),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("power_level", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.Text()),
        sa.Column("left_at", sa.Text()),
        sa.PrimaryKeyConstraint("room_id", "user_id"),
    )

    op.create_table(
        "matrix_rooms",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("gate_id", sa.Text()),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("created_at", sa.Text()),
        sa.Column("archived_at", sa.Text()),
    )

    op.create_table(
        "model_base_case",
        sa.Column("claim_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("pathway_id", sa.Text()),
        sa.Column("subject_node", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text()),
        sa.Column("cost_basis_hash", sa.Text(), nullable=False),
        sa.Column("capex_eur", sa.Float()),
        sa.Column("opex_eur_per_year", sa.Float()),
        sa.Column("lcop", sa.Float()),
        sa.Column("nameplate_capacity", sa.Float()),
        sa.Column("nameplate_unit", sa.Text()),
        sa.Column("run_evidence_id", sa.Text()),
        sa.Column("supersedes_claim_id", sa.Text()),
        sa.Column("superseded_by", sa.Text()),
        sa.Column("reconciliation_group_id", sa.Text()),
        sa.Column("approved_by", sa.Text()),
        sa.Column("approval_decision_id", sa.Text()),
        sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("valid_to", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "offtake_contracts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("buyer_id", sa.Text(), nullable=False),
        sa.Column("buyer_credit_rating", sa.Text()),
        sa.Column("contract_type", sa.Text(), nullable=False),
        sa.Column("annual_volume_mt", sa.Float(), nullable=False),
        sa.Column("minimum_availability_pct", sa.Float(), nullable=False),
        sa.Column("performance_penalty_rate", sa.Float(), nullable=False),
        sa.Column("has_cfd_support", sa.Integer()),
        sa.Column("is_active", sa.Integer()),
    )

    op.create_table(
        "pathway_claims",
        sa.Column("claim_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("pathway_id", sa.Text()),
        sa.Column("subject_node", sa.Text()),
        sa.Column("claim_type", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("unit", sa.Text()),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("method", sa.Text()),
        sa.Column("evidence_id", sa.Text()),
        sa.Column("supersedes_claim_id", sa.Text()),
        sa.Column("superseded_by", sa.Text()),
        sa.Column("approved_by", sa.Text()),
        sa.Column("approval_decision_id", sa.Text()),
        sa.Column("valid_from", sa.Text(), nullable=False),
        sa.Column("valid_to", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "plant_data",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("gateway_id", sa.Text(), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("sha256_hash", sa.Text(), nullable=False),
        sa.Column("received_at", sa.Text()),
    )

    op.create_table(
        "pre_cod_snapshots",
        sa.Column("snapshot_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.Text(), nullable=False),
        sa.Column("cec_value", sa.Float()),
        sa.Column("fri_value", sa.Float()),
        sa.Column("rmr_value", sa.Float()),
        sa.Column("cbm_value", sa.Float()),
        sa.Column("llcr_value", sa.Float()),
        sa.Column("suc_value", sa.Float()),
        sa.Column("overall_score", sa.Float()),
        sa.Column("fid_signal", sa.Text()),
        sa.Column("capital_gap_eur", sa.Float()),
        sa.Column("report_json", sa.Text(), nullable=False),
    )

    op.create_table(
        "production_readings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("created_at", sa.Text()),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("facility_id", sa.Text(), nullable=False),
        sa.Column("reading_timestamp", sa.Text(), nullable=False),
        sa.Column("volume_produced", sa.Float(), nullable=False),
        sa.Column("production_rate", sa.Float(), nullable=False),
        sa.Column("ghg_intensity", sa.Float(), nullable=False),
        sa.Column("purity", sa.Float(), nullable=False),
        sa.Column("renewable_electricity_pct", sa.Float(), nullable=False),
        sa.Column("production_status", sa.Text(), nullable=False),
        sa.Column("availability_pct", sa.Float(), nullable=False),
    )

    op.create_table(
        "quality_certificates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("delivery_id", sa.Text(), nullable=False),
        sa.Column("certificate_number", sa.Text(), nullable=False),
        sa.Column("ghg_intensity_measured", sa.Float(), nullable=False),
        sa.Column("purity_measured", sa.Float(), nullable=False),
        sa.Column("red_iii_compliant", sa.Integer()),
        sa.Column("v45_compliant", sa.Integer()),
        sa.Column("is_valid", sa.Integer()),
    )

    op.create_table(
        "risk_flag_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("flag_id", sa.Text(), nullable=False),
        sa.Column("old_status", sa.Text()),
        sa.Column("new_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("at", sa.Text(), nullable=False),
    )

    op.create_table(
        "risk_flag_status",
        sa.Column("project_id", sa.Text()),
        sa.Column("flag_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "flag_id"),
    )

    op.create_table(
        "settlement_events",
        sa.Column("settlement_id", sa.Text(), primary_key=True),
        sa.Column("contract_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("token_id", sa.Text(), nullable=False),
        sa.Column("counterparty_buyer_id", sa.Text(), nullable=False),
        sa.Column("counterparty_seller_id", sa.Text(), nullable=False),
        sa.Column("settlement_type", sa.Text(), nullable=False),
        sa.Column("settlement_status", sa.Text(), nullable=False),
        sa.Column("volume_kg", sa.Float(), nullable=False),
        sa.Column("price_per_kg", sa.Float(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("payment_reference", sa.Text()),
        sa.Column("settlement_date", sa.Text()),
        sa.Column("matrix_thread_id", sa.Text()),
        sa.Column("audit_hash", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "sovereign_instruments",
        sa.Column("instrument_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("host_nation", sa.Text(), nullable=False),
        sa.Column("instrument_type", sa.Text(), nullable=False),
        sa.Column("instrument_status", sa.Text(), nullable=False),
        sa.Column("counterparty", sa.Text(), nullable=False),
        sa.Column("nominal_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("carbon_commitment_tonnes", sa.Float()),
        sa.Column("swap_ratio", sa.Float()),
        sa.Column("effective_date", sa.Text()),
        sa.Column("maturity_date", sa.Text()),
        sa.Column("linked_token_ids", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_changed_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "spend_waves",
        sa.Column("spend_wave_id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("package_id", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("amount_drawn", sa.Float(), nullable=False),
        sa.Column("capital_layer", sa.Text(), nullable=False),
        sa.Column("tranche_id", sa.Text()),
        sa.Column("phase_at_drawdown", sa.Text(), nullable=False),
        sa.Column("fid_year", sa.Integer(), nullable=False),
        sa.Column("equity_first_loss", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    conn = op.get_bind()
    for table in ALL_TABLES:
        conn.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        if table in PROJECT_SCOPED:
            using = (f"{ADMIN} OR app_company_owns_project(project_id, {ME}) "
                     f"OR app_company_has_project_access(project_id, {ME})")
        else:
            # No project_id: no honest tenant policy exists, so admin-only
            # rather than open. Same reasoning as the tb_* tables in 036 —
            # a policy that only appears to isolate is worse than none.
            using = ADMIN
        conn.execute(sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ({using})"))
        conn.execute(sa.text(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gex_app"))
    for t in SEQUENCES:
        conn.execute(sa.text(
            f"GRANT USAGE, SELECT ON SEQUENCE {t}_id_seq TO gex_app"))


def downgrade() -> None:
    conn = op.get_bind()
    for table in ALL_TABLES:
        conn.execute(sa.text(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    for table in reversed(ALL_TABLES):
        op.drop_table(table)
