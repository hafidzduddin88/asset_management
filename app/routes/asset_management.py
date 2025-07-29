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
from app.utils.sheets import get_dropdown_options, add_asset as sheets_add_asset
from app.utils.flash import set_flash
from app.utils.auth import get_current_user, get_admin_user
from app.config import load_config

config = load_config()
router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_user)
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
    current_profile = Depends(get_current_user)
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
    current_profile = Depends(get_current_user)
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
    current_profile = Depends(get_current_user)
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
    current_profile = Depends(get_current_user)
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
    
    if current_profile.role == UserRole.ADMIN:
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
                    "user": current_profile,
                    "dropdown_options": dropdown_options,
                    "error": "Error adding asset to Google Sheets",
                    "form_data": asset_data
                },
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
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
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset request submitted for approval", "success")
        return response
    else:
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