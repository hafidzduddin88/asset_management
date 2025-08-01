# app/routes/asset_management.py
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import io

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.photo import resize_and_convert_image, upload_to_drive
from app.utils.database_manager import get_dropdown_options, add_asset as db_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_profile, get_admin_user
from app.config import load_config
import logging

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    return templates.TemplateResponse(
        "asset_management/add.html",
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """List assets for editing (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import get_all_assets
    assets = get_all_assets()
    
    locations = list(set(asset.get('Location', '') for asset in assets if asset.get('Location')))
    location_rooms = {}
    for asset in assets:
        location = asset.get('Location', '')
        room = asset.get('Room', '')
        if location and room:
            if location not in location_rooms:
                location_rooms[location] = set()
            location_rooms[location].add(room)
    
    for location in location_rooms:
        location_rooms[location] = list(location_rooms[location])
    
    return templates.TemplateResponse(
        "asset_management/list.html",
        {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "locations": sorted(locations),
            "location_rooms": location_rooms
        }
    )


@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.utils.sheets import get_asset_by_id
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse(
        "asset_management/edit.html",
        {
            "request": request,
            "user": current_profile,
            "asset": asset,
            "dropdown_options": dropdown_options
        }
    )


@router.post("/edit/{asset_id}")
async def update_asset(
    asset_id: str,
    request: Request,
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.utils.sheets import update_asset as sheets_update_asset, calculate_asset_financials, get_asset_by_id
    asset = get_asset_by_id(asset_id)

    update_data = {
        "Status": status,
        "Company": company,
        "Location": location,
        "Room": room,
        "Bisnis Unit": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('Item Name', ''),
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Edit asset: {asset.get('Item Name', '')} - Reason: {edit_reason}",
        'edit_reason': edit_reason,
        'request_data': json.dumps(update_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/edit.html",
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
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
    current_profile = Depends(get_current_profile)
):
    """Process add asset form."""
    dropdown_options = get_dropdown_options()
    
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
    
    photo_url = None
    if photo and photo.filename:
        try:
            contents = await photo.read()
            image_file = io.BytesIO(contents)
            processed_image = resize_and_convert_image(image_file)
            
            if processed_image:
                photo_url = upload_to_drive(processed_image, photo.filename, "new")
                if photo_url:
                    asset_data["Photo URL"] = photo_url
        except Exception as e:
            print(f"Error processing photo: {str(e)}")
    
    # All roles now require approval
    from app.utils.sheets import add_approval_request
    
    # Determine approval type based on user role
    if current_profile.role == UserRole.ADMIN:
        approval_type = "admin_add_asset"  # Admin needs manager approval
        logging.info(f"Admin {current_profile.email} submitting asset for manager approval: {asset_data.get('Item Name')}")
    else:
        approval_type = "add_asset"  # Manager/Staff need admin approval
        logging.info(f"{current_profile.role.value} {current_profile.email} submitting asset for admin approval: {asset_data.get('Item Name')}")
    
    from app.utils.sheets import add_approval_request
    
    approval_data = {
        'type': 'add_asset',
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_data = {
        'type': approval_type,
        'asset_id': 'NEW',
        'asset_name': item_name,
        'submitted_by': current_profile.full_name or current_profile.email,
        'submitted_date': datetime.now().strftime('%Y-%m-%d'),
        'description': f"Add new asset: {item_name}",
        'request_data': json.dumps(asset_data, ensure_ascii=False)
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        if current_profile.role == UserRole.ADMIN:
            approver = "Manager"
            approval_msg = "manager approval"
        else:
            approver = "Admin"
            approval_msg = "admin approval"
        
        logging.info(f"Asset approval request submitted for {approval_msg}: {asset_data.get('Item Name')}")
        
        # Show confirmation page instead of redirect
        return templates.TemplateResponse(
            "asset_management/confirmation.html",
            {
                "request": request,
                "user": current_profile,
                "asset_name": item_name,
                "approver": approver,
                "message": f"Asset registration has been received and is waiting for approval from {approver}"
            }
        )
    else:
        logging.error(f"Failed to submit approval request for: {asset_data.get('Item Name')}")
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Error submitting approval request",
                "form_data": asset_data
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )