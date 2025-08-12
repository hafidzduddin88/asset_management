# app/routes/repair.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_supabase
from app.utils.device_detector import get_template
from app.utils.flash import set_flash
from fastapi.responses import JSONResponse
import logging

router = APIRouter(prefix="/repair", tags=["repair"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def repair_page(request: Request, current_profile=Depends(get_current_profile)):
    """Repair asset page - accessible by all users"""
    try:
        supabase = get_supabase()
        
        # Get assets with "Under Repair" status from assets table
        assets_response = supabase.table("assets").select('''
            asset_id, asset_name, status,
            ref_categories(category_name),
            ref_locations(location_name, room_name)
        ''').eq('status', 'Under Repair').execute()
        
        # Get corresponding damage records for these assets
        damaged_assets = []
        if assets_response.data:
            asset_ids = [asset['asset_id'] for asset in assets_response.data]
            damaged_response = supabase.table("damage_log").select('''
                damage_id, asset_id, asset_name, damage_type, severity, description,
                reported_by_name, created_at, status
            ''').in_('asset_id', asset_ids).eq('status', 'approved').execute()
            
            damaged_assets = damaged_response.data or []
        
        template_path = get_template(request, "repair/index.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "damaged_assets": damaged_assets
        })
        
    except Exception as e:
        logging.error(f"Error loading repair page: {e}")
        template_path = get_template(request, "repair/index.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "damaged_assets": [],
            "error": "Failed to load damaged assets"
        })

@router.post("/report/{damage_id}")
async def report_repair(
    damage_id: int,
    request: Request,
    repair_action: str = Form(...),
    description: str = Form(...),
    location_name: str = Form(""),
    room_name: str = Form(""),
    current_profile=Depends(get_current_profile)
):
    """Report asset repair with approval workflow"""
    try:
        supabase = get_supabase()
        
        # Get damage record
        damage_response = supabase.table("damage_log").select("*").eq("damage_id", damage_id).execute()
        if not damage_response.data:
            raise Exception("Damage record not found")
        
        damage_record = damage_response.data[0]
        
        # Create approval request based on user role
        approval_data = {
            "type": "repair",
            "asset_id": damage_record["asset_id"],
            "asset_name": damage_record["asset_name"],
            "submitted_by": current_profile.full_name or current_profile.username,
            "submitted_by_id": current_profile.id,
            "submitted_date": "now()",
            "status": "pending",
            "description": f"Repair Action: {repair_action}\nDescription: {description}",
            "metadata": {
                "damage_id": damage_id,
                "repair_action": repair_action,
                "repair_description": description,
                "return_location": location_name,
                "return_room": room_name
            }
        }
        
        # Set approver based on requester role
        if current_profile.role in ["staff", "manager"]:
            approval_data["requires_admin_approval"] = True
        elif current_profile.role == "admin":
            approval_data["requires_manager_approval"] = True
        
        supabase.table("approvals").insert(approval_data).execute()
        
        response = RedirectResponse(url="/repair", status_code=303)
        set_flash(response, f"Repair request submitted for approval: {damage_record['asset_name']}", "success")
        return response
        
    except Exception as e:
        logging.error(f"Error submitting repair request: {e}")
        response = RedirectResponse(url="/repair", status_code=303)
        set_flash(response, "Failed to submit repair request", "error")
        return response

@router.get("/api/locations")
async def get_locations():
    """Get locations for repair form"""
    try:
        from app.utils.database_manager import get_dropdown_options
        dropdown_options = get_dropdown_options()
        return JSONResponse({"locations": dropdown_options.get('locations', {})})
    except Exception as e:
        logging.error(f"Error getting locations: {e}")
        return JSONResponse({"locations": {}})