"""
Application Configuration
"""
import os
from pathlib import Path
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings

# A PostgreSQL connection that is never answered must fail, not wait for ever. With Docker Desktop
# paused, port 55432 still accepts the TCP connection (the forwarder) and nothing replies: on 5 Nov
# 2026 the 07:30 expiry sweep hung for over two hours and the test suite froze at 10%. libpq reads
# this variable for every psycopg2 connection (the shim and SQLAlchemy's sync engines), and an
# explicit PGCONNECT_TIMEOUT or a connect_timeout in a DSN still wins. Set before any connection.
os.environ.setdefault("PGCONNECT_TIMEOUT", "10")

# Anchor for all filesystem paths: the backend/ directory. Never the CWD.
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "GreenEarthX Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "dev_secret_key_change_in_production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENABLE_ABAC_MIDDLEWARE: bool = True
    ABAC_PHASE: int = 2

    # JWT RS256 key paths (leave empty to fall back to HS256 in development)
    JWT_PRIVATE_KEY_PATH: str = ""
    JWT_PUBLIC_KEY_PATH: str = ""
    JWT_ISSUER: str = "https://api.greenearthx.com"
    JWT_AUDIENCE: str = "gex-platform"

    # Demo mode — when False, x-demo-* header fallback is disabled
    GEX_DEMO_MODE: bool = True
    
    # Database — PostgreSQL is the committed system of record (ADR 2026-07-06).
    #
    # RUNTIME credential. From migration 045 this is `gex_app`: no SUPERUSER, no
    # BYPASSRLS, no CREATE on schema public — so RLS actually constrains the
    # application. Pointing this at a superuser makes every policy decorative.
    DATABASE_URL: str = "postgresql://gex_app:gex_app_password_dev@localhost:5432/gex_platform"
    # MIGRATOR credential — DDL only, read by alembic/env.py, which prefers it
    # over DATABASE_URL. Declared here because Settings forbids extra inputs and
    # this legitimately appears in .env. Alembic itself reads os.getenv, so it
    # must also be EXPORTED to reach a migration run.
    ALEMBIC_DATABASE_URL: str = ""
    # Which store the auth slice reads/writes: "sqlite" | "postgres".
    # Declared here (not just os.getenv) so it can live in .env — Settings
    # forbids extra inputs, and pydantic does not export .env into os.environ.
    AUTH_DB_BACKEND: str = "sqlite"
    # Which store the evidence/bankability slice uses: "sqlite" | "postgres".
    # Separate from AUTH_DB_BACKEND so slices flip independently.
    EVIDENCE_DB_BACKEND: str = "sqlite"
    # Which store slice 5 (capital bridge + development packages) uses.
    CAPITAL_DB_BACKEND: str = "sqlite"
    # Which store slice 6 (marketplace / trading tail) uses.
    MARKET_DB_BACKEND: str = "sqlite"
    # Automated matching (GEX pairing third-party offers with RFQs). OFF: JML,
    # 2026-10-23, decision 2B on the trading-book spec — matching is bilateral (a
    # named company accepts a specific listing) until counsel confirms GEX would
    # not be operating a trading venue. Turn on only on that confirmation.
    MARKET_AUTO_MATCHING: bool = False
    # ── Ledger anchor (Phase 4 of "One contract record", 2026-11-10) ─────────
    # Per contract event, only {schema_version, pseudo_id, event_type, event_hash,
    # prev_hash} goes to a public ledger (Hedera Consensus Service messages only;
    # no token of any kind). OFF by default: "none" leaves every outbox row
    # PENDING and starts no worker. "hedera_testnet" is the only ledger value;
    # mainnet is not a value until JML adds it.
    LEDGER_ANCHOR_BACKEND: str = "none"
    # HMAC-SHA256 salt for the pseudonymous contract id (Q12). One per environment,
    # NEVER rotated (existing anchors would stop matching), with an off-machine copy.
    LEDGER_ANCHOR_SALT: str = ""
    # The worker's own role, gex_anchor (migration 095): reads the outbox and
    # updates its anchoring columns, nothing else. Not the runtime credential.
    LEDGER_ANCHOR_DATABASE_URL: str = ""
    LEDGER_ANCHOR_INTERVAL_SECONDS: int = 30
    # Hedera operator and topic — from files/.env only, never compose or code.
    HEDERA_OPERATOR_ID: str = ""
    HEDERA_OPERATOR_KEY: str = ""
    HEDERA_TOPIC_ID: str = ""
    HEDERA_MIRROR_URL: str = "https://testnet.mirrornode.hedera.com"

    @field_validator("LEDGER_ANCHOR_BACKEND", mode="after")
    @classmethod
    def _anchor_backend(cls, value: str) -> str:
        if value not in ("none", "hedera_testnet"):
            raise ValueError(f"LEDGER_ANCHOR_BACKEND must be none or hedera_testnet, not {value!r}")
        return value

    # Which store slice 6b-1 (entitlements) uses.
    ENTITLEMENT_DB_BACKEND: str = "sqlite"
    # Which store slice 6b-2 (the platform event ledger) uses.
    EVENTSTORE_DB_BACKEND: str = "sqlite"
    # Which store slice 6b-3 (fuel reference data) uses.
    FUELREF_DB_BACKEND: str = "sqlite"
    # Which store slice 6b-4 (governance / access control) uses.
    GOVERNANCE_DB_BACKEND: str = "sqlite"
    # Which store the domain tail (migrations 043 + 044) uses: mass balance,
    # settlement, sovereign instruments, spend waves, drawdown schedules, DFI
    # criteria, additionality, adversarial reviews, the external corpus, the OT
    # boundary, TEA base cases and risk flags.
    #
    # One switch for the whole tail, not one per module: 043/044 created those
    # tables together and `scripts/migrate_tail_slices.py` copies them together,
    # so splitting them at runtime would let half a domain live in each store.
    # Before this existed, thirteen modules opened SQLite directly on a path
    # captured at import and consulted no switch at all — the 2026-09-22 cutover
    # copied their 30 tables into PostgreSQL while their writes kept going to
    # SQLite, which is a snapshot pretending to be a migration.
    DOMAIN_DB_BACKEND: str = "sqlite"
    # Which store the OWNER-SCOPED personal work uses: canvas documents, a
    # user's plants, their equipment equations (migration 050).
    #
    # One declared switch replacing three undeclared ones — `CANVAS_DB_BACKEND`,
    # `PLANTS_DB_BACKEND` and `EQUATIONS_DB_BACKEND` were read straight from
    # os.getenv, so `Settings` never saw them and nothing validated them. They
    # move together because they are one thing: what a user built on the canvas.
    #
    # These tables are scoped by OWNER, not by company. 050's policies compare
    # `owner_user_id` to `app.current_user_id` and contain no admin clause, so
    # staff cannot read another user's canvas through normal operation. Support,
    # deletion requests and offboarding go through `app/core/break_glass.py`,
    # which is per-user, reason-bearing and written to `admin_log`.
    WORKSPACE_DB_BACKEND: str = "sqlite"
    # Transitional SQLite store. THE ONLY database file in the system.
    # Doctrine: no hidden database, no relative path, no second database,
    # no module-owned path. Modules must use settings.SQLITE_DB_PATH — never
    # os.getenv, never __file__-relative joins, never a literal filename.
    # A relative value (from env or default) is resolved against BACKEND_ROOT,
    # so the path is identical no matter which directory the process starts in.
    SQLITE_DB_PATH: str = "gex_platform.db"

    @field_validator("SQLITE_DB_PATH", mode="after")
    @classmethod
    def _resolve_sqlite_path(cls, value: str) -> str:
        p = Path(value)
        if not p.is_absolute():
            p = BACKEND_ROOT / p
        return str(p.resolve())
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"dev", "debug", "development"}:
                return True
        return value
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


# ── Production guardrails ────────────────────────────────────────────────────
# A production process must never start with the development signing key or
# with demo-mode header authentication enabled. Fail fast — a server that
# silently signs tokens with a public default is worse than one that is down.

_DEV_SECRET_DEFAULT = "dev_secret_key_change_in_production"

if settings.ENVIRONMENT.lower() in ("production", "prod", "staging"):
    if settings.SECRET_KEY == _DEV_SECRET_DEFAULT and not settings.JWT_PRIVATE_KEY_PATH:
        raise RuntimeError(
            "FATAL: SECRET_KEY is the development default in a "
            f"{settings.ENVIRONMENT} environment. Set SECRET_KEY (or RS256 "
            "JWT_PRIVATE_KEY_PATH/JWT_PUBLIC_KEY_PATH) before starting."
        )
    if settings.GEX_DEMO_MODE:
        raise RuntimeError(
            "FATAL: GEX_DEMO_MODE=True in a production environment — demo "
            "header authentication bypasses JWT verification. Set GEX_DEMO_MODE=False."
        )
elif settings.SECRET_KEY == _DEV_SECRET_DEFAULT:
    import logging
    logging.getLogger("gex.config").warning(
        "SECRET_KEY is the development default — acceptable for local dev only."
    )
