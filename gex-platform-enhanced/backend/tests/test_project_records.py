"""
Project data lives in PostgreSQL only (JML, 2026-10-25; alembic 068).

Five copies of project data used to live in code: the frontend's
customerProjects.ts array, and in the backend PROJECT_ACCESS_PROFILES,
PROJECT_PHYSICAL, _PROJECT_META, FALLBACK_PROJECT_META and RISK_FLAGS. They were
moved into projects / project_access / project_context / project_profile /
project_risk_flag and deleted. These tests keep it that way, and check the
profiles the access rules now read (dev database, read only).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from pg_support import requires_pg

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"
REMOVED = {"PROJECT_ACCESS_PROFILES", "PROJECT_PHYSICAL", "_PROJECT_META", "FALLBACK_PROJECT_META", "RISK_FLAGS",
           "_PROJECT_PROFILE_INTELLIGENCE", "PROJECT_TRUTH", "DEFAULT_PROJECT_TRUTH", "DEMO_CONTEXTS",
           "_DEFAULT_CTX", "_DRAWDOWN_BY_PROJECT", "_DRAWDOWN_DEFAULT", "MOCK_PROJECTS", "PROJECT_ID_ALIASES"}


def test_no_backend_module_defines_project_data():
    """Read from the AST: the comments that say where the data went may name it."""
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else \
                [node.target] if isinstance(node, ast.AnnAssign) else []
            offenders += [f"{path.relative_to(BACKEND)}:{t.id}" for t in targets
                          if isinstance(t, ast.Name) and t.id in REMOVED]
    assert not offenders, f"project data defined in code again: {offenders}"


def test_the_frontend_holds_no_project_records():
    data = (FRONTEND / "data" / "customerProjects.ts").read_text()
    code = re.sub(r"//[^\n]*|/\*.*?\*/", "", data, flags=re.S)
    assert not re.search(r"export\s+const\s+CUSTOMER_PROJECTS\b|DEFAULT_PROJECT_ID|getProjectById", code), \
        "customerProjects.ts must hold types only"
    importers = [str(p.relative_to(FRONTEND)) for p in FRONTEND.rglob("*.ts*") if p.is_file()
                 if "__tests__" not in p.parts and "test" not in p.parts
                 and re.search(r"""from\s+['"]@/test/fixtures/""", p.read_text())]
    assert not importers, f"application code imports the test fixture: {importers}"


def test_access_profiles_come_from_postgresql():
    requires_pg()
    from app.core.project_registry import get_project_profile

    p = get_project_profile("proj_hamburgone_emethanol")
    assert p is not None and p.owner_company_id == "hamburgone_com"
    assert p.jurisdiction == "DE", "the country moved from the dictionary must survive"
    assert "nordlb" in p.mandated_lender_ids and "allianz" in p.mandated_insurer_ids
    assert {"brementhree_ag", "nordlb", "allianz"} <= p.shared_with_company_ids
    pecos = get_project_profile("proj_etf_pecos1")
    assert {"ing_capital", "bnp_paribas_cib", "maersk_decarbonization"} <= pecos.shared_with_company_ids
    assert get_project_profile("proj_does_not_exist") is None


def test_reviewers_are_not_stakeholders():
    """An appointed reviewer's project_access row (REVIEWER) grants gate-scoped
    access only; it must not make its company a project stakeholder."""
    from app.core import project_registry as reg

    row = {"project_id": "p", "project_name": "TEST", "owner_company_name": "TEST Owner", "country": "DE"}
    access = [{"company_name": "TEST Engineer", "access_role": "REVIEWER"},
              {"company_name": "TEST Lender", "access_role": "MANDATED_LENDER"}]
    profile = reg._build_profile(row, access)
    assert profile.shared_with_company_ids == {"test_lender"}


def test_risk_flags_come_from_postgresql():
    requires_pg()
    from app.core.risk_flags import visible_risk_flags

    admin = visible_risk_flags("proj_etf_pecos1", {"is_platform_admin": True})
    assert admin and all(f.project_id == "proj_etf_pecos1" for f in admin)
    assert visible_risk_flags("proj_etf_pecos1", {"company_name": "TEST Stranger"}) is None


def test_profile_intelligence_comes_from_postgresql():
    requires_pg()
    from app.core.projects_store import _rows

    rows = _rows("SELECT record_id, narrative FROM project_profile_intelligence WHERE project_id = :pid",
                 {"pid": "proj_etf_pecos1"})
    assert [r["record_id"] for r in rows] == ["profile_intel_proj_etf_pecos1_public_v1"]


def test_project_inputs_come_from_postgresql_and_nothing_stands_in():
    """Part 2 (alembic 069): deal-killer / task-router inputs are datasets; a
    project without them has none — no invented default answers for it."""
    requires_pg()
    from app.core.project_truth import get_project_truth

    bremen = get_project_truth("proj_bremen_h2")
    assert bremen["inputs_recorded"] and bremen["deal_killers"] and bremen["inputs_verification"] == "UNVERIFIED"
    other = get_project_truth("proj_north_sea_e_methanol_203b51")
    assert other["inputs_recorded"] is False and other["deal_killers"] == {}


def test_structuring_refuses_a_project_with_no_recorded_context():
    requires_pg()
    from fastapi import HTTPException

    from app.api.v1.routes_structuring import _get_demo_context

    assert _get_demo_context("proj_bremen_h2")["jurisdiction"] == "DE"
    with pytest.raises(HTTPException) as refused:
        _get_demo_context("proj_hamburgone_emethanol")
    assert refused.value.detail["code"] == "STRUCTURING_CONTEXT_NOT_RECORDED"


def test_retired_ids_resolve_through_postgresql():
    requires_pg()
    from app.core.project_registry import normalize_project_id

    assert normalize_project_id("proj_le_havre_eng") == "proj_lehavre_eng"
    assert normalize_project_id("proj_bremen_h2") == "proj_bremen_h2"


def test_eligible_instruments_answers_for_a_recorded_context_and_refuses_otherwise():
    """It raised NameError (a 500 for every project) until 2026-10-25."""
    requires_pg()
    import asyncio

    from fastapi import HTTPException

    from app.api.v1.routes_instruments import eligible_instruments

    assert asyncio.run(eligible_instruments("proj_bremen_h2"))["project_id"] == "proj_bremen_h2"
    with pytest.raises(HTTPException) as refused:
        asyncio.run(eligible_instruments("proj_hamburgone_emethanol"))
    assert refused.value.status_code == 404
