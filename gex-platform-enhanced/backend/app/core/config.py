"""
Application Configuration
"""
from pathlib import Path
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings

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
    DATABASE_URL: str = "postgresql://gex_user:gex_password_dev@localhost:5432/gex_platform"
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
