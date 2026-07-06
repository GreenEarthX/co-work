"""tea_engine — GEX Techno-Economic Assessment service (FastAPI, port 8002).

Wraps OpenPyTEA (pbtamarona/OpenPyTEA) behind the SAME GEX-JWT bridge as
gex_pf_engine. Sits UPSTREAM of the PF engine (8001): it produces a provisional
cost basis (CAPEX/OPEX/LCOP) + a truth-stack evidence entry; the PF engine
consumes the PlantSummary extract once an IE/CFO has promoted it to a verified
model_base_case.

Environment:
  GEX_JWT_SECRET / GEX_JWKS_URL / GEX_JWT_ISSUER / GEX_JWT_AUDIENCE — see auth bridge
  TEA_STUB=1            deterministic stub output (demo/CI without OpenPyTEA)
  TEA_ENGINE_VERSION    overrides the version string
  PORT                  default 8002
"""
from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tea_engine.auth.gex_jwt import AuthenticatedUser, get_current_user
from tea_engine.compute import engine_name
from tea_engine.routes import tea_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="GEX TEA Engine",
    description=(
        "Techno-economic assessment for **GreenEarthX**, wrapping OpenPyTEA.\n\n"
        "Upstream of the Project-Finance engine: produces a **provisional** cost "
        "basis (CAPEX · OPEX · LCOP) plus a truth-stack **evidence** entry. The "
        "run is never self-verified — promotion to `model_base_case` requires an "
        "IE/CFO approval, and no release-gated compute runs on a provisional basis."
    ),
    version=os.getenv("TEA_ENGINE_VERSION", "sprint1"),
)

_origins = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "https://gex.lovable.app,https://staging.greenearthx.io,https://app.greenearthx.io",
    ).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """No auth — for Cloud Run liveness probes."""
    return {"status": "ok", "engine": app.version, "tea_engine": engine_name()}


@app.get("/whoami")
def whoami(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "engine": app.version,
        "tea_engine": engine_name(),
    }


app.include_router(tea_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "tea_engine.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        reload=os.getenv("DEV", "0") == "1",
    )
