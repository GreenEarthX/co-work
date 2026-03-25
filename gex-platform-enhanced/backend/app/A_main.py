"""
GreenEarthX Platform - Main FastAPI Application
"""
# 1. Third-party imports
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware


# 2. Internal application imports
from app.api.v1 import capacity_sqlite as capacity
from app.api.v1 import audit
from app.api.v1 import trader_rfqs
from app.api.v1 import marketplace_analytics
from app.api.v1 import onboarding
from app.api.v1 import decision_twin

from app.api.v1.routes_events import router as events_router

from app.api.endpoints import finance
from app.core.config import settings
from app.core.event_bus import EventBus, set_event_bus, get_event_bus

# ── Deal Structuring Workbench (v5.0) ──
# ── Deal Structuring Workbench (v5.0) ──
from app.api.v1.routes_structuring import router as structuring_router
from app.api.v1.routes_instruments import instruments_router
from app.api.v1.routes_demand import demand_router
from app.api.v1.routes_risk_pricing import risk_pricing_router

app.include_router(structuring_router)
app.include_router(instruments_router)
app.include_router(demand_router)
app.include_router(risk_pricing_router)
#### added 19 march 2026 via claude and chatgpt - event bus integration for 
### decoupled async events across microservices and external systems (e.g. Matrix, WAE, CISO, etc.)

import logging

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    aioredis = None
    HAS_REDIS = False
    print("⚠️  redis.asyncio not found - event bus disabled")

try:
    from app.core.event_bus import EventBus, set_event_bus
    HAS_EVENT_BUS = True
except ImportError:
    EventBus = None
    set_event_bus = None
    HAS_EVENT_BUS = False
    print("⚠️  app.core.event_bus not found - event bus disabled")

try:
    from app.api.v1.routes_events import router as events_router
    HAS_EVENTS_ROUTER = True
except ImportError:
    events_router = None
    HAS_EVENTS_ROUTER = False
    print("⚠️  routes_events not found - skipping")


logger = logging.getLogger("gex.main")
# end of addition  and bakc to original main.py file

# Import optional modules (may not exist yet)

try:
    from app.api.v1 import tokens_sqlite as tokenisation
    HAS_TOKENS = True
except ImportError:
    HAS_TOKENS = False
    print("⚠️  tokens_sqlite not found - skipping")

try:
    from app.api.v1 import marketplace_sqlite as marketplace
    HAS_MARKETPLACE = True
except ImportError:
    HAS_MARKETPLACE = False
    print("⚠️  marketplace_sqlite not found - skipping")

try:
    from app.api.v1 import matching_sqlite as matching
    HAS_MATCHING = True
except ImportError:
    HAS_MATCHING = False
    print("⚠️  matching_sqlite not found - skipping")

try:
    from app.api.v1 import contracts_sqlite as contracts
    HAS_CONTRACTS = True
except ImportError:
    HAS_CONTRACTS = False
    print("⚠️  contracts_sqlite not found - skipping")

try:
    from app.api.v1 import greenmesh
    HAS_GREENMESH = True
except ImportError:
    HAS_GREENMESH = False
    print("⚠️  greenmesh not found - skipping")

try:
    from app.api.v1 import routes_bankability_proxy
    HAS_BANKABILITY_PROXY = True
except ImportError:
    HAS_BANKABILITY_PROXY = False
    print("⚠️  routes_bankability_proxy not found - skipping")

try:
    from app.api.v1 import routes_finance_model
    HAS_FINANCE_MODEL = True
except ImportError:
    HAS_FINANCE_MODEL = False
    print("⚠️  routes_finance_model not found - skipping")

try:
    from app.api.v1 import routes_project_ratings
    HAS_PROJECT_RATINGS = True
except ImportError:
    HAS_PROJECT_RATINGS = False
    print("⚠️  routes_project_ratings not found - skipping")

try:
    from app.api.v1 import routes_ciso
    HAS_CISO = True
except ImportError:
    HAS_CISO = False
    print("⚠️  routes_ciso not found - skipping")

