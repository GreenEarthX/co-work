"""
JWT auth and seeded demo identity store.

This replaces the frontend-only token illusion with:
- server-side credential verification
- bcrypt password hashing
- signed JWT access tokens with project-scoped claims
- persistent user and role records in SQLite
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.project_registry import (
    company_slug,
    get_project_profile,
    visible_project_ids_for_company,
)

# ── Algorithm selection ────────────────────────────────────────────────────
# RS256 is used when key paths are configured; HS256 is the dev fallback.

def _load_rsa_keys() -> tuple[str | None, str | None]:
    """Return (private_key_pem, public_key_pem) or (None, None) if not configured."""
    priv_path = settings.JWT_PRIVATE_KEY_PATH
    pub_path = settings.JWT_PUBLIC_KEY_PATH
    if not priv_path or not pub_path:
        return None, None
    try:
        private_key = Path(priv_path).read_text()
        public_key = Path(pub_path).read_text()
        return private_key, public_key
    except OSError:
        return None, None


_PRIVATE_KEY, _PUBLIC_KEY = _load_rsa_keys()
ALGORITHM = "RS256" if _PRIVATE_KEY else "HS256"

# Sign key: private key for RS256, shared secret for HS256
_SIGN_KEY: str = _PRIVATE_KEY or settings.SECRET_KEY
# Verify key: public key for RS256, shared secret for HS256
_VERIFY_KEY: str = _PUBLIC_KEY or settings.SECRET_KEY

DB_PATH = settings.SQLITE_DB_PATH
logger = logging.getLogger("gex.auth")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# Demo credentials are a development convenience, never a production posture:
#   GEX_DEMO_PASSWORD overrides the shared demo password.
#   GEX_SEED_DEMO_USERS=0 disables demo-user seeding entirely (production).
DEMO_PASSWORD = os.getenv("GEX_DEMO_PASSWORD", "demo1234")
SEED_DEMO_USERS = os.getenv("GEX_SEED_DEMO_USERS", "1").lower() not in ("0", "false", "no")

DEMO_USER_SEEDS: list[dict[str, Any]] = [
    {
        "email": "admin@greenearthx.com",
        "company_type": "THIRD_PARTY",
        "service_type": "PLATFORM",
        "business_function": "EXECUTIVE",
        "company_name": "GreenEarthX",
        "user_name": "GEX Administrator",
        "clearance_level": "CONFIDENTIAL",
        "is_platform_admin": True,
    },
    {
        "email": "lisa.friedrich@hamburgone.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "EXECUTIVE",
        "company_name": "HamburgOne.com",
        "user_name": "Lisa Friedrich",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "mark.puntz@hamburgone.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "ENGINEERING",
        "company_name": "HamburgOne.com",
        "user_name": "Mark Puntz",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "lucie.mertz@hamburgone.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "company_name": "HamburgOne.com",
        "user_name": "Lucie Mertz",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "diego.martinez@madrid2.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "EXECUTIVE",
        "company_name": "Madrid2.com",
        "user_name": "Diego Martinez",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "claudia.nunez@madrid2.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "company_name": "Madrid2.com",
        "user_name": "Claudia Nunez",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "karl.tish@brementhree.com",
        "company_type": "OFFTAKER",
        "service_type": None,
        "business_function": "EXECUTIVE",
        "company_name": "BremenThree AG",
        "user_name": "Karl Tish",
        "clearance_level": "CONFIDENTIAL",
        # ── Prosumer attributes (same company-level profile as Frank) ──
        "capabilities": ["OFFTAKE", "PRODUCE", "SELL"],
        "credit_rating": "A-",
        "credit_rating_source": "S&P",
        "export_licenses": ["DE"],
        "token_ready": True,
        "transformation_license": True,
        "aggregation_limit_mt": None,
    },
    {
        "email": "frank.sabak@brementhree.com",
        "company_type": "OFFTAKER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "company_name": "BremenThree AG",
        "user_name": "Frank Sabak",
        "clearance_level": "STANDARD",
        # ── Prosumer attributes ──
        "capabilities": ["OFFTAKE", "PRODUCE", "SELL"],
        "credit_rating": "A-",
        "credit_rating_source": "S&P",
        "export_licenses": ["DE"],              # Germany-only SAF sales
        "token_ready": True,                    # buys only tokenised molecules
        "transformation_license": True,         # licensed to transform e-methanol → SAF
        "aggregation_limit_mt": None,
    },
    {
        "email": "luc.marchand@rotterdamofftake4.com",
        "company_type": "OFFTAKER",
        "service_type": None,
        "business_function": "FINANCE_TREASURY",
        "company_name": "RotterdamOfftake4 AG",
        "user_name": "Luc Marchand",
        "clearance_level": "CONFIDENTIAL",
        # ── Pure offtaker / end-buyer ──
        "capabilities": ["OFFTAKE"],
        "credit_rating": "BBB+",
        "credit_rating_source": "HOUSE_BANK",
        "export_licenses": ["NL", "DE", "BE"],  # Benelux + Germany
        "token_ready": True,
        "transformation_license": False,
        "aggregation_limit_mt": 10000,           # max 10 000 MT aggregation
    },
    {
        "email": "henrik.vost@nordlb.com",
        "company_type": "THIRD_PARTY",
        "service_type": "BANK",
        "business_function": "FINANCE_TREASURY",
        "company_name": "NordLB",
        "user_name": "Henrik Vost",
        "clearance_level": "RESTRICTED",
    },
    {
        "email": "sander.devries@abnamro.com",
        "company_type": "THIRD_PARTY",
        "service_type": "BANK",
        "business_function": "FINANCE_TREASURY",
        "company_name": "ABN-AMRO",
        "user_name": "Sander de Vries",
        "clearance_level": "RESTRICTED",
    },
    {
        "email": "olaf.jacques@siemens-energy.com",
        "company_type": "THIRD_PARTY",
        "service_type": "ENGINEER",
        "business_function": "ENGINEERING",
        "company_name": "Siemens Energy",
        "user_name": "Olaf Jacques",
        "clearance_level": "CONFIDENTIAL",
    },
    {
        "email": "florian.schmidt@allianz.com",
        "company_type": "THIRD_PARTY",
        "service_type": "INSURER",
        "business_function": "FINANCE_TREASURY",
        "company_name": "Allianz",
        "user_name": "Florian Schmidt",
        "clearance_level": "RESTRICTED",
    },
    {
        "email": "phillipe.blanker@zurich.com",
        "company_type": "THIRD_PARTY",
        "service_type": "INSURER",
        "business_function": "FINANCE_TREASURY",
        "company_name": "Zurich Versicherung AG",
        "user_name": "Phillipe Blanker",
        "clearance_level": "RESTRICTED",
    },
    {
        "email": "thierry.groell@etfuels.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "FINANCE_TREASURY",
        "company_name": "ETFuels SA",
        "user_name": "Thierry Groell",
        "clearance_level": "CONFIDENTIAL",
        "capabilities": ["PRODUCE", "SELL", "TRADE"],
    },
    {
        "email": "felix.leworthy@etfuels.com",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "company_name": "ETFuels SA",
        "user_name": "Felix Leworthy",
        "clearance_level": "CONFIDENTIAL",
        "capabilities": ["PRODUCE", "SELL", "TRADE"],
    },
    # Prosumer demo — balance-sheet financing, hybrid power, self-offtake
    {
        "email": "anna.keller@rheinwerk.de",
        "company_type": "PRODUCER",
        "service_type": None,
        "business_function": "EXECUTIVE",
        "company_name": "RheinWerk Industries AG",
        "user_name": "Anna Keller",
        "clearance_level": "CONFIDENTIAL",
        "capabilities": ["PRODUCE"],
    },
]


def _get_conn():
    """
    Connection to whichever store the auth slice is pointed at
    (AUTH_DB_BACKEND: sqlite | postgres). The SQL below is unchanged and runs
    against both — see core/db_backend.py for why the shim exists.
    """
    from app.core.db_backend import auth_connection

    return auth_connection(DB_PATH)


def auth_db_connection() -> sqlite3.Connection:
    """
    Connection to the store that owns `auth_users`.

    Public because other modules legitimately need to read/write account rows
    (account vetting), and they must NOT open their own path to this table —
    a module-owned database path is exactly what the data-layer doctrine
    forbids. One owner, one accessor.
    """
    init_auth_db()
    return _get_conn()


def _ensure_tables(conn) -> None:
    # On Postgres the schema is owned by alembic (revision 030, branch
    # "auth_slice"). Running this SQLite DDL there would either fail on
    # `datetime('now')` defaults or, worse, half-succeed and diverge from the
    # migration. One owner per schema.
    from app.core.db_backend import is_postgres

    if is_postgres():
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            company_id TEXT NOT NULL,
            company_name TEXT NOT NULL,
            company_type TEXT NOT NULL,
            service_type TEXT,
            business_function TEXT NOT NULL,
            user_name TEXT NOT NULL,
            company_logo_url TEXT,
            clearance_level TEXT NOT NULL DEFAULT 'STANDARD',
            jurisdiction TEXT NOT NULL DEFAULT 'EU',
            kyc_status TEXT NOT NULL DEFAULT 'VERIFIED',
            nda_signed_with_json TEXT NOT NULL DEFAULT '[]',
            assigned_audits_json TEXT NOT NULL DEFAULT '[]',
            -- Prosumer / trade attributes (Phase 3)
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            credit_rating TEXT NOT NULL DEFAULT 'NR',
            credit_rating_source TEXT NOT NULL DEFAULT 'GEX',
            export_licenses_json TEXT NOT NULL DEFAULT '[]',
            token_ready INTEGER NOT NULL DEFAULT 0,
            transformation_license INTEGER NOT NULL DEFAULT 0,
            aggregation_limit_mt REAL,
            is_platform_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user_project_roles (
            user_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            PRIMARY KEY (user_id, project_id, actor_type)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_login_history (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'signin',
            ip_address TEXT,
            user_agent TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            success INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_users(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_roles_user ON auth_user_project_roles(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_history_user ON auth_login_history(user_id)")
    _ensure_column(conn, "auth_users", "is_platform_admin", "INTEGER NOT NULL DEFAULT 0")
    _ensure_account_lifecycle_columns(conn)
    conn.commit()


def _ensure_account_lifecycle_columns(conn: sqlite3.Connection) -> None:
    """
    Vetting-before-trust columns (see core/account_lifecycle.py).

    NOTE the default: **PENDING**. `auth_users` originally defaulted
    `kyc_status` to 'VERIFIED' and `is_active` to 1, so any row that came into
    existence was fully trusted by construction. New accounts now start
    untrusted and can only be advanced by a named GEX employee.
    """
    from app.core.account_lifecycle import AccountState

    _ensure_column(
        conn, "auth_users", "account_state",
        f"TEXT NOT NULL DEFAULT '{AccountState.PENDING.value}'",
    )
    for col in ("registered_at", "phone_verified_at", "phone_verified_by",
                "agreement_signed_at", "agreement_ref", "activated_at",
                "activated_by", "vetting_note"):
        _ensure_column(conn, "auth_users", col, "TEXT")

    # ── Grandfathering ──────────────────────────────────────────────────────
    # The 17 seeded accounts predate this policy and are how the running
    # platform is used. Locking them out would be a regression, so they are
    # moved to ACTIVE — but HONESTLY: phone_verified_at / agreement_ref stay
    # NULL because no call was made and no agreement was signed. They are
    # marked so an audit can tell a grandfathered account from a vetted one,
    # and so nothing later mistakes the absence of evidence for a lost record.
    grandfathered = conn.execute(
        "UPDATE auth_users SET account_state = ?, activated_by = ?, "
        # No datetime('now') here: it is SQLite-only, and this statement now
        # runs against Postgres too. Every pre-existing row qualifies anyway —
        # the policy post-dates all of them.
        "vetting_note = ? WHERE account_state = ? AND is_active = 1",
        (AccountState.ACTIVE.value, "SEED_GRANDFATHERED",
         "Pre-dates the vetting policy of 2026-08-07. No telephone verification "
         "and no signed usage agreement are on file. Re-vet before relying on "
         "this account's status.", AccountState.PENDING.value),
    ).rowcount
    if grandfathered:
        logger.warning(
            "Account lifecycle: grandfathered %d pre-policy account(s) to ACTIVE "
            "without vetting evidence. They are marked SEED_GRANDFATHERED.",
            grandfathered,
        )


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _actor_types_for_seed(seed: dict[str, Any]) -> list[str]:
    """Derive actor type(s) from seed.  Prosumers with capabilities get multiple types."""
    company_type = seed["company_type"]
    service_type = seed.get("service_type")
    capabilities = seed.get("capabilities", [])

    # If capabilities explicitly include both OFFTAKE and PRODUCE → prosumer
    types: list[str] = []
    if "OFFTAKE" in capabilities:
        types.append("OFFTAKER")
    if "PRODUCE" in capabilities:
        types.append("PRODUCER")

    # If capabilities didn't produce anything, fall back to legacy logic
    if not types:
        if company_type == "PRODUCER":
            types = ["PRODUCER"]
        elif company_type == "OFFTAKER":
            types = ["OFFTAKER"]
        elif service_type == "BANK":
            types = ["COMMERCIAL_BANKER"]
        elif service_type == "INSURER":
            types = ["INSURER"]
        elif service_type == "CERTIFIER":
            types = ["CERTIFIER"]
        elif service_type == "LOGISTICS":
            types = ["LOGISTICS_OPERATOR"]
        elif service_type == "EQUIPMENT":
            types = ["TECHNOLOGY_PROVIDER"]
        elif service_type == "ENGINEER":
            types = ["EPC_CONTRACTOR"]
        else:
            types = ["EXECUTIVE"]

    return types


def _seed_user(conn: sqlite3.Connection, seed: dict[str, Any]) -> None:
    email = seed["email"].lower()
    company_name = seed["company_name"]
    company_id = company_slug(company_name)
    user_id = company_slug(email)
    password_hash = pwd_context.hash(DEMO_PASSWORD)
    actor_types = _actor_types_for_seed(seed)
    visible_projects = visible_project_ids_for_company(company_name)

    nda_signed_with = sorted(
        {
            "greenearthx_admin",
            *(get_project_profile(project_id).owner_company_id for project_id in visible_projects if get_project_profile(project_id)),
            *(company_slug(company) for project_id in visible_projects for company in (get_project_profile(project_id).associated_company_names if get_project_profile(project_id) else ())),
        }
        - {company_id}
    )

    conn.execute(
        """
        INSERT INTO auth_users (
            user_id, email, password_hash, company_id, company_name, company_type,
            service_type, business_function, user_name, company_logo_url,
            clearance_level, jurisdiction, kyc_status, nda_signed_with_json,
            assigned_audits_json,
            capabilities_json, credit_rating, credit_rating_source,
            export_licenses_json, token_ready, transformation_license,
            aggregation_limit_mt,
            is_platform_admin,
            is_active, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(email) DO UPDATE SET
            password_hash=excluded.password_hash,
            company_id=excluded.company_id,
            company_name=excluded.company_name,
            company_type=excluded.company_type,
            service_type=excluded.service_type,
            business_function=excluded.business_function,
            user_name=excluded.user_name,
            clearance_level=excluded.clearance_level,
            jurisdiction=excluded.jurisdiction,
            kyc_status=excluded.kyc_status,
            nda_signed_with_json=excluded.nda_signed_with_json,
            assigned_audits_json=excluded.assigned_audits_json,
            capabilities_json=excluded.capabilities_json,
            credit_rating=excluded.credit_rating,
            credit_rating_source=excluded.credit_rating_source,
            export_licenses_json=excluded.export_licenses_json,
            token_ready=excluded.token_ready,
            transformation_license=excluded.transformation_license,
            aggregation_limit_mt=excluded.aggregation_limit_mt,
            is_platform_admin=excluded.is_platform_admin,
            is_active=1,
            updated_at=excluded.updated_at
        """,
        (
            user_id,
            email,
            password_hash,
            company_id,
            company_name,
            seed["company_type"],
            seed.get("service_type"),
            seed["business_function"],
            seed["user_name"],
            seed.get("company_logo_url"),
            seed.get("clearance_level", "STANDARD"),
            seed.get("jurisdiction", "EU"),
            seed.get("kyc_status", "VERIFIED"),
            json.dumps(nda_signed_with),
            json.dumps(seed.get("assigned_audits", [])),
            json.dumps(seed.get("capabilities", [])),
            seed.get("credit_rating", "NR"),
            seed.get("credit_rating_source", "GEX"),
            json.dumps(seed.get("export_licenses", [])),
            1 if seed.get("token_ready") else 0,
            1 if seed.get("transformation_license") else 0,
            seed.get("aggregation_limit_mt"),
            1 if seed.get("is_platform_admin") else 0,
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    # Insert all actor types per project (prosumers get multiple rows)
    conn.execute("DELETE FROM auth_user_project_roles WHERE user_id = ?", (user_id,))
    for project_id in visible_projects:
        for actor_type in actor_types:
            conn.execute(
                """
                -- Standard upsert, not SQLite's INSERT OR REPLACE: both
                -- SQLite (>=3.24) and Postgres support ON CONFLICT, so one
                -- statement serves both backends.
                INSERT INTO auth_user_project_roles (user_id, project_id, actor_type)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id, project_id, actor_type) DO NOTHING
                """,
                (user_id, project_id, actor_type),
            )


def init_auth_db() -> None:
    conn = _get_conn()
    try:
        _ensure_tables(conn)
        if SEED_DEMO_USERS:
            for seed in DEMO_USER_SEEDS:
                _seed_user(conn, seed)
        conn.commit()
    finally:
        conn.close()


def _load_user_by_email(email: str) -> sqlite3.Row | None:
    init_auth_db()
    conn = _get_conn()
    try:
        # NOT filtered by is_active. `account_state` is the authoritative gate
        # (core/account_lifecycle.py) and authenticate_user enforces it. Filtering
        # here made an un-vetted account indistinguishable from a non-existent
        # one, so a registered applicant got "Invalid credentials" instead of
        # "awaiting vetting" — and the 403 branch was unreachable.
        return conn.execute(
            "SELECT * FROM auth_users WHERE email = ?",
            (email.lower(),),
        ).fetchone()
    finally:
        conn.close()


def _load_project_roles(user_id: str) -> dict[str, list[str]]:
    """Load project roles.  Returns {project_id: [actor_type, …]} to support prosumers."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT project_id, actor_type FROM auth_user_project_roles WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row["project_id"], []).append(row["actor_type"])
        return result
    finally:
        conn.close()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


