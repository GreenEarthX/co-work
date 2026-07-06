"""
GreenEarthX Platform - Main FastAPI Application
"""
# 1. Third-party imports
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# 2. Internal application imports (always available)
from app.api.v1 import capacity_sqlite as capacity
from app.api.v1 import audit
from app.api.v1 import trader_rfqs
from app.api.v1 import marketplace_analytics
from app.api.v1 import onboarding
from app.api.v1 import decision_twin
from app.api.endpoints import finance
from app.core.config import settings

logger = logging.getLogger("gex.main")

# 3. Optional: Redis + Event Bus
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

# 4. Optional: Deal Structuring Workbench (v5.0)
try:
    from app.api.v1.routes_structuring import router as structuring_router
    HAS_STRUCTURING = True
except ImportError:
    HAS_STRUCTURING = False
    print("⚠️  routes_structuring not found - skipping")

try:
    from app.api.v1.routes_instruments import instruments_router
    HAS_INSTRUMENTS = True
except ImportError:
    HAS_INSTRUMENTS = False
    print("⚠️  routes_instruments not found - skipping")

try:
    from app.api.v1.routes_demand import demand_router
    HAS_DEMAND = True
except ImportError:
    HAS_DEMAND = False
    print("⚠️  routes_demand not found - skipping")

try:
    from app.api.v1.routes_risk_pricing import risk_pricing_router
    HAS_RISK_PRICING = True
except ImportError:
    HAS_RISK_PRICING = False
    print("⚠️  routes_risk_pricing not found - skipping")

try:
    from app.api.v1 import routes_pricing_proxy
    HAS_PRICING_PROXY = True
except ImportError:
    HAS_PRICING_PROXY = False
    print("⚠️  routes_pricing_proxy not found - skipping")

try:
    from app.api.v1.routes_plant_builder import router as plant_builder_router
    HAS_PLANT_BUILDER = True
except ImportError:
    HAS_PLANT_BUILDER = False
    print("⚠️  routes_plant_builder not found - skipping")

# 5. Optional: existing modules
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

# ── R0/R1/R6/R10: Architectural Reform v6.0 routes ────────────────────────────
try:
    from app.api.v1.routes_verification import router as verification_router
    HAS_VERIFICATION = True
except ImportError:
    HAS_VERIFICATION = False
    print("⚠️  routes_verification not found - skipping")

try:
    from app.api.v1.routes_deal_killers import router as deal_killers_router
    HAS_DEAL_KILLERS = True
except ImportError:
    HAS_DEAL_KILLERS = False
    print("⚠️  routes_deal_killers not found - skipping")

try:
    from app.api.v1.routes_task_router import router as task_router_router
    HAS_TASK_ROUTER = True
except ImportError:
    HAS_TASK_ROUTER = False
    print("⚠️  routes_task_router not found - skipping")
# ── End R0/R1/R6/R10 ──────────────────────────────────────────────────────────

try:
    from app.api.v1 import routes_bankability_proxy
    HAS_BANKABILITY_PROXY = True
except ImportError:
    HAS_BANKABILITY_PROXY = False
    print("⚠️  routes_bankability_proxy not found - skipping")

try:
    from app.trading_book.api import router as trading_book_router
    HAS_TRADING_BOOK = True
except ImportError:
    trading_book_router = None
    HAS_TRADING_BOOK = False
    print("⚠️  trading_book not found - skipping")

try:
    from app.api.v1.routes_gate_registry import router as gate_registry_router
    HAS_GATE_REGISTRY = True
except ImportError:
    HAS_GATE_REGISTRY = False
    print("⚠️  routes_gate_registry not found - skipping")

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
    from app.api.v1 import routes_auth
    HAS_AUTH = True
except ImportError as exc:
    HAS_AUTH = False
    print(f"⚠️  routes_auth not found - skipping: {exc}")

try:
    from app.api.v1 import routes_fuels
    HAS_FUELS = True
except ImportError as exc:
    HAS_FUELS = False
    print(f"⚠️  routes_fuels not found - skipping: {exc}")

try:
    from app.api.v1 import routes_permissions
    HAS_PERMISSIONS = True
except ImportError:
    HAS_PERMISSIONS = False
    print("⚠️  routes_permissions not found - skipping")

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

try:
    from app.api.v1 import routes_project_activity
    HAS_PROJECT_ACTIVITY = True
