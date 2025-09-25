# app/routes/damage.py
import logging
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.device_detector import get_template

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/damage")
async def damage_page(request: Request, asset_id: int = None, current_profile = Depends(get_current_profile)):
    """Damage reporting page"""
    from app.utils.database_manager import get_supabase, get_all_assets
    
    if asset_id:
        # Individual asset damage form with proper relationships
        supabase = get_supabase()
        response = supabase.table('assets').select('''
            *,
            ref_categories(category_name),
            ref_locations(location_name, room_name)
        ''').eq('asset_id', asset_id).execute()
        asset_data = response.data[0] if response.data else None
        
        template_path = get_template(request, "damage/form.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "current_profile": current_profile,
            "user": current_profile,
            "asset": asset_data
        })
    else:
        # Asset selection page
        all_assets = get_all_assets()
        active_assets = [asset for asset in all_assets if asset.get('status') not in ['Disposed', 'Lost', 'Under Repair']]
        
        template_path = get_template(request, "damage/index.html")
        return templates.TemplateResponse(template_path, {
            "request": request,
            "user": current_profile,
            "assets": active_assets
        })













@router.post("/damage/report/{asset_id}")
async def submit_damage_report(
    asset_id: str,
    request: Request,
    damage_type: str = Form(...),
    severity: str = Form(...),
    description: str = Form(...),
    current_profile = Depends(get_current_profile)
):
    """Submit damage report for individual asset - creates approval request"""
    from app.utils.database_manager import get_asset_by_id, get_supabase
    from datetime import datetime
    import json

    try:
        # Get asset data
        asset = get_asset_by_id(asset_id)
        if not asset:
            return {"status": "error", "message": "Asset not found"}
        
        if asset.get('status') in ['Disposed', 'Lost']:
            return {"status": "error", "message": "Asset is already disposed or lost"}
        
        supabase = get_supabase()
        
        # Get warehouse location for damaged assets
        warehouse_response = supabase.table('ref_locations').select('location_id').eq('location_name', 'HO - Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
        warehouse_location_id = warehouse_response.data[0]['location_id'] if warehouse_response.data else None
        
        # Create approval request only (damage_log will be created when approved)
        approval_data = {
            'type': 'damage_report',
            'asset_id': int(asset_id),
            'asset_name': asset.get('asset_name', ''),
            'submitted_by': current_profile.id,
            'status': 'pending',
            'description': f"Damage Report: {damage_type} - {severity}",
            'from_location_id': int(asset.get('location_id')) if asset.get('location_id') else None,
            'to_location_id': int(warehouse_location_id) if warehouse_location_id else None,
            'notes': json.dumps({
                'damage_type': damage_type,
                'severity': severity,
                'description': description
            })
        }
        
        supabase.table('approvals').insert(approval_data).execute()
        
        return RedirectResponse(url="/damage/success", status_code=302)
        
    except Exception as e:
        logging.error(f"Error submitting damage report: {e}")
        return RedirectResponse(url="/damage/error", status_code=302)

@router.get("/damage/success")
async def damage_success(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Display damage report success page."""
    template_path = get_template(request, "damage/success.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile
        }
    )

@router.get("/damage/error")
async def damage_error(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Display damage report error page."""
    template_path = get_template(request, "damage/error.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "current_profile": current_profile
        }
    )