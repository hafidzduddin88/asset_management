# app/routes/relocation.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json

from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_assets, get_dropdown_options, add_approval_request, get_asset_by_id
from app.utils.device_detector import get_template

router = APIRouter(prefix="/relocation", tags=["relocation"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def relocation_page(
    request: Request,
    asset_id: int = Query(None),
    current_profile = Depends(get_current_profile)
):
    """Handle relocation requests with asset_id parameter."""
    if asset_id:
        # Get asset data
        asset = get_asset_by_id(asset_id)
        if not asset:
            return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
        
        # Get dropdown options for locations
        dropdown_options = get_dropdown_options()
        
        template_path = get_template(request, "relocation/form.html")
        return templates.TemplateResponse(
            template_path,
            {
                "request": request,
                "user": current_profile,
                "asset": asset,
                "dropdown_options": dropdown_options
            }
        )
    else:
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/success", response_class=HTMLResponse)
async def relocation_success(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Display relocation success page."""
    template_path = get_template(request, "relocation/success.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile
        }
    )

@router.get("/error", response_class=HTMLResponse)
async def relocation_error(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Display relocation error page."""
    template_path = get_template(request, "relocation/error.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile
        }
    )

@router.post("/relocate/{asset_id}")
async def relocate_asset(
    asset_id: str,
    request: Request,
    new_location: str = Form(...),
    new_room: str = Form(...),
    reason: str = Form(...),
    notes: str = Form(None),
    current_profile = Depends(get_current_profile)
):
    """Submit asset relocation request."""
    try:
        # Get asset data
        asset = get_asset_by_id(asset_id)
        if not asset:
            return RedirectResponse(url="/relocation/error", status_code=status.HTTP_303_SEE_OTHER)
        
        # Create relocation approval request
        relocation_data = {
            'new_location': new_location,
            'new_room': new_room,
            'current_location': asset.get('ref_locations', {}).get('location_name', '') if asset.get('ref_locations') else '',
            'current_room': asset.get('ref_locations', {}).get('room_name', '') if asset.get('ref_locations') else asset.get('room_name', ''),
            'reason': reason,
            'notes': notes or ''
        }
        
        # Get current and new location_id
        from app.utils.database_manager import get_supabase
        supabase = get_supabase()
        
        # Current location_id from asset
        current_location_id = asset.get('location_id')
        
        # New location_id
        new_loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', new_location).eq('room_name', new_room).execute()
        new_location_id = new_loc_response.data[0]['location_id'] if new_loc_response.data else None
        
        approval_data = {
            'type': 'relocation',
            'asset_id': int(asset_id),
            'asset_name': asset.get('asset_name', ''),
            'submitted_by': current_profile.id,
            'status': 'pending',
            'description': f"Relocate from {asset.get('ref_locations', {}).get('location_name', '') if asset.get('ref_locations') else ''} - {asset.get('ref_locations', {}).get('room_name', '') if asset.get('ref_locations') else asset.get('room_name', '')} to {new_location} - {new_room}",
            'to_location_id': new_location_id,
            'notes': json.dumps(relocation_data)
        }
        
        approval_success = add_approval_request(approval_data)
        
        if approval_success:
            return RedirectResponse(url="/relocation/success", status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse(url="/relocation/error", status_code=status.HTTP_303_SEE_OTHER)
    
    except Exception as e:
        return RedirectResponse(url="/relocation/error", status_code=status.HTTP_303_SEE_OTHER)