"""
PostgreSQL session factory with per-request Row-Level Security context.

Every FastAPI route that touches `projects` or `project_access` must use
`get_db` as a dependency.  The dependency sets `app.current_company_id` on
the PostgreSQL connection before yielding the session, activating the RLS
policies defined in migration 020.

Usage in a route:
    @router.get("/projects")
    async def list_projects(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Project))
        return result.scalars().all()

Platform admins (is_platform_admin=True) bypass RLS by having company_id set
to the literal sentinel 'PLATFORM_ADMIN', which the RLS policy allows through.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# Convert sync postgresql:// URL to asyncpg driver URL if needed.
def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Engines are built LAZILY. Constructing them at import time resolves the
# dialect's DBAPI immediately, so importing this module raised
# ModuleNotFoundError('asyncpg') in any deployment without the async driver —
# which meant the *synchronous* path below could not be used either, and this
# module was unimportable everywhere. During the strangler migration most code
# is still sync; it must not be blocked by the async driver.
_engine = None
_AsyncSessionLocal = None


def get_async_engine():
    global _engine, _AsyncSessionLocal
    if _engine is None:
        _engine = create_async_engine(
            _async_url(settings.DATABASE_URL),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            # Echo SQL only in debug mode — avoids leaking tenant data to logs in prod
            echo=settings.DEBUG and settings.ENVIRONMENT == "development",
        )
        _AsyncSessionLocal = async_sessionmaker(
            _engine, expire_on_commit=False, autoflush=False, autocommit=False,
        )
    return _engine


def AsyncSessionLocal(*args, **kwargs):
    """Session factory — builds the engine on first use."""
    get_async_engine()
    return _AsyncSessionLocal(*args, **kwargs)


# ── Tenant context extraction ─────────────────────────────────────────────────

def _company_id_from_request(request: Request) -> Optional[str]:
    """
    Extract the authenticated user's company_id from the request state.

    auth_middleware (abac_middleware.py) populates request.state.user_payload
    after verifying the JWT.  If no auth header is present the request is
    treated as a guest (returns None → RLS will apply 'GUEST' sentinel).
    """
    from app.core.request_tenant import company_from_payload, payload_from_request

    # Reads BOTH state attribute names and applies the one shared derivation
    # rule, so this path and the shim path always agree on who the caller is.
    return company_from_payload(payload_from_request(request))


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency — yields an AsyncSession with RLS context set.

    1. Opens a connection from the pool.
    2. Sets app.current_company_id on the PostgreSQL session so RLS
       policies on `projects` and `project_access` filter correctly.
    3. Yields the session.
    4. Commits on clean exit, rolls back on exception.
    """
    company_id = _company_id_from_request(request) or "GUEST"

    async with AsyncSessionLocal() as session:
        # SET LOCAL is transaction-scoped — resets automatically at COMMIT/ROLLBACK.
        # Using parameterised text is not possible for SET LOCAL, but company_id
        # is derived from a verified JWT claim (not user input), so format is safe.
        # We still whitelist the value to be defensive.
        safe_company_id = _sanitise_company_id(company_id)
        await session.execute(
            text(f"SET LOCAL app.current_company_id = '{safe_company_id}'")
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _sanitise_company_id(value: str) -> str:
    """
    Whitelist company_id characters before interpolating into SET LOCAL.
    Valid slugs are lowercase alphanumeric + underscore, max 120 chars.
    The sentinels PLATFORM_ADMIN and GUEST are also allowed.
    """
    import re
    if value in ("PLATFORM_ADMIN", "GUEST"):
        return value
    if re.fullmatch(r"[a-z0-9_]{1,120}", value):
        return value
    # Unexpected format — deny rather than risk RLS bypass
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid tenant identity in token.",
    )


# ── Synchronous helper for non-async code paths ──────────────────────────────
# Used by legacy endpoints that haven't been migrated to async yet.

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_sync_engine = None
_SyncSessionLocal = None


def get_sync_engine():
    """Lazily-built sync engine. See the note on the async engine above."""
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _SyncSessionLocal = sessionmaker(
            _sync_engine, autocommit=False, autoflush=False,
        )
    return _sync_engine


def SyncSessionLocal(*args, **kwargs):
    get_sync_engine()
    return _SyncSessionLocal(*args, **kwargs)


def get_sync_db_for_company(company_id: str):
    """
    Context manager for synchronous DB access with RLS context.
    Usage:
        with get_sync_db_for_company(company_id) as db:
            rows = db.execute(select(Project)).scalars().all()
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        safe = _sanitise_company_id(company_id or "GUEST")
        db: Session = SyncSessionLocal()
        try:
            db.execute(text(f"SET LOCAL app.current_company_id = '{safe}'"))
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return _ctx()
