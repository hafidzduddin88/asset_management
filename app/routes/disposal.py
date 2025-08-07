# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_admin_user
from app.utils.database_manager import get_all_assets, update_asset
from app.utils.flash import set_flash

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    # Debug: check all statuses
    statuses = [str(asset.get('Status', '')).strip() for asset in all_assets]
    print(f"All statuses found: {set(statuses)}")
    
    disposable_assets = []
    for asset in all_assets:
        status = str(asset.get('Status', '')).strip()
        if status in ['To Be Disposed', 'To be Disposed', 'TO BE DISPOSED']:
            disposable_assets.append(asset)
    
    return templates.TemplateResponse(
        "disposal/index.html",
        {
            "request": request,
            "user": current_profile,
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
    current_profile = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.database_manager import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if str(asset.get('Status', '')).strip() != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.database_manager import add_approval_request
    
    approval_data = {
        'type': 'disposal',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'disposal_reason': disposal_reason,
        'disposal_method': disposal_method,
        'notes': f"Description: {description or ''} | Notes: {notes or ''}"
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('Item Name', '')} submitted for manager approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response