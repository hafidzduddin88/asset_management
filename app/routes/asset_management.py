from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException, status
from app.utils.photo import upload_to_drive
import io
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import json
from datetime import datetime
import uuid

from app.utils.database_manager import get_dropdown_options, add_approval_request, get_all_assets, get_asset_by_id
from app.utils.flash import set_flash
from app.utils.auth import get_current_profile, UserRole
from app.utils.device_detector import get_template
import logging

router = APIRouter(prefix="/asset_management", tags=["asset_management"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/add", response_class=HTMLResponse)
async def add_asset_form(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Form to add a new asset."""
    dropdown_options = get_dropdown_options()
    from app.utils.database_manager import get_next_asset_id
    next_asset_id = get_next_asset_id()
    
    template_path = get_template(request, "asset_management/add.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "dropdown_options": dropdown_options,
            "next_asset_id": next_asset_id
        }
    )


@router.get("/list", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """List assets with advanced filtering and management features."""
    assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    template_path = get_template(request, "asset_management/list.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_user": current_profile,
            "assets": assets,
            "dropdown_options": dropdown_options
        }
    )


@router.get("/view/{asset_id}", response_class=HTMLResponse)
async def view_asset(
    asset_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """View asset details."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    template_path = get_template(request, "asset_management/view.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "asset": asset
        }
    )

@router.get("/edit/{asset_id}", response_class=HTMLResponse)
async def edit_asset_form(
    asset_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Form to edit an existing asset (admin/manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")

    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    dropdown_options = get_dropdown_options()
    
    template_path = get_template(request, "asset_management/edit.html")
    return templates.TemplateResponse(
        template_path,
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
    asset_name: str = Form(...),
    manufacture: str = Form(""),
    model: str = Form(""),
    serial_number: str = Form(""),
    purchase_cost: float = Form(...),
    journal: str = Form(""),
    photo: UploadFile = File(None),
    status: str = Form(...),
    company: str = Form(...),
    location: str = Form(...),
    room: str = Form(...),
    bisnis_unit: str = Form(None),
    edit_reason: str = Form(...),
    current_profile = Depends(get_current_profile)
):
    """Update existing asset (admin and manager only)."""
    if current_profile.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    asset = get_asset_by_id(asset_id)

    # Handle photo upload
    photo_url = asset.get('photo_url', '')  # Keep existing photo by default
    if photo and photo.filename:
        try:
            contents = await photo.read()
            new_photo_url = upload_to_drive(contents, photo.filename, asset_id)
            if new_photo_url:
                photo_url = new_photo_url
        except Exception as e:
            logging.error(f"Error uploading photo: {str(e)}")

    update_data = {
        "asset_name": asset_name,
        "manufacture": manufacture,
        "model": model,
        "serial_number": serial_number,
        "purchase_cost": purchase_cost,
        "journal": journal,
        "photo_url": photo_url,
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
        'description': f"Edit asset: {asset_name} - Reason: {edit_reason}",
        'notes': json.dumps(update_data)
    }
    
    # Role-based approval will be handled in approvals page filtering
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management/list", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Asset edit request submitted for manager approval", "success")
        return response
    else:
        dropdown_options = get_dropdown_options()
        template_path = get_template(request, "asset_management/edit.html")
        return templates.TemplateResponse(
            template_path,
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options,
                "error": "Error submitting edit request"
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get("/success", response_class=HTMLResponse)
async def add_asset_success(
    request: Request,
    asset_id: str = None,
    asset_name: str = None,
    current_profile = Depends(get_current_profile)
):
    """Success page for asset registration."""
    template_path = get_template(request, "asset_management/success.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile,
            "asset_id": asset_id,
            "asset_name": asset_name
        }
    )


@router.get("/error", response_class=HTMLResponse)
async def add_asset_error(
    request: Request,
    asset_id: str = None,
    asset_name: str = None,
    current_profile = Depends(get_current_profile)
):
    """Error page for asset registration."""
    template_path = get_template(request, "asset_management/error.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile,
            "asset_id": asset_id,
            "asset_name": asset_name
        }
    )


@router.post("/add")
async def add_asset(
    request: Request,
    asset_id: int = Form(...),
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
        "asset_id": asset_id,
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
        "status": "In Storage" if location_name == "HO - Ciputat" and room_name == "1022 - Gudang Support TOG" else "Active"
    }
    
    # Handle photo upload
    if photo and photo.filename:
        try:
            contents = await photo.read()
            # Use asset_name as identifier since asset_id doesn't exist yet
            photo_url = upload_to_drive(contents, photo.filename, asset_name.replace(" ", "_"))
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
        return RedirectResponse(url=f"/asset_management/success?asset_id={asset_id}&asset_name={asset_name}", status_code=status.HTTP_303_SEE_OTHER)
    else:
        return RedirectResponse(url=f"/asset_management/error?asset_id={asset_id}&asset_name={asset_name}", status_code=status.HTTP_303_SEE_OTHER)
