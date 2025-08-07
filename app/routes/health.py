# app/routes/health.py
from fastapi import APIRouter
import time

router = APIRouter(tags=["health"])

@router.get("/health")
@router.head("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": time.time()}

@router.get("/wake")
@router.head("/wake")
async def wake_up():
    """Wake up endpoint for keeping service alive."""
    return {"status": "awake", "timestamp": time.time()}