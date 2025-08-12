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
        
        # Get assets with Under Repair status directly
        assets_response = supabase.table("assets").select('''
            asset_id, asset_name, asset_tag, manufacture, model, serial_number,
            purchase_date, purchase_cost, book_value, status, updated_at,
            ref_categories(category_name),
            ref_locations(location_name, room_name),
            ref_companies(company_name),
            ref_business_units(business_unit_name)
        ''').eq('status', 'Under Repair').execute()
        
        damaged_assets = assets_response.data or []
        
        # Get damage info for each asset
        for asset in damaged_assets:
            damage_response = supabase.table("damage_log").select('''
                damage_type, severity, description, reported_by_name, created_at
            ''').eq('asset_id', asset['asset_id']).eq('status', 'approved').order('created_at', desc=True).limit(1).execute()
            
            if damage_response.data:
                asset['damage_info'] = damage_response.data[0]
            else:
                asset['damage_info'] = None
        
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

@router.post("/report/{asset_id}")
async def report_repair(
    asset_id: int,
    request: Request,
    repair_action: str = Form(...),
    description: str = Form(...),
    location_name: str = Form(""),
    room_name: str = Form(""),
    current_profile=Depends(get_current_profile)
):
    """Report asset repair completion - goes to approval workflow"""
    try:
        supabase = get_supabase()
        
        # Get asset record
        asset_response = supabase.table("assets").select("asset_id, asset_name").eq("asset_id", asset_id).execute()
        if not asset_response.data:
            raise Exception("Asset not found")
        
        asset_record = asset_response.data[0]
        
        # Create approval request - repair reports go to approval
        approval_data = {
            "type": "repair",
            "asset_id": asset_record["asset_id"],
            "asset_name": asset_record["asset_name"],
            "submitted_by": current_profile.full_name or current_profile.username,
            "submitted_by_id": current_profile.id,
            "submitted_date": "now()",
            "status": "pending",
            "description": f"Repair Action: {repair_action}\nDescription: {description}",
            "metadata": {
                "asset_id": asset_id,
                "repair_action": repair_action,
                "repair_description": description,
                "return_location": location_name,
                "return_room": room_name
            }
        }
        
        supabase.table("approvals").insert(approval_data).execute()
        
        response = RedirectResponse(url="/repair", status_code=303)
        set_flash(response, f"Repair completion report submitted for approval: {asset_record['asset_name']}", "success")
        return response
        
    except Exception as e:
        logging.error(f"Error submitting repair completion report: {e}")
        response = RedirectResponse(url="/repair", status_code=303)
        set_flash(response, "Failed to submit repair completion report", "error")
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