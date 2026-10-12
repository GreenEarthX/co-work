#!/usr/bin/env python3
"""
load_fortaverde_test_project.py — FortaVerde (Pecém) as a labelled TEST fixture.
===============================================================================
Loads the FortaVerde knowledge record (scripts/fortaverde_knowledge_v2.json by
default) into the platform so GEX can walk it through the verification protocol
internally before the real company has registered. JML chose this route on
2026-10-09 over waiting for self-registration or registering the contacts from
details supplied by GEX.

THE KNOWLEDGE FILE IS THE ONLY SOURCE
-------------------------------------
Every fact — ids, names, premise, claims, contradictions, the expected protocol
result — comes from the JSON. This script holds mechanics only. The file is run
through validate_fortaverde_knowledge.py first; any problem aborts before a
connection is opened. Edit the JSON, not this script, when what GEX knows changes.

WHAT IT WRITES
--------------
  tenants          company.fixture_tenant
  projects         project.project_id; metadata_json holds the whole knowledge
                   record plus its sha256, so the database row can be traced to
                   the exact file that produced it
  project_context  project.context values
  project_access   the tenant as PRODUCER / OWNER
  auth_users       one PENDING stand-in per contact (see below)

WHAT IT DELIBERATELY DOES NOT WRITE
-----------------------------------
* No bankability_evidence rows. Nothing has been submitted and no reviewer is
  appointed, so every item is NOT_STARTED — what the engine assumes for an item
  with no row. Request rows would also break test_evidence_slice.py, whose parity
  exemption covers only the comprehension marker and only VERIFIED rows.
* maturity_claimed is never written anywhere as a maturity: it is what a source
  says, and bankability_evidence.maturity is the submitter's declaration.
* No ACTIVE accounts and no real names. Contacts are CRM data. Each stand-in uses
  a reserved .test address and an unusable password, and cannot log in
  (LOGIN_PERMITTED_STATES = {ACTIVE}). Rows 346/347, archived 2026-09-26, are
  the precedent for why invented content under real people's names is refused.
* No commitment cards while commitment_cards.load_after names any contradiction.
* gex_working_assumptions stay in metadata only; they are GEX/IFE estimates.

Every row carries meta.fixture_marker, which is how --remove finds them. View
the project as PLATFORM_ADMIN.

USAGE
    export ALEMBIC_DATABASE_URL=...        # gex_user: this writes data
    python scripts/load_fortaverde_test_project.py              # dry run
    python scripts/load_fortaverde_test_project.py --execute
    python scripts/load_fortaverde_test_project.py --verify     # engines vs protocol_result; writes nothing
    python scripts/load_fortaverde_test_project.py --remove --execute
    python scripts/load_fortaverde_test_project.py --activate P1 --execute   # see ACTIVATING
    ... --knowledge path/to/other.json                          # another version of the record

ACTIVATING A STAND-IN (JML, 2026-10-12)
---------------------------------------
--activate <contact_id> makes one stand-in loginable so GEX can walk the
producer's own screens. It BYPASSES vetting and the row says so:
  activated_by = meta.fixture_marker   (not SEED_GRANDFATHERED, not MANUAL_ADMIN_GRANT)
  phone_verified_*, agreement_*        stay EMPTY — no call, no agreement happened
  vetting_note                         gains an ACTIVATED line naming the bypass
Only a marked stand-in of a proj_TEST_ fixture can be activated; a real account
cannot be touched by this flag. The password is then set by the person who will
use it, with scripts/set_password.py (getpass; never stored here).
A later --execute recreates the stand-ins as PENDING: activate again afterwards.

Idempotent: --execute removes this fixture's own rows first, then writes them.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
DEFAULT_KNOWLEDGE = HERE / "fortaverde_knowledge_v2.json"

# Contact role -> auth_users.business_function. Unknown roles fall back to
# EXECUTIVE and say so in the vetting note; a stand-in cannot log in either way.
FUNCTION_FOR_ROLE = {"FINANCE": "FINANCE", "ENGINEERING": "ENGINEERING", "LEGAL": "LEGAL"}


# ── The knowledge file ──────────────────────────────────────────────────────

class Knowledge:
    """Validated view of the knowledge JSON. Construct with Knowledge.load()."""

    def __init__(self, doc: dict, path: Path, sha256: str):
        self.doc, self.path, self.sha256 = doc, path, sha256
        meta, project, company = doc["meta"], doc["project"], doc["company"]
        tenant = company["fixture_tenant"]
        ctx = project["context"]
        self.marker: str = meta["fixture_marker"]
        self.project_id: str = project["project_id"]
        self.project_name: str = project["fixture_name"]
        self.molecule: str = project["molecule"]
        self.location: str = f"{project['location']} — synthetic record"
        self.country: str = project["country"]
        self.capacity_mtpd = project.get("capacity_mtpd_pilot")
        self.capex_eur = project.get("capex_eur")
        self.tenant_id: str = tenant["company_id"]
        self.tenant_name: str = tenant["company_name"]
        self.tenant_type: str = tenant["company_type"]
        self.tenant_jurisdiction: str = tenant["jurisdiction"]
        self.power_model: str = ctx["power_model"]["value"]
        self.phase: str = ctx["phase"]["value"]
        self.financing_model: str = ctx["financing_model"]["value"]
        self.contacts: list[dict] = doc.get("contacts", [])
        self.cards: dict = doc.get("commitment_cards", {})
        self.expected: dict = doc["protocol_result"]

    @classmethod
    def load(cls, path: Path) -> "Knowledge":
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict) or doc.get("meta", {}).get("schema_version", "").split(".")[0] != "2":
            sys.exit(f"{path.name}: not a schema-2 knowledge record — refusing")
        problems = _validator().validate(doc)
        if problems:
            print(f"  {path.name} failed validation — nothing done:")
            for p in problems:
                print(f"    - {p}")
            sys.exit(1)
        if not doc["project"]["project_id"].startswith("proj_TEST_"):
            sys.exit("project_id must start with proj_TEST_: this script loads fixtures only")
        if not doc["meta"].get("synthetic"):
            sys.exit("meta.synthetic is not true: this script loads fixtures only")
        return cls(doc, path, hashlib.sha256(raw).hexdigest())

    def stand_ins(self) -> list[tuple[str, str, str, str, str]]:
        """(user_id, email, user_name, business_function, note) per contact. No real names."""
        out = []
        for c in self.contacts:
            cid = c["contact_id"].lower()
            role = (c.get("role") or "").upper()
            function = FUNCTION_FOR_ROLE.get(role, "EXECUTIVE")
            role_note = "" if role in FUNCTION_FOR_ROLE else " Contact's role unknown; EXECUTIVE is a placeholder."
            out.append((
                f"usr_test_fv_{cid}", f"contact-{cid}@fortaverde.test",
                f"TEST FortaVerde — stand-in for contact {c['contact_id']}", function,
                f"{self.marker}: synthetic stand-in for contact {c['contact_id']} of the knowledge record "
                f"(sha256 {self.sha256[:12]}). Not created by that person, not vetted, cannot log in."
                f"{role_note} Remove with scripts/load_fortaverde_test_project.py --remove --execute.",
            ))
        return out

    def metadata(self) -> dict:
        return {
            "fixture_marker": self.marker,
            "synthetic": True,
            "knowledge_file": self.path.name,
            "knowledge_sha256": self.sha256,
            "loaded_by": "scripts/load_fortaverde_test_project.py",
            "knowledge": self.doc,
        }

    def cards_to_load(self) -> tuple[dict, list[str]]:
        """Cards with content, or none at all while load_after names open contradictions."""
        blocked_by = self.cards.get("load_after") or []
        if blocked_by:
            return {}, blocked_by
        return {k: v for k, v in self.cards.items() if k != "load_after" and v}, []


def _validator():
    """validate_fortaverde_knowledge.py from this directory, loaded by path."""
    spec = importlib.util.spec_from_file_location("gex_validate_fortaverde", HERE / "validate_fortaverde_knowledge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Engines ─────────────────────────────────────────────────────────────────

def _engine():
    """The runtime engine (:8001), imported as pf_engine — never as `app`."""
    engine_backend = str(HERE.parents[2] / "gex_pf_engine" / "backend")
    if engine_backend not in sys.path:
        sys.path.insert(0, engine_backend)
    from pf_engine.core import bankability_engine  # type: ignore

    return bankability_engine


def _deal_killers():
    """Platform deal-killer engine, loaded from its file so app/__init__ is not run."""
    path = HERE.parent / "app" / "core" / "deal_killers.py"
    spec = importlib.util.spec_from_file_location("gex_deal_killers_fixture", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses resolves the module by name
    spec.loader.exec_module(mod)
    return mod.deal_killer_engine


def killer_facts(k: Knowledge) -> dict:
    """What is known, in the deal-killer engine's terms. Nothing is evidenced, so
    every fact is the fail-closed value; status/phase come from the premise."""
    return dict(
        offtake_binding_pct=0, third_party_binding_offtake_pct=0,
        epc_contract_executed=False, ie_appointed=bool(k.doc["reviewers"]["appointed"]),
        financial_model_status="SELF_ASSESSED", insurance_fully_placed=False,
        rfnbo_pathway_viable=False, dscr_p90=0, grid_connection_firm=False,
        status=k.phase, phase=f"{k.phase} (premise, unverified)",
    )


# ── Database ────────────────────────────────────────────────────────────────

def connect():
    import psycopg2
    import psycopg2.extras

    dsn = os.environ.get("ALEMBIC_DATABASE_URL")
    if not dsn:
        sys.exit("export ALEMBIC_DATABASE_URL (the gex_user credential) — this script writes data")
    conn = psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"))
    conn.cursor_factory = psycopg2.extras.DictCursor
    return conn


def _deletes(k: Knowledge) -> list[tuple[str, str, str, tuple]]:
    """(table, count sql, delete sql, params) — every statement scoped to this fixture."""
    p, t, m = (k.project_id,), k.tenant_id, k.marker + "%"
    return [
        ("commitment_terms", "SELECT count(*) FROM commitment_terms WHERE project_id = %s",
         "DELETE FROM commitment_terms WHERE project_id = %s", p),
        ("project_access", "SELECT count(*) FROM project_access WHERE project_id = %s",
         "DELETE FROM project_access WHERE project_id = %s", p),
        ("project_context", "SELECT count(*) FROM project_context WHERE project_id = %s",
         "DELETE FROM project_context WHERE project_id = %s", p),
        ("projects", "SELECT count(*) FROM projects WHERE project_id = %s",
         "DELETE FROM projects WHERE project_id = %s", p),
        ("auth_users", "SELECT count(*) FROM auth_users WHERE company_id = %s AND vetting_note LIKE %s",
         "DELETE FROM auth_users WHERE company_id = %s AND vetting_note LIKE %s", (t, m)),
        ("tenants", "SELECT count(*) FROM tenants WHERE company_id = %s",
         "DELETE FROM tenants WHERE company_id = %s", (t,)),
    ]


def _guard(cur, k: Knowledge) -> None:
    """Refuse to touch a tenant id that holds anything this script did not write."""
    cur.execute("SELECT count(*) FROM projects WHERE owner_tenant_id = %s AND project_id <> %s",
                (k.tenant_id, k.project_id))
    other_projects = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM auth_users WHERE company_id = %s "
                "AND COALESCE(vetting_note,'') NOT LIKE %s", (k.tenant_id, k.marker + "%"))
    other_users = cur.fetchone()[0]
    if other_projects or other_users:
        sys.exit(f"refusing: tenant {k.tenant_id} also holds {other_projects} other project(s) and "
                 f"{other_users} unmarked account(s). Nothing changed.")


def remove(conn, k: Knowledge, execute: bool) -> None:
    cur = conn.cursor()
    _guard(cur, k)
    for table, count_sql, delete_sql, params in _deletes(k):
        cur.execute(count_sql, params)
        n = cur.fetchone()[0]
        if n:
            print(f"  {'delete' if execute else 'would delete'} {n:3d} from {table}")
            if execute:
                cur.execute(delete_sql, params)
    if execute:
        conn.commit()
        print("  removed.")


def load(conn, k: Knowledge, execute: bool) -> None:
    from passlib.context import CryptContext

    users = k.stand_ins()
    cards, blocked_by = k.cards_to_load()
    print(f"  knowledge: {k.path.name}  sha256 {k.sha256[:12]}  "
          f"({len(k.doc['claims'])} claims, {len(k.doc['contradictions'])} contradictions)")
    print(f"  premise:   {k.power_model} / {k.phase} / {k.financing_model}")
    print(f"  writes:    tenant {k.tenant_id}, project {k.project_id}, {len(users)} PENDING stand-in(s); "
          "no evidence rows")
    print(f"  cards:     " + (f"skipped — load_after {blocked_by}" if blocked_by else
                              (", ".join(cards) or "none")))
    if not execute:
        print("\n  DRY RUN — nothing written. Re-run with --execute.")
        return

    remove(conn, k, execute=True)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur.execute("""
        INSERT INTO tenants (company_id, company_name, company_type, jurisdiction)
        VALUES (%s, %s, %s, %s)
    """, (k.tenant_id, k.tenant_name, k.tenant_type, k.tenant_jurisdiction))

    cur.execute("""
        INSERT INTO projects (project_id, project_name, owner_tenant_id, molecule, status,
                              jurisdiction, capex_eur, capacity_mtpd, location, country,
                              metadata_json, is_active, created_by, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,'EU',%s,%s,%s,%s,%s::jsonb,true,%s,now(),now())
    """, (k.project_id, k.project_name, k.tenant_id, k.molecule, k.phase, k.capex_eur,
          k.capacity_mtpd, k.location, k.country,
          json.dumps(k.metadata(), ensure_ascii=False), k.marker))

    cur.execute("""
        INSERT INTO project_context (project_id, power_model, phase, financing_model,
                                     updated_by, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (k.project_id, k.power_model, k.phase, k.financing_model, k.marker, now))

    cur.execute("""
        INSERT INTO project_access (project_id, company_id, actor_type, access_role, granted_by)
        VALUES (%s,%s,'PRODUCER','OWNER',%s)
    """, (k.project_id, k.tenant_id, k.marker))

    pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    for user_id, email, name, function, note in users:
        cur.execute("""
            INSERT INTO auth_users (
                user_id, email, password_hash, company_id, company_name, company_type,
                business_function, user_name, jurisdiction, clearance_level, kyc_status,
                is_platform_admin, is_active, account_state, registered_at, vetting_note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'STANDARD','UNVERIFIED',0,0,'PENDING',%s,%s)
        """, (user_id, email,
              pwd.hash(secrets.token_urlsafe(32)),     # never stored or shown: unusable
              k.tenant_id, k.tenant_name, k.tenant_type, function, name,
              k.tenant_jurisdiction, now, note))

    for card, terms in cards.items():
        cur.execute("""
            INSERT INTO commitment_terms (project_id, card_type, terms_json, updated_by, updated_at)
            VALUES (%s,%s,%s,%s,%s)
        """, (k.project_id, card, json.dumps(terms), k.marker, now))

    conn.commit()
    print(f"  WROTE tenant, project, context, access, {len(users)} PENDING stand-in(s)"
          + (f", {len(cards)} card(s)." if cards else "."))