class AccountNotActive(Exception):
    """Credentials were correct but the account is not vetted. Never a 500."""

    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"account is {state}, not ACTIVE")


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """
    Verify credentials AND vetting status.

    Credentials alone are not trust (policy 2026-08-07). An account that has
    registered but not been vetted by a GEX employee holds a valid password and
    still cannot log in. The password check runs FIRST and unconditionally, so
    the vetting refusal cannot be used to enumerate which addresses are
    registered — a wrong password looks the same either way.
    """
    from app.core.account_lifecycle import can_login

    user = _load_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None

    state = user["account_state"] if "account_state" in user.keys() else None
    # Belt and braces: `is_active` is the legacy flag the vetting endpoints keep
    # in sync. If the two ever disagree, refuse — a row that is ACTIVE by state
    # but deactivated by flag is a contradiction, and contradictions fail closed.
    legacy_active = bool(user["is_active"]) if "is_active" in user.keys() else True
    if not can_login(state) or not legacy_active:
        logger.warning(
            "login refused for %s — account_state=%s (credentials were valid)",
            email, state,
        )
        raise AccountNotActive(str(state))

    return _user_record_to_payload(user)


def get_user_payload_by_email(email: str) -> dict[str, Any] | None:
    """Resolve a seeded/auth user into the same payload shape used by JWT claims."""
    user = _load_user_by_email(email)
    if not user:
        return None
    return _user_record_to_payload(user)


