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

# Removed get_dashboard_data function as it's no longer needed

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
@router.get("/dashboard", response_class=HTMLResponse)
async def home(
    request: Request, 
    year: str = None,
    category: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page / Dashboard."""
    try:
        # Get assets data
        assets = get_all_assets()
        
        # Get available years from assets
        years = set()
        categories = set()
        for asset in assets:
            if asset.get('Purchase Date'):
                try:
                    asset_year = datetime.strptime(asset.get('Purchase Date'), '%Y-%m-%d').year
                    years.add(str(asset_year))
                except:
                    pass
            if asset.get('Category'):
                categories.add(asset.get('Category'))
        
        years = sorted(list(years), reverse=True)
        categories = sorted(list(categories))
        
        # Get chart data with filters
        chart_data = get_chart_data(year, category)
        
        # Calculate total assets based on filtered data
        total_assets = sum(chart_data['status_counts'].values())
        
        # Get flash messages
        flash = get_flash(request)
        
        # Prepare template context
        context = {
            "request": request,
            "user": current_user,
            "flash": flash,
            "total_assets": total_assets,
            "status_counts": chart_data['status_counts'],
            "category_counts": chart_data['category_counts'],
            "company_counts": chart_data['company_counts'],
            "location_chart_data": chart_data['location_chart_data'],
            "monthly_chart_data": chart_data['monthly_chart_data'],
            "years": years,
            "categories": categories,
            "year": year,
            "category": category
        }
        
        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
        logging.error(f"Dashboard error: {str(e)}", exc_info=True)
        
        # Prepare error context
        error_context = {
            "request": request,
            "user": current_user,
            "total_assets": 0,
            "status_counts": {},
            "category_counts": {},
            "company_counts": {},
            "location_chart_data": {"labels": [], "values": []},
            "monthly_chart_data": {"labels": [], "values": []},
            "years": [],
            "categories": [],
            "year": None,
            "category": None,
            "flash": f"Something went wrong: {str(e)}"
        }
        
        return templates.TemplateResponse("dashboard.html", error_context, status_code=500)

@router.get("/refresh-data", response_class=JSONResponse)
async def refresh_data(
    request: Request,
    year: str = None,
    category: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Refresh data from Google Sheets by invalidating cache."""
    try:
        # Invalidate all cache to force refresh from Google Sheets
        invalidate_cache()
        
        # Get fresh data with filters
        chart_data = get_chart_data(year, category)
        
        # Calculate total assets based on filtered data
        total_assets = sum(chart_data['status_counts'].values())
        
        # Return basic stats for updating the UI
        response_data = {
            "success": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_assets": total_assets,
            "status_counts": chart_data['status_counts'],
            "category_counts": chart_data['category_counts'],
            "company_counts": chart_data['company_counts'],
            "location_chart_data": chart_data['location_chart_data'],
            "monthly_chart_data": chart_data['monthly_chart_data']
        }
        
        # Ensure all data is JSON serializable
        # Convert dict_values to lists for JSON serialization
        for key in ['status_counts', 'category_counts', 'company_counts']:
            if key in response_data:
                response_data[key] = {k: v for k, v in response_data[key].items()}
                
        # Ensure chart data is properly serializable
        if 'location_chart_data' in response_data:
            if isinstance(response_data['location_chart_data'].get('values'), type(dict.values)):
                response_data['location_chart_data']['values'] = list(response_data['location_chart_data']['values'])
                
        if 'monthly_chart_data' in response_data:
            if isinstance(response_data['monthly_chart_data'].get('values'), type(dict.values)):
                response_data['monthly_chart_data']['values'] = list(response_data['monthly_chart_data']['values'])
        
        return response_data
    except Exception as e:
        logging.error(f"Error refreshing data: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}