def activate(conn, k: Knowledge, contact_ids: list[str], execute: bool) -> list[str]:
    """Make marked stand-ins ACTIVE, recording the vetting bypass. Returns their emails."""
    known = {c["contact_id"].upper(): c for c in k.contacts}
    stand_in = {u[0]: u for u in k.stand_ins()}
    cur = conn.cursor()
    emails: list[str] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for cid in contact_ids:
        cid = cid.upper()
        if cid not in known:
            sys.exit(f"refusing: {cid} is not a contact in {k.path.name} ({sorted(known)})")
        user_id, email = stand_in[f"usr_test_fv_{cid.lower()}"][:2]
        cur.execute("SELECT account_state FROM auth_users WHERE user_id = %s AND company_id = %s "
                    "AND vetting_note LIKE %s", (user_id, k.tenant_id, k.marker + "%"))
        row = cur.fetchone()
        if not row:
            sys.exit(f"refusing: no marked stand-in {user_id} in tenant {k.tenant_id}. "
                     "Run --execute first. Nothing changed.")
        print(f"  {'activate' if execute else 'would activate'} {user_id} <{email}> "
              f"({row[0]} -> ACTIVE, activated_by={k.marker})")
        emails.append(email)
        if execute:
            cur.execute("""
                UPDATE auth_users
                   SET account_state = 'ACTIVE', is_active = 1,
                       activated_by = %s, activated_at = %s,
                       vetting_note = vetting_note || %s
                 WHERE user_id = %s AND company_id = %s AND vetting_note LIKE %s
            """, (k.marker, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  f" ACTIVATED {today} by the fixture script on JML's instruction: VETTING BYPASSED "
                  "for an internal walk-through of the producer screens. No telephone verification, "
                  "no usage agreement. Not a vetted account.",
                  user_id, k.tenant_id, k.marker + "%"))
    if execute:
        conn.commit()
    return emails


