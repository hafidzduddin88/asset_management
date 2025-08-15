from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.auth import get_current_profile
from app.utils.flash import set_flash
from starlette.templating import Jinja2Templates
import logging

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

router = APIRouter()

@router.get("/repair", response_class=HTMLResponse)
async def repair_page(request: Request, asset_id: int = None, current_profile = Depends(get_current_profile)):
    """Display repair form for assets with Under Repair status"""
    try:
        supabase = get_supabase()
        
        # Get assets with "Under Repair" status
        assets_response = supabase.table('assets').select('''
            asset_id, asset_name, asset_tag, status,
            ref_categories(category_name),
            ref_locations(location_name, room_name),
            ref_companies(company_name),
            ref_business_units(business_unit_name)
        ''').eq('status', 'Under Repair').execute()
        
        assets = assets_response.data if assets_response.data else []
        
        # Get damage information for the asset if asset_id is provided
        damage_info = None
        if asset_id:
            damage_response = supabase.table('damage_log').select('*').eq('asset_id', asset_id).order('created_at', desc=True).limit(1).execute()
            if damage_response.data:
                damage_info = damage_response.data[0]
        
        # Get locations for dropdown
        locations_response = supabase.table('ref_locations').select('*').execute()
        locations = locations_response.data if locations_response.data else []
        
        template_path = get_template(request, "repair/index.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "assets": assets,
            "selected_asset_id": asset_id,
            "damage_info": damage_info,
            "locations": locations
        })
        
    except Exception as e:
        logger.error(f"Error loading repair page: {str(e)}")
        flash_message(request, f"Error loading repair page: {str(e)}", "error")
        return RedirectResponse(url="/", status_code=302)

@router.post("/repair/submit")
async def submit_repair(
    request: Request,
    asset_id: int = Form(...),
    location_id: int = Form(...),
    room_name: str = Form(""),
    repair_notes: str = Form(""),
    current_profile = Depends(get_current_profile)
):
    """Submit repair completion"""
    try:
        supabase = get_supabase()
        
        # Get asset details
        asset_response = supabase.table('assets').select('asset_name').eq('asset_id', asset_id).execute()
        if not asset_response.data:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        asset_name = asset_response.data[0]['asset_name']
        
        # Get location details
        location_response = supabase.table('ref_locations').select('location_name').eq('location_id', location_id).execute()
        location_name = location_response.data[0]['location_name'] if location_response.data else "Unknown"
        
        # Create approval request
        approval_data = {
            "type": "repair",
            "asset_id": asset_id,
            "asset_name": asset_name,
            "submitter_id": current_profile.user_id,
            "submitter_name": current_profile.full_name or current_profile.username,
            "submitter_role": current_profile.role,
            "status": "pending",
            "details": {
                "asset_id": asset_id,
                "asset_name": asset_name,
                "new_location_id": location_id,
                "new_location_name": location_name,
                "new_room_name": room_name,
                "repair_notes": repair_notes
            }
        }
        
        # Determine approval requirements based on submitter role
        if current_profile.role in ['staff', 'manager']:
            approval_data["requires_admin_approval"] = True
            approval_data["requires_manager_approval"] = False
        elif current_profile.role == 'admin':
            approval_data["requires_admin_approval"] = False
            approval_data["requires_manager_approval"] = True
        
        # Insert approval request
        supabase.table('approvals').insert(approval_data).execute()
        
        flash_message(request, f"Repair completion for {asset_name} submitted for approval", "success")
        return RedirectResponse(url="/repair", status_code=302)
        
    except Exception as e:
        logger.error(f"Error submitting repair: {str(e)}")
        flash_message(request, f"Error submitting repair: {str(e)}", "error")
        return RedirectResponse(url="/repair", status_code=302)

@router.get("/repair/locations/{location_id}")
async def get_location_rooms(location_id: int):
    """API endpoint to get rooms for a location"""
    try:
        supabase = get_supabase()
        response = supabase.table('ref_locations').select('room_name').eq('location_id', location_id).execute()
        
        rooms = []
        if response.data:
            rooms = [{"room_name": loc['room_name']} for loc in response.data if loc['room_name']]
        
        return {"rooms": rooms}
        
    except Exception as e:
        logger.error(f"Error getting location rooms: {str(e)}")
        return {"rooms": []}