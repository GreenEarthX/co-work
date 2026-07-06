"""
Tenant administration — grant/revoke project access, sync registry, list tenants.

All mutations write to PostgreSQL.  RLS is bypassed here because these
functions run under a service/admin connection (BYPASSRLS role) or with
company_id = 'PLATFORM_ADMIN'.

CLI usage (from backend/):
    python -m app.core.tenant_admin sync
    python -m app.core.tenant_admin list-projects --company hamburgone_com
    python -m app.core.tenant_admin grant  --project proj_hamburgone_emethanol --company nordlb --actor COMMERCIAL_BANKER --role MANDATED_LENDER
    python -m app.core.tenant_admin revoke --project proj_hamburgone_emethanol --company nordlb --actor COMMERCIAL_BANKER
"""

from __future__ import annotations

import sys
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.project_registry import PROJECT_ACCESS_PROFILES, company_slug

_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, autocommit=False, autoflush=False)


def _admin_session() -> Session:
    """Session without RLS filtering — used for admin operations only."""
    db = _SessionLocal()
    # Bypass RLS by setting the sentinel used by the PLATFORM_ADMIN branch
    db.execute(text("SET LOCAL app.current_company_id = 'PLATFORM_ADMIN'"))
    return db


# ── Sync ──────────────────────────────────────────────────────────────────────

def sync_from_registry() -> None:
    """
    Upsert tenants, projects, and project_access rows from the static
    project_registry.py.  Safe to run repeatedly — uses ON CONFLICT DO UPDATE.
    """
    db = _admin_session()
    try:
        # Collect all company names that appear anywhere in the registry
        all_companies: dict[str, str] = {}  # company_id -> company_name
        for profile in PROJECT_ACCESS_PROFILES.values():
            for name in (profile.owner_company_name, *profile.associated_company_names):
                cid = company_slug(name)
                all_companies[cid] = name

        # Upsert tenants
        for cid, name in all_companies.items():
            db.execute(text("""
                INSERT INTO tenants (company_id, company_name, company_type, jurisdiction)
                VALUES (:cid, :name, 'THIRD_PARTY', 'EU')
                ON CONFLICT (company_id) DO UPDATE
                  SET company_name = EXCLUDED.company_name,
                      updated_at   = now()
            """), {"cid": cid, "name": name})

        # Upsert projects
        for project_id, profile in PROJECT_ACCESS_PROFILES.items():
            db.execute(text("""
                INSERT INTO projects
                    (project_id, project_name, owner_tenant_id, molecule, jurisdiction)
                VALUES (:pid, :pname, :oid, 'H2', :jur)
                ON CONFLICT (project_id) DO UPDATE
                  SET project_name    = EXCLUDED.project_name,
                      owner_tenant_id = EXCLUDED.owner_tenant_id,
                      jurisdiction    = EXCLUDED.jurisdiction,
                      updated_at      = now()
            """), {
                "pid":   project_id,
                "pname": profile.project_name,
                "oid":   profile.owner_company_id,
                "jur":   profile.jurisdiction,
            })

            # Owner access row
            _upsert_access(db, project_id, profile.owner_company_id,
                           "PRODUCER", "OWNER", profile.owner_company_id)

            # Associated company access rows
            for name in profile.associated_company_names:
                cid = company_slug(name)
                if cid in profile.mandated_lender_ids:
                    actor, role = "COMMERCIAL_BANKER", "MANDATED_LENDER"
                elif cid in profile.mandated_insurer_ids:
                    actor, role = "INSURER", "MANDATED_INSURER"
                else:
                    actor, role = "STAKEHOLDER", "STAKEHOLDER"
                _upsert_access(db, project_id, cid, actor, role, profile.owner_company_id)

        db.commit()
        print(f"Synced {len(PROJECT_ACCESS_PROFILES)} projects from registry.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _upsert_access(
    db: Session,
    project_id: str,
    company_id: str,
    actor_type: str,
    access_role: str,
    granted_by: str,
) -> None:
    db.execute(text("""
        INSERT INTO project_access
            (project_id, company_id, actor_type, access_role, granted_by)
        VALUES (:pid, :cid, :at, :ar, :gb)
        ON CONFLICT (project_id, company_id, actor_type) DO UPDATE
          SET access_role = EXCLUDED.access_role,
              granted_by  = EXCLUDED.granted_by
    """), {"pid": project_id, "cid": company_id, "at": actor_type, "ar": access_role, "gb": granted_by})


