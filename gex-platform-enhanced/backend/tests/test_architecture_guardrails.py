"""
Architecture guardrails (ADR 2026-07-06). These tests are the CI enforcement
layer of the doctrine:

  Database: no hidden database, no relative path, no second database,
            no module-owned database path.
  Security: authentication by default, explicit public routes with reasons,
            no demo shortcut in production, ABAC list derived from the
            single registry.

A failure here is not a broken test — it is a doctrine regression. Fix the
code, not the test.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
REPO = BACKEND.parent

ALLOWED_DB_FILES = {BACKEND / "gex_platform.db"}


def _py_sources():
    for f in APP.rglob("*.py"):
        yield f, f.read_text()


# ── Database doctrine ─────────────────────────────────────────────────────────

FORBIDDEN_DB_IDIOMS = [
    # (regex, why it is forbidden)
    (re.compile(r"greenearth\.db"), "second database — retired 2026-07-06"),
    (re.compile(r"GEX_DB_PATH|GEX_PLATFORM_DB_PATH"),
     "module-owned env var — use settings.SQLITE_DB_PATH"),
    (re.compile(r"dirname\(__file__\).{0,80}\.db"),
     "module-owned relative path — use settings.SQLITE_DB_PATH"),
    (re.compile(r"""['"]gex_platform\.db['"]"""),
     "literal DB filename — only config.py may name the file"),
]


def test_no_module_owned_database_paths():
    violations = []
    for f, src in _py_sources():
        if f == APP / "core" / "config.py":
            continue
        for pat, why in FORBIDDEN_DB_IDIOMS:
            for m in pat.finditer(src):
                line = src[: m.start()].count("\n") + 1
                violations.append(f"{f.relative_to(BACKEND)}:{line} — {why}")
    assert not violations, "DB doctrine violations:\n" + "\n".join(violations)


def test_sqlite_path_is_absolute_and_cwd_independent():
    from app.core.config import settings, BACKEND_ROOT

    p = Path(settings.SQLITE_DB_PATH)
    assert p.is_absolute(), "SQLITE_DB_PATH must resolve to an absolute path"
    assert str(p).startswith(str(BACKEND_ROOT)), (
        "SQLITE_DB_PATH must be anchored at the backend root"
    )


def test_exactly_one_database_file_in_repo():
    strays = []
    for f in REPO.rglob("*.db"):
        if "db_backups" in f.parts or "node_modules" in f.parts:
            continue
        if f not in ALLOWED_DB_FILES:
            strays.append(str(f.relative_to(REPO)))
    assert not strays, (
        "Second database file(s) found — doctrine allows exactly "
        f"backend/gex_platform.db:\n" + "\n".join(strays)
    )


# ── Security doctrine ─────────────────────────────────────────────────────────

def test_app_has_global_auth_dependency():
    from app.main import app
    from app.core.route_security import require_authenticated

    deps = [d.dependency for d in (app.router.dependencies or [])]
    assert require_authenticated in deps, (
        "FastAPI app must carry require_authenticated as a global dependency "
        "— authentication by default is not optional"
    )


def test_every_public_route_has_a_reason():
    from app.core import route_security as rs

    for registry in (rs.PUBLIC_ROUTES, rs.PUBLIC_PREFIXES,
                     rs.ABAC_EXEMPT_ROUTES, rs.ABAC_EXEMPT_PREFIXES):
        for path, reason in registry.items():
            assert isinstance(reason, str) and len(reason.strip()) >= 10, (
                f"Public/exempt entry {path!r} lacks a substantive reason"
            )


def test_abac_bypass_is_derived_from_registry():
    from app.core import abac_middleware as mw
    from app.core import route_security as rs

    assert mw.BYPASS_ROUTES == set(rs.PUBLIC_ROUTES) | set(rs.ABAC_EXEMPT_ROUTES)
    assert mw.BYPASS_PREFIXES == set(rs.PUBLIC_PREFIXES) | set(rs.ABAC_EXEMPT_PREFIXES)


def test_unregistered_routes_reject_anonymous_requests():
    """Sample real registered GET routes and confirm they 401 without a token."""
    from fastapi.testclient import TestClient
    from starlette.routing import Route
    from app.main import app
    from app.core.route_security import is_public

    client = TestClient(app)
    checked = 0
    for route in app.routes:
        if not isinstance(route, Route) or "GET" not in (route.methods or set()):
            continue
        path = route.path
        if is_public(path) or "{" in path or not path.startswith("/api/"):
            continue
        r = client.get(path)
        assert r.status_code == 401, (
            f"{path} answered {r.status_code} to an anonymous request — "
            "every unregistered route must fail closed with 401"
        )
        checked += 1
        if checked >= 25:
            break
    assert checked > 0, "no protected routes were exercised — test is vacuous"


