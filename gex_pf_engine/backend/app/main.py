"""
`app.main` — the deprecated entry point, re-exporting the real one.

`uvicorn app.main:app` resolves here. There is deliberately no second FastAPI
instance: this is the SAME object as `pf_engine.main.app`, so routes, exception
handlers and startup hooks cannot drift between the two names.
`app/__init__.py` explains why the alias exists and what it refuses to do.
"""
from __future__ import annotations

from pf_engine.main import app  # noqa: F401  — re-export, not a copy

__all__ = ["app"]
