# app/routes/assets.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
import logging

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_current_active_user
from app.utils.sheets import get_all_assets, get_asset_by_id, get_dropdown_options, get_valid_asset_statuses
from app.utils.flash import get_flash

router = APIRouter(prefix="/assets", tags=["assets"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def list_assets(
    request: Request,
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List assets with optional filtering."""
    # Get all assets from Google Sheets
    all_assets = get_all_assets()
    
    # Apply filters
    filtered_assets = all_assets
    
    if status:
        filtered_assets = [a for a in filtered_assets if a.get('Status') == status]
    if category:
        filtered_assets = [a for a in filtered_assets if a.get('Category') == category]
    if location:
        filtered_assets = [a for a in filtered_assets if a.get('Location') == location]
    if search:
        search = search.lower()
        filtered_assets = [a for a in filtered_assets if 
            search in str(a.get('Item Name', '')).lower() or
            search in str(a.get('Asset Tag', '')).lower() or
            search in str(a.get('Notes', '')).lower() or
            search in str(a.get('Serial Number', '')).lower()
        ]
        
    # Pagination
    ITEMS_PER_PAGE = 20
    total_items = len(filtered_assets)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Ceiling division
    
    # Ensure page is within valid range
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
        
    # Calculate start and end indices for current page
    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    
    # Get assets for current page
    paginated_assets = filtered_assets[start_idx:end_idx]
    
    # Get dropdown options for filters
    dropdown_options = get_dropdown_options()
    
    # Get valid asset statuses
    asset_statuses = get_valid_asset_statuses()
    
    # Get flash messages
    flash = get_flash(request)
    
    return templates.TemplateResponse(
        "assets/list.html",
        {
            "request": request,
            "user": current_user,
            "assets": paginated_assets,
            "categories": dropdown_options['categories'],
            "locations": list(dropdown_options['locations'].keys()),
            "statuses": list(asset_statuses.keys()),
            "status_descriptions": asset_statuses,
            "selected_status": status,
            "selected_category": category,
            "selected_location": location,
            "search": search,
            "flash": flash,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "items_per_page": ITEMS_PER_PAGE
        }
    )

@router.get("/{asset_id}", response_class=HTMLResponse)
async def asset_detail(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Asset detail page."""
    try:
        # Log for debugging
        logging.info(f"Fetching asset details for ID: {asset_id}")
        
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            logging.warning(f"Asset with ID {asset_id} not found, redirecting to assets list")
            return RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
        
        # Get flash messages
        flash = get_flash(request)
        
        # Log success
        logging.info(f"Successfully retrieved asset: {asset.get('Item Name')}")
        
        return templates.TemplateResponse(
            "assets/detail.html",
            {
                "request": request,
                "user": current_user,
                "asset": asset,
                "flash": flash
            }
        )
    except Exception as e:
        # Log error
        logging.error(f"Error in asset_detail: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Redirect to assets list with error message
        response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
        from app.utils.flash import set_flash
        set_flash(response, f"Error loading asset details: {str(e)}", "error")
        return response