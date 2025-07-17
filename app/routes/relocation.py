# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import Asset, User, Relocation, Approval, ApprovalStatus
from app.database.dependencies import get_current_active_user, get_admin_user

router = APIRouter(tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets/{asset_id}/relocate", response_class=HTMLResponse)
async def relocate_form(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to relocate an asset."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        "relocation/form.html",
        {
            "request": request,
            "user": current_user,
            "asset": asset
        }
    )

@router.post("/assets/{asset_id}/relocate")
async def relocate_asset(
    request: Request,
    asset_id: int,
    new_location: str = Form(...),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process asset relocation form."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Check if new location is different
    if asset.location == new_location:
        return templates.TemplateResponse(
            "relocation/form.html",
            {
                "request": request,
                "user": current_user,
                "asset": asset,
                "error": "New location must be different from current location",
                "form_data": {
                    "new_location": new_location,
                    "reason": reason
                }
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Prepare relocation data
    relocation_data = {
        "asset_id": asset_id,
        "previous_location": asset.location,
        "new_location": new_location,
        "relocated_by": current_user.id,
        "relocation_date": datetime.utcnow(),
        "reason": reason
    }
    
    # If admin, relocate asset directly
    if current_user.role == "admin":
        # Create relocation record
        relocation = Relocation(**relocation_data)
        db.add(relocation)
        
        # Update asset location
        asset.location = new_location
        
        db.commit()
        return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    
    # If staff, create approval request
    approval = Approval(
        action_type="relocate",
        asset_id=asset_id,
        request_data=json.dumps(relocation_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)