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
import os
import sqlite3
from datetime import datetime, timedelta, timezone
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

ALGORITHM = "HS256"
DB_PATH = os.getenv("GEX_PLATFORM_DB_PATH", "gex_platform.db")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


DEMO_PASSWORD = "demo1234"

DEMO_USER_SEEDS: list[dict[str, Any]] = [
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
    },
    {
        "email": "frank.sabak@brementhree.com",
        "company_type": "OFFTAKER",
        "service_type": None,
        "business_function": "COMMERCIAL",
        "company_name": "BremenThree AG",
        "user_name": "Frank Sabak",
        "clearance_level": "STANDARD",
    },
    {
        "email": "luc.marchand@rotterdamofftake4.com",
        "company_type": "OFFTAKER",
        "service_type": None,
        "business_function": "FINANCE_TREASURY",
        "company_name": "RotterdamOfftake4 AG",
        "user_name": "Luc Marchand",
        "clearance_level": "CONFIDENTIAL",
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
]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
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
            PRIMARY KEY (user_id, project_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_users(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_roles_user ON auth_user_project_roles(user_id)")
    conn.commit()


def _actor_type_for_seed(seed: dict[str, Any]) -> str:
    company_type = seed["company_type"]
    service_type = seed.get("service_type")

    if company_type == "PRODUCER":
        return "PRODUCER"
    if company_type == "OFFTAKER":
        return "OFFTAKER"
    if service_type == "BANK":
        return "COMMERCIAL_BANKER"
    if service_type == "INSURER":
        return "INSURER"
    if service_type == "CERTIFIER":
        return "CERTIFIER"
    if service_type == "LOGISTICS":
        return "LOGISTICS_OPERATOR"
    if service_type == "EQUIPMENT":
        return "TECHNOLOGY_PROVIDER"
    if service_type == "ENGINEER":
        return "EPC_CONTRACTOR"
    return "EXECUTIVE"


def _seed_user(conn: sqlite3.Connection, seed: dict[str, Any]) -> None:
    email = seed["email"].lower()
    company_name = seed["company_name"]
    company_id = company_slug(company_name)
    user_id = company_slug(email)
    password_hash = pwd_context.hash(DEMO_PASSWORD)
    actor_type = _actor_type_for_seed(seed)
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
            assigned_audits_json, is_active, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(email) DO UPDATE SET
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
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    conn.execute("DELETE FROM auth_user_project_roles WHERE user_id = ?", (user_id,))
    for project_id in visible_projects:
        conn.execute(
            """
            INSERT OR REPLACE INTO auth_user_project_roles (user_id, project_id, actor_type)
            VALUES (?, ?, ?)
            """,
            (user_id, project_id, actor_type),
        )


def init_auth_db() -> None:
    conn = _get_conn()
    try:
        _ensure_tables(conn)
        for seed in DEMO_USER_SEEDS:
            _seed_user(conn, seed)
        conn.commit()
    finally:
        conn.close()


def _load_user_by_email(email: str) -> sqlite3.Row | None:
    init_auth_db()
    conn = _get_conn()
    try:
        return conn.execute(
            "SELECT * FROM auth_users WHERE email = ? AND is_active = 1",
            (email.lower(),),
        ).fetchone()
    finally:
        conn.close()


def _load_project_roles(user_id: str) -> dict[str, str]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT project_id, actor_type FROM auth_user_project_roles WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {row["project_id"]: row["actor_type"] for row in rows}
    finally:
        conn.close()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = _load_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
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
    }
    return payload


def create_access_token(subject: dict[str, Any]) -> tuple[str, str]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = {
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
        "session_tier": "authenticated",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_at.isoformat()


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def get_user_payload_from_token(token: str) -> dict[str, Any]:
    claims = decode_access_token(token)
    return {
        "user_id": claims["sub"],
        "email": claims["email"],
        "company_id": claims["company_id"],
        "company_name": claims["company_name"],
        "company_type": claims["company_type"],
        "service_type": claims.get("service_type"),
        "business_function": claims["business_function"],
        "user_name": claims["user_name"],
        "company_logo_url": claims.get("company_logo_url"),
        "clearance_level": claims.get("clearance_level", "STANDARD"),
        "jurisdiction": claims.get("jurisdiction", ""),
        "kyc_status": claims.get("kyc_status", "VERIFIED"),
        "nda_signed_with": claims.get("nda_signed_with", []),
        "assigned_audits": claims.get("assigned_audits", []),
        "actor_type_per_project": claims.get("actor_type_per_project", {}),
    }


def role_payload_from_user(user_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_type": user_payload["company_type"],
        "service_type": user_payload.get("service_type"),
        "business_function": user_payload["business_function"],
        "company_name": user_payload["company_name"],
        "user_name": user_payload["user_name"],
        "company_logo_url": user_payload.get("company_logo_url"),
    }


def issue_login_response(email: str, password: str) -> dict[str, Any] | None:
    user_payload = authenticate_user(email, password)
    if not user_payload:
        return None
    token, expires_at = create_access_token(user_payload)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "email": user_payload["email"],
        "role": role_payload_from_user(user_payload),
        "user": user_payload,
    }


init_auth_db()

