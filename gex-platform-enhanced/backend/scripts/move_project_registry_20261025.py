"""
Move what only the code knew about projects into PostgreSQL (JML, 2026-10-25).

`project_registry.PROJECT_ACCESS_PROFILES` was a Python dictionary holding, for
12 projects, the owner, associated companies, mandated lenders and insurers and
the jurisdiction. tenant_admin.sync_from_registry had copied most of it into
`projects`, `tenants` and `project_access`; this closes the rest, so the
dictionary can be deleted and PostgreSQL is the only source:

  1. projects.country, where NULL, from the dictionary's jurisdiction (7 projects).
     Access checks compare this value, so it must survive the move unchanged.
  2. proj_etf_pecos1's associated companies (ING Capital, BNP Paribas CIB,
     Maersk Decarbonization): tenants rows, created the way sync_from_registry
     always created them (THIRD_PARTY, EU), and STAKEHOLDER access rows.

The values are written here verbatim from the dictionary as it stood on
2026-10-25 (the dictionary itself is deleted in the same change).
Idempotent; dry run unless --execute.

    cd backend && set -a && source .env && set +a
    ./venv/bin/python scripts/move_project_registry_20261025.py [--execute]

A database rebuilt from Alembic needs this run (after the 020 / restore_* project
scripts); a pg_dump restore already carries it.
"""
from __future__ import annotations

import os
import sys

COUNTRY = {   # project_id -> the dictionary's jurisdiction (ISO country)
    "proj_bremen_h2": "DE", "proj_rotterdam_nh3": "NL", "proj_sansebastian_emethanol": "ES",
    "proj_wales_saf": "GB", "proj_lehavre_eng": "FR", "proj_hamburgone_emethanol": "DE",
    "proj_madrid2_sansebastian": "ES",
}
STAKEHOLDERS = {  # project_id -> associated companies (company_id, company_name)
    "proj_etf_pecos1": (("ing_capital", "ING Capital"), ("bnp_paribas_cib", "BNP Paribas CIB"),
                        ("maersk_decarbonization", "Maersk Decarbonization")),
}


def main(execute: bool) -> int:
    import psycopg2

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")       # gex_user: a data migration, like the copiers
    if not (dsn or "").startswith("postgres"):
        print("ALEMBIC_DATABASE_URL must be exported")
        return 1
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()
        for pid, country in COUNTRY.items():
            cur.execute("UPDATE projects SET country = %s, updated_at = now() WHERE project_id = %s "
                        "AND country IS NULL", (country, pid))
            print(f"1. {pid}: country {country} {'set' if cur.rowcount else 'already set'}")
        for pid, companies in STAKEHOLDERS.items():
            cur.execute("SELECT owner_tenant_id FROM projects WHERE project_id = %s", (pid,))
            owner = cur.fetchone()[0]
            for cid, name in companies:
                cur.execute("INSERT INTO tenants (company_id, company_name, company_type, jurisdiction) "
                            "VALUES (%s, %s, 'THIRD_PARTY', 'EU') ON CONFLICT (company_id) DO NOTHING",
                            (cid, name))
                tenant = cur.rowcount
                cur.execute("INSERT INTO project_access (project_id, company_id, actor_type, access_role, "
                            "granted_by) SELECT %s, %s, 'STAKEHOLDER', 'STAKEHOLDER', %s WHERE NOT EXISTS "
                            "(SELECT 1 FROM project_access WHERE project_id = %s AND company_id = %s)",
                            (pid, cid, owner, pid, cid))
                print(f"2. {pid}: {name} tenant {'added' if tenant else 'present'}, "
                      f"access {'added' if cur.rowcount else 'present'}")
        if execute:
            conn.commit()
            print("committed")
        else:
            conn.rollback()
            print("dry run — nothing written; pass --execute")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main("--execute" in sys.argv))
