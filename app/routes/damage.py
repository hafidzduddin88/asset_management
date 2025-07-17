# app/routes/damage.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import Asset, User, Damage, Approval, ApprovalStatus, AssetStatus
from app.database.dependencies import get_current_active_user, get_admin_user
from app.utils.photo import upload_photo_to_drive
from app.config import load_config

config = load_config()
router = APIRouter(tags=["damage"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets/{asset_id}/report-damage", response_class=HTMLResponse)
async def report_damage_form(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to report asset damage."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
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
    asset_id: int,
    description: str = Form(...),
    damage_date: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process damage report form."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Prepare damage data
    damage_data = {
        "asset_id": asset_id,
        "reported_by": current_user.id,
        "description": description,
        "damage_date": datetime.strptime(damage_date, "%Y-%m-%d")
    }
    
    # Handle photo upload
    photo_url = None
    if photo:
        try:
            _, photo_url = await upload_photo_to_drive(
                photo, 
                f"{asset.asset_tag}_damage_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
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
    
    # If admin, create damage report directly and update asset status
    if current_user.role == "admin":
        damage = Damage(**damage_data)
        db.add(damage)
        
        # Update asset status
        asset.status = AssetStatus.DAMAGED
        
        db.commit()
        return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    
    # If staff, create approval request
    approval = Approval(
        action_type="damage",
        asset_id=asset_id,
        request_data=json.dumps(damage_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/assets/{asset_id}/repair", response_class=HTMLResponse)
async def repair_form(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to report asset repair."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset or asset.status != AssetStatus.DAMAGED:
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
    
    # Get latest damage report
    damage = (
        db.query(Damage)
        .filter(Damage.asset_id == asset_id, Damage.is_repaired == False)
        .order_by(Damage.damage_date.desc())
        .first()
    )
    
    return templates.TemplateResponse(
        "damage/repair.html",
        {
            "request": request,
            "user": current_user,
            "asset": asset,
            "damage": damage
        }
    )

@router.post("/assets/{asset_id}/repair")
async def repair_asset(
    request: Request,
    asset_id: int,
    repair_notes: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process repair form."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset or asset.status != AssetStatus.DAMAGED:
        raise HTTPException(status_code=404, detail="Asset not found or not damaged")
    
    # Get latest damage report
    damage = (
        db.query(Damage)
        .filter(Damage.asset_id == asset_id, Damage.is_repaired == False)
        .order_by(Damage.damage_date.desc())
        .first()
    )
    
    if not damage:
        raise HTTPException(status_code=404, detail="No damage report found")
    
    # Prepare repair data
    repair_data = {
        "damage_id": damage.id,
        "repair_notes": repair_notes,
        "repair_date": datetime.utcnow()
    }
    
    # If admin, update damage and asset status directly
    if current_user.role == "admin":
        damage.is_repaired = True
        damage.repair_date = datetime.utcnow()
        damage.repair_notes = repair_notes
        
        # Update asset status
        asset.status = AssetStatus.REPAIRED
        
        db.commit()
        return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)
    
    # If staff, create approval request
    approval = Approval(
        action_type="repair",
        asset_id=asset_id,
        request_data=json.dumps(repair_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    return RedirectResponse(url=f"/assets/{asset_id}", status_code=status.HTTP_303_SEE_OTHER)