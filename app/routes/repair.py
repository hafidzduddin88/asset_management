from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.auth import get_current_profile
from app.utils.flash import set_flash
from starlette.templating import Jinja2Templates
import logging
import json

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

router = APIRouter()

@router.get("/repair", response_class=HTMLResponse)
async def repair_page(request: Request, asset_id: int = None, current_profile = Depends(get_current_profile)):
    """Display repair completion form for specific asset with Under Repair status"""
    from fastapi import HTTPException
    
    if not asset_id:
        raise HTTPException(status_code=400, detail="Asset ID is required")
    
    try:
        supabase = get_supabase()
        
        # Get specific asset with Under Repair status
        asset_response = supabase.table('assets').select('''
            asset_id, asset_name, asset_tag, status,
            ref_categories(category_name),
            ref_locations(location_name, room_name)
        ''').eq('asset_id', asset_id).eq('status', 'Under Repair').execute()
        
        if not asset_response.data:
            raise HTTPException(status_code=404, detail="Asset not found or not under repair")
        
        asset = asset_response.data[0]
        
        # Get damage information for the asset
        damage_info = None
        damage_response = supabase.table('damage_log').select('*').eq('asset_id', asset_id).order('created_at', desc=True).limit(1).execute()
        if damage_response.data:
            damage_info = damage_response.data[0]
        
        # Get locations and rooms for dropdown (same format as relocation)
        locations_response = supabase.table('ref_locations').select('location_name, room_name').execute()
        dropdown_options = {'locations': {}}
        
        for location in locations_response.data if locations_response.data else []:
            location_name = location['location_name']
            room_name = location['room_name']
            
            if location_name not in dropdown_options['locations']:
                dropdown_options['locations'][location_name] = []
            
            if room_name and room_name not in dropdown_options['locations'][location_name]:
                dropdown_options['locations'][location_name].append(room_name)
        
        template_path = get_template(request, "repair/form.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile,
            "asset": asset,
            "damage_info": damage_info,
            "dropdown_options": dropdown_options
        })
        
    except Exception as e:
        logger.error(f"Error loading repair page: {str(e)}")
        response = RedirectResponse(url="/asset_management/list", status_code=302)
        set_flash(response, f"Error loading repair page: {str(e)}", "error")
        return response

@router.post("/repair/submit")
async def submit_repair(
    request: Request,
    asset_id: int = Form(...),
    new_location: str = Form(...),
    new_room: str = Form(...),
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
        
        # Use location and room names directly
        location_name = new_location
        room_name = new_room
        
        # Get new location_id
        location_response = supabase.table('ref_locations').select('location_id').eq('location_name', location_name).eq('room_name', room_name).execute()
        new_location_id = location_response.data[0]['location_id'] if location_response.data else None
        
        # Get current location_id
        current_asset = supabase.table('assets').select('location_id').eq('asset_id', asset_id).execute()
        current_location_id = current_asset.data[0]['location_id'] if current_asset.data else None
        
        # Create approval request
        approval_data = {
            "type": "repair",
            "asset_id": asset_id,
            "asset_name": asset_name,
            "submitted_by": current_profile.id,
            "status": "pending",
            "description": f"Repair completion for {asset_name}",
            "from_location_id": int(current_location_id) if current_location_id else None,
            "to_location_id": int(new_location_id) if new_location_id else None,
            "notes": json.dumps({
                "new_location": location_name,
                "new_room": room_name,
                "repair_notes": repair_notes
            })
        }
        
        # Role-based approval will be handled in approvals page filtering
        
        # Insert approval request
        supabase.table('approvals').insert(approval_data).execute()
        
        response = RedirectResponse(url="/repair", status_code=302)
        set_flash(response, f"Repair completion for {asset_name} submitted for approval", "success")
        return response
        
    except Exception as e:
        logger.error(f"Error submitting repair: {str(e)}")
        response = RedirectResponse(url="/repair", status_code=302)
        set_flash(response, f"Error submitting repair: {str(e)}", "error")
        return response

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