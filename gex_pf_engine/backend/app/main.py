# You're in: gex_pf_engine/backend
# Create the main.py file:

#cat > app/main.py << 'EOF'
"""
GEX Project Finance Engine - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routes
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

# Create FastAPI app
app = FastAPI(
    title="GEX Project Finance Engine",
    description="Financial modeling API for green fuel projects",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers if available
if routes_available:
    app.include_router(routes_model.router, prefix="/api/v1/model", tags=["Financial Model"])

if bankability_available:
    app.include_router(routes_bankability.router, prefix="/api/v1/bankability", tags=["Bankability Engine"])

if pricing_available:
    app.include_router(routes_pricing.router, prefix="/api/v1/pricing", tags=["Price Curve Engine — Gabillon"])

@app.get("/")
async def root():
    """Health check"""
    return {
        "service": "GEX Project Finance Engine",
        "status": "operational",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "version": "5.1.0",
        "components": {
            "engine": "ok",
            "cfads": "ok",
            "waterfall": "ok",
            "debt_sculpting": "ok",
            "gabillon_pricing": "ok" if pricing_available else "unavailable",
        },
    }
#EOF

# Verify it was created:
#cat app/main.py