def test_production_refuses_demo_mode_and_dev_secret():
    """Config must hard-fail at import in production with demo mode on."""
    code = (
        "import os;"
        "os.environ['ENVIRONMENT']='production';"
        "os.environ['GEX_DEMO_MODE']='true';"
        "os.environ['SECRET_KEY']='x'*64;"
        "import app.core.config"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND,
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
    )
    assert proc.returncode != 0, "production import with GEX_DEMO_MODE=True must fail"
    assert "GEX_DEMO_MODE" in proc.stderr


def test_every_api_route_maps_to_a_domain():
    """Layer-2 coverage: no registered /api route may be domain-unmapped."""
    from starlette.routing import Route
    from app.main import app
    from app.core.domain_authorization import domain_for_path, DOMAINS, DOMAIN_PREFIXES
    from app.core.route_security import is_public

    unmapped = []
    for route in app.routes:
        if not isinstance(route, Route) or not route.path.startswith("/api/"):
            continue
        if is_public(route.path):
            continue
        if domain_for_path(route.path) is None:
            unmapped.append(route.path)
    assert not unmapped, (
        "Routes without a business domain (register in DOMAIN_PREFIXES):\n"
        + "\n".join(sorted(set(unmapped)))
    )
    # every mapped domain must exist and carry a description
    for prefix, domain in DOMAIN_PREFIXES.items():
        assert domain in DOMAINS, f"{prefix} maps to unknown domain {domain!r}"
    for d in DOMAINS.values():
        assert len(d.description) >= 10, f"domain {d.name} lacks a description"


def test_domain_write_policy_decisions():
    from app.core.domain_authorization import check_domain_access

    commercial = {"business_function": "COMMERCIAL", "service_type": None}
    treasury = {"business_function": "FINANCE_TREASURY", "service_type": None}
    admin = {"business_function": "COMMERCIAL", "is_platform_admin": True}
    service = {"session_tier": "service", "business_function": "SERVICE"}

    # reads always pass
    assert check_domain_access(commercial, "/api/v1/capital-bridge/x", "GET")[0]
    # finance writes: treasury yes, commercial no
    assert check_domain_access(treasury, "/api/v1/capital-bridge/x", "POST")[0]
    ok, domain, _ = check_domain_access(commercial, "/api/v1/capital-bridge/x", "POST")
    assert not ok and domain == "finance"
    # commercial CAN write marketplace
    assert check_domain_access(commercial, "/api/v1/marketplace/listings", "POST")[0]
    # platform admin and service tokens pass everywhere
    assert check_domain_access(admin, "/api/v1/ciso/policies", "POST")[0]
    assert check_domain_access(service, "/api/v1/bankability/evaluate", "POST")[0]
    # unmapped route fails closed
    ok, domain, reason = check_domain_access(treasury, "/api/v1/brand-new-module/x", "POST")
    assert not ok and domain is None and "not mapped" in reason


def test_engines_verify_gex_identity_only():
    """One issuer: no Supabase (or other third-party) verifier in any engine."""
    engine_trees = [
        REPO / "tea_engine",
        REPO / "gex_pf_engine",
        REPO.parent / "gex_pf_engine" / "backend" / "app",
    ]
    offenders = []
    for tree in engine_trees:
        if not tree.exists():
            continue
        for f in tree.rglob("*.py"):
            if "venv" in f.parts or f.name == "gex_jwt.py":
                continue
            if "supabase" in f.read_text().lower():
                offenders.append(str(f))
    assert not offenders, (
        "Engine files still reference Supabase:\n" + "\n".join(offenders)
    )
    for tree in engine_trees:
        assert not list(tree.rglob("supabase_jwt.py")), (
            f"retired verifier still present under {tree}"
        )


