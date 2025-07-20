# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_current_active_user
from app.utils.sheets import get_asset_by_id, update_asset
from app.utils.flash import get_flash, set_flash

router = APIRouter(tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets/{asset_id}/mark-to-dispose", response_class=HTMLResponse)
async def mark_to_dispose(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Mark an asset as To Be Disposed."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can mark assets for disposal.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        # Get flash messages
        flash = get_flash(request)
        
        return templates.TemplateResponse(
            "disposal/mark_to_dispose.html",
            {
                "request": request,
                "user": current_user,
                "asset": asset,
                "flash": flash
            }
        )
    except Exception as e:
        logging.error(f"Error in mark_to_dispose: {str(e)}")
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error loading disposal form: {str(e)}", "error")
        return response

@router.post("/assets/{asset_id}/mark-to-dispose", response_class=HTMLResponse)
async def process_mark_to_dispose(
    request: Request,
    asset_id: str,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process marking an asset as To Be Disposed."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can mark assets for disposal.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        # Update asset status
        update_data = {
            'Status': 'To Be Disposed',
            'Notes': f"{asset.get('Notes', '')} | Marked for disposal: {reason}"
        }
        
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset successfully marked for disposal.", "success")
            return response
        else:
            response = RedirectResponse(url=f"/assets/{asset_id}/mark-to-dispose", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Failed to mark asset for disposal.", "error")
            return response
    except Exception as e:
        logging.error(f"Error in process_mark_to_dispose: {str(e)}")
        response = RedirectResponse(url=f"/assets/{asset_id}/mark-to-dispose", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error marking asset for disposal: {str(e)}", "error")
        return response

@router.get("/assets/{asset_id}/dispose", response_class=HTMLResponse)
async def dispose_asset(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Dispose of an asset."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can dispose of assets.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        if asset.get('Status') != 'To Be Disposed':
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset must be marked for disposal before it can be disposed.", "error")
            return response
        
        # Get flash messages
        flash = get_flash(request)
        
        return templates.TemplateResponse(
            "disposal/dispose.html",
            {
                "request": request,
                "user": current_user,
                "asset": asset,
                "flash": flash
            }
        )
    except Exception as e:
        logging.error(f"Error in dispose_asset: {str(e)}")
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error loading disposal form: {str(e)}", "error")
        return response

@router.post("/assets/{asset_id}/dispose", response_class=HTMLResponse)
async def process_dispose_asset(
    request: Request,
    asset_id: str,
    disposal_date: str = Form(...),
    disposal_reason: str = Form(...),
    disposal_notes: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process disposing of an asset."""
    if current_user.role != 'admin':
        response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Only administrators can dispose of assets.", "error")
        return response
    
    try:
        # Get asset by ID
        asset = get_asset_by_id(asset_id)
        
        if not asset:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, f"Asset with ID {asset_id} not found.", "error")
            return response
        
        # Update asset status
        update_data = {
            'Status': 'Disposed',
            'Disposal Date': disposal_date,
            'Disposal Reason': disposal_reason,
            'Disposed By': current_user.username,
            'Notes': f"{asset.get('Notes', '')} | Disposed: {disposal_notes}"
        }
        
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset successfully disposed.", "success")
            return response
        else:
            response = RedirectResponse(url=f"/assets/{asset_id}/dispose", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Failed to dispose of asset.", "error")
            return response
    except Exception as e:
        logging.error(f"Error in process_dispose_asset: {str(e)}")
        response = RedirectResponse(url=f"/assets/{asset_id}/dispose", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Error disposing of asset: {str(e)}", "error")
        return response