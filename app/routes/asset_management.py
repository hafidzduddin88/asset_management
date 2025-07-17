# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import os

from app.database.database import get_db
from app.database.models import Asset, User, Approval, ApprovalStatus
from app.database.dependencies import get_current_active_user, get_admin_user
from app.utils.photo import upload_photo_to_drive
from app.config import load_config

config = load_config()
router = APIRouter(tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/asset/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to add a new asset."""
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_user
        }
    )

@router.post("/asset/add")
async def add_asset(
    request: Request,
    name: str = Form(...),
    asset_tag: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    location: str = Form(...),
    purchase_date: str = Form(None),
    purchase_cost: str = Form(None),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process add asset form."""
    # Check if asset tag already exists
    existing_asset = db.query(Asset).filter(Asset.asset_tag == asset_tag).first()
    if existing_asset:
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_user,
                "error": "Asset tag already exists",
                "form_data": {
                    "name": name,
                    "asset_tag": asset_tag,
                    "description": description,
                    "category": category,
                    "location": location,
                    "purchase_date": purchase_date,
                    "purchase_cost": purchase_cost
                }
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    
    # Prepare asset data
    asset_data = {
        "name": name,
        "asset_tag": asset_tag,
        "description": description,
        "category": category,
        "location": location,
        "purchase_cost": purchase_cost
    }
    
    if purchase_date:
        asset_data["purchase_date"] = datetime.strptime(purchase_date, "%Y-%m-%d")
    
    # Handle photo upload if admin
    photo_url = None
    photo_drive_id = None
    
    if current_user.role == "admin" and photo:
        try:
            photo_drive_id, photo_url = await upload_photo_to_drive(photo, asset_tag)
            asset_data["photo_url"] = photo_url
            asset_data["photo_drive_id"] = photo_drive_id
        except Exception as e:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_user,
                    "error": f"Error uploading photo: {str(e)}",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If admin, create asset directly
    if current_user.role == "admin":
        new_asset = Asset(**asset_data, owner_id=current_user.id)
        db.add(new_asset)
        db.commit()
        db.refresh(new_asset)
        return RedirectResponse(url=f"/assets/{new_asset.id}", status_code=status.HTTP_303_SEE_OTHER)
    
    # If staff, create approval request
    approval = Approval(
        action_type="add",
        request_data=json.dumps(asset_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)