"""
GEX Project Finance Engine — FastAPI Application

Three modules: Bankability scoring, Financial Model (CFADS / drawdown / covenants),
and Price Curves (Gabillon two-factor).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.routers.pricing import router as pf_pricing_router

try:
    from app.api import routes_model
    routes_available = True
except ImportError:
    routes_available = False
    print("Warning: routes_model not found, running without API endpoints")

try:
    from app.api import routes_bankability
    bankability_available = True
except ImportError:
    bankability_available = False
    print("Warning: routes_bankability not found, running without bankability endpoints")

try:
    from app.api import routes_pricing
    pricing_available = True
except ImportError:
    pricing_available = False
    print("Warning: routes_pricing not found, running without pricing endpoints")

_TAG_META = [
    {
        "name": "Bankability Engine",
        "description": "Weighted scoring across 5 certainty dimensions "
        "(Cost · Revenue · Certification · Execution · Counterparty). "
        "Gate evaluation, persona views, and regression checks.",
    },
    {
        "name": "Financial Model",
        "description": "Phase-aware CFADS, drawdown, covenant and lifetime modelling. "
        "Construction · COD · Operations are first-class — DSCR is intentionally "
        "undefined pre-COD.",
    },
    {
        "name": "Gabillon — Market Curves (per molecule)",
        "description": "**Scope: one curve per MOLECULE** (H2, NH3, E_METHANOL, SAF, …). "
        "Market-level Gabillon two-factor engine: implied spot, term structure, single "
        "forwards, Monte-Carlo simulation, seasonal decomposition, model parameters, "
        "CFADS price inputs, and the price decomposition (Information Lineage). "
        "Holds ONE calibration per molecule — SEED expert priors until market "
        "observations are loaded via `POST /api/v1/pricing/calibrate`. "
        "Model reference: `docs/GABILLON_MODEL.md`.",
    },
    {
        "name": "Gabillon — Project Calibration & Offtake (per project)",
        "description": "**Scope: one curve per PROJECT** (`project_id`). "
        "Project-scoped curve service under `/pf/*`: calibrates a Gabillon curve "
        "against project fundamentals (LCOF anchor) with per-project audit memory, "
        "generates Q pricing curves and P forecast cones, values offtake contracts, "
        "and rolls up GreenMesh portfolios. Use this when pricing a specific deal; "
        "use Market Curves when quoting the molecule reference market.",
    },
    {
        "name": "Service",
        "description": "Service identity and health.",
    },
]

# One identity issuer (ADR 2026-07-06): every endpoint requires a GEX
# platform JWT (user or service token) except the explicit public list.
# The platform forwards the caller's bearer or mints a service token.
from fastapi import Depends
from app.auth.gex_jwt import public_path_guard

ENGINE_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json"}

app = FastAPI(
    title="GEX Project Finance Engine",
    description=(
        "Phase-aware project-finance compute for **GreenEarthX**.\n\n"
        "Construction · COD · Operations are first-class phases — "
        "DSCR is intentionally undefined pre-COD.\n\n"
        "Three modules: **Bankability** scoring, **Financial Model** "
        "(CFADS / drawdown / covenants), and **Price Curves** (Gabillon)."
    ),
    version="1.0.0",
    openapi_tags=_TAG_META,
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(public_path_guard(ENGINE_PUBLIC_PATHS))],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if routes_available:
    app.include_router(routes_model.router, prefix="/api/v1/model", tags=["Financial Model"])

if bankability_available:
    app.include_router(routes_bankability.router, prefix="/api/v1/bankability", tags=["Bankability Engine"])

if pricing_available:
    app.include_router(routes_pricing.router, prefix="/api/v1/pricing", tags=["Gabillon — Market Curves (per molecule)"])

app.include_router(pf_pricing_router)


@app.get("/docs", include_in_schema=False)
async def custom_docs() -> HTMLResponse:
    modules = []
    if bankability_available:
        modules.append("Bankability")
    if routes_available:
        modules.append("Financial Model")
    if pricing_available:
        modules.append("Gabillon Pricing")
    status_chips = " ".join(
        f'<span class="chip on">{m}</span>' for m in modules
    )
    if not modules:
        status_chips = '<span class="chip off">No modules loaded</span>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GEX Project Finance Engine — API</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
<style>
  :root {{ --gex-teal: #0ea5a0; --gex-dark: #0f172a; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #f8fafc; font-family: system-ui, -apple-system, sans-serif; }}

  /* ── header ── */
  .gex-header {{
    background: var(--gex-dark); color: #fff; padding: 16px 32px;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  }}
  .gex-header .logo {{
    width: 36px; height: 36px; border-radius: 8px; background: var(--gex-teal);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 16px; color: #fff; flex-shrink: 0;
  }}
  .gex-header h1 {{
    margin: 0; font-size: 18px; font-weight: 600; letter-spacing: -0.3px;
  }}
  .gex-header .version {{
    font-size: 11px; background: rgba(14,165,160,.25); color: var(--gex-teal);
    padding: 2px 8px; border-radius: 10px; font-weight: 600;
  }}
  .gex-header .spacer {{ flex: 1; }}
  .chip {{
    font-size: 11px; padding: 3px 10px; border-radius: 10px;
    font-weight: 500; display: inline-block;
  }}
  .chip.on {{ background: rgba(14,165,160,.15); color: #0d9488; }}
  .chip.off {{ background: rgba(239,68,68,.15); color: #ef4444; }}

  /* ── swagger overrides ── */
  .swagger-ui .topbar {{ display: none; }}
  .swagger-ui .info {{ margin: 24px 0 12px; }}
  .swagger-ui .info .title {{ color: var(--gex-dark); font-weight: 700; }}
  .swagger-ui .info .description p {{ color: #475569; line-height: 1.6; }}

  .swagger-ui .opblock-tag {{
    border-bottom: 2px solid var(--gex-teal) !important; font-weight: 600;
  }}
  .swagger-ui .opblock-tag small {{ color: #64748b; }}

  .swagger-ui .opblock.opblock-get .opblock-summary-method {{ background: var(--gex-teal); }}
  .swagger-ui .opblock.opblock-post .opblock-summary-method {{ background: #3b82f6; }}
  .swagger-ui .opblock.opblock-get {{ border-color: var(--gex-teal); }}
  .swagger-ui .opblock.opblock-get .opblock-summary {{ border-color: var(--gex-teal); }}

  .swagger-ui .btn.execute {{ background: var(--gex-teal); border-color: var(--gex-teal); }}
  .swagger-ui .btn.execute:hover {{ background: #0d9488; }}
  .swagger-ui .btn.authorize {{ color: var(--gex-teal); border-color: var(--gex-teal); }}
  .swagger-ui .btn.authorize svg {{ fill: var(--gex-teal); }}

  .swagger-ui .response-col_status {{ color: var(--gex-teal); font-weight: 600; }}
  .swagger-ui section.models {{ display: none; }}
  .swagger-ui .scheme-container {{ background: #f1f5f9; box-shadow: none; padding: 16px 0; }}
  .swagger-ui .wrapper {{ max-width: 1200px; }}
</style>
</head>
<body>
<div class="gex-header">
  <div class="logo">G</div>
  <h1>GEX Project Finance Engine</h1>
  <span class="version">v1.0.0</span>
  <div class="spacer"></div>
  {status_chips}
</div>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({{
  url: "/openapi.json",
  dom_id: "#swagger-ui",
  docExpansion: "list",
  defaultModelsExpandDepth: 0,
  filter: true,
  tryItOutEnabled: true,
  deepLinking: true,
}});
</script>
</body>
</html>""")


@app.get("/", tags=["Service"], summary="Service identity")
async def root():
    return {
        "service": "GEX Project Finance Engine",
        "status": "operational",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Service"], summary="Health check — per-module component status")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "engine": "ok",
            "cfads": "ok",
            "waterfall": "ok",
            "debt_sculpting": "ok",
            "gabillon_pricing": "ok" if pricing_available else "unavailable",
        },
    }
