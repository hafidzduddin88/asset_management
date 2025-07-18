# app/routes/damage.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.utils.sheets import get_asset_by_id, update_asset
from app.database.dependencies import get_current_active_user, get_admin_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.flash import set_flash
from app.config import load_config

config = load_config()
router = APIRouter(tags=["damage"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets/{asset_id}/report-damage", response_class=HTMLResponse)
async def report_damage_form(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to report asset damage."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        "damage/report.html",
        {
            "request": request,
            "user": current_user,
            "asset": asset
        }
    )

@router.post("/assets/{asset_id}/report-damage")
async def report_damage(
    request: Request,
    asset_id: str,
    description: str = Form(...),
    damage_date: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process damage report form."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Prepare damage data
    damage_data = {
        "asset_id": asset_id,
        "asset_tag": asset.get("Asset Tag", ""),
        "reported_by": current_user.username,
        "description": description,
        "damage_date": damage_date
    }
    
    # Handle photo upload
    photo_url = None
    if photo and photo.filename:
        try:
            # Process image
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                # Upload to Google Drive
                photo_url = upload_to_drive(
                    processed_image, 
                    photo.filename, 
                    f"damage_{asset.get('Asset Tag', '')}"
                )
                if photo_url:
                    damage_data["photo_url"] = photo_url
        except Exception as e:
            return templates.TemplateResponse(
                "damage/report.html",
                {
                    "request": request,
                    "user": current_user,
                    "asset": asset,
                    "error": f"Error uploading photo: {str(e)}",
                    "form_data": {
                        "description": description,
                        "damage_date": damage_date
                    }
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If admin, update asset status directly in Google Sheets
    if current_user.role == UserRole.ADMIN:
        # Update asset status to Damaged
        update_data = {"Status": "Damaged"}
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset marked as damaged", "success")
            return response
        else:
            return templates.TemplateResponse(
                "damage/report.html",
                {
                    "request": request,
                    "user": current_user,
                    "asset": asset,
                    "error": "Error updating asset status",
                    "form_data": {
                        "description": description,
                        "damage_date": damage_date
                    }
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If staff, create approval request
    approval = Approval(
        action_type="damage",
        request_data=json.dumps(damage_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Damage report submitted for approval", "success")
    return response

@router.get("/assets/{asset_id}/repair", response_class=HTMLResponse)
async def repair_form(
    request: Request,
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to report asset repair."""
    asset = get_asset_by_id(asset_id)
    if not asset or asset.get("Status") != "Damaged":
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        "damage/repair.html",
        {
            "request": request,
            "user": current_user,
            "asset": asset
        }
    )

@router.post("/assets/{asset_id}/repair")
async def repair_asset(
    request: Request,
    asset_id: str,
    repair_notes: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process repair form."""
    asset = get_asset_by_id(asset_id)
    if not asset or asset.get("Status") != "Damaged":
        raise HTTPException(status_code=404, detail="Asset not found or not damaged")
    
    # Prepare repair data
    repair_data = {
        "asset_id": asset_id,
        "asset_tag": asset.get("Asset Tag", ""),
        "repair_notes": repair_notes,
        "repair_date": datetime.now().strftime("%Y-%m-%d"),
        "repaired_by": current_user.username
    }
    
    # If admin, update asset status directly in Google Sheets
    if current_user.role == UserRole.ADMIN:
        # Update asset status to Repaired
        update_data = {"Status": "Repaired"}
        success = update_asset(asset_id, update_data)
        
        if success:
            response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset marked as repaired", "success")
            return response
        else:
            return templates.TemplateResponse(
                "damage/repair.html",
                {
                    "request": request,
                    "user": current_user,
                    "asset": asset,
                    "error": "Error updating asset status",
                    "form_data": {
                        "repair_notes": repair_notes
                    }
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If staff, create approval request
    approval = Approval(
        action_type="repair",
        request_data=json.dumps(repair_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    response = RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Repair request submitted for approval", "success")
    return response