# ── Grant / Revoke ────────────────────────────────────────────────────────────

def grant_project_access(
    project_id: str,
    company_id: str,
    actor_type: str,
    access_role: str = "STAKEHOLDER",
    granted_by: str = "platform_admin",
) -> None:
    db = _admin_session()
    try:
        _upsert_access(db, project_id, company_id, actor_type, access_role, granted_by)
        db.commit()
        print(f"Granted {actor_type}/{access_role} on {project_id} to {company_id}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def revoke_project_access(
    project_id: str,
    company_id: str,
    actor_type: str,
) -> None:
    db = _admin_session()
    try:
        result = db.execute(text("""
            DELETE FROM project_access
            WHERE project_id = :pid
              AND company_id  = :cid
              AND actor_type  = :at
        """), {"pid": project_id, "cid": company_id, "at": actor_type})
        db.commit()
        if result.rowcount:
            print(f"Revoked {actor_type} on {project_id} from {company_id}.")
        else:
            print(f"No matching access row found.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Query helpers ─────────────────────────────────────────────────────────────

def list_projects_for_company(company_id: str) -> list[dict]:
    db = _admin_session()
    try:
        rows = db.execute(text("""
            SELECT p.project_id, p.project_name, p.molecule, p.status,
                   pa.actor_type, pa.access_role
            FROM project_access pa
            JOIN projects p ON p.project_id = pa.project_id
            WHERE pa.company_id = :cid
              AND p.is_active = true
            ORDER BY p.project_name
        """), {"cid": company_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


def list_companies_on_project(project_id: str) -> list[dict]:
    db = _admin_session()
    try:
        rows = db.execute(text("""
            SELECT pa.company_id, t.company_name, pa.actor_type, pa.access_role, pa.granted_by
            FROM project_access pa
            JOIN tenants t ON t.company_id = pa.company_id
            WHERE pa.project_id = :pid
            ORDER BY pa.access_role, pa.company_id
        """), {"pid": project_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

def _cli() -> None:  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser(description="GEX tenant admin")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("sync", help="Sync tenants/projects from project_registry.py")

    lp = sub.add_parser("list-projects", help="List projects visible to a company")
    lp.add_argument("--company", required=True)

    lc = sub.add_parser("list-companies", help="List companies on a project")
    lc.add_argument("--project", required=True)

    gp = sub.add_parser("grant", help="Grant project access")
    gp.add_argument("--project", required=True)
    gp.add_argument("--company", required=True)
    gp.add_argument("--actor",   required=True)
    gp.add_argument("--role",    default="STAKEHOLDER")
    gp.add_argument("--by",      default="platform_admin")

    rp = sub.add_parser("revoke", help="Revoke project access")
    rp.add_argument("--project", required=True)
    rp.add_argument("--company", required=True)
    rp.add_argument("--actor",   required=True)

    args = parser.parse_args()

    if args.cmd == "sync":
        sync_from_registry()

    elif args.cmd == "list-projects":
        rows = list_projects_for_company(args.company)
        for r in rows:
            print(f"  {r['project_id']:40s} {r['actor_type']:20s} {r['access_role']}")

    elif args.cmd == "list-companies":
        rows = list_companies_on_project(args.project)
        for r in rows:
            print(f"  {r['company_id']:30s} {r['actor_type']:20s} {r['access_role']:20s} granted_by={r['granted_by']}")

    elif args.cmd == "grant":
        grant_project_access(args.project, args.company, args.actor, args.role, args.by)

    elif args.cmd == "revoke":
        revoke_project_access(args.project, args.company, args.actor)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    _cli()
