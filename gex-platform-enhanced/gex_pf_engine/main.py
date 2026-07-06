"""gex_pf_engine — FastAPI entry point.

Sprint 1: auth bridge (/healthz, /whoami) + stub /deals/{id}/compute.
Sprint 2: real phased compute via routes/deals.py.

Environment:
  GEX_JWT_SECRET               platform SECRET_KEY for HS256 verification
  GEX_JWKS_URL                 platform JWKS endpoint for RS256 (optional)
  GEX_JWT_ISSUER / GEX_JWT_AUDIENCE  — must match the platform (see auth bridge)
  GEX_ENGINE_VERSION           overrides the version string in outputs
  LOG_LEVEL                    DEBUG | INFO | WARNING | ERROR
"""
from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from gex_pf_engine.auth.gex_jwt import AuthenticatedUser, get_current_user
from gex_pf_engine.routes import deals_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_TAG_META = [
    {
        "name": "Bankability Engine",
        "description": "Weighted scoring across 5 certainty dimensions "
        "(Cost · Revenue · Certification · Execution · Counterparty). "
        "Gate evaluation and regression checks.",
    },
    {
        "name": "Financial Model",
        "description": "Phase-aware CFADS, drawdown, covenant and lifetime modelling. "
        "DSCR is intentionally undefined pre-COD.",
    },
    {
        "name": "Price Curve Engine — Gabillon",
        "description": "Gabillon two-factor forward curves, seasonal decomposition, "
        "Monte-Carlo simulation and CFADS integration per molecule.",
    },
]

app = FastAPI(
    title="GEX Project Finance Engine",
    description=(
        "Phase-aware project-finance compute for **GreenEarthX**.\n\n"
        "Construction · COD · Operations are first-class phases — "
        "DSCR is intentionally undefined pre-COD.\n\n"
        "Three modules: **Bankability** scoring, **Financial Model** "
        "(CFADS / drawdown / covenants), and **Price Curves** (Gabillon)."
    ),
    version=os.getenv("GEX_ENGINE_VERSION", "sprint2"),
    openapi_tags=_TAG_META,
    docs_url=None,
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
def custom_docs() -> HTMLResponse:
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GEX Project Finance Engine — API</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
<style>
  :root { --gex-teal: #0ea5a0; --gex-dark: #0f172a; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }
  .gex-header {
    background: var(--gex-dark); color: #fff; padding: 18px 32px;
    display: flex; align-items: center; gap: 14px;
  }
  .gex-header .logo {
    width: 36px; height: 36px; border-radius: 8px; background: var(--gex-teal);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 16px; color: #fff; flex-shrink: 0;
  }
  .gex-header h1 { margin: 0; font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
  .gex-header .badge {
    font-size: 11px; background: rgba(14,165,160,.25); color: var(--gex-teal);
    padding: 2px 8px; border-radius: 10px; font-weight: 600; margin-left: 8px;
  }
  .swagger-ui .topbar { display: none; }
  .swagger-ui .info { margin: 24px 0 12px; }
  .swagger-ui .info .title { color: var(--gex-dark); font-weight: 700; }
  .swagger-ui .info .description p { color: #475569; line-height: 1.6; }
  .swagger-ui .opblock-tag {
    border-bottom: 2px solid var(--gex-teal) !important; font-weight: 600;
  }
  .swagger-ui .opblock-tag small { color: #64748b; }
  .swagger-ui .opblock.opblock-get .opblock-summary-method { background: var(--gex-teal); }
  .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #3b82f6; }
  .swagger-ui .opblock.opblock-get { border-color: var(--gex-teal); }
  .swagger-ui .opblock.opblock-get .opblock-summary { border-color: var(--gex-teal); }
  .swagger-ui .btn.execute { background: var(--gex-teal); border-color: var(--gex-teal); }
  .swagger-ui .btn.execute:hover { background: #0d9488; }
  .swagger-ui .btn.authorize { color: var(--gex-teal); border-color: var(--gex-teal); }
  .swagger-ui .btn.authorize svg { fill: var(--gex-teal); }
  .swagger-ui .response-col_status { color: var(--gex-teal); font-weight: 600; }
  .swagger-ui section.models { display: none; }
  .swagger-ui .scheme-container { background: #f1f5f9; box-shadow: none; padding: 16px 0; }
  .swagger-ui .wrapper { max-width: 1200px; }
</style>
</head>
<body>
<div class="gex-header">
  <div class="logo">G</div>
  <h1>GEX Project Finance Engine <span class="badge">sprint2</span></h1>
</div>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: "/openapi.json",
  dom_id: "#swagger-ui",
  docExpansion: "list",
  defaultModelsExpandDepth: 0,
  filter: true,
  tryItOutEnabled: true,
  deepLinking: true,
});
</script>
</body>
</html>""")

# CORS — Lovable preview, staging, production
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

# ---------------------------------------------------------------------------
# Health & smoke endpoints (Sprint 1)
# ---------------------------------------------------------------------------

@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """No auth — for Cloud Run liveness probes."""
    return {"status": "ok", "engine": app.version}


@app.get("/whoami")
def whoami(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Echoes the authenticated user. Useful for verifying the JWT bridge."""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "tenant_ids": user.tenant_ids,
        "engine": app.version,
    }


# ---------------------------------------------------------------------------
# Sprint 2 routers
# ---------------------------------------------------------------------------

app.include_router(deals_router)


# ---------------------------------------------------------------------------
# Local dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gex_pf_engine.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=os.getenv("DEV", "0") == "1",
    )