def _user_record_to_payload(user: sqlite3.Row) -> dict[str, Any]:
    project_roles = _load_project_roles(user["user_id"])
    payload = {
        "user_id": user["user_id"],
        "email": user["email"],
        "company_id": user["company_id"],
        "company_name": user["company_name"],
        "company_type": user["company_type"],
        "service_type": user["service_type"],
        "business_function": user["business_function"],
        "user_name": user["user_name"],
        "company_logo_url": user["company_logo_url"],
        "clearance_level": user["clearance_level"],
        "jurisdiction": user["jurisdiction"],
        "kyc_status": user["kyc_status"],
        "nda_signed_with": json.loads(user["nda_signed_with_json"] or "[]"),
        "assigned_audits": json.loads(user["assigned_audits_json"] or "[]"),
        "actor_type_per_project": project_roles,
        # Prosumer / trade attributes
        "capabilities": json.loads(user["capabilities_json"] or "[]"),
        "credit_rating": user["credit_rating"],
        "credit_rating_source": user["credit_rating_source"],
        "export_licenses": json.loads(user["export_licenses_json"] or "[]"),
        "token_ready": bool(user["token_ready"]),
        "transformation_license": bool(user["transformation_license"]),
        "aggregation_limit_mt": user["aggregation_limit_mt"],
        "is_platform_admin": bool(user["is_platform_admin"]),
    }
    return payload