try:
    from app.api.v1 import routes_matrix
    HAS_MATRIX = True
except ImportError:
    HAS_MATRIX = False
    print("⚠️  routes_matrix not found - skipping")

try:
    from app.api.v1 import routes_approvals
    HAS_APPROVALS = True
except ImportError:
    HAS_APPROVALS = False
    print("⚠️  routes_approvals not found - skipping")

try:
    from app.api.v1 import routes_plant_data
    HAS_PLANT_DATA = True
except ImportError:
    HAS_PLANT_DATA = False
    print("⚠️  routes_plant_data not found - skipping")

try:
    from app.api.v1 import routes_commitments
    HAS_COMMITMENTS = True
except ImportError:
    HAS_COMMITMENTS = False
    print("⚠️  routes_commitments not found - skipping")

# ── Bankability v2.0 — Workflow + Bankability Cockpit ───────────────────────
try:
    from app.api.v1 import routes_workflow
    HAS_WORKFLOW = True
except ImportError:
    HAS_WORKFLOW = False
    print("⚠️  routes_workflow not found - skipping")

try:
    from app.api.v1 import routes_timeline
    HAS_TIMELINE = True
except ImportError:
    HAS_TIMELINE = False
    print("⚠️  routes_timeline not found - skipping")

try:
    from app.api.v1 import routes_reports
    HAS_REPORTS = True
except ImportError:
    HAS_REPORTS = False
    print("⚠️  routes_reports not found - skipping")

try:
    from app.api.v1 import routes_performance
    HAS_PERFORMANCE = True
except ImportError:
    HAS_PERFORMANCE = False
    print("⚠️  routes_performance not found - skipping")

try:
    from app.api.v1 import routes_ic_pack
    HAS_IC_PACK = True
except ImportError:
    HAS_IC_PACK = False
    print("⚠️  routes_ic_pack not found - skipping")

try:
    from app.api.v1 import routes_data_room
    HAS_DATA_ROOM = True
except ImportError:
    HAS_DATA_ROOM = False
    print("⚠️  routes_data_room not found - skipping")

try:
    from app.api.v1 import routes_terms
    HAS_TERMS = True
except ImportError:
    HAS_TERMS = False
    print("⚠️  routes_terms not found - skipping")


# ═══════════════════════════════════════════════════════════════
# CREATE APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="GreenEarthX Platform API",
    description="Green fuels orchestration platform for H2, NH3, SAF, and eMeOH",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
### new event bus initialisation and registration of events route module added below in steps 2 and 3


@app.on_event("startup")
async def startup_event_bus():
    if not (HAS_REDIS and HAS_EVENT_BUS):
        logger.warning("Event bus dependencies unavailable - startup skipped")
        app.state.event_bus = None
        app.state.redis = None
        return

    try:
        redis_client = aioredis.from_url(
            "redis://redis:6379/0",
            decode_responses=False,
        )
        bus = EventBus(redis_client)
        await bus.initialize()
        set_event_bus(bus)
        app.state.event_bus = bus
        app.state.redis = redis_client
        logger.info("Event bus initialized successfully")
    except Exception as e:
        app.state.event_bus = None
        app.state.redis = None
        logger.warning("Event bus unavailable (Redis not running): %s", e)
        logger.warning("Platform will operate without event bus — events will not propagate")


@app.on_event("shutdown")
async def shutdown_event_bus():
    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.aclose()
        logger.info("Event bus Redis connection closed")

## end of addition for event bus integration
# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }


# ═══════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════

app.include_router(
    capacity.router,
    prefix="/api/v1/capacities",
    tags=["Capacity Management"]
)

if HAS_TOKENS:
    app.include_router(
        tokenisation.router,
        prefix="/api/v1/tokens",
        tags=["Tokenisation"]
    )

if HAS_MARKETPLACE:
    app.include_router(
        marketplace.router,
        prefix="/api/v1/marketplace",
        tags=["Marketplace"]
    )
    app.include_router(
        marketplace_analytics.router,
        prefix="/api/v1/marketplace",
        tags=["Marketplace Analytics"]
    )

