# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io
import os

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus
from app.database.dependencies import get_current_active_user, get_admin_user
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Form to add a new asset."""
    # Get dropdown options from Google Sheets
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_user,
            "dropdown_options": dropdown_options
        }
    )

@router.post("/add")
async def add_asset(
    request: Request,
    item_name: str = Form(...),
    category: str = Form(...),
    type: str = Form(...),
    manufacture: str = Form(None),
    model: str = Form(None),
    serial_number: str = Form(None),
    company: str = Form(...),
    bisnis_unit: str = Form(None),
    location: str = Form(...),
    room: str = Form(...),
    notes: str = Form(None),
    item_condition: str = Form(None),
    purchase_date: str = Form(...),
    purchase_cost: str = Form(...),
    warranty: str = Form(None),
    supplier: str = Form(None),
    journal: str = Form(None),
    owner: str = Form(...),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process add asset form."""
    # Get dropdown options for form redisplay if needed
    dropdown_options = get_dropdown_options()
    
    # Prepare asset data for Google Sheets
    asset_data = {
        "Item Name": item_name,
        "Category": category,
        "Type": type,
        "Manufacture": manufacture or "",
        "Model": model or "",
        "Serial Number": serial_number or "",
        "Company": company,
        "Bisnis Unit": bisnis_unit or "",
        "Location": location,
        "Room": room,
        "Notes": notes or "",
        "Item Condition": item_condition or "",
        "Purchase Date": purchase_date,
        "Purchase Cost": purchase_cost,
        "Warranty": warranty or "",
        "Supplier": supplier or "",
        "Journal": journal or "",
        "Owner": owner,
        "Status": "Active"
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
                # We'll use a placeholder asset_id since we don't have the ID yet
                # In a real implementation, you might want to update this later
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            # Log error and continue without photo
            print(f"Error processing photo: {str(e)}")
    
    # If admin, add asset directly to Google Sheets
    if current_user.role == UserRole.ADMIN:
        success = sheets_add_asset(asset_data)
        
        if success:
            response = RedirectResponse(url="/assets/", status_code=status.HTTP_303_SEE_OTHER)
            set_flash(response, "Asset added successfully", "success")
            return response
        else:
            return templates.TemplateResponse(
                "asset_management/add.html",
                {
                    "request": request,
                    "user": current_user,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # If staff, create approval request
    approval = Approval(
        action_type="add",
        request_data=json.dumps(asset_data),
        requester_id=current_user.id,
        status=ApprovalStatus.PENDING
    )
    
    db.add(approval)
    db.commit()
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    set_flash(response, "Asset request submitted for approval", "success")
    return response