except ImportError:
    HAS_PROJECT_ACTIVITY = False
    print("⚠️  routes_project_activity not found - skipping")

try:
    from app.api.v1 import routes_project_truth
    HAS_PROJECT_TRUTH = True
except ImportError:
    HAS_PROJECT_TRUTH = False
    print("⚠️  routes_project_truth not found - skipping")

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

try:
    from app.api.v1 import routes_adversarial_reviews
    HAS_ADVERSARIAL_REVIEWS = True
except ImportError:
    HAS_ADVERSARIAL_REVIEWS = False
    print("⚠️  routes_adversarial_reviews not found - skipping")

try:
    from app.core.abac_middleware import ABACMiddleware
    HAS_ABAC_MIDDLEWARE = True
except ImportError:
    ABACMiddleware = None
    HAS_ABAC_MIDDLEWARE = False
    print("⚠️  ABAC middleware not found - skipping")

try:
    from app.api.v1.development_packages import router as dev_packages_router, init_db as dev_packages_init_db
    dev_packages_init_db()
    HAS_DEV_PACKAGES = True
except ImportError:
    dev_packages_router = None
    HAS_DEV_PACKAGES = False
    print("⚠️  development_packages not found - skipping")

try:
    from app.api.v1.pre_cod_metrics import router as pre_cod_router, init_db as pre_cod_init_db
    pre_cod_init_db()
    HAS_PRE_COD_METRICS = True
except ImportError:
    pre_cod_router = None
    HAS_PRE_COD_METRICS = False
    print("⚠️  pre_cod_metrics not found - skipping")

try:
    from app.api.v1.routes_entitlements import router as entitlements_router
    from app.core.entitlements import init_entitlements_db
    init_entitlements_db()
    HAS_ENTITLEMENTS = True
except ImportError:
    entitlements_router = None
    HAS_ENTITLEMENTS = False
    print("⚠️  routes_entitlements not found - skipping")

try:
    from app.api.v1.additionality import router as additionality_router, init_db as additionality_init_db
    additionality_init_db()
    HAS_ADDITIONALITY = True
except ImportError:
    additionality_router = None
    HAS_ADDITIONALITY = False
    print("⚠️  additionality not found - skipping")

try:
    from app.api.v1.capital_bridge import router as capital_bridge_router, init_db as capital_bridge_init_db
    capital_bridge_init_db()
    HAS_CAPITAL_BRIDGE = True
except ImportError as exc:
    capital_bridge_router = None
    HAS_CAPITAL_BRIDGE = False
    print(f"⚠️  capital_bridge not found - skipping: {exc}")

try:
    from app.api.v1.spend_wave import router as spend_wave_router, init_db as spend_wave_init_db
    spend_wave_init_db()
    HAS_SPEND_WAVE = True
except ImportError:
    spend_wave_router = None
    HAS_SPEND_WAVE = False
    print("⚠️  spend_wave not found - skipping")

try:
    from app.api.v1.drawdown_schedule import router as drawdown_router, init_db as drawdown_init_db
    drawdown_init_db()
    HAS_DRAWDOWN = True
except ImportError:
    drawdown_router = None
    HAS_DRAWDOWN = False
    print("⚠️  drawdown_schedule not found - skipping")

try:
    from app.api.v1.settlement_events import router as settlement_router, init_db as settlement_init_db
    settlement_init_db()
    HAS_SETTLEMENTS = True
except ImportError:
    settlement_router = None
    HAS_SETTLEMENTS = False
    print("⚠️  settlement_events not found - skipping")

try:
    from app.api.v1.carbon_attribution import router as carbon_attr_router, init_db as carbon_attr_init_db
    carbon_attr_init_db()
    HAS_CARBON_ATTR = True
except ImportError:
    carbon_attr_router = None
    HAS_CARBON_ATTR = False
    print("⚠️  carbon_attribution not found - skipping")

try:
    from app.api.v1.sovereign_instruments import router as sovereign_router, init_db as sovereign_init_db
    sovereign_init_db()
    HAS_SOVEREIGN = True
except ImportError:
    sovereign_router = None
    HAS_SOVEREIGN = False
    print("⚠️  sovereign_instruments not found - skipping")

try:
    from app.api.v1.dfi_criteria import router as dfi_criteria_router, init_db as dfi_criteria_init_db
    dfi_criteria_init_db()
    HAS_DFI_CRITERIA = True
