from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.database.dependencies import get_current_user
from app.utils.sheets import get_all_assets, get_asset_statistics, get_valid_asset_statuses, invalidate_cache, get_chart_data, ensure_serializable
from app.utils.flash import get_flash

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Auto-refresh interval in milliseconds (60 seconds)
AUTO_REFRESH_INTERVAL = 60000

@router.get("/", response_class=HTMLResponse)
@router.head("/", response_class=HTMLResponse)
@router.get("/home", response_class=HTMLResponse)
@router.head("/home", response_class=HTMLResponse)
async def home(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page / Dashboard."""
    try:
        assets = get_all_assets()
        statistics = get_asset_statistics() or {}
        status_counts = statistics.get('status_counts', {})
        financial_summary = statistics.get('financial_summary', {})

        total_assets = len(assets)
        active_assets = status_counts.get('Active', 0)
        under_repair_assets = status_counts.get('Under Repair', 0)
        in_storage_assets = status_counts.get('In Storage', 0)
        to_be_disposed_assets = status_counts.get('To Be Disposed', 0)
        disposed_assets = status_counts.get('Disposed', 0)
        
        # Get pre-formatted chart data that is guaranteed to be JSON serializable
        chart_data = get_chart_data()
        status_chart_data = chart_data['status_chart_data']
        category_chart_data = chart_data['category_chart_data']
        location_chart_data = chart_data['location_chart_data']
        monthly_chart_data = chart_data['monthly_chart_data']

        flash = get_flash(request)
        return templates.TemplateResponse(
            "dashboard_modern.html",
            {
                "request": request,
                "user": current_user,
                "assets": assets,
                "total_assets": total_assets,
                "active_assets": active_assets,
                "under_repair_assets": under_repair_assets,
                "in_storage_assets": in_storage_assets,
                "to_be_disposed_assets": to_be_disposed_assets,
                "disposed_assets": disposed_assets,
                "status_counts": status_counts,
                "status_chart_data": status_chart_data,
                "category_chart_data": category_chart_data,
                "location_chart_data": location_chart_data,
                "monthly_chart_data": monthly_chart_data,
                "financial_summary": financial_summary,
                "flash": flash,
                "auto_refresh_interval": AUTO_REFRESH_INTERVAL
            }
        )
    except Exception as e:
        # Default chart data (empty) to prevent template error
        empty_chart_data = {
            "labels": [],
            "values": [],
            "colors": []
        }
        return templates.TemplateResponse(
            "dashboard_modern.html",
            {
                "request": request,
                "user": current_user,
                "assets": [],
                "total_assets": 0,
                "active_assets": 0,
                "under_repair_assets": 0,
                "in_storage_assets": 0,
                "to_be_disposed_assets": 0,
                "disposed_assets": 0,
                "status_counts": {},
                "category_counts": {},
                "location_counts": {},
                "monthly_data": {},
                "financial_summary": {},
                "status_chart_data": empty_chart_data,
                "category_chart_data": empty_chart_data,
                "location_chart_data": empty_chart_data,
                "monthly_chart_data": empty_chart_data,
                "flash": f"Something went wrong: {str(e)}",
                "auto_refresh_interval": AUTO_REFRESH_INTERVAL
            },
            status_code=500
        )

@router.get("/refresh-data", response_class=JSONResponse)
async def refresh_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh data from Google Sheets by invalidating cache."""
    try:
        # Invalidate all cache to force refresh from Google Sheets
        invalidate_cache()
        
        # Get fresh data
        assets = get_all_assets()
        statistics = get_asset_statistics()
        status_counts = statistics['status_counts']
        chart_data = get_chart_data()
        
        # Return basic stats for updating the UI
        response_data = {
            "success": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_assets": len(assets),
            "status_counts": status_counts,
            "status_chart_data": chart_data['status_chart_data'],
            "category_chart_data": chart_data['category_chart_data'],
            "location_chart_data": chart_data['location_chart_data'],
            "financial_summary": statistics['financial_summary']
        }
        
        # Ensure all data is JSON serializable
        return ensure_serializable(response_data)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error refreshing data: {str(e)}\n{error_details}")
        return {"success": False, "error": str(e)}