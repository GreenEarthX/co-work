"""
Screen access rules — a client CISO's tailoring of the platform's default
screen access, per company and per business function.

The default lives in the frontend menu config (menuArchitecture.ts `visible_to`
plus the executive default). A rule here overrides it for one company:
  ALLOW — open the screen to that function,
  DENY  — close it to that function.
Navigation only: data access is still decided by ABAC and the permission engine.

Schema: SQLite is created here; on PostgreSQL alembic migration 060 owns it,
with company-scoped row-level security.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.core.db_backend import governance_connection, governance_is_postgres

BUSINESS_FUNCTIONS = {
    "ENGINEERING", "FINANCE_TREASURY", "COMMERCIAL",
    "COMPLIANCE_LEGAL", "OPERATIONS", "EXECUTIVE",
}
EFFECTS = {"ALLOW", "DENY"}
_SCREEN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_RULES = 1000


class ScreenAccessError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def init_screen_access_db(db_path: str | None = None) -> None:
    if governance_is_postgres():
        return  # alembic 060
    con = governance_connection(sqlite_path=db_path)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS screen_access_rules (
                company_id TEXT NOT NULL,
                screen_id TEXT NOT NULL,
                business_function TEXT NOT NULL,
                effect TEXT NOT NULL CHECK (effect IN ('ALLOW', 'DENY')),
                updated_by TEXT,
                updated_at TEXT,
                PRIMARY KEY (company_id, screen_id, business_function)
            )
        """)
        con.commit()
    finally:
        con.close()


def validate_rules(rules: list[dict]) -> list[dict]:
    """Return normalised rules or raise with every problem found."""
    problems: list[str] = []
    if len(rules) > MAX_RULES:
        problems.append(f"at most {MAX_RULES} rules per company")
    out: dict[tuple[str, str], dict] = {}
    for i, r in enumerate(rules[:MAX_RULES]):
        sid = str(r.get("screen_id", ""))
        fn = str(r.get("business_function", ""))
        eff = str(r.get("effect", "")).upper()
        if not _SCREEN_ID.match(sid):
            problems.append(f"rule {i}: invalid screen_id {sid!r}")
        if sid.startswith("ciso-"):
            problems.append(f"rule {i}: security administration screens cannot be tailored")
        if fn not in BUSINESS_FUNCTIONS:
            problems.append(f"rule {i}: unknown business_function {fn!r}")
        if eff not in EFFECTS:
            problems.append(f"rule {i}: effect must be ALLOW or DENY")
        out[(sid, fn)] = {"screen_id": sid, "business_function": fn, "effect": eff}
    if problems:
        raise ScreenAccessError(problems)
    return list(out.values())


def list_rules(company_id: str) -> list[dict]:
    con = governance_connection(company_id)
    try:
        rows = con.execute(
            "SELECT screen_id, business_function, effect, updated_by, updated_at "
            "FROM screen_access_rules WHERE company_id = ? "
            "ORDER BY screen_id, business_function",
            (company_id,),
        ).fetchall()
        return [
            {"screen_id": r["screen_id"], "business_function": r["business_function"],
             "effect": r["effect"], "updated_by": r["updated_by"], "updated_at": r["updated_at"]}
            for r in rows
        ]
    finally:
        con.close()


def replace_rules(company_id: str, rules: list[dict], updated_by: str | None) -> list[dict]:
    """Replace the company's whole rule set in one transaction."""
    clean = validate_rules(rules)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con = governance_connection(company_id)
    try:
        con.execute("DELETE FROM screen_access_rules WHERE company_id = ?", (company_id,))
        for r in clean:
            con.execute(
                "INSERT INTO screen_access_rules "
                "(company_id, screen_id, business_function, effect, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (company_id, r["screen_id"], r["business_function"], r["effect"], updated_by, now),
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return list_rules(company_id)
