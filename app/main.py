from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os

from app.config import load_config
from app.database.database import engine, Base
from app.routes import (
    home, assets, asset_management, approvals, 
    login, damage, export, health, offline, relocation, profile
)
from app.middleware.session_auth import SessionAuthMiddleware
from app.utils.flash import FlashMiddleware

# Create tables (only for users and approvals)
Base.metadata.create_all(bind=engine)

# Import dan jalankan seed script untuk membuat user default
from app.database.seed import create_admin_user, create_manager_user, create_staff_user
create_admin_user()
create_manager_user()
create_staff_user()

# Load configuration
config = load_config()

# Initialize FastAPI app
app = FastAPI(
    title="Asset Management Business Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session authentication middleware
app.add_middleware(SessionAuthMiddleware)

# Flash messages middleware
app.add_middleware(FlashMiddleware)

# Include routers
app.include_router(health.router)
app.include_router(home.router)
app.include_router(login.router)
app.include_router(assets.router)
app.include_router(asset_management.router)
app.include_router(approvals.router)
app.include_router(damage.router)
app.include_router(export.router)
app.include_router(offline.router)
app.include_router(relocation.router)
app.include_router(profile.router)

# Service worker route
@app.get("/service-worker.js", response_class=HTMLResponse)
async def get_service_worker():
    with open("app/static/service-worker.js") as f:
        return f.read()

# Manifest route
@app.get("/manifest.json", response_class=HTMLResponse)
async def get_manifest():
    with open("app/static/manifest.json") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)