# Company identity carried by platform service tokens. Deliberately not a valid
# company slug so it can never match a real company in an ABAC project check.
PLATFORM_SERVICE_COMPANY_ID = "__platform_service__"


def create_service_token(service_name: str = "gex-backend", ttl_minutes: int = 5) -> str:
    """
    Short-lived service identity for backend→engine calls (one-issuer
    doctrine, ADR 2026-07-06). Engines verify these with auth/gex_jwt.py and
    distinguish them from user tokens via session_tier == "service".
    """
    now = datetime.now(timezone.utc)
    claims = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "sub": f"service:{service_name}",
        "email": None,
        "session_tier": "service",
        "business_function": "SERVICE",
        "is_platform_admin": False,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, _SIGN_KEY, algorithm=ALGORITHM)


def create_access_token(subject: dict[str, Any]) -> tuple[str, str]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "sub": subject["user_id"],
        "email": subject["email"],
        "company_id": subject["company_id"],
        "company_name": subject["company_name"],
        "company_type": subject["company_type"],
        "service_type": subject["service_type"],
        "business_function": subject["business_function"],
        "user_name": subject["user_name"],
        "company_logo_url": subject.get("company_logo_url"),
        "clearance_level": subject["clearance_level"],
        "jurisdiction": subject["jurisdiction"],
        "kyc_status": subject["kyc_status"],
        "nda_signed_with": subject["nda_signed_with"],
        "assigned_audits": subject["assigned_audits"],
        "actor_type_per_project": subject["actor_type_per_project"],
        # Prosumer / trade attributes
        "capabilities": subject.get("capabilities", []),
        "credit_rating": subject.get("credit_rating", "NR"),
        "credit_rating_source": subject.get("credit_rating_source", "GEX"),
        "export_licenses": subject.get("export_licenses", []),
        "token_ready": subject.get("token_ready", False),
        "transformation_license": subject.get("transformation_license", False),
        "aggregation_limit_mt": subject.get("aggregation_limit_mt"),
        "is_platform_admin": subject.get("is_platform_admin", False),
        "session_tier": "authenticated",
        "iat": now_ts,
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, _SIGN_KEY, algorithm=ALGORITHM)
    return token, expires_at.isoformat()


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _VERIFY_KEY,
            algorithms=[ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def build_jwks() -> dict:
    """Return a JWKS document for the current signing key (RS256 only)."""
    if ALGORITHM != "RS256" or not _PUBLIC_KEY:
        return {"keys": []}
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        import base64, struct

        pub = load_pem_public_key(_PUBLIC_KEY.encode())
        if not isinstance(pub, RSAPublicKey):
            return {"keys": []}
        pub_numbers = pub.public_key().public_numbers() if hasattr(pub, "public_key") else pub.public_numbers()

        def _b64url_uint(val: int) -> str:
            length = (val.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(val.to_bytes(length, "big")).rstrip(b"=").decode()

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": "gex-rs256-1",
                    "n": _b64url_uint(pub_numbers.n),
                    "e": _b64url_uint(pub_numbers.e),
                }
            ]
        }
    except Exception:
        return {"keys": []}


