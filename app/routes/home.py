from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.database.dependencies import get_current_user
from app.utils.sheets import get_all_assets, get_asset_statistics, get_valid_asset_statuses, invalidate_cache, get_chart_data
from app.utils.flash import get_flash

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Auto-refresh interval in milliseconds (60 seconds)
AUTO_REFRESH_INTERVAL = 60000

# Maximum number of recent assets to display
MAX_RECENT_ASSETS = 5

# Dashboard sections configuration
DASHBOARD_SECTIONS = {
    "overview": True,
    "charts": True,
    "lifecycle": True,
    "recent_assets": True,
    "pending_approvals": True,
    "financial_summary": True
}

def get_dashboard_data(db: Session, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Prepare all data needed for the dashboard in a structured format.
    
    Args:
        db: Database session
        assets: List of assets from Google Sheets
        
    Returns:
        Dictionary containing all dashboard data
    """
    # Get asset statistics
    statistics = get_asset_statistics() or {}
    status_counts = statistics.get('status_counts', {})
    financial_summary = statistics.get('financial_summary', {})
    
    # Calculate asset counts
    total_assets = len(assets)
    active_assets = status_counts.get('Active', 0)
    under_repair_assets = status_counts.get('Under Repair', 0)
    in_storage_assets = status_counts.get('In Storage', 0)
    to_be_disposed_assets = status_counts.get('To Be Disposed', 0)
    disposed_assets = status_counts.get('Disposed', 0)
    
    # Get chart data
    chart_data = get_chart_data()
    
    # Get recent assets (sort by ID in reverse to get newest first)
    recent_assets = sorted(assets, key=lambda x: x.get('ID', '0'), reverse=True)[:MAX_RECENT_ASSETS]
    
    # Return structured dashboard data
    return {
        "assets": assets,
        "total_assets": total_assets,
        "active_assets": active_assets,
        "under_repair_assets": under_repair_assets,
        "in_storage_assets": in_storage_assets,
        "to_be_disposed_assets": to_be_disposed_assets,
        "disposed_assets": disposed_assets,
        "status_counts": status_counts,
        "status_chart_data": chart_data['status_chart_data'],
        "category_chart_data": chart_data['category_chart_data'],
        "location_chart_data": chart_data['location_chart_data'],
        "monthly_chart_data": chart_data['monthly_chart_data'],
        "financial_summary": financial_summary,
        "recent_assets": recent_assets,
        "sections": DASHBOARD_SECTIONS,
        "auto_refresh_interval": AUTO_REFRESH_INTERVAL
    }

def get_pending_approvals(db: Session, user: User) -> List[Approval]:
    """
    Get pending approvals for admin users.
    
    Args:
        db: Database session
        user: Current user
        
    Returns:
        List of pending approvals or empty list if user is not admin
    """
    if user.role != UserRole.ADMIN:
        return []
        
    return (
        db.query(Approval)
        .filter(Approval.status == ApprovalStatus.PENDING)
        .order_by(Approval.created_at.desc())
        .limit(MAX_RECENT_ASSETS)
        .all()
    )

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
        # Get assets data
        assets = get_all_assets()
        
        # Get dashboard data
        dashboard_data = get_dashboard_data(db, assets)
        
        # Get pending approvals for admin users
        pending_approvals = get_pending_approvals(db, current_user)
        
        # Get flash messages
        flash = get_flash(request)
        
        # Prepare template context
        context = {
            "request": request,
            "user": current_user,
            "pending_approvals": pending_approvals,
            "flash": flash,
            **dashboard_data  # Unpack all dashboard data
        }
        
        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
        logging.error(f"Dashboard error: {str(e)}", exc_info=True)
        
        # Default chart data (empty) to prevent template error
        empty_chart_data = {
            "labels": [],
            "values": [],
            "colors": []
        }
        
        # Prepare error context
        error_context = {
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
            "status_chart_data": empty_chart_data,
            "category_chart_data": empty_chart_data,
            "location_chart_data": empty_chart_data,
            "monthly_chart_data": empty_chart_data,
            "financial_summary": {},
            "recent_assets": [],
            "pending_approvals": [],
            "sections": DASHBOARD_SECTIONS,
            "flash": f"Something went wrong: {str(e)}",
            "auto_refresh_interval": AUTO_REFRESH_INTERVAL
        }
        
        return templates.TemplateResponse("dashboard.html", error_context, status_code=500)

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
        dashboard_data = get_dashboard_data(db, assets)
        
        # Return basic stats for updating the UI
        response_data = {
            "success": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_assets": dashboard_data["total_assets"],
            "status_counts": dashboard_data["status_counts"],
            "status_chart_data": dashboard_data["status_chart_data"],
            "category_chart_data": dashboard_data["category_chart_data"],
            "location_chart_data": dashboard_data["location_chart_data"],
            "financial_summary": dashboard_data["financial_summary"]
        }
        
        # Ensure all data is JSON serializable
        # Convert dict_values to lists for JSON serialization
        if 'status_chart_data' in response_data and 'values' in response_data['status_chart_data']:
            response_data['status_chart_data']['values'] = list(response_data['status_chart_data']['values'])
        if 'category_chart_data' in response_data and 'values' in response_data['category_chart_data']:
            response_data['category_chart_data']['values'] = list(response_data['category_chart_data']['values'])
        if 'location_chart_data' in response_data and 'values' in response_data['location_chart_data']:
            response_data['location_chart_data']['values'] = list(response_data['location_chart_data']['values'])
        
        return response_data
    except Exception as e:
        logging.error(f"Error refreshing data: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}