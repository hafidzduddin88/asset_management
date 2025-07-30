# app/routes/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import time

from app.database.database import get_db
from app.config import load_config

router = APIRouter(tags=["health"])
config = load_config()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    start_time = time.time()
    
    # Check database connection
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Google Sheets API
    sheets_status = "configured" if config.GOOGLE_SHEET_ID else "not configured"
    
    # Response time
    response_time = time.time() - start_time
    
    return {
        "status": "ok",
        "database": db_status,
        "google_sheets": sheets_status,
        "response_time_ms": round(response_time * 1000, 2)
    }

@router.get("/wake")
async def wake_up():
    """Wake up endpoint for keeping service alive."""
    return {"status": "awake", "timestamp": time.time()}