except ImportError:
    dfi_criteria_router = None
    HAS_DFI_CRITERIA = False
    print("⚠️  dfi_criteria not found - skipping")

try:
    from app.api.v1.evidence_ledger import router as evidence_ledger_router, init_db as evidence_ledger_init_db
    evidence_ledger_init_db()
    HAS_EVIDENCE_LEDGER = True
except ImportError:
    evidence_ledger_router = None
    HAS_EVIDENCE_LEDGER = False
    print("⚠️  evidence_ledger not found - skipping")

try:
    from app.api.v1.routes_tea import router as tea_bridge_router, init_db as tea_bridge_init_db
    tea_bridge_init_db()
    HAS_TEA_BRIDGE = True
except ImportError:
    tea_bridge_router = None
    HAS_TEA_BRIDGE = False
    print("⚠️  routes_tea not found - skipping")

try:
    from app.api.v1.next_best_action import router as nba_router
    HAS_NBA = True
except ImportError:
    nba_router = None
    HAS_NBA = False
    print("⚠️  next_best_action not found - skipping")

try:
    from app.api.v1.corpus_routes import router as corpus_router, init_db as corpus_init_db
    corpus_init_db()
    HAS_CORPUS = True
except ImportError:
    corpus_router = None
    HAS_CORPUS = False
    print("⚠️  corpus_routes not found - skipping")

try:
    from app.api.v1.lineage import router as lineage_router, init_db as lineage_init_db
    lineage_init_db()
    HAS_LINEAGE = True
except ImportError:
    lineage_router = None
    HAS_LINEAGE = False
    print("⚠️  lineage not found - skipping")

try:
    from app.api.v1.adjacency import router as adjacency_router, init_db as adjacency_init_db
    adjacency_init_db()
    HAS_ADJACENCY = True
except ImportError:
    adjacency_router = None
    HAS_ADJACENCY = False
    print("⚠️  adjacency not found - skipping")

try:
    from app.api.v1.mass_balance import router as mass_balance_router, init_db as mass_balance_init_db
    mass_balance_init_db()
    HAS_MASS_BALANCE = True
except ImportError:
    mass_balance_router = None
    HAS_MASS_BALANCE = False
    print("⚠️  mass_balance not found - skipping")


# ═══════════════════════════════════════════════════════════════
# CREATE APP
# ═══════════════════════════════════════════════════════════════

# Security layering (ADR 2026-07-06), outermost first:
#   1. require_authenticated — identity by default; public routes are the
#      explicit registry in app.core.route_security. Holds even if the ABAC
#      middleware is disabled — defense in depth, fail closed.
#   2. enforce_domain_authorization — business-function write policy per
#      domain (app.core.domain_authorization); unmapped routes fail closed.
#   3. ABAC middleware + permission engine (below) — policy + audit.
#   4. PostgreSQL RLS — final backstop as slices migrate.
from fastapi import Depends
from app.core.route_security import require_authenticated
from app.core.domain_authorization import enforce_domain_authorization

app = FastAPI(
    title="GreenEarthX Platform API",
    description="Green fuels orchestration platform for H2, NH3, SAF, and eMeOH",
    version="5.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    dependencies=[
        Depends(require_authenticated),
        Depends(enforce_domain_authorization),
    ],
)


# ═══════════════════════════════════════════════════════════════
# STARTUP / SHUTDOWN
# ═══════════════════════════════════════════════════════════════

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


@app.on_event("shutdown")
async def shutdown_event_bus():
    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.aclose()
        logger.info("Event bus Redis connection closed")


# ═══════════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════════

if HAS_ABAC_MIDDLEWARE and settings.ENABLE_ABAC_MIDDLEWARE:
    app.add_middleware(ABACMiddleware, phase=settings.ABAC_PHASE)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "GreenEarthX Platform API",
        "version": "5.0.0",
        "docs": "/docs",
    }


@app.get("/health")
@app.get("/healthz")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "5.0.0",
    }


# ═══════════════════════════════════════════════════════════════
# API ROUTES — all include_router calls BELOW app = FastAPI()
# ═══════════════════════════════════════════════════════════════

# ── R0/R1/R6/R10: Architectural Reform v6.0 ──
if HAS_VERIFICATION:
    app.include_router(verification_router, prefix="/api/v1", tags=["Verification State Engine"])
