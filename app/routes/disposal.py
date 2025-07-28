# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_admin_user
from app.utils.sheets import get_all_assets, update_asset, add_disposal_log
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that can be disposed (not already disposed)
    all_assets = get_all_assets()
    disposable_assets = [asset for asset in all_assets if asset.get('Status') != 'Disposed']
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_user,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.get('Status') == 'Disposed':
        raise HTTPException(status_code=400, detail="Asset already disposed")
    
    # Add to disposal log
    disposal_data = {
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'description': description or '',
        'requested_by': current_user.username,
        'request_date': datetime.now().strftime('%Y-%m-%d'),
        'disposal_date': datetime.now().strftime('%Y-%m-%d'),
        'disposed_by': current_user.username,
        'notes': notes or ''
    }
    
    log_success = add_disposal_log(disposal_data)
    
    # Update asset status to Disposed
    update_success = update_asset(asset_id, {'Status': 'Disposed'})
    
    if log_success and update_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Asset {asset.get('Item Name', '')} disposed successfully", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error disposing asset", "error")
        return response