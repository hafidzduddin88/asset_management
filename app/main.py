from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.middleware.session_auth import SessionAuthMiddleware
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Asset Management System")

# Add middleware
app.add_middleware(SessionAuthMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Health check first for readiness probe
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/wake")
async def wake_up():
    return {"status": "awake"}

# Root redirect
@app.get("/")
async def root():
    return {"message": "Asset Management System"}

# Lazy load routes on startup
@app.on_event("startup")
async def startup_event():
    from app.routes import (
        login, health, offline, home, assets, asset_management,
        damage, profile, repair, approvals, disposal, user_management,
        logs, relocation, reset_password, auth_callback
    )
    
    # Include all routers
    app.include_router(login.router)
    app.include_router(health.router)
    app.include_router(offline.router)
    app.include_router(home.router)
    app.include_router(assets.router)
    app.include_router(asset_management.router)
    app.include_router(damage.router)
    app.include_router(profile.router)
    app.include_router(repair.router)
    app.include_router(approvals.router)
    app.include_router(disposal.router)
    app.include_router(user_management.router)
    app.include_router(logs.router)
    app.include_router(relocation.router)
    app.include_router(reset_password.router)
    app.include_router(auth_callback.router)
    
    logger.info("All routes loaded successfully")

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)