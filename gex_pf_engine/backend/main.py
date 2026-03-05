"""
GEX Project Finance Engine - Main Application
Microservice for financial calculations, CFADS, waterfall, and covenant monitoring
Runs on port 8001
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_model
from app.api.routes_bankability import router as bankability_router


# Create FastAPI app
app = FastAPI(
    title="GEX Project Finance Engine",
    description="Financial modeling, CFADS, waterfall, and covenant monitoring for green fuel projects",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(
    routes_model.router,
    prefix="/api/v1/model",
    tags=["Financial Model"]
)
# Bankability router for bankability assessments and related endpoints.
app.include_router(
    bankability_router, 
    prefix="/api/v1/bankability", 
    tags=["Bankability"]
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "GEX Project Finance Engine",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "project-finance-engine"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
