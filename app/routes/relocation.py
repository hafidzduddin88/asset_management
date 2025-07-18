# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.utils.sheets import get_asset_by_id, update_asset
from app.utils.flash import set_flash
from app.database.dependencies import get_current_active_user, get_admin_user

router = APIRouter(tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets/{asset_id}/relocate", response_class=HTMLResponse)
async def relocate_form(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to relocate an asset."""
    asset = get_asset_by_id(asset_id)
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
    asset_id: str,
    new_location: str = Form(...),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process asset relocation form."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Check if new location is different
    if asset.get('Location') == new_location:
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
        "asset_tag": asset.get('Asset Tag', ''),
        "previous_location": asset.get('Location', ''),
        "new_location": new_location,
        "relocated_by": current_user.username,
        "relocation_date": datetime.now().strftime("%Y-%m-%d"),
        "reason": reason
    }
    
    # If admin, relocate asset directly in Google Sheets
    if current_user.role == UserRole.ADMIN:
        # Update asset location
        update_data = {"Location": new_location}
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset relocated successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "relocation/form.html",
                {
                    "request": request,
                    "user": current_user,
                    "asset": asset,
                    "error": "Error updating asset location",
                    "form_data": {
                        "new_location": new_location,
                        "reason": reason
                    }
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If staff, create approval request
    approval = Approval(
        action_type="relocate",
        request_data=json.dumps(relocation_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Relocation request submitted for approval", "success")
    return response