def get_user_payload_from_token(token: str) -> dict[str, Any]:
    claims = decode_access_token(token)

    # Platform service tokens (create_service_token) carry a deliberately
    # minimal claim set — no company, no user profile. They must not be forced
    # through the user-shaped extraction below: `claims["company_id"]` raises
    # KeyError, which the ABAC middleware surfaces as a bare 500. Every key the
    # user payload defines is present here with a safe default so downstream
    # consumers can treat both shapes uniformly.
    # domain_authorization.check_domain_access() recognises the identity via
    # session_tier == "service"; keep that claim, do not invent an identity.
    if claims.get("session_tier") == "service":
        subject = claims["sub"]
        return {
            "user_id": subject,
            "email": claims.get("email"),
            # An explicit, non-colliding sentinel rather than None or a derived
            # slug: a service token has no company, and ABAC must not be able to
            # match it against any real company's projects. Fails closed, and is
            # unmistakable in an audit log.
            "company_id": PLATFORM_SERVICE_COMPANY_ID,
            "company_name": "GEX Platform Service",
            "company_type": None,
            "service_type": None,
            "business_function": claims.get("business_function", "SERVICE"),
            "user_name": subject,
            "company_logo_url": None,
            "session_tier": "service",
            "clearance_level": "STANDARD",
            "jurisdiction": "",
            "kyc_status": "N/A",
            "nda_signed_with": [],
            "assigned_audits": [],
            "actor_type_per_project": {},
            "capabilities": [],
            "credit_rating": "NR",
            "credit_rating_source": "GEX",
            "export_licenses": [],
            "token_ready": False,
            "transformation_license": False,
            "aggregation_limit_mt": None,
            "is_platform_admin": False,
        }

    return {
        "user_id": claims["sub"],
        "email": claims["email"],
        "company_id": claims["company_id"],
        "company_name": claims["company_name"],
        "company_type": claims["company_type"],
        "service_type": claims.get("service_type"),
        "business_function": claims["business_function"],
        "user_name": claims["user_name"],
        "session_tier": claims.get("session_tier"),
        "company_logo_url": claims.get("company_logo_url"),
        "clearance_level": claims.get("clearance_level", "STANDARD"),
        "jurisdiction": claims.get("jurisdiction", ""),
        "kyc_status": claims.get("kyc_status", "VERIFIED"),
        "nda_signed_with": claims.get("nda_signed_with", []),
        "assigned_audits": claims.get("assigned_audits", []),
        "actor_type_per_project": claims.get("actor_type_per_project", {}),
        # Prosumer / trade attributes
        "capabilities": claims.get("capabilities", []),
        "credit_rating": claims.get("credit_rating", "NR"),
        "credit_rating_source": claims.get("credit_rating_source", "GEX"),
        "export_licenses": claims.get("export_licenses", []),
        "token_ready": claims.get("token_ready", False),
        "transformation_license": claims.get("transformation_license", False),
        "aggregation_limit_mt": claims.get("aggregation_limit_mt"),
        "is_platform_admin": claims.get("is_platform_admin", False),
    }


