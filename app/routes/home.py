from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.database.dependencies import get_current_user
from app.utils.sheets import get_all_assets, get_asset_statistics, get_valid_asset_statuses, invalidate_cache
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
    
    # Get assets from Google Sheets
    assets = get_all_assets()
    
    # Get asset statistics for charts
    statistics = get_asset_statistics()
    valid_statuses = get_valid_asset_statuses()
    
    # Get dashboard stats
    total_assets = len(assets)
    status_counts = statistics['status_counts']
    active_assets = status_counts.get('Active', 0)
    under_repair_assets = status_counts.get('Under Repair', 0)
    in_storage_assets = status_counts.get('In Storage', 0)
    to_be_disposed_assets = status_counts.get('To Be Disposed', 0)
    disposed_assets = status_counts.get('Disposed', 0)
    
    # Prepare chart data
    status_chart_data = {
        'labels': list(status_counts.keys()),
        'values': list(status_counts.values()),
        'colors': [
            '#10B981',  # Active - green
            '#EF4444',  # Under Repair - red
            '#3B82F6',  # In Storage - blue
            '#F59E0B',  # To Be Disposed - yellow
            '#6B7280',  # Disposed - gray
            '#8B5CF6'   # Other - purple
        ]
    }
    
    category_chart_data = {
        'labels': list(statistics['category_counts'].keys()),
        'values': list(statistics['category_counts'].values()),
    }
    
    location_chart_data = {
        'labels': list(statistics['location_counts'].keys()),
        'values': list(statistics['location_counts'].values()),
    }
    
    # Monthly additions chart
    monthly_data = statistics['monthly_additions']
    sorted_months = sorted(monthly_data.keys())
    monthly_chart_data = {
        'labels': [month.split('-')[1] + '/' + month.split('-')[0][2:] for month in sorted_months],
        'values': [monthly_data[month] for month in sorted_months]
    }
    
    # Financial summary
    financial_summary = statistics['financial_summary']
    
    # Get pending approvals (for admins)
    pending_approvals = []
    if current_user.role == UserRole.ADMIN:
        pending_approvals = (
            db.query(Approval)
            .filter(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.created_at.desc())
            .limit(5)
            .all()
        )
    
    # Get recent assets (sort by ID in reverse to get newest first)
    recent_assets = sorted(assets, key=lambda x: x.get('ID', '0'), reverse=True)[:5]
    
    # Get flash messages
    flash = get_flash(request)
    
    return templates.TemplateResponse(
        "dashboard_modern.html",
        {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "active_assets": active_assets,
            "under_repair_assets": under_repair_assets,
            "in_storage_assets": in_storage_assets,
            "to_be_disposed_assets": to_be_disposed_assets,
            "disposed_assets": disposed_assets,
            "pending_approvals": pending_approvals,
            "recent_assets": recent_assets,
            "flash": flash,
            "status_chart_data": status_chart_data,
            "category_chart_data": category_chart_data,
            "location_chart_data": location_chart_data,
            "monthly_chart_data": monthly_chart_data,
            "financial_summary": financial_summary,
            "valid_statuses": valid_statuses,
            "auto_refresh_interval": AUTO_REFRESH_INTERVAL
        },
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
        
        # Return basic stats for updating the UI
        return {
            "success": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_assets": len(assets),
            "status_counts": status_counts,
            "status_chart_data": {
                'labels': list(status_counts.keys()),
                'values': list(status_counts.values()),
            },
            "category_chart_data": {
                'labels': list(statistics['category_counts'].keys()),
                'values': list(statistics['category_counts'].values()),
            },
            "location_chart_data": {
                'labels': list(statistics['location_counts'].keys()),
                'values': list(statistics['location_counts'].values()),
            },
            "financial_summary": statistics['financial_summary']
        }
    except Exception as e:
        logging.error(f"Error refreshing data: {str(e)}")
        return {"success": False, "error": str(e)}