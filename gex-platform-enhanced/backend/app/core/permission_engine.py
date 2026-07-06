"""
GEX Permission Engine v1.0 — Feature-Level Access Control
============================================================
Enterprise-grade permission matrix for CISO administration.

Architecture (two-layer model):
    Layer 1: ABAC (abac.py)           — Data sensitivity rules R0-R6, trade rules R7-R9
    Layer 2: Permission Engine (this) — Feature-level screen/action access

The permission engine maps:
    (entity_type × employee_role) → set of 165 permission strings

With:
    - Capability-based extensions for prosumers (PRODUCE, OFFTAKE, SELL, TRADE, …)
    - Context conditions (credit gate, geofence, KYC, mandated-lender, token_ready)
    - Per-user overrides (CISO can grant/revoke individual permissions)

Inspired by Hoop's group-first model:
    - Permissions are assigned to PROFILES (groups), not individual users
    - Users inherit by profile membership
    - CISO manages profile-to-permission mappings + individual overrides

Usage:
    from app.core.permission_engine import check_permission, get_effective_permissions

    result = check_permission(user_attrs, "gam.supply.token.mint")
    perms  = get_effective_permissions(user_attrs)
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from app.core.config import settings


# ═══════════════════════════════════════════════════════════════
# 1. TYPES
# ═══════════════════════════════════════════════════════════════

class AccessTier(str, Enum):
    """Classification of how sensitive/restricted a permission is."""
    PUBLIC = "PUBLIC"            # All authenticated users
    STAKEHOLDER = "STAKEHOLDER"  # Project stakeholders only
    PRIVILEGED = "PRIVILEGED"    # Specific roles/functions only
    ADMIN = "ADMIN"              # CISO / platform admin only


@dataclass
class PermissionDef:
    """Registry entry for a single permission."""
    perm_id: int
    perm_string: str
    module: str
    sub_service: str
    resource: str
    action: str
    description: str
    access_tier: AccessTier
    context_conditions: list[str] = field(default_factory=list)


@dataclass
class PermissionResult:
    """Result of a permission check — includes reasoning for audit."""
    allowed: bool
    perm_string: str
    reason: str
    profile_key: str
    conditions_evaluated: list[dict] = field(default_factory=list)
    override_applied: bool = False


# ═══════════════════════════════════════════════════════════════
# 2. PERMISSION REGISTRY — All 165 permissions from Book3.csv
# ═══════════════════════════════════════════════════════════════

PERMISSIONS: dict[str, PermissionDef] = {}


def _r(pid, ps, mod, sub, res, act, desc, tier=AccessTier.STAKEHOLDER, ctx=None):
    """Register a permission."""
    PERMISSIONS[ps] = PermissionDef(pid, ps, mod, sub, res, act, desc, tier, ctx or [])


# ── ORCHESTRATOR (14 perms: #30-43) ──────────────────────────
_r(30, "orchestrator.hub.orchestrator.view", "orchestrator", "hub", "orchestrator", "view",
   "View the main orchestrator hub (tabs: portfolio + team)", AccessTier.PRIVILEGED)
_r(31, "orchestrator.portfolio.portfolio.view", "orchestrator", "portfolio", "portfolio", "view",
   "View all owned plants with summary cards", AccessTier.PRIVILEGED)
_r(32, "orchestrator.portfolio.plant.navigate_dashboard", "orchestrator", "portfolio", "plant", "navigate_dashboard",
   "Navigate to Plant Dashboard from portfolio", AccessTier.PRIVILEGED)
_r(33, "orchestrator.portfolio.plant.navigate_canvas", "orchestrator", "portfolio", "plant", "navigate_canvas",
   "Navigate to Plant Canvas from portfolio", AccessTier.PRIVILEGED)
_r(34, "orchestrator.portfolio.plant.create", "orchestrator", "portfolio", "plant", "create",
   "Create new plant from portfolio", AccessTier.PRIVILEGED,
   ["requires_capability:PRODUCE"])
_r(35, "orchestrator.team.team_member.view", "orchestrator", "team", "team_member", "view",
   "View list of all team members", AccessTier.PRIVILEGED)
_r(36, "orchestrator.team.team_member.invite", "orchestrator", "team", "team_member", "invite",
   "Invite a new team member", AccessTier.PRIVILEGED)
_r(37, "orchestrator.team.team_member.edit", "orchestrator", "team", "team_member", "edit",
   "Edit team member details (name, email, role, org)", AccessTier.PRIVILEGED)
_r(38, "orchestrator.team.team_member.deactivate", "orchestrator", "team", "team_member", "deactivate",
   "Deactivate a team member", AccessTier.PRIVILEGED)
_r(39, "orchestrator.team.team_member.reactivate", "orchestrator", "team", "team_member", "reactivate",
   "Reactivate an inactive team member", AccessTier.PRIVILEGED)
_r(40, "orchestrator.team.team_member.search", "orchestrator", "team", "team_member", "search",
   "Search team members by name/email/org", AccessTier.PRIVILEGED)
_r(41, "orchestrator.team.team_member.filter_role", "orchestrator", "team", "team_member", "filter_role",
   "Filter team members by global role", AccessTier.PRIVILEGED)
_r(42, "orchestrator.team.team_member.toggle_inactive", "orchestrator", "team", "team_member", "toggle_inactive",
   "Toggle visibility of inactive members", AccessTier.PRIVILEGED)
_r(43, "orchestrator.team.global_role.assign", "orchestrator", "team", "global_role", "assign",
   "Assign global role (Head of Engineering/Manager/Engineer/Technician/External Partner)", AccessTier.ADMIN)

# ── ECOSYSTEM (35 perms: #44-78) ─────────────────────────────
_r(44, "ecosystem.map.map.view", "ecosystem", "map", "map", "view",
   "View the ecosystem map with project markers", AccessTier.PUBLIC)
_r(45, "ecosystem.map.layer.switch", "ecosystem", "map", "layer", "switch",
   "Switch between production/infrastructure/offtaker layers", AccessTier.PUBLIC)
_r(46, "ecosystem.map.filter.apply", "ecosystem", "map", "filter", "apply",
   "Apply molecule/pathway/sector/sub-sector filters", AccessTier.PUBLIC)
_r(47, "ecosystem.map.filter.clear", "ecosystem", "map", "filter", "clear",
   "Clear all active filters", AccessTier.PUBLIC)
_r(48, "ecosystem.map.overlay.toggle_shipping", "ecosystem", "map", "overlay", "toggle_shipping",
   "Toggle shipping route overlay", AccessTier.PUBLIC)
_r(49, "ecosystem.map.overlay.toggle_aviation", "ecosystem", "map", "overlay", "toggle_aviation",
   "Toggle aviation route overlay", AccessTier.PUBLIC)
_r(50, "ecosystem.map.overlay.toggle_clusters", "ecosystem", "map", "overlay", "toggle_clusters",
   "Toggle cluster overlay", AccessTier.PUBLIC)
_r(51, "ecosystem.map.overlay.toggle_co2_pipelines", "ecosystem", "map", "overlay", "toggle_co2_pipelines",
   "Toggle CO2 pipeline overlay", AccessTier.PUBLIC)
_r(52, "ecosystem.map.overlay.toggle_heatmap", "ecosystem", "map", "overlay", "toggle_heatmap",
   "Toggle density heatmap overlay", AccessTier.PUBLIC)
_r(53, "ecosystem.map.overlay.toggle_verified_only", "ecosystem", "map", "overlay", "toggle_verified_only",
   "Filter to show only verified projects", AccessTier.PUBLIC)
_r(54, "ecosystem.map.project.select", "ecosystem", "map", "project", "select",
   "Click a project marker to view detail panel", AccessTier.PUBLIC)
_r(55, "ecosystem.map.project.search", "ecosystem", "map", "project", "search",
   "Search projects by name/type", AccessTier.PUBLIC)
_r(56, "ecosystem.map.project.view_profile", "ecosystem", "map", "project", "view_profile",
   "Navigate to full project profile page", AccessTier.PUBLIC)
_r(57, "ecosystem.map.my_projects.filter", "ecosystem", "map", "my_projects", "filter",
   "Toggle My Projects Only view", AccessTier.STAKEHOLDER)
_r(58, "ecosystem.map.basemap.switch", "ecosystem", "map", "basemap", "switch",
   "Switch basemap style (dark/satellite/etc)", AccessTier.PUBLIC)
_r(59, "ecosystem.map.project.add", "ecosystem", "map", "project", "add",
   "Start adding a new project (navigate to Plant Builder)", AccessTier.PRIVILEGED,
   ["requires_capability:PRODUCE"])
_r(60, "ecosystem.project_profile.project.view", "ecosystem", "project_profile", "project", "view",
   "View project profile with details", AccessTier.PUBLIC)
_r(61, "ecosystem.project_profile.project.edit", "ecosystem", "project_profile", "project", "edit",
   "Edit project details (requires KYC verified)", AccessTier.PRIVILEGED,
   ["requires_kyc:VERIFIED"])
_r(62, "ecosystem.project_profile.kyc.start", "ecosystem", "project_profile", "kyc", "start",
   "Start KYC verification process", AccessTier.PUBLIC)
_r(63, "ecosystem.kyc.kyc.select_role", "ecosystem", "kyc", "kyc", "select_role",
   "Select organization role (production/infrastructure/offtaker)", AccessTier.PUBLIC)
_r(64, "ecosystem.kyc.kyc.submit_email", "ecosystem", "kyc", "kyc", "submit_email",
   "Submit company email for verification", AccessTier.PUBLIC)
_r(65, "ecosystem.kyc.kyc.submit_details", "ecosystem", "kyc", "kyc", "submit_details",
   "Submit personal and company details", AccessTier.PUBLIC)
_r(66, "ecosystem.kyc.kyc.submit_sector", "ecosystem", "kyc", "kyc", "submit_sector",
   "Submit sector-specific details (production/infra/offtaker)", AccessTier.PUBLIC)
_r(67, "ecosystem.kyc.document.upload", "ecosystem", "kyc", "document", "upload",
   "Upload verification documents", AccessTier.PUBLIC)
_r(68, "ecosystem.kyc.document.remove", "ecosystem", "kyc", "document", "remove",
   "Remove uploaded document", AccessTier.PUBLIC)
_r(69, "ecosystem.kyc.colleague.add", "ecosystem", "kyc", "colleague", "add",
   "Add colleague for dual verification", AccessTier.PUBLIC)
_r(70, "ecosystem.kyc.kyc.submit", "ecosystem", "kyc", "kyc", "submit",
   "Submit full KYC for verification", AccessTier.PUBLIC)
_r(71, "ecosystem.news.news_article.view", "ecosystem", "news", "news_article", "view",
   "View aggregated news feed", AccessTier.PUBLIC)
_r(72, "ecosystem.news.news_article.search", "ecosystem", "news", "news_article", "search",
   "Search news articles", AccessTier.PUBLIC)
_r(73, "ecosystem.news.news_article.filter", "ecosystem", "news", "news_article", "filter",
   "Filter news by type/region", AccessTier.PUBLIC)
_r(74, "ecosystem.siting.siting_analysis.view", "ecosystem", "siting", "siting_analysis", "view",
   "View siting optimizer intro", AccessTier.PRIVILEGED)
_r(75, "ecosystem.siting.siting_analysis.configure", "ecosystem", "siting", "siting_analysis", "configure",
   "Configure siting parameters (tech, capacity, market, priorities)", AccessTier.PRIVILEGED)
_r(76, "ecosystem.siting.siting_analysis.run", "ecosystem", "siting", "siting_analysis", "run",
   "Run AI site optimization analysis", AccessTier.PRIVILEGED)
_r(77, "ecosystem.siting.siting_result.view", "ecosystem", "siting", "siting_result", "view",
   "View optimization results with ranked sites", AccessTier.PRIVILEGED)
_r(78, "ecosystem.siting.siting_result.start_project", "ecosystem", "siting", "siting_result", "start_project",
   "Start a project from a recommended site", AccessTier.PRIVILEGED,
   ["requires_capability:PRODUCE"])

# ── PLAUSIBILITY (6 perms: #79-84) ───────────────────────────
_r(79, "plausibility.document_verification.plausibility_check.view", "plausibility", "document_verification", "plausibility_check", "view",
   "View plausibility check overview", AccessTier.STAKEHOLDER)
_r(80, "plausibility.document_verification.document.upload", "plausibility", "document_verification", "document", "upload",
   "Upload operational evidence documents (locked/preview)", AccessTier.PRIVILEGED)
_r(81, "plausibility.api_connections.api_connection.connect", "plausibility", "api_connections", "api_connection", "connect",
   "Connect external data sources (SCADA/EMS/grid/etc)", AccessTier.PRIVILEGED)
_r(82, "plausibility.cross_check.cross_check.view", "plausibility", "cross_check", "cross_check", "view",
   "View cross-check engine results", AccessTier.STAKEHOLDER)
_r(83, "plausibility.blockchain.attestation.view", "plausibility", "blockchain", "attestation", "view",
   "View blockchain attestation status", AccessTier.PUBLIC)
_r(84, "plausibility.blockchain.attestation.generate", "plausibility", "blockchain", "attestation", "generate",
   "Generate Hedera blockchain hash (locked)", AccessTier.PRIVILEGED,
   ["requires_capability:PRODUCE,CERTIFY"])

# ── PROCUREMENT (16 perms: #85-100) ──────────────────────────
_r(85, "procurement.equipment.equipment.view", "procurement", "equipment", "equipment", "view",
   "View all plant equipment with procurement status", AccessTier.PRIVILEGED)
_r(86, "procurement.equipment.equipment.search", "procurement", "equipment", "equipment", "search",
   "Search equipment or manufacturer", AccessTier.PRIVILEGED)
_r(87, "procurement.equipment.supplier.browse", "procurement", "equipment", "supplier", "browse",
   "Browse suppliers for specific equipment", AccessTier.PRIVILEGED)
_r(88, "procurement.equipment.supplier.select", "procurement", "equipment", "supplier", "select",
   "Select/change supplier for equipment", AccessTier.PRIVILEGED)
_r(89, "procurement.equipment.procurement.save", "procurement", "equipment", "procurement", "save",
   "Save all procurement selections to localStorage", AccessTier.PRIVILEGED)
_r(90, "procurement.strategy.strategy.view", "procurement", "strategy", "strategy", "view",
   "View strategy comparison (Best Price/Efficiency/Scale)", AccessTier.PRIVILEGED)
_r(91, "procurement.strategy.strategy.preview", "procurement", "strategy", "strategy", "preview",
   "Preview a strategy configuration", AccessTier.PRIVILEGED)
_r(92, "procurement.strategy.strategy.apply_all", "procurement", "strategy", "strategy", "apply_all",
   "Apply a strategy to all equipment at once", AccessTier.PRIVILEGED)
_r(93, "procurement.equipment.procurement.export", "procurement", "equipment", "procurement", "export",
   "Export procurement documents (EPC/BoQ/specs)", AccessTier.PRIVILEGED)
_r(94, "procurement.equipment.economics.navigate", "procurement", "equipment", "economics", "navigate",
   "Navigate to project economics from procurement", AccessTier.PRIVILEGED)
_r(95, "procurement.supplier_db.supplier.view", "procurement", "supplier_db", "supplier", "view",
   "Browse full supplier database catalog", AccessTier.STAKEHOLDER)
_r(96, "procurement.supplier_db.supplier.search", "procurement", "supplier_db", "supplier", "search",
   "Search by manufacturer or model", AccessTier.STAKEHOLDER)
_r(97, "procurement.supplier_db.supplier.filter_category", "procurement", "supplier_db", "supplier", "filter_category",
   "Filter by equipment category", AccessTier.STAKEHOLDER)
_r(98, "procurement.supplier_db.supplier.filter_strategy", "procurement", "supplier_db", "supplier", "filter_strategy",
   "Filter by procurement strategy", AccessTier.STAKEHOLDER)
_r(99, "procurement.supplier_db.supplier.filter_country", "procurement", "supplier_db", "supplier", "filter_country",
   "Filter by manufacturer country", AccessTier.STAKEHOLDER)
_r(100, "procurement.supplier_db.supplier.sort", "procurement", "supplier_db", "supplier", "sort",
   "Sort suppliers by price/lead time/TRL/manufacturer", AccessTier.STAKEHOLDER)

# ── ECONOMICS (19 perms: #101-119) ───────────────────────────
_r(101, "economics.snapshot.economics_dashboard.view", "economics", "snapshot", "economics_dashboard", "view",
   "View project economics snapshot (LCOH, margin, waterfall)", AccessTier.PRIVILEGED)
_r(102, "economics.snapshot.scenario.select", "economics", "snapshot", "scenario", "select",
   "Select scenario for economics analysis", AccessTier.PRIVILEGED)
_r(103, "economics.snapshot.economics_report.export", "economics", "snapshot", "economics_report", "export",
   "Export economics documents (PDF/XLSX)", AccessTier.PRIVILEGED)
_r(104, "economics.cost_stack.cost_stack.view", "economics", "cost_stack", "cost_stack", "view",
   "View levelized cost of hydrogen breakdown", AccessTier.PRIVILEGED)
_r(105, "economics.cost_stack.capex.view", "economics", "cost_stack", "capex", "view",
   "View CAPEX breakdown with procurement data", AccessTier.PRIVILEGED,
   ["mandated_lender_for:BANK"])
_r(106, "economics.cost_stack.opex.view", "economics", "cost_stack", "opex", "view",
   "View OPEX items with optimization details", AccessTier.PRIVILEGED)
_r(107, "economics.cost_stack.opex.expand", "economics", "cost_stack", "opex", "expand",
   "Expand OPEX item to see benchmarks/optimization/scenarios", AccessTier.PRIVILEGED)
_r(108, "economics.cost_stack.cost_model.adjust", "economics", "cost_stack", "cost_model", "adjust",
   "Adjust operational cost modeling sliders", AccessTier.PRIVILEGED)
_r(109, "economics.cost_stack.cost_model.reset", "economics", "cost_stack", "cost_model", "reset",
   "Reset cost model to baseline values", AccessTier.PRIVILEGED)
_r(110, "economics.cost_stack.cost_model.toggle_operational", "economics", "cost_stack", "cost_model", "toggle_operational",
   "Toggle plant operational mode", AccessTier.PRIVILEGED)
_r(111, "economics.cost_stack.scenario.select", "economics", "cost_stack", "scenario", "select",
   "Select scenario for cost analysis", AccessTier.PRIVILEGED)
_r(112, "economics.cost_stack.cost_report.export", "economics", "cost_stack", "cost_report", "export",
   "Export cost documents (PDF/XLSX/CSV)", AccessTier.PRIVILEGED)
_r(113, "economics.cost_stack.procurement.navigate", "economics", "cost_stack", "procurement", "navigate",
   "Navigate to procurement from CAPEX", AccessTier.PRIVILEGED)
_r(114, "economics.benchmark.benchmark.view", "economics", "benchmark", "benchmark", "view",
   "View H2 price benchmark methodology and regional comparison", AccessTier.PUBLIC)
_r(115, "economics.benchmark.benchmark_report.export", "economics", "benchmark", "benchmark_report", "export",
   "Export benchmark documents", AccessTier.STAKEHOLDER)
_r(116, "economics.lca.lifecycle_assessment.view", "economics", "lca", "lifecycle_assessment", "view",
   "View lifecycle assessment panel", AccessTier.STAKEHOLDER)
_r(117, "economics.lca.methodology.select", "economics", "lca", "methodology", "select",
   "Select LCA methodology (RED III/EU ETS/IRA 45V/ISO/IPCC/GHG Protocol/FuelEU/ReFuelEU)", AccessTier.STAKEHOLDER)
_r(118, "economics.lca.scenario.select", "economics", "lca", "scenario", "select",
   "Select scenario for LCA", AccessTier.STAKEHOLDER)
_r(119, "economics.lca.lca_report.export", "economics", "lca", "lca_report", "export",
   "Export LCA documents (PDF/XLSX/CSV)", AccessTier.PRIVILEGED)

# ── COMPLIANCE (21 perms: #120-140) ──────────────────────────
_r(120, "compliance.regulatory.compliance_dashboard.view", "compliance", "regulatory", "compliance_dashboard", "view",
   "View regulatory compliance with policy instruments", AccessTier.PRIVILEGED)
_r(121, "compliance.regulatory.policy_instrument.toggle", "compliance", "regulatory", "policy_instrument", "toggle",
   "Toggle policy instruments on/off for stacking analysis", AccessTier.PRIVILEGED)
_r(122, "compliance.regulatory.profitability_waterfall.view", "compliance", "regulatory", "profitability_waterfall", "view",
   "View profitability waterfall with selected instruments", AccessTier.PRIVILEGED)
_r(123, "compliance.regulatory.scenario.select", "compliance", "regulatory", "scenario", "select",
   "Select scenario for regulatory analysis", AccessTier.PRIVILEGED)
_r(124, "compliance.regulatory.compliance_report.export", "compliance", "regulatory", "compliance_report", "export",
   "Export regulatory documents (PDF/XLSX/DOCX)", AccessTier.PRIVILEGED)
_r(125, "compliance.policy.policy_dashboard.view", "compliance", "policy", "policy_dashboard", "view",
   "View policy optimization with baseline summary", AccessTier.PRIVILEGED)
_r(126, "compliance.policy.policy_instrument.toggle", "compliance", "policy", "policy_instrument", "toggle",
   "Toggle policy instruments for optimization", AccessTier.PRIVILEGED)
_r(127, "compliance.policy.profitability_waterfall.view", "compliance", "policy", "profitability_waterfall", "view",
   "View profitability waterfall", AccessTier.PRIVILEGED)
_r(128, "compliance.policy.policy_report.export", "compliance", "policy", "policy_report", "export",
   "Export policy documents", AccessTier.PRIVILEGED)
_r(129, "compliance.instrument.instrument_access.view", "compliance", "instrument", "instrument_access", "view",
   "View single instrument access analysis (hero + tabs)", AccessTier.PRIVILEGED)
_r(130, "compliance.instrument.scope_assessment.view", "compliance", "instrument", "scope_assessment", "view",
   "View scope/eligibility assessment tab", AccessTier.PRIVILEGED)
_r(131, "compliance.instrument.electricity_strategy.view", "compliance", "instrument", "electricity_strategy", "view",
   "View electricity supply strategy tab", AccessTier.PRIVILEGED)
_r(132, "compliance.instrument.requirements.view", "compliance", "instrument", "requirements", "view",
   "View certification requirements checklist tab", AccessTier.PRIVILEGED)
_r(133, "compliance.instrument.viability_rollup.view", "compliance", "instrument", "viability_rollup", "view",
   "View viability scoring rollup tab", AccessTier.STAKEHOLDER)
_r(134, "compliance.instrument.operational_flags.view", "compliance", "instrument", "operational_flags", "view",
   "View operational risk flags tab", AccessTier.PRIVILEGED)
_r(135, "compliance.instrument.instrument_report.export", "compliance", "instrument", "instrument_report", "export",
   "Export instrument assessment as PDF (print)", AccessTier.PRIVILEGED)
_r(136, "compliance.ghg.ghg_calculation.view", "compliance", "ghg", "ghg_calculation", "view",
   "View GHG calculation breakdown (pipeline + methodology + matrix)", AccessTier.PRIVILEGED)
_r(137, "compliance.ghg.methodology.select", "compliance", "ghg", "methodology", "select",
   "Select GHG methodology via URL param", AccessTier.PRIVILEGED)
_r(138, "compliance.ghg.ghg_report.export", "compliance", "ghg", "ghg_report", "export",
   "Export GHG documents (XLSX/PDF/CSV)", AccessTier.PRIVILEGED)
_r(139, "compliance.certification.certification_scheme.view", "compliance", "certification", "certification_scheme", "view",
   "View recommended certification schemes for a plant", AccessTier.STAKEHOLDER)
_r(140, "compliance.certification.scheme_website.visit", "compliance", "certification", "scheme_website", "visit",
   "Visit external certification scheme website", AccessTier.PUBLIC)

# ── GAM — GREEN ASSET MARKETPLACE (44 perms: #141-184) ──────
# Supply side
_r(141, "gam.supply.persona.switch", "gam", "supply", "persona", "switch",
   "Switch between producer/offtaker persona", AccessTier.PRIVILEGED)
_r(142, "gam.supply.supply_project.select", "gam", "supply", "supply_project", "select",
   "Select project to view supply dashboard", AccessTier.PRIVILEGED)
_r(143, "gam.supply.supply_volume.view", "gam", "supply", "supply_volume", "view",
   "View production volume and tokenization status", AccessTier.PRIVILEGED)
_r(144, "gam.supply.token.mint", "gam", "supply", "token", "mint",
   "Tokenize supply volume (set volume, denomination, mint)", AccessTier.PRIVILEGED,
   ["requires_token_ready", "requires_capability:SELL"])
_r(145, "gam.supply.token.view_receipt", "gam", "supply", "token", "view_receipt",
   "View blockchain receipt after tokenization", AccessTier.STAKEHOLDER)
_r(146, "gam.supply.token.copy_hash", "gam", "supply", "token", "copy_hash",
   "Copy transaction hash to clipboard", AccessTier.STAKEHOLDER)
_r(147, "gam.supply.token_score.view", "gam", "supply", "token_score", "view",
   "View Token Score Track (history, batches, breakdown)", AccessTier.STAKEHOLDER)
_r(148, "gam.supply.token_score.select_batch", "gam", "supply", "token_score", "select_batch",
   "Select specific batch to view score at mint time", AccessTier.STAKEHOLDER)
_r(149, "gam.supply.token_score.view_mechanism", "gam", "supply", "token_score", "view_mechanism",
   "View full scoring mechanism details", AccessTier.PRIVILEGED)
_r(150, "gam.supply.milestone.view", "gam", "supply", "milestone", "view",
   "View tokenization milestone progress", AccessTier.STAKEHOLDER)
_r(151, "gam.supply.milestone.navigate", "gam", "supply", "milestone", "navigate",
   "Navigate to milestone requirement page", AccessTier.PRIVILEGED)
_r(152, "gam.supply.volume_attributes.view_ghg", "gam", "supply", "volume_attributes", "view_ghg",
   "View GHG emissions tab in volume attributes", AccessTier.STAKEHOLDER)
_r(153, "gam.supply.volume_attributes.view_lca", "gam", "supply", "volume_attributes", "view_lca",
   "View LCA compliance tab", AccessTier.STAKEHOLDER)
_r(154, "gam.supply.volume_attributes.view_regulation", "gam", "supply", "volume_attributes", "view_regulation",
   "View regulation compliance tab", AccessTier.PRIVILEGED)
_r(155, "gam.supply.volume_attributes.view_credit", "gam", "supply", "volume_attributes", "view_credit",
   "View credit quality assessment tab", AccessTier.PRIVILEGED,
   ["requires_credit_rating_set"])
_r(156, "gam.supply.credit_quality.view_breakdown", "gam", "supply", "credit_quality", "view_breakdown",
   "View credit quality pillar breakdown", AccessTier.PRIVILEGED)
_r(157, "gam.supply.credit_quality.view_benchmark", "gam", "supply", "credit_quality", "view_benchmark",
   "View benchmarking against platform projects", AccessTier.PRIVILEGED)
_r(158, "gam.supply.credit_quality.view_upgrade_path", "gam", "supply", "credit_quality", "view_upgrade_path",
   "View path to credit upgrade actions", AccessTier.PRIVILEGED)
_r(159, "gam.supply.price_recommendation.view", "gam", "supply", "price_recommendation", "view",
   "View recommended selling price with methodology", AccessTier.PRIVILEGED)
_r(160, "gam.supply.price_recommendation.view_methodology", "gam", "supply", "price_recommendation", "view_methodology",
   "View pricing methodology and data sources", AccessTier.PRIVILEGED)
_r(161, "gam.supply.price_recommendation.navigate_economics", "gam", "supply", "price_recommendation", "navigate_economics",
   "Navigate to full project economics", AccessTier.PRIVILEGED)
# Matchmaking — seller side
_r(162, "gam.matchmaking.offtaker_search.configure", "gam", "matchmaking", "offtaker_search", "configure",
   "Configure offtaker search criteria (molecule, location, volume)", AccessTier.PRIVILEGED,
   ["requires_capability:SELL"])
_r(163, "gam.matchmaking.offtaker_search.execute", "gam", "matchmaking", "offtaker_search", "execute",
   "Execute offtaker matching search", AccessTier.PRIVILEGED,
   ["requires_capability:SELL"])
_r(164, "gam.matchmaking.match_result.view", "gam", "matchmaking", "match_result", "view",
   "View offtaker match results with scores", AccessTier.PRIVILEGED)
_r(165, "gam.matchmaking.match_breakdown.view", "gam", "matchmaking", "match_breakdown", "view",
   "View detailed match score breakdown by criteria", AccessTier.PRIVILEGED)
_r(166, "gam.matchmaking.matching_methodology.view", "gam", "matchmaking", "matching_methodology", "view",
   "View matching methodology documentation", AccessTier.PUBLIC)
_r(167, "gam.matchmaking.offtaker.contact", "gam", "matchmaking", "offtaker", "contact",
   "Send contact message to matched offtaker", AccessTier.PRIVILEGED,
   ["requires_capability:SELL", "requires_export_license"])
# Demand side
_r(168, "gam.demand.demand_summary.view", "gam", "demand", "demand_summary", "view",
   "View total demand/secured/open procurement summary", AccessTier.PRIVILEGED)
_r(169, "gam.demand.offtake_site.select", "gam", "demand", "offtake_site", "select",
   "Select offtake site to view demand details", AccessTier.PRIVILEGED)
_r(170, "gam.demand.demand_volume.view", "gam", "demand", "demand_volume", "view",
   "View demand volume bar with fulfillment status", AccessTier.PRIVILEGED)
_r(171, "gam.demand.supplier.view", "gam", "demand", "supplier", "view",
   "View current suppliers for offtake site", AccessTier.PRIVILEGED)
_r(172, "gam.demand.supplier.view_profile", "gam", "demand", "supplier", "view_profile",
   "View supplier profile dialog", AccessTier.PRIVILEGED)
_r(173, "gam.demand.supplier.adjust_volume", "gam", "demand", "supplier", "adjust_volume",
   "Adjust traded volume for a supplier", AccessTier.PRIVILEGED,
   ["requires_aggregation_limit_check"])
_r(174, "gam.demand.ghg_requirement.view", "gam", "demand", "ghg_requirement", "view",
   "View GHG lifecycle requirement for site", AccessTier.STAKEHOLDER)
_r(175, "gam.demand.sustainability_attrs.view", "gam", "demand", "sustainability_attrs", "view",
   "View required sustainability attributes", AccessTier.STAKEHOLDER)
_r(176, "gam.demand.credit_requirement.view", "gam", "demand", "credit_requirement", "view",
   "View required credit quality", AccessTier.PRIVILEGED)
# Matchmaking — buyer side
_r(177, "gam.matchmaking.producer_search.configure", "gam", "matchmaking", "producer_search", "configure",
   "Configure producer search criteria (molecule, region, volume, credit, GHG, attrs)", AccessTier.PRIVILEGED,
   ["requires_capability:OFFTAKE"])
_r(178, "gam.matchmaking.producer_search.execute", "gam", "matchmaking", "producer_search", "execute",
   "Execute producer matching search", AccessTier.PRIVILEGED,
   ["requires_capability:OFFTAKE"])
_r(179, "gam.matchmaking.producer_result.view", "gam", "matchmaking", "producer_result", "view",
   "View producer match results", AccessTier.PRIVILEGED)
_r(180, "gam.matchmaking.sustainability_attr.add", "gam", "matchmaking", "sustainability_attr", "add",
   "Add sustainability attribute to search criteria", AccessTier.PRIVILEGED)
_r(181, "gam.matchmaking.sustainability_attr.remove", "gam", "matchmaking", "sustainability_attr", "remove",
   "Remove sustainability attribute from criteria", AccessTier.PRIVILEGED)
_r(182, "gam.matchmaking.sustainability_attr.set_priority", "gam", "matchmaking", "sustainability_attr", "set_priority",
   "Cycle priority (Mandatory/Preferred/Bonus)", AccessTier.PRIVILEGED)
_r(183, "gam.matchmaking.credit_quality.toggle", "gam", "matchmaking", "credit_quality", "toggle",
   "Toggle accepted credit quality levels", AccessTier.PRIVILEGED)
_r(184, "gam.matchmaking.producer.contact", "gam", "matchmaking", "producer", "contact",
   "Send contact message to matched producer", AccessTier.PRIVILEGED,
   ["requires_capability:OFFTAKE"])

# ── AUTH (7 perms: #185-191) ─────────────────────────────────
_r(185, "auth.account.profile.view", "auth", "account", "profile", "view",
   "View user profile page", AccessTier.PUBLIC)
_r(186, "auth.account.profile.view_security", "auth", "account", "profile", "view_security",
   "View account security section", AccessTier.PUBLIC)
_r(187, "auth.account.two_factor.toggle", "auth", "account", "two_factor", "toggle",
   "Enable/disable two-factor authentication", AccessTier.PUBLIC)
_r(188, "auth.account.session.logout", "auth", "account", "session", "logout",
   "Sign out of the application", AccessTier.PUBLIC)
_r(189, "auth.account.login_history.view", "auth", "account", "login_history", "view",
   "View login history", AccessTier.PUBLIC)
_r(190, "auth.account.kyc_profile.view", "auth", "account", "kyc_profile", "view",
   "View KYC profile details", AccessTier.PUBLIC)
_r(191, "auth.admin.all_screens.view", "auth", "admin", "all_screens", "view",
   "Admin-only directory to all platform screens", AccessTier.ADMIN)

# ── GLOBAL (3 perms: #192-194) ───────────────────────────────
_r(192, "global.auth.app.login", "global", "auth", "app", "login",
   "Login to the application (GlobalLoginScreen)", AccessTier.PUBLIC)
_r(193, "global.navigation.app_nav.use", "global", "navigation", "app_nav", "use",
   "Use global navigation bar", AccessTier.PUBLIC)
_r(194, "global.navigation.project_hub.view", "global", "navigation", "project_hub", "view",
   "View post-save project hub with module links", AccessTier.PUBLIC)


# ═══════════════════════════════════════════════════════════════
# 3. PERMISSION SETS — Building blocks for role profiles
# ═══════════════════════════════════════════════════════════════
#
# Each set groups permissions by functional area.
# Role profiles are composed from these sets via union (|).
# This makes the CISO reasoning transparent: "Producer.Engineering
# gets _ORCH_CREATE because they build plants."
#

# ── Orchestrator ──
_ORCH_VIEW = {
    "orchestrator.hub.orchestrator.view",
    "orchestrator.portfolio.portfolio.view",
    "orchestrator.portfolio.plant.navigate_dashboard",
    "orchestrator.portfolio.plant.navigate_canvas",
}
_ORCH_CREATE = _ORCH_VIEW | {
    "orchestrator.portfolio.plant.create",
}
_ORCH_TEAM_VIEW = {
    "orchestrator.team.team_member.view",
    "orchestrator.team.team_member.search",
    "orchestrator.team.team_member.filter_role",
}
_ORCH_TEAM_MANAGE = _ORCH_TEAM_VIEW | {
    "orchestrator.team.team_member.invite",
    "orchestrator.team.team_member.edit",
    "orchestrator.team.team_member.deactivate",
    "orchestrator.team.team_member.reactivate",
    "orchestrator.team.team_member.toggle_inactive",
    "orchestrator.team.global_role.assign",
}

# ── Ecosystem — public (all authenticated users) ──
_ECO_MAP = {
    "ecosystem.map.map.view",
    "ecosystem.map.layer.switch",
    "ecosystem.map.filter.apply",
    "ecosystem.map.filter.clear",
    "ecosystem.map.overlay.toggle_shipping",
    "ecosystem.map.overlay.toggle_aviation",
    "ecosystem.map.overlay.toggle_clusters",
    "ecosystem.map.overlay.toggle_co2_pipelines",
    "ecosystem.map.overlay.toggle_heatmap",
    "ecosystem.map.overlay.toggle_verified_only",
    "ecosystem.map.project.select",
    "ecosystem.map.project.search",
    "ecosystem.map.project.view_profile",
    "ecosystem.map.basemap.switch",
}
_ECO_MY_PROJECTS = {"ecosystem.map.my_projects.filter"}
_ECO_ADD_PROJECT = {"ecosystem.map.project.add"}
_ECO_PROJECT_VIEW = {"ecosystem.project_profile.project.view"}
_ECO_PROJECT_EDIT = {"ecosystem.project_profile.project.edit"}
_ECO_KYC = {
    "ecosystem.project_profile.kyc.start",
    "ecosystem.kyc.kyc.select_role",
    "ecosystem.kyc.kyc.submit_email",
    "ecosystem.kyc.kyc.submit_details",
    "ecosystem.kyc.kyc.submit_sector",
    "ecosystem.kyc.document.upload",
    "ecosystem.kyc.document.remove",
    "ecosystem.kyc.colleague.add",
    "ecosystem.kyc.kyc.submit",
}
_ECO_NEWS = {
    "ecosystem.news.news_article.view",
    "ecosystem.news.news_article.search",
    "ecosystem.news.news_article.filter",
}
_ECO_SITING_VIEW = {
    "ecosystem.siting.siting_analysis.view",
    "ecosystem.siting.siting_result.view",
}
_ECO_SITING_RUN = _ECO_SITING_VIEW | {
    "ecosystem.siting.siting_analysis.configure",
    "ecosystem.siting.siting_analysis.run",
    "ecosystem.siting.siting_result.start_project",
}

# ── Plausibility ──
_PLAUS_VIEW = {
    "plausibility.document_verification.plausibility_check.view",
    "plausibility.cross_check.cross_check.view",
    "plausibility.blockchain.attestation.view",
}
_PLAUS_UPLOAD = _PLAUS_VIEW | {
    "plausibility.document_verification.document.upload",
    "plausibility.api_connections.api_connection.connect",
    "plausibility.blockchain.attestation.generate",
}

# ── Procurement ──
_PROC_BROWSE = {
    "procurement.equipment.equipment.view",
    "procurement.equipment.equipment.search",
    "procurement.equipment.supplier.browse",
    "procurement.supplier_db.supplier.view",
    "procurement.supplier_db.supplier.search",
    "procurement.supplier_db.supplier.filter_category",
    "procurement.supplier_db.supplier.filter_strategy",
    "procurement.supplier_db.supplier.filter_country",
    "procurement.supplier_db.supplier.sort",
}
_PROC_MANAGE = _PROC_BROWSE | {
    "procurement.equipment.supplier.select",
    "procurement.equipment.procurement.save",
    "procurement.strategy.strategy.view",
    "procurement.strategy.strategy.preview",
    "procurement.strategy.strategy.apply_all",
    "procurement.equipment.procurement.export",
    "procurement.equipment.economics.navigate",
}

# ── Economics ──
_ECON_VIEW = {
    "economics.snapshot.economics_dashboard.view",
    "economics.snapshot.scenario.select",
    "economics.cost_stack.cost_stack.view",
    "economics.cost_stack.capex.view",
    "economics.cost_stack.opex.view",
    "economics.cost_stack.opex.expand",
    "economics.cost_stack.scenario.select",
    "economics.benchmark.benchmark.view",
}
_ECON_ADJUST = _ECON_VIEW | {
    "economics.cost_stack.cost_model.adjust",
    "economics.cost_stack.cost_model.reset",
    "economics.cost_stack.cost_model.toggle_operational",
}
_ECON_EXPORT = {
    "economics.snapshot.economics_report.export",
    "economics.cost_stack.cost_report.export",
    "economics.benchmark.benchmark_report.export",
}
_ECON_NAVIGATE = {"economics.cost_stack.procurement.navigate"}
_ECON_LCA = {
    "economics.lca.lifecycle_assessment.view",
    "economics.lca.methodology.select",
    "economics.lca.scenario.select",
    "economics.lca.lca_report.export",
}

# ── Compliance ──
_COMP_REG_VIEW = {
    "compliance.regulatory.compliance_dashboard.view",
    "compliance.regulatory.profitability_waterfall.view",
    "compliance.regulatory.scenario.select",
}
_COMP_REG_MANAGE = _COMP_REG_VIEW | {
    "compliance.regulatory.policy_instrument.toggle",
    "compliance.regulatory.compliance_report.export",
}
_COMP_POLICY = {
    "compliance.policy.policy_dashboard.view",
    "compliance.policy.policy_instrument.toggle",
    "compliance.policy.profitability_waterfall.view",
    "compliance.policy.policy_report.export",
}
_COMP_INSTRUMENT = {
    "compliance.instrument.instrument_access.view",
    "compliance.instrument.scope_assessment.view",
    "compliance.instrument.electricity_strategy.view",
    "compliance.instrument.requirements.view",
    "compliance.instrument.viability_rollup.view",
    "compliance.instrument.operational_flags.view",
    "compliance.instrument.instrument_report.export",
}
_COMP_GHG = {
    "compliance.ghg.ghg_calculation.view",
    "compliance.ghg.methodology.select",
    "compliance.ghg.ghg_report.export",
}
_COMP_CERT = {
    "compliance.certification.certification_scheme.view",
    "compliance.certification.scheme_website.visit",
}

# ── GAM Supply ──
_GAM_SUPPLY_VIEW = {
    "gam.supply.persona.switch",
    "gam.supply.supply_project.select",
    "gam.supply.supply_volume.view",
    "gam.supply.milestone.view",
    "gam.supply.volume_attributes.view_ghg",
    "gam.supply.volume_attributes.view_lca",
    "gam.supply.volume_attributes.view_regulation",
}
_GAM_SUPPLY_TOKEN = {
    "gam.supply.token.mint",
    "gam.supply.token.view_receipt",
    "gam.supply.token.copy_hash",
    "gam.supply.token_score.view",
    "gam.supply.token_score.select_batch",
    "gam.supply.token_score.view_mechanism",
}
_GAM_SUPPLY_CREDIT = {
    "gam.supply.volume_attributes.view_credit",
    "gam.supply.credit_quality.view_breakdown",
    "gam.supply.credit_quality.view_benchmark",
    "gam.supply.credit_quality.view_upgrade_path",
}
_GAM_SUPPLY_PRICE = {
    "gam.supply.price_recommendation.view",
    "gam.supply.price_recommendation.view_methodology",
    "gam.supply.price_recommendation.navigate_economics",
}
_GAM_SUPPLY_MILESTONE_NAV = {"gam.supply.milestone.navigate"}

# ── GAM Matchmaking ──
_GAM_MATCH_SELL = {
    "gam.matchmaking.offtaker_search.configure",
    "gam.matchmaking.offtaker_search.execute",
    "gam.matchmaking.match_result.view",
    "gam.matchmaking.match_breakdown.view",
    "gam.matchmaking.matching_methodology.view",
    "gam.matchmaking.offtaker.contact",
}
_GAM_MATCH_BUY = {
    "gam.matchmaking.producer_search.configure",
    "gam.matchmaking.producer_search.execute",
    "gam.matchmaking.producer_result.view",
    "gam.matchmaking.sustainability_attr.add",
    "gam.matchmaking.sustainability_attr.remove",
    "gam.matchmaking.sustainability_attr.set_priority",
    "gam.matchmaking.credit_quality.toggle",
    "gam.matchmaking.producer.contact",
}

# ── GAM Demand ──
_GAM_DEMAND_VIEW = {
    "gam.demand.demand_summary.view",
    "gam.demand.offtake_site.select",
    "gam.demand.demand_volume.view",
    "gam.demand.supplier.view",
    "gam.demand.supplier.view_profile",
    "gam.demand.ghg_requirement.view",
    "gam.demand.sustainability_attrs.view",
    "gam.demand.credit_requirement.view",
}
_GAM_DEMAND_WRITE = _GAM_DEMAND_VIEW | {
    "gam.demand.supplier.adjust_volume",
}

# ── Auth / Global ──
_AUTH_SELF = {
    "auth.account.profile.view",
    "auth.account.profile.view_security",
    "auth.account.two_factor.toggle",
    "auth.account.session.logout",
    "auth.account.login_history.view",
    "auth.account.kyc_profile.view",
}
_AUTH_ADMIN = _AUTH_SELF | {"auth.admin.all_screens.view"}
_GLOBAL = {
    "global.auth.app.login",
    "global.navigation.app_nav.use",
    "global.navigation.project_hub.view",
}


# ═══════════════════════════════════════════════════════════════
# 4. ROLE PROFILES — The CISO's Policy Matrix
# ═══════════════════════════════════════════════════════════════
#
# Profile key format: "{ENTITY_TYPE}.{EMPLOYEE_ROLE}"
#
# Entity types map to the existing GEX dimensions:
#   PRODUCER   → company_type=PRODUCER (any business_function)
#   OFFTAKER   → company_type=OFFTAKER (any business_function)
#   BANK       → company_type=THIRD_PARTY, service_type=BANK
#   INSURER    → company_type=THIRD_PARTY, service_type=INSURER
#   CERTIFIER  → company_type=THIRD_PARTY, service_type=CERTIFIER
#   ENGINEER   → company_type=THIRD_PARTY, service_type=ENGINEER
#   EQUIPMENT  → company_type=THIRD_PARTY, service_type=EQUIPMENT
#   LOGISTICS  → company_type=THIRD_PARTY, service_type=LOGISTICS
#   LEGAL      → company_type=THIRD_PARTY, service_type=LEGAL
#
# Employee roles map to business_function:
#   EXECUTIVE, ENGINEERING, FINANCE_TREASURY, COMMERCIAL,
#   COMPLIANCE_LEGAL, OPERATIONS
#
# ═══════════════════════════════════════════════════════════════

# Base permissions every authenticated user gets
_ALL_BASE = (
    _ECO_MAP | _ECO_PROJECT_VIEW | _ECO_KYC | _ECO_NEWS
    | _AUTH_SELF | _GLOBAL
    | {"compliance.certification.scheme_website.visit",
       "economics.benchmark.benchmark.view",
       "gam.matchmaking.matching_methodology.view",
       "plausibility.blockchain.attestation.view"}
)

ROLE_PROFILES: dict[str, set[str]] = {

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PRODUCER — owns and operates production plants
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "PRODUCER.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_CREATE | _ORCH_TEAM_MANAGE
        | _ECO_MY_PROJECTS | _ECO_ADD_PROJECT | _ECO_PROJECT_EDIT | _ECO_SITING_RUN
        | _PLAUS_UPLOAD
        | _PROC_MANAGE
        | _ECON_ADJUST | _ECON_EXPORT | _ECON_NAVIGATE | _ECON_LCA
        | _COMP_REG_MANAGE | _COMP_POLICY | _COMP_INSTRUMENT | _COMP_GHG | _COMP_CERT
        | _GAM_SUPPLY_VIEW | _GAM_SUPPLY_TOKEN | _GAM_SUPPLY_CREDIT
        | _GAM_SUPPLY_PRICE | _GAM_SUPPLY_MILESTONE_NAV
        | _GAM_MATCH_SELL
    ),  # ~130 perms: Full visibility. CEO/MD needs total oversight.

    "PRODUCER.ENGINEERING": (
        _ALL_BASE
        | _ORCH_CREATE
        | _ECO_MY_PROJECTS | _ECO_ADD_PROJECT | _ECO_PROJECT_EDIT | _ECO_SITING_RUN
        | _PLAUS_UPLOAD
        | _PROC_MANAGE
        | _ECON_VIEW | _ECON_NAVIGATE
        | {"compliance.instrument.electricity_strategy.view",
           "compliance.instrument.viability_rollup.view"}
        | _COMP_GHG
        | _GAM_SUPPLY_VIEW | _GAM_SUPPLY_MILESTONE_NAV
    ),  # ~85 perms: Plant builder, procurement, technical compliance. No finance write.

    "PRODUCER.FINANCE_TREASURY": (
        _ALL_BASE
        | _ORCH_VIEW
        | _ECO_MY_PROJECTS | _ECO_SITING_VIEW
        | _PLAUS_VIEW
        | {"procurement.strategy.strategy.view",
           "procurement.strategy.strategy.preview",
           "procurement.equipment.procurement.export",
           "procurement.equipment.economics.navigate"}
        | _ECON_ADJUST | _ECON_EXPORT | _ECON_NAVIGATE | _ECON_LCA
        | _COMP_REG_MANAGE | _COMP_POLICY
        | {"compliance.instrument.viability_rollup.view"}
        | _GAM_SUPPLY_VIEW | _GAM_SUPPLY_CREDIT | _GAM_SUPPLY_PRICE
    ),  # ~90 perms: Economics owner. Cost modeling. Credit quality. No plant build.

    "PRODUCER.COMMERCIAL": (
        _ALL_BASE
        | _ORCH_VIEW
        | _ECO_MY_PROJECTS | _ECO_SITING_VIEW
        | _PROC_BROWSE
        | _ECON_VIEW
        | _GAM_SUPPLY_VIEW | _GAM_SUPPLY_TOKEN | _GAM_SUPPLY_PRICE
        | _GAM_MATCH_SELL
    ),  # ~75 perms: Marketplace + matchmaking seller. Token minting. Price view.

    "PRODUCER.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _ORCH_VIEW
        | _ECO_MY_PROJECTS
        | _PLAUS_VIEW
        | _ECON_LCA
        | _COMP_REG_MANAGE | _COMP_POLICY | _COMP_INSTRUMENT | _COMP_GHG | _COMP_CERT
        | {"gam.supply.volume_attributes.view_regulation"}
    ),  # ~72 perms: Full compliance suite. LCA. GHG. Certification. No economics write.

    "PRODUCER.OPERATIONS": (
        _ALL_BASE
        | _ORCH_VIEW | _ORCH_TEAM_VIEW
        | _ECO_MY_PROJECTS
        | _PLAUS_UPLOAD
        | {"compliance.instrument.operational_flags.view"}
        | _GAM_SUPPLY_VIEW
    ),  # ~55 perms: Plant operations. Evidence upload. Operational flags. Limited scope.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OFFTAKER — buys molecules. Can be pure end-buyer or prosumer.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "OFFTAKER.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _ECON_VIEW | {"economics.benchmark.benchmark_report.export"}
        | _GAM_DEMAND_WRITE
        | _GAM_MATCH_BUY
        | {"gam.supply.persona.switch",
           "gam.supply.token_score.view",
           "gam.supply.token_score.select_batch"}
    ),  # ~70 perms: Full demand + matchmaking. Team mgmt. Economics read.

    "OFFTAKER.FINANCE_TREASURY": (
        _ALL_BASE
        | _ECON_VIEW
        | _GAM_DEMAND_VIEW
        | {"gam.matchmaking.credit_quality.toggle",
           "gam.demand.credit_requirement.view"}
    ),  # ~50 perms: Demand view + credit gating config. Economics view only.

    "OFFTAKER.COMMERCIAL": (
        _ALL_BASE
        | _GAM_DEMAND_WRITE
        | _GAM_MATCH_BUY
        | {"gam.supply.persona.switch",
           "gam.supply.token_score.view",
           "gam.supply.token_score.select_batch",
           "gam.supply.volume_attributes.view_ghg",
           "gam.supply.volume_attributes.view_lca"}
    ),  # ~65 perms: Buyer. Matchmaking. Demand management. Token score view.

    "OFFTAKER.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _COMP_REG_VIEW | _COMP_CERT
        | {"gam.demand.ghg_requirement.view",
           "gam.demand.sustainability_attrs.view"}
    ),  # ~42 perms: Compliance view only. Demand sustainability attrs.

    "OFFTAKER.ENGINEERING": _ALL_BASE,  # ~35 perms: Base only. Offtakers rarely have engineering.

    "OFFTAKER.OPERATIONS": (
        _ALL_BASE
        | _GAM_DEMAND_VIEW
    ),  # ~43 perms: Demand view. Logistics coordination.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BANK / LENDER — finances projects. Credit analysis.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "BANK.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _ECON_VIEW | _ECON_EXPORT
        | {"compliance.regulatory.profitability_waterfall.view",
           "compliance.instrument.viability_rollup.view"}
        | {"gam.supply.token_score.view", "gam.supply.milestone.view",
           "gam.supply.volume_attributes.view_credit",
           "gam.supply.credit_quality.view_breakdown",
           "gam.supply.credit_quality.view_benchmark"}
    ),  # ~60 perms: Portfolio view. Economics + credit quality.

    "BANK.FINANCE_TREASURY": (
        _ALL_BASE
        | _ECON_VIEW | _ECON_EXPORT
        | _PLAUS_VIEW
        | {"compliance.regulatory.profitability_waterfall.view",
           "compliance.instrument.viability_rollup.view"}
        | _GAM_SUPPLY_CREDIT
        | {"gam.supply.token.view_receipt",
           "gam.supply.token_score.view",
           "gam.supply.token_score.select_batch",
           "gam.supply.token_score.view_mechanism",
           "gam.supply.milestone.view"}
        | {"gam.matchmaking.match_breakdown.view"}
        | {"gam.demand.credit_requirement.view"}
    ),  # ~65 perms: Credit analyst / underwriter. Deep economics + credit views.

    "BANK.COMMERCIAL": (
        _ALL_BASE
        | _ECON_VIEW
        | {"gam.supply.credit_quality.view_breakdown",
           "gam.supply.credit_quality.view_benchmark"}
    ),  # ~42 perms: Relationship manager. Limited view.

    "BANK.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _COMP_REG_VIEW | _COMP_CERT
    ),  # ~40 perms: Bank compliance. Regulatory read only.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INSURER — underwriting risk for projects
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "INSURER.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _ECON_VIEW | {"economics.benchmark.benchmark_report.export"}
        | _PLAUS_VIEW
        | {"compliance.instrument.operational_flags.view",
           "compliance.instrument.viability_rollup.view"}
    ),  # ~55 perms: Risk overview.

    "INSURER.FINANCE_TREASURY": (
        _ALL_BASE
        | _ECON_VIEW | {"economics.benchmark.benchmark_report.export"}
        | _PLAUS_VIEW
        | {"compliance.instrument.operational_flags.view",
           "compliance.instrument.viability_rollup.view"}
        | _GAM_SUPPLY_CREDIT
    ),  # ~55 perms: Underwriter. Economics + plausibility + credit quality.

    "INSURER.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _COMP_REG_VIEW | _COMP_CERT
        | _PLAUS_VIEW
    ),  # ~43 perms: Insurance compliance.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CERTIFIER — audits and certifies projects
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "CERTIFIER.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _PLAUS_UPLOAD
        | _ECON_LCA
        | _COMP_INSTRUMENT | _COMP_GHG | _COMP_CERT
        | {"gam.supply.token_score.view",
           "gam.supply.token_score.view_mechanism",
           "gam.supply.volume_attributes.view_ghg",
           "gam.supply.volume_attributes.view_lca",
           "gam.supply.volume_attributes.view_regulation"}
        | {"gam.demand.ghg_requirement.view",
           "gam.demand.sustainability_attrs.view"}
    ),  # ~65 perms: Full audit scope.

    "CERTIFIER.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _PLAUS_UPLOAD
        | _ECON_LCA
        | _COMP_INSTRUMENT | _COMP_GHG | _COMP_CERT
        | {"gam.supply.volume_attributes.view_ghg",
           "gam.supply.volume_attributes.view_lca",
           "gam.supply.volume_attributes.view_regulation"}
        | {"gam.demand.ghg_requirement.view",
           "gam.demand.sustainability_attrs.view"}
    ),  # ~60 perms: Auditor. Plausibility upload. Full compliance.

    "CERTIFIER.ENGINEERING": (
        _ALL_BASE
        | _PLAUS_UPLOAD
        | _COMP_GHG | _COMP_CERT
    ),  # ~45 perms: Technical auditor. GHG + plausibility.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ENGINEER / EPC CONTRACTOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "ENGINEER.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _PROC_BROWSE
        | _PLAUS_VIEW
    ),  # ~50 perms: EPC management view.

    "ENGINEER.ENGINEERING": (
        _ALL_BASE
        | _PROC_BROWSE
        | _PLAUS_VIEW
    ),  # ~45 perms: Equipment browsing + plausibility view.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # EQUIPMENT SUPPLIER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "EQUIPMENT.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _PROC_BROWSE
    ),  # ~48 perms: Supplier catalog visibility.

    "EQUIPMENT.COMMERCIAL": (
        _ALL_BASE
        | _PROC_BROWSE
    ),  # ~42 perms: Sales rep browsing supplier DB.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LOGISTICS OPERATOR
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "LOGISTICS.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
    ),  # ~43 perms: Team management + base ecosystem.

    "LOGISTICS.OPERATIONS": _ALL_BASE,  # ~35 perms: Map + news only.

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LEGAL / ADVISORY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "LEGAL.EXECUTIVE": (
        _ALL_BASE
        | _ORCH_TEAM_MANAGE
        | _COMP_REG_MANAGE | _COMP_INSTRUMENT | _COMP_CERT
    ),  # ~55 perms: Legal advisory with compliance access.

    "LEGAL.COMPLIANCE_LEGAL": (
        _ALL_BASE
        | _COMP_REG_MANAGE | _COMP_INSTRUMENT | _COMP_CERT
        | {"gam.supply.volume_attributes.view_regulation"}
    ),  # ~50 perms: Full compliance + regulatory.
}


# ═══════════════════════════════════════════════════════════════
# 5. CAPABILITY EXTENSIONS — Prosumer permission grants
# ═══════════════════════════════════════════════════════════════
#
# When a user holds a Capability (from abac.py), they gain
# ADDITIONAL permissions on top of their role profile.
# This is how Frank Sabak (BremenThree AG, OFFTAKER.COMMERCIAL)
# also sees PRODUCER screens — his PRODUCE capability grants them.
#

CAPABILITY_GRANTS: dict[str, set[str]] = {
    "PRODUCE": (
        _ORCH_CREATE | _ECO_ADD_PROJECT | _ECO_PROJECT_EDIT | _ECO_SITING_RUN
        | _PLAUS_UPLOAD | _PROC_MANAGE
        | _GAM_SUPPLY_VIEW | _GAM_SUPPLY_TOKEN | _GAM_SUPPLY_MILESTONE_NAV
    ),
    "OFFTAKE": (
        _GAM_DEMAND_WRITE | _GAM_MATCH_BUY
    ),
    "SELL": (
        _GAM_MATCH_SELL | _GAM_SUPPLY_PRICE | _GAM_SUPPLY_TOKEN
    ),
    "TRADE": (
        _GAM_MATCH_SELL | _GAM_MATCH_BUY
        | _GAM_SUPPLY_TOKEN | _GAM_SUPPLY_PRICE
        | _GAM_DEMAND_WRITE
    ),
    "FINANCE": (
        _ECON_VIEW | _ECON_EXPORT | _GAM_SUPPLY_CREDIT
    ),
    "INSURE": (
        _PLAUS_VIEW
        | {"compliance.instrument.operational_flags.view"}
    ),
    "CERTIFY": (
        _PLAUS_UPLOAD | _COMP_GHG | _COMP_CERT
        | {"gam.supply.token_score.view_mechanism"}
    ),
}


# ═══════════════════════════════════════════════════════════════
# 6. CONTEXT CONDITIONS — Runtime checks per permission
# ═══════════════════════════════════════════════════════════════
#
# Even if a profile grants a permission, context conditions may
# still block it at runtime. These are the conditions that a CISO
# sees in the "Conditions" column of the matrix.
#

CONTEXT_CONDITIONS: dict[str, list[dict]] = {
    "gam.supply.token.mint": [
        {"type": "requires_attribute", "attr": "token_ready", "value": True,
         "reason": "Token minting requires token_ready=true in user profile"},
        {"type": "requires_capability", "capability": "SELL",
         "reason": "Only entities with SELL capability can mint tokens"},
    ],
    "gam.matchmaking.offtaker.contact": [
        {"type": "requires_capability", "capability": "SELL",
         "reason": "Contacting offtakers requires SELL capability"},
        {"type": "requires_export_license",
         "reason": "Seller must have export_licenses covering the deal destination"},
    ],
    "gam.matchmaking.producer.contact": [
        {"type": "requires_capability", "capability": "OFFTAKE",
         "reason": "Contacting producers requires OFFTAKE capability"},
    ],
    "gam.demand.supplier.adjust_volume": [
        {"type": "aggregation_limit",
         "reason": "Volume capped at aggregation_limit_mt for this entity"},
    ],
    "gam.supply.volume_attributes.view_credit": [
        {"type": "requires_credit_rating",
         "reason": "Credit tab requires credit_rating to be set (not NR)"},
    ],
    "ecosystem.project_profile.project.edit": [
        {"type": "requires_kyc", "value": "VERIFIED",
         "reason": "Editing project profiles requires KYC verified status"},
    ],
    "orchestrator.portfolio.plant.create": [
        {"type": "requires_capability", "capability": "PRODUCE",
         "reason": "Only entities with PRODUCE capability can create plants"},
    ],
    "ecosystem.map.project.add": [
        {"type": "requires_capability", "capability": "PRODUCE",
         "reason": "Only entities with PRODUCE capability can add projects"},
    ],
    "economics.cost_stack.capex.view": [
        {"type": "mandated_lender_only", "entity_type": "BANK",
         "reason": "Banks can only view CAPEX if mandated lender on the project"},
    ],
    "gam.matchmaking.offtaker_search.configure": [
        {"type": "requires_capability", "capability": "SELL",
         "reason": "Configuring offtaker search requires SELL capability"},
    ],
    "gam.matchmaking.producer_search.configure": [
        {"type": "requires_capability", "capability": "OFFTAKE",
         "reason": "Configuring producer search requires OFFTAKE capability"},
    ],
    "plausibility.blockchain.attestation.generate": [
        {"type": "requires_capability", "capability": "PRODUCE",
         "reason": "Only producers/certifiers can generate attestations",
         "alternative_capability": "CERTIFY"},
    ],
    "ecosystem.siting.siting_result.start_project": [
        {"type": "requires_capability", "capability": "PRODUCE",
         "reason": "Starting a project from siting requires PRODUCE capability"},
    ],
}


# ═══════════════════════════════════════════════════════════════
# 7. PER-USER OVERRIDES — Durable SQLite store
# ═══════════════════════════════════════════════════════════════
#
# CISO can grant or revoke individual permissions for specific users.
# These override the role profile defaults.
# Stored durably in the auth/platform SQLite DB so overrides survive restarts.
#
_OVERRIDE_DB_PATH = settings.SQLITE_DB_PATH


def _override_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_OVERRIDE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_override_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS permission_user_overrides (
            user_id TEXT NOT NULL,
            perm_string TEXT NOT NULL,
            granted INTEGER NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, perm_string)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_permission_user_overrides_user "
        "ON permission_user_overrides(user_id)"
    )
    conn.commit()


def init_permission_override_store() -> None:
    conn = _override_conn()
    try:
        _ensure_override_table(conn)
    finally:
        conn.close()


def set_user_override(user_id: str, perm_string: str, granted: bool):
    """CISO action: grant or revoke a specific permission for a user."""
    conn = _override_conn()
    try:
        _ensure_override_table(conn)
        conn.execute(
            """
            INSERT INTO permission_user_overrides (user_id, perm_string, granted, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, perm_string)
            DO UPDATE SET granted=excluded.granted, updated_at=datetime('now')
            """,
            (user_id, perm_string, 1 if granted else 0),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_override(user_id: str, perm_string: str):
    """Remove override — revert to profile default."""
    conn = _override_conn()
    try:
        _ensure_override_table(conn)
        conn.execute(
            "DELETE FROM permission_user_overrides WHERE user_id = ? AND perm_string = ?",
            (user_id, perm_string),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_overrides(user_id: str) -> dict[str, set[str]]:
    """Get all overrides for a user."""
    conn = _override_conn()
    try:
        _ensure_override_table(conn)
        rows = conn.execute(
            "SELECT perm_string, granted FROM permission_user_overrides WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    grants = {row["perm_string"] for row in rows if row["granted"]}
    revocations = {row["perm_string"] for row in rows if not row["granted"]}
    return {"grants": grants, "revocations": revocations}


# ═══════════════════════════════════════════════════════════════
# 8. CORE API — Permission resolution and checking
# ═══════════════════════════════════════════════════════════════

def resolve_profile_key(
    company_type: str,
    business_function: str,
    service_type: Optional[str] = None,
) -> str:
    """
    Map GEX user dimensions to a profile key.

    Examples:
        PRODUCER + ENGINEERING + None     → "PRODUCER.ENGINEERING"
        THIRD_PARTY + FINANCE_TREASURY + BANK → "BANK.FINANCE_TREASURY"
        OFFTAKER + COMMERCIAL + None      → "OFFTAKER.COMMERCIAL"
    """
    if company_type == "THIRD_PARTY" and service_type:
        entity = service_type  # BANK, INSURER, CERTIFIER, ENGINEER, EQUIPMENT, LOGISTICS, LEGAL
    else:
        entity = company_type  # PRODUCER, OFFTAKER

    return f"{entity}.{business_function}"


def get_effective_permissions(
    company_type: str,
    business_function: str,
    service_type: Optional[str] = None,
    capabilities: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> set[str]:
    """
    Compute the full set of permissions for a user.

    Resolution order:
        1. Base profile from (entity_type × employee_role)
        2. + Capability extensions (prosumer grants)
        3. + Per-user grants (CISO overrides)
        4. - Per-user revocations (CISO overrides)

    Args:
        company_type: PRODUCER, OFFTAKER, THIRD_PARTY
        business_function: EXECUTIVE, ENGINEERING, FINANCE_TREASURY, etc.
        service_type: BANK, INSURER, etc. (only for THIRD_PARTY)
        capabilities: List of capability strings (OFFTAKE, PRODUCE, SELL, etc.)
        user_id: For applying per-user overrides

    Returns:
        Set of permission strings this user has.
    """
    profile_key = resolve_profile_key(company_type, business_function, service_type)

    # 1. Base profile
    perms = set(ROLE_PROFILES.get(profile_key, _ALL_BASE))

    # 2. Capability extensions
    for cap in (capabilities or []):
        cap_str = cap if isinstance(cap, str) else cap.value
        if cap_str in CAPABILITY_GRANTS:
            perms |= CAPABILITY_GRANTS[cap_str]

    # 3-4. Per-user overrides
    if user_id:
        overrides = get_user_overrides(user_id)
        perms |= overrides["grants"]
        perms -= overrides["revocations"]

    return perms


def check_permission(
    perm_string: str,
    company_type: str,
    business_function: str,
    service_type: Optional[str] = None,
    capabilities: Optional[list[str]] = None,
    user_id: Optional[str] = None,
    context: Optional[dict] = None,
) -> PermissionResult:
    """
    Check if a user has a specific permission.

    This is the primary API called by the middleware and route handlers.

    Args:
        perm_string: The permission to check (e.g., "gam.supply.token.mint")
        company_type, business_function, service_type: User dimensions
        capabilities: User capabilities for prosumer extension
        user_id: For per-user override lookup
        context: Optional runtime context (e.g., {"kyc_status": "VERIFIED"})

    Returns:
        PermissionResult with allowed/denied + reasoning
    """
    profile_key = resolve_profile_key(company_type, business_function, service_type)
    perms = get_effective_permissions(
        company_type, business_function, service_type, capabilities, user_id
    )

    # Check profile grant
    if perm_string not in perms:
        # Check if it was explicitly revoked
        overrides = get_user_overrides(user_id) if user_id else {"grants": set(), "revocations": set()}
        if perm_string in overrides["revocations"]:
            reason = f"Permission revoked by CISO override for user {user_id}"
        else:
            reason = f"Permission not granted to profile '{profile_key}'"
        return PermissionResult(
            allowed=False, perm_string=perm_string,
            reason=reason, profile_key=profile_key,
        )

    # Check context conditions
    conditions = CONTEXT_CONDITIONS.get(perm_string, [])
    evaluated = []
    ctx = context or {}

    for cond in conditions:
        cond_type = cond["type"]
        passed = True
        cond_reason = cond.get("reason", "")

        if cond_type == "requires_attribute":
            attr_val = ctx.get(cond["attr"])
            if attr_val != cond.get("value"):
                passed = False

        elif cond_type == "requires_capability":
            user_caps = set(capabilities or [])
            required = cond["capability"]
            alt = cond.get("alternative_capability")
            if required not in user_caps and (not alt or alt not in user_caps):
                passed = False

        elif cond_type == "requires_kyc":
            if ctx.get("kyc_status") != cond.get("value"):
                passed = False

        elif cond_type == "requires_credit_rating":
            if ctx.get("credit_rating", "NR") == "NR":
                passed = False

        elif cond_type == "aggregation_limit":
            limit = ctx.get("aggregation_limit_mt")
            volume = ctx.get("trade_volume_mt", 0)
            if limit is not None and volume > limit:
                passed = False

        elif cond_type == "requires_export_license":
            licenses = ctx.get("export_licenses", [])
            destination = ctx.get("destination", "")
            if destination and destination not in licenses:
                passed = False

        elif cond_type == "mandated_lender_only":
            # Only blocks if user IS the entity_type but NOT mandated
            if profile_key.startswith(cond.get("entity_type", "")):
                if not ctx.get("is_mandated_lender"):
                    passed = False

        elif cond_type == "requires_token_ready":
            if not ctx.get("token_ready"):
                passed = False

        evaluated.append({"condition": cond_type, "passed": passed, "reason": cond_reason})

        if not passed:
            return PermissionResult(
                allowed=False, perm_string=perm_string,
                reason=f"Context condition failed: {cond_reason}",
                profile_key=profile_key,
                conditions_evaluated=evaluated,
            )

    # Check if override was applied
    override_applied = False
    if user_id:
        overrides = get_user_overrides(user_id)
        if perm_string in overrides["grants"]:
            override_applied = True

    return PermissionResult(
        allowed=True, perm_string=perm_string,
        reason="Granted via profile" + (" + CISO override" if override_applied else ""),
        profile_key=profile_key,
        conditions_evaluated=evaluated,
        override_applied=override_applied,
    )


# ═══════════════════════════════════════════════════════════════
# 9. QUERY HELPERS — For CISO dashboard and Excel export
# ═══════════════════════════════════════════════════════════════

def get_all_profiles() -> dict[str, int]:
    """Return all profile keys with their permission counts."""
    return {k: len(v) for k, v in sorted(ROLE_PROFILES.items())}


def get_profile_permissions(profile_key: str) -> list[dict]:
    """Return all permissions for a profile with metadata."""
    perms = ROLE_PROFILES.get(profile_key, set())
    result = []
    for ps in sorted(perms):
        pdef = PERMISSIONS.get(ps)
        if pdef:
            result.append({
                "perm_id": pdef.perm_id,
                "perm_string": pdef.perm_string,
                "module": pdef.module,
                "description": pdef.description,
                "access_tier": pdef.access_tier.value,
                "has_conditions": ps in CONTEXT_CONDITIONS,
            })
    return result


def get_full_matrix() -> dict:
    """
    Return the complete permission matrix for Excel/CISO display.

    Structure:
        {
            "profiles": ["PRODUCER.EXECUTIVE", "PRODUCER.ENGINEERING", ...],
            "permissions": [
                {
                    "perm_id": 30,
                    "perm_string": "orchestrator.hub.orchestrator.view",
                    "module": "orchestrator",
                    "description": "...",
                    "access_tier": "PRIVILEGED",
                    "grants": {"PRODUCER.EXECUTIVE": true, "PRODUCER.ENGINEERING": true, ...},
                    "conditions": [...],
                },
                ...
            ],
        }
    """
    profiles = sorted(ROLE_PROFILES.keys())
    permissions = []

    for ps in sorted(PERMISSIONS.keys(), key=lambda x: PERMISSIONS[x].perm_id):
        pdef = PERMISSIONS[ps]
        grants = {}
        for profile_key in profiles:
            grants[profile_key] = ps in ROLE_PROFILES.get(profile_key, set())

        permissions.append({
            "perm_id": pdef.perm_id,
            "perm_string": pdef.perm_string,
            "module": pdef.module,
            "sub_service": pdef.sub_service,
            "resource": pdef.resource,
            "action": pdef.action,
            "description": pdef.description,
            "access_tier": pdef.access_tier.value,
            "grants": grants,
            "conditions": CONTEXT_CONDITIONS.get(ps, []),
        })

    return {"profiles": profiles, "permissions": permissions}


def get_capability_impact(capability: str) -> list[str]:
    """Return the permissions granted by a specific capability."""
    return sorted(CAPABILITY_GRANTS.get(capability, set()))


def diff_profiles(profile_a: str, profile_b: str) -> dict:
    """Compare two profiles — useful for CISO to understand differences."""
    perms_a = ROLE_PROFILES.get(profile_a, set())
    perms_b = ROLE_PROFILES.get(profile_b, set())
    return {
        "only_in_a": sorted(perms_a - perms_b),
        "only_in_b": sorted(perms_b - perms_a),
        "shared": sorted(perms_a & perms_b),
        "count_a": len(perms_a),
        "count_b": len(perms_b),
    }


init_permission_override_store()
