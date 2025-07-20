# app/routes/storage.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_current_active_user
from app.utils.sheets import get_asset_by_id, update_asset, get_dropdown_options
from app.utils.flash import get_flash, set_flash

router = APIRouter(prefix="/storage", tags=["storage"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/{asset_id}", response_class=HTMLResponse)
async def move_to_storage(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Move an asset to storage."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can move assets to storage.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        # Get dropdown options for locations
        dropdown_options = get_dropdown_options()
        
        # Get flash messages
        flash = get_flash(request)
        
        return templates.TemplateResponse(
            "storage/move_to_storage.html",
            {
                "request": request,
                "user": current_user,
                "asset": asset,
                "locations": dropdown_options['locations'],
                "flash": flash
            }
        )
    except Exception as e:
        logging.error(f"Error in move_to_storage: {str(e)}")
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error loading storage form: {str(e)}", "error")
        return response

@router.post("/{asset_id}", response_class=HTMLResponse)
async def process_move_to_storage(
    request: Request,
    asset_id: str,
    notes: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process moving an asset to storage."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can move assets to storage.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        # Update asset status and location
        update_data = {
            'Status': 'In Storage',
            'Location': 'HO - Ciputat',
            'Room': '1022 - Gudang Support TOG',
            'Notes': f"{asset.get('Notes', '')} | Moved to storage: {notes}"
        }
        
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset successfully moved to storage.", "success")
            return response
        else:
            response = RedirectResponse(url=f"/storage/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Failed to move asset to storage.", "error")
            return response
    except Exception as e:
        logging.error(f"Error in process_move_to_storage: {str(e)}")
        response = RedirectResponse(url=f"/storage/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error moving asset to storage: {str(e)}", "error")
        return response