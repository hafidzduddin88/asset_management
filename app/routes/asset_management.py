from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from app.utils.photo import upload_to_drive
import io
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime
import uuid

from app.database.database import get_db
from app.database.models import Profile, UserRole
from app.utils.database_manager import get_dropdown_options, add_approval_request, get_all_assets, get_asset_by_id
from app.utils.flash import set_flash
from app.utils.auth import get_current_profile
import logging

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
    
    assets = get_all_assets()
    
    locations = list(set(asset.get('ref_locations', {}).get('location_name', '') for asset in assets if asset.get('ref_locations')))
    location_rooms = {}
    for asset in assets:
        location_data = asset.get('ref_locations', {})
        location = location_data.get('location_name', '') if isinstance(location_data, dict) else ''
        room = location_data.get('room_name', '') if isinstance(location_data, dict) else ''
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
    
    asset = get_asset_by_id(asset_id)

    update_data = {
        "status": status,
        "company_name": company,
        "location_name": location,
        "room_name": room,
        "business_unit_name": bisnis_unit or ""
    }
    
    # Jika perlu hitung ulang nilai finansial, misalnya setelah perubahan harga
    # financials = calculate_asset_financials(purchase_cost, purchase_date, category)
    # update_data.update(financials)
    
    approval_data = {
        'type': 'edit_asset',
        'asset_id': asset_id,
        'asset_name': asset.get('asset_name', ''),
        'submitted_by': current_profile.id,
        'status': 'pending',
        'description': f"Edit asset: {asset.get('asset_name', '')} - Reason: {edit_reason}",
        'notes': json.dumps(update_data)
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
    asset_name: str = Form(...),
    category_name: str = Form(...),
    type_name: str = Form(...),
    manufacture: str = Form(""),
    model: str = Form(""),
    serial_number: str = Form(""),
    company_name: str = Form(...),
    business_unit_name: str = Form(""),
    location_name: str = Form(...),
    room_name: str = Form(...),
    notes: str = Form(""),
    item_condition: str = Form(""),
    purchase_date: str = Form(...),
    purchase_cost: float = Form(...),
    warranty: str = Form(""),
    supplier: str = Form(""),
    journal: str = Form(""),
    owner_name: str = Form(...),
    photo: UploadFile = File(None),
    current_profile = Depends(get_current_profile)
):
    """Process add asset form."""
    asset_data = {
        "asset_id": str(uuid.uuid4()),
        "asset_name": asset_name,
        "category_name": category_name,
        "type_name": type_name,
        "manufacture": manufacture,
        "model": model,
        "serial_number": serial_number,
        "company_name": company_name,
        "business_unit_name": business_unit_name,
        "location_name": location_name,
        "room_name": room_name,
        "notes": notes,
        "item_condition": item_condition,
        "purchase_date": purchase_date,
        "purchase_cost": purchase_cost,
        "warranty": warranty,
        "supplier": supplier,
        "journal": journal,
        "owner_name": owner_name,
        "status": "Active" if location_name != "HO - Ciputat" or room_name != "1022 - Gudang Support TOG" else "In Storage"
    }
    
    # Handle photo upload
    if photo and photo.filename:
        try:
            contents = await photo.read()
            photo_url = upload_to_drive(contents, photo.filename, asset_data["asset_id"])
            if photo_url:
                asset_data["photo_url"] = photo_url
        except Exception as e:
            logging.error(f"Error uploading photo: {str(e)}")
    
    # Get to_location_id for new asset placement
    from app.utils.database_manager import get_supabase
    supabase = get_supabase()
    loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', location_name).eq('room_name', room_name).execute()
    to_location_id = loc_response.data[0]['location_id'] if loc_response.data else None
    
    approval_data = {
        "type": "add_asset",
        "asset_name": asset_name,
        "submitted_by": current_profile.id,
        "status": "pending",
        "description": f"Add new asset: {asset_name}",
        "to_location_id": to_location_id,
        "notes": json.dumps(asset_data)
    }
    
    if add_approval_request(approval_data):
        return templates.TemplateResponse(
            "asset_management/confirmation.html",
            {
                "request": request,
                "user": current_profile,
                "asset_name": asset_name,
                "message": "Asset registration submitted for approval"
            }
        )
    else:
        dropdown_options = get_dropdown_options()
        return templates.TemplateResponse(
            "asset_management/add.html",
            {
                "request": request,
                "user": current_profile,
                "dropdown_options": dropdown_options,
                "error": "Failed to submit asset registration"
            }
        )