def test_compose_runs_the_tree_that_tests_inspect():
    """
    Copy-tree entropy guard (consolidation, ADR 2026-07-06): the code this
    suite tests must be the code docker-compose runs. Two assertions:

    1. The blessed compose (REPO/docker-compose.yml) builds AND volume-mounts
       its backend service from exactly this backend tree.
    2. No other compose file in the workspace defines a backend service that
       builds from a different tree. (`co-work/` is excluded pending the
       inventory decision of 2026-07-06 — it is the git push channel;
       `_retired/` holds the archived fossils.)
    """
    import yaml

    compose_path = REPO / "docker-compose.yml"
    cfg = yaml.safe_load(compose_path.read_text())
    backend_svc = cfg["services"]["backend"]

    ctx = (REPO / backend_svc["build"]["context"]).resolve()
    assert ctx == BACKEND, (
        f"blessed compose builds backend from {ctx}, tests inspect {BACKEND}"
    )
    app_mounts = [v for v in backend_svc.get("volumes", []) if v.endswith(":/app")]
    for mount in app_mounts:
        src = (REPO / mount.split(":")[0]).resolve()
        assert src == BACKEND, (
            f"blessed compose mounts {src} over /app, tests inspect {BACKEND}"
        )

    workspace = REPO.parent
    skip_parts = {"node_modules", "_retired", "co-work", ".git", "venv", ".venv"}
    offenders = []
    for depth in ("", "*/", "*/*/"):
        for f in workspace.glob(f"{depth}docker-compose*.yml"):
            if set(f.parts) & skip_parts or f == compose_path:
                continue
            try:
                data = yaml.safe_load(f.read_text()) or {}
            except yaml.YAMLError:
                offenders.append(f"{f} — unparseable")
                continue
            svc = (data.get("services") or {}).get("backend")
            if not svc or "build" not in svc:
                continue  # no backend, or image-based (prod) — fine
            bctx = (f.parent / svc["build"].get("context", ".")).resolve()
            if bctx != BACKEND:
                offenders.append(f"{f} builds backend from {bctx}")
    assert not offenders, (
        "compose files run a DIFFERENT backend tree than the one under test "
        "(reviewed code != running code):\n" + "\n".join(offenders)
    )


def test_no_new_raw_sqlite_connections():
    """
    Transitional ratchet for the Postgres migration: raw sqlite3.connect call
    sites may only DECREASE. Baseline frozen 2026-07-06. When you migrate a
    module to the SQLAlchemy/Postgres layer, lower the baseline. Never raise it.
    """
    # 98 on 2026-07-06. Auth slice (2026-08-07) removed the call sites in
    # core/auth.py and core/refresh_tokens.py; both now go through
    # core/db_backend.auth_connection(), the slice's single SQLite entry point,
    # which is itself one site. Net: 98 → 97.
    BASELINE = 97
    count = sum(src.count("sqlite3.connect") for _, src in _py_sources())
    assert count <= BASELINE, (
        f"{count} raw sqlite3.connect sites (baseline {BASELINE}) — new code "
        "must use the app.db.session layer, not raw SQLite"
    )


def test_pg_support_is_the_only_postgres_connect_site_in_the_suite():
    """
    An unreachable database must SKIP, never FAIL (added 2026-08-10).

    Before `tests/pg_support.py`, seven files each had their own `_pg()` and 24
    call sites guarded PostgreSQL access with nothing but a DSN *string* check:

        if not (os.environ.get("DATABASE_URL") or "").startswith("postgres"):

    That does not check whether anything is listening. Helpers that caught the
    connection error skipped; raw `psycopg2.connect` call sites raised it and
    failed. With the container stopped the suite reported *8 failed, 209 passed,
    70 skipped* — an outage that reads exactly like a regression, which wastes
    the reviewer's attention on the one thing that is not a code defect.

    Now: 0 failed, 209 passed, 78 skipped.

    This is enforced over the AST, not the text, because the explanation above
    contains both offending patterns verbatim and an earlier generation of these
    guardrails repeatedly matched its own prose.
    """
    import ast

    # This file is excluded because it is the scanner: the detector below
    # necessarily contains a literal `.startswith("postgres")`, so including it
    # makes the guardrail flag itself. It holds no PostgreSQL tests.
    SCANNER = Path(__file__).name

    offenders = []
    for path in sorted((BACKEND / "tests").glob("test_*.py")):
        if path.name == SCANNER:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            # psycopg2.connect(...)
            if (isinstance(f, ast.Attribute) and f.attr == "connect"
                    and isinstance(f.value, ast.Name) and f.value.id == "psycopg2"):
                offenders.append(f"{path.name}:{node.lineno} psycopg2.connect()")
            # <dsn>.startswith("postgres")
            if (isinstance(f, ast.Attribute) and f.attr == "startswith"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and str(node.args[0].value).startswith("postgres")):
                offenders.append(f"{path.name}:{node.lineno} DSN-string guard")

    assert not offenders, (
        "PostgreSQL must be reached only through tests/pg_support.py, so that an "
        "absent or unreachable database always reads as a skip:\n  "
        + "\n  ".join(offenders)
    )