if HAS_DEAL_KILLERS:
    app.include_router(deal_killers_router, prefix="/api/v1", tags=["Deal-Killer System"])
if HAS_TASK_ROUTER:
    app.include_router(task_router_router, prefix="/api/v1", tags=["Task Router"])

# ── Always available ──
app.include_router(capacity.router, prefix="/api/v1/capacities", tags=["Capacity Management"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit & Compliance"])
app.include_router(trader_rfqs.router, prefix="/api/v1/trader/rfqs", tags=["Trader - RFQ Management"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["Onboarding Wizard"])
app.include_router(decision_twin.router, prefix="/api/v1/decision-twin", tags=["Decision Twin - Certification Engine"])
app.include_router(finance.router, prefix="/api/v1/finance", tags=["Finance & Risk Management"])
if HAS_AUTH:
    app.include_router(routes_auth.router, prefix="/api/v1", tags=["Auth"])

if HAS_FUELS:
    app.include_router(routes_fuels.router, prefix="/api/v1", tags=["Fuel Catalogue"])

# ── Optional core modules ──
if HAS_TOKENS:
    app.include_router(tokenisation.router, prefix="/api/v1/tokens", tags=["Tokenisation"])

if HAS_MARKETPLACE:
    app.include_router(marketplace.router, prefix="/api/v1/marketplace", tags=["Marketplace"])
    app.include_router(marketplace_analytics.router, prefix="/api/v1/marketplace", tags=["Marketplace Analytics"])

if HAS_MATCHING:
    app.include_router(matching.router, prefix="/api/v1/matching", tags=["Matching Engine"])

if HAS_CONTRACTS:
    app.include_router(contracts.router, prefix="/api/v1/contracts", tags=["Contracts & Commitments"])

if HAS_BANKABILITY_PROXY:
    app.include_router(routes_bankability_proxy.router, prefix="/api/v1/bankability", tags=["Bankability Proxy"])

if HAS_TRADING_BOOK:
    app.include_router(trading_book_router, prefix="/api/v1/trading-book", tags=["Trading Book (B1)"])

if HAS_GATE_REGISTRY:
    app.include_router(gate_registry_router, prefix="/api/v1/gates", tags=["Gate Registry"])

if HAS_FINANCE_MODEL:
    app.include_router(routes_finance_model.router, prefix="/api/v1/finance-model", tags=["Finance Model Proxy"])

if HAS_PROJECT_RATINGS:
    app.include_router(routes_project_ratings.router, prefix="/api/v1/project-ratings", tags=["Project Quality Rating"])

# ── Security Architecture Extension ──
if HAS_CISO:
    app.include_router(routes_ciso.router, prefix="/api/v1/ciso", tags=["CISO — Security & Compliance"])

if HAS_PERMISSIONS:
    app.include_router(routes_permissions.router, prefix="/api/v1/ciso", tags=["CISO — Permission Engine"])

if HAS_MATRIX:
    app.include_router(routes_matrix.router, prefix="/api/v1/comms", tags=["Secure Communications — Matrix/Synapse"])

if HAS_APPROVALS:
    app.include_router(routes_approvals.router, prefix="/api/v1/approvals", tags=["WAE — Workflow Authorization Engine"])

if HAS_PLANT_DATA:
    app.include_router(routes_plant_data.router, prefix="/api/v1/plant-data", tags=["OT/IT Boundary — Plant Data Ingestion"])

if HAS_COMMITMENTS:
    app.include_router(routes_commitments.router, prefix="/api/v1/commitments", tags=["CSS — Commitment Signature Service"])

if HAS_PROJECT_ACTIVITY:
    app.include_router(routes_project_activity.router, prefix="/api/v1", tags=["Project Activity Ledger"])

if HAS_PROJECT_TRUTH:
    app.include_router(routes_project_truth.router, prefix="/api/v1", tags=["Project Truth"])

from app.api.v1.routes_projects import router as projects_router
app.include_router(projects_router, prefix="/api/v1/projects", tags=["Projects"])

# ── Bankability Cockpit v2.0 ──
if HAS_WORKFLOW:
    app.include_router(routes_workflow.router, prefix="/api/v1/workflow", tags=["Bankability — Workflow State Management"])

if HAS_TIMELINE:
    app.include_router(routes_timeline.router, prefix="/api/v1/timeline", tags=["Bankability — Funding Timeline"])

if HAS_REPORTS:
    app.include_router(routes_reports.router, prefix="/api/v1/reports", tags=["Bankability — Report Assembly"])

if HAS_PERFORMANCE:
    app.include_router(routes_performance.router, prefix="/api/v1/performance", tags=["Bankability — Performance Matrix"])

if HAS_IC_PACK:
    app.include_router(routes_ic_pack.router, prefix="/api/v1/ic-pack", tags=["Bankability — IC Pack Assembly"])

if HAS_DATA_ROOM:
    app.include_router(routes_data_room.router, prefix="/api/v1/data-room", tags=["Bankability — Virtual Data Room"])

if HAS_TERMS:
    app.include_router(routes_terms.router, prefix="/api/v1/terms", tags=["Bankability — Term Sheet Tracker"])

if HAS_ADVERSARIAL_REVIEWS:
    app.include_router(routes_adversarial_reviews.router, prefix="/api/v1", tags=["Adversarial Reviews"])

# ── Development Packages + Pre-COD Metrics + Additionality (Bridge Doc v3.0) ──
if HAS_DEV_PACKAGES:
    app.include_router(dev_packages_router, tags=["Development Packages"])

if HAS_PRE_COD_METRICS:
    app.include_router(pre_cod_router, tags=["Pre-COD Metrics"])

if HAS_ENTITLEMENTS:
    app.include_router(entitlements_router, prefix="/api/v1/entitlements", tags=["Finance Entitlements"])

if HAS_ADDITIONALITY:
    app.include_router(additionality_router, tags=["DFI Additionality"])

if HAS_CAPITAL_BRIDGE:
    app.include_router(capital_bridge_router, tags=["Capital Bridge (multi-fuel)"])

# ── Spend Wave + Drawdown Schedule (Bridge Doc v4.1) ──
if HAS_SPEND_WAVE:
    app.include_router(spend_wave_router, tags=["Spend Wave"])

if HAS_DRAWDOWN:
    app.include_router(drawdown_router, tags=["Drawdown Schedule"])

# ── DFI Criteria + Evidence Ledger + Lineage + Adjacency ──
if HAS_DFI_CRITERIA:
    app.include_router(dfi_criteria_router, tags=["DFI Criteria"])

if HAS_EVIDENCE_LEDGER:
    app.include_router(evidence_ledger_router, tags=["Evidence Ledger"])

if HAS_TEA_BRIDGE:
    app.include_router(tea_bridge_router, prefix="/api/v1/tea", tags=["TEA Engine Bridge"])

if HAS_NBA:
    app.include_router(nba_router, prefix="/api/v1/nba", tags=["Next Best Action"])

if HAS_CORPUS:
    app.include_router(corpus_router, prefix="/api/v1/corpus", tags=["External Corpus"])

if HAS_LINEAGE:
    app.include_router(lineage_router, tags=["Lineage Synthesis"])

if HAS_ADJACENCY:
    app.include_router(adjacency_router, tags=["Adjacency Benchmark"])

if HAS_MASS_BALANCE:
    app.include_router(mass_balance_router, tags=["Mass Balance Ledger"])

# ── Settlement + Carbon Attribution + Sovereign Instruments (B4) ──
if HAS_SETTLEMENTS:
    app.include_router(settlement_router, tags=["Settlement Events"])

if HAS_CARBON_ATTR:
    app.include_router(carbon_attr_router, tags=["Carbon Attribution"])

if HAS_SOVEREIGN:
    app.include_router(sovereign_router, tags=["Sovereign Instruments"])

# ── Event Bus ──
if HAS_EVENTS_ROUTER:
    app.include_router(events_router)

# ── Deal Structuring Workbench v5.0 ──
if HAS_STRUCTURING:
    app.include_router(structuring_router)

if HAS_INSTRUMENTS:
    app.include_router(instruments_router)

if HAS_DEMAND:
    app.include_router(demand_router)

if HAS_RISK_PRICING:
    app.include_router(risk_pricing_router)

if HAS_PRICING_PROXY:
    app.include_router(routes_pricing_proxy.router, prefix="/api/v1/pricing", tags=["Pricing Proxy"])

if HAS_PLANT_BUILDER:
    app.include_router(plant_builder_router, prefix="/api/v1/plant-builder", tags=["Plant Builder — CAPEX/OPEX Engine"])


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