def role_payload_from_user(user_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_type": user_payload["company_type"],
        "service_type": user_payload.get("service_type"),
        "business_function": user_payload["business_function"],
        "company_name": user_payload["company_name"],
        "user_name": user_payload["user_name"],
        "company_logo_url": user_payload.get("company_logo_url"),
        # Prosumer / trade attributes
        "capabilities": user_payload.get("capabilities", []),
        "credit_rating": user_payload.get("credit_rating", "NR"),
        "credit_rating_source": user_payload.get("credit_rating_source", "GEX"),
        "export_licenses": user_payload.get("export_licenses", []),
        "token_ready": user_payload.get("token_ready", False),
        "transformation_license": user_payload.get("transformation_license", False),
        "aggregation_limit_mt": user_payload.get("aggregation_limit_mt"),
        "is_platform_admin": user_payload.get("is_platform_admin", False),
    }


def has_platform_admin_access(user_payload: dict[str, Any]) -> bool:
    return bool(user_payload.get("is_platform_admin"))


def record_login_event(user_id: str, email: str, ip_address: str | None = None, user_agent: str | None = None, success: bool = True) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO auth_login_history (id, user_id, email, event_type, ip_address, user_agent, timestamp, success) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, email, "signin", ip_address, user_agent, datetime.now(timezone.utc).isoformat(), 1 if success else 0),
        )
        conn.commit()
    finally:
        conn.close()


def get_login_history(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT event_type, ip_address, user_agent, timestamp, success FROM auth_login_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_password(email: str, new_password: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, updated_at = ? WHERE email = ?",
            (pwd_context.hash(new_password), datetime.now(timezone.utc).isoformat(), email.lower()),
        )
        conn.commit()
    finally:
        conn.close()


def issue_login_response(email: str, password: str, ip_address: str | None = None, user_agent: str | None = None) -> dict[str, Any] | None:
    from app.core.refresh_tokens import issue_refresh_token
    user_payload = authenticate_user(email, password)
    if not user_payload:
        return None
    token, expires_at = create_access_token(user_payload)
    refresh_token, _ = issue_refresh_token(user_payload["user_id"], expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    record_login_event(user_payload["user_id"], user_payload["email"], ip_address=ip_address, user_agent=user_agent, success=True)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "refresh_token": refresh_token,
        "email": user_payload["email"],
        "role": role_payload_from_user(user_payload),
        "user": user_payload,
    }


init_auth_db()