if HAS_MATCHING:
    app.include_router(
        matching.router,
        prefix="/api/v1/matching",
        tags=["Matching Engine"]
    )

if HAS_CONTRACTS:
    app.include_router(
        contracts.router,
        prefix="/api/v1/contracts",
        tags=["Contracts & Commitments"]
    )

app.include_router(
    audit.router,
    prefix="/api/v1/audit",
    tags=["Audit & Compliance"]
)

app.include_router(
    trader_rfqs.router,
    prefix="/api/v1/trader/rfqs",
    tags=["Trader - RFQ Management"]
)

app.include_router(
    onboarding.router,
    prefix="/api/v1/onboarding",
    tags=["Onboarding Wizard"]
)

app.include_router(
    decision_twin.router,
    prefix="/api/v1/decision-twin",
    tags=["Decision Twin - Certification Engine"]
)

app.include_router(
    finance.router,
    prefix="/api/v1/finance",
    tags=["Finance & Risk Management"]
)

if HAS_BANKABILITY_PROXY:
    app.include_router(
        routes_bankability_proxy.router,
        prefix="/api/v1/bankability",
        tags=["Bankability Proxy"]
    )

if HAS_FINANCE_MODEL:
    app.include_router(
        routes_finance_model.router,
        prefix="/api/v1/finance-model",
        tags=["Finance Model Proxy"]
    )

if HAS_PROJECT_RATINGS:
    app.include_router(
        routes_project_ratings.router,
        prefix="/api/v1/project-ratings",
        tags=["Project Quality Rating"]
    )

if HAS_CISO:
    app.include_router(
        routes_ciso.router,
        prefix="/api/v1/ciso",
        tags=["CISO — Security & Compliance"]
    )

if HAS_MATRIX:
    app.include_router(
        routes_matrix.router,
        prefix="/api/v1/comms",
        tags=["Secure Communications — Matrix/Synapse"]
    )

if HAS_APPROVALS:
    app.include_router(
        routes_approvals.router,
        prefix="/api/v1/approvals",
        tags=["WAE — Workflow Authorization Engine"]
    )

if HAS_PLANT_DATA:
    app.include_router(
        routes_plant_data.router,
        prefix="/api/v1/plant-data",
        tags=["OT/IT Boundary — Plant Data Ingestion"]
    )

if HAS_COMMITMENTS:
    app.include_router(
        routes_commitments.router,
        prefix="/api/v1/commitments",
        tags=["CSS — Commitment Signature Service"]
    )

# ── Bankability v2.0 — Workflow + Bankability Cockpit ───────────────────────
if HAS_WORKFLOW:
    app.include_router(
        routes_workflow.router,
        prefix="/api/v1/workflow",
        tags=["Bankability — Workflow State Management"]
    )

if HAS_TIMELINE:
    app.include_router(
        routes_timeline.router,
        prefix="/api/v1/timeline",
        tags=["Bankability — Funding Timeline & Milestones"]
    )

if HAS_REPORTS:
    app.include_router(
        routes_reports.router,
        prefix="/api/v1/reports",
        tags=["Bankability — Report Assembly (CFO + Banker)"]
    )

if HAS_PERFORMANCE:
    app.include_router(
        routes_performance.router,
        prefix="/api/v1/performance",
        tags=["Bankability — EPC/OEM Performance Matrix"]
    )

if HAS_IC_PACK:
    app.include_router(
        routes_ic_pack.router,
        prefix="/api/v1/ic-pack",
        tags=["Bankability — IC Pack Assembly & Export"]
    )

if HAS_DATA_ROOM:
    app.include_router(
        routes_data_room.router,
        prefix="/api/v1/data-room",
        tags=["Bankability — Virtual Data Room"]
    )

if HAS_TERMS:
    app.include_router(
        routes_terms.router,
        prefix="/api/v1/terms",
        tags=["Bankability — Term Sheet Tracker"]
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