def verify(k: Knowledge) -> int:
    """Evaluate through both engines and compare with protocol_result. Writes nothing."""
    be = _engine()
    snap = be.evaluate(k.project_id, [], None, k.power_model, k.phase, k.financing_model, None)
    dk = _deal_killers()
    facts = killer_facts(k)
    active = dk.get_active_killers(facts)
    exp = k.expected
    want = {
        "rules_version": exp["rules_version"], "state": exp["state"],
        "verified": exp["verified"], "applicable": exp["applicable"],
        "offtake_level": exp["offtake_level"], "epc_level": exp["epc_level"],
        "gates_blocking_next": exp["gates_blocking_next"], "committee": exp["committee"],
        "fatal": sorted(exp["active_deal_killers"]["FATAL"]),
        "critical": sorted(exp["active_deal_killers"]["CRITICAL"]),
    }
    got = {
        "rules_version": snap.get("rules_version"), "state": snap["current_state"],
        "verified": snap["total_verified"], "applicable": snap["total_evidence"],
        "offtake_level": snap["offtake"]["level"], "epc_level": snap["epc"]["level"],
        "gates_blocking_next": snap["gates_blocking_next_state"],
        "committee": dk.committee_ready(facts)["status"],
        "fatal": sorted(x.id for x in active if x.severity.value == "FATAL"),
        "critical": sorted(x.id for x in active if x.severity.value == "CRITICAL"),
    }
    bad = {key for key in want if got[key] != want[key]}
    for key in want:
        print(f"  [{'FAIL' if key in bad else 'ok  '}] {key:20} {got[key]}")
    if bad:
        print("\n  MISMATCH with protocol_result — the rules or the record changed. Re-run the protocol\n"
              "  and update protocol_result in the knowledge file; do not edit this script.")
        return 1
    print(f"\n  Matches protocol_result of {exp['run_date']} in {k.path.name}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--knowledge", type=Path, default=DEFAULT_KNOWLEDGE, help="knowledge JSON (schema 2)")
    ap.add_argument("--execute", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--remove", action="store_true", help="delete every row this script wrote")
    ap.add_argument("--verify", action="store_true", help="engines vs protocol_result; writes nothing")
    ap.add_argument("--activate", action="append", metavar="CONTACT_ID", default=[],
                    help="make this contact's stand-in loginable (vetting bypassed, marked); repeatable")
    args = ap.parse_args()

    k = Knowledge.load(args.knowledge)
    print(f"\n  project: {k.project_id}  ({k.project_name})")
    print(f"  tenant:  {k.tenant_id}   marker: {k.marker}\n")

    if args.verify:
        return verify(k)

    conn = connect()
    try:
        if args.activate:
            emails = activate(conn, k, args.activate, args.execute)
            if not args.execute:
                print("\n  DRY RUN — nothing changed. Re-run with --execute.")
            else:
                print("\n  Now set the password yourself (not echoed, at least 12 characters, without\n"
                      "  'test', 'fortaverde', 'contact' or 'stand'):")
                for e in emails:
                    print(f"    venv/bin/python scripts/set_password.py {e}")
            return 0
        if args.remove:
            remove(conn, k, args.execute)
            if not args.execute:
                print("\n  DRY RUN — nothing deleted. Re-run with --execute.")
            return 0
        load(conn, k, args.execute)
    finally:
        conn.close()

    if args.execute:
        print("\n  View it as PLATFORM_ADMIN. The stand-ins are PENDING and cannot log in.\n"
              "  Remove everything with --remove --execute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
