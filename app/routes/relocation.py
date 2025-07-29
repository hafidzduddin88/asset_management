# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_profile
from app.utils.sheets import get_all_assets, get_dropdown_options, add_approval_request
from app.utils.flash import set_flash

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Asset relocation page."""
    # Get assets and dropdown options
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "relocation/index.html",
        {
            "request": request,
            "user": current_profile,
            "assets": all_assets,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Submit asset relocation request."""
    from app.utils.sheets import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create relocation approval request
    relocation_data = {
        'new_location': new_location,
        'new_room': new_room,
        'current_location': asset.get('Location', ''),
        'current_room': asset.get('Room', ''),
        'reason': reason,
        'notes': notes or ''
    }
    
    approval_data = {
        'type': 'relocation',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Relocate from {asset.get('Location', '')} - {asset.get('Room', '')} to {new_location} - {new_room}",
        'request_data': json.dumps(relocation_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Relocation request for {asset.get('Item Name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/relocation", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting relocation request", "error")
        return response