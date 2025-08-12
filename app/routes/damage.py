# app/routes/damage.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.utils.device_detector import get_template

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/damage")
async def damage_page(request: Request, asset_id: int = None, current_profile = Depends(get_current_profile)):
    """Damage reporting page"""
    from app.utils.database_manager import get_supabase
    
    supabase = get_supabase()
    asset_data = None
    
    if asset_id:
        # Get specific asset
        response = supabase.table('assets').select('*').eq('asset_id', asset_id).execute()
        if response.data:
            asset_data = response.data[0]
    
    template_path = get_template(request, "damage/form.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "asset": asset_data
    })


@router.get("/lost")
async def lost_page(request: Request, asset_id: int = None, current_profile = Depends(get_current_profile)):
    """Lost reporting page"""
    from app.utils.database_manager import get_supabase
    
    supabase = get_supabase()
    asset_data = None
    
    if asset_id:
        # Get specific asset
        response = supabase.table('assets').select('*').eq('asset_id', asset_id).execute()
        if response.data:
            asset_data = response.data[0]
    
    template_path = get_template(request, "lost/form.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "asset": asset_data
    })

@router.post("/damage/lost")
async def submit_lost_report(request: Request, current_profile = Depends(get_current_profile)):
    """Submit lost report - syncs to Supabase"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime

    try:
        data = await request.json()
        supabase = get_supabase()
        asset_ids = data.get('asset_ids', [])
        
        success_count = 0
        for asset_id in asset_ids:
            try:
                # Add to lost_log table
                lost_data = {
                    'asset_id': int(asset_id),
                    'date_lost': data.get('date_lost'),
                    'description': data.get('description'),
                    'reported_by': current_profile.id,
                    'reported_by_name': current_profile.full_name or current_profile.username,
                    'status': 'pending'
                }
                supabase.table('lost_log').insert(lost_data).execute()
                success_count += 1
                
            except Exception as e:
                logging.error(f"Error processing lost report for asset {asset_id}: {e}")
                continue
        
        if success_count > 0:
            return {"status": "success", "message": f"Lost report submitted for {success_count} asset(s)"}
        else:
            return {"status": "error", "message": "Failed to submit lost reports"}

    except Exception as e:
        logging.error(f"Error submitting lost report: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/disposal")
async def submit_disposal_request(request: Request, current_profile = Depends(get_current_profile)):
    """Submit disposal request - syncs to Supabase"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime

    try:
        data = await request.json()
        supabase = get_supabase()
        asset_ids = data.get('asset_ids', [])
        
        success_count = 0
        for asset_id in asset_ids:
            try:
                # Add to disposal_log table
                disposal_data = {
                    'asset_id': int(asset_id),
                    'disposal_reason': data.get('disposal_reason', 'User request'),
                    'description': data.get('description'),
                    'requested_by': current_profile.id,
                    'requested_by_name': current_profile.full_name or current_profile.username,
                    'status': 'pending'
                }
                supabase.table('disposal_log').insert(disposal_data).execute()
                success_count += 1
                
            except Exception as e:
                logging.error(f"Error processing disposal request for asset {asset_id}: {e}")
                continue
        
        if success_count > 0:
            return {"status": "success", "message": f"Disposal request submitted for {success_count} asset(s)"}
        else:
            return {"status": "error", "message": "Failed to submit disposal requests"}

    except Exception as e:
        logging.error(f"Error submitting disposal request: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/repair")
async def submit_repair_report(request: Request, current_profile = Depends(get_current_profile)):
    """Submit repair report - syncs to Supabase"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime

    try:
        data = await request.json()
        supabase = get_supabase()
        asset_ids = data.get('asset_ids', [])
        
        success_count = 0
        for asset_id in asset_ids:
            try:
                # Add to repair_log table
                repair_data = {
                    'asset_id': int(asset_id),
                    'repair_action': data.get('repair_action'),
                    'action_type': 'repair',
                    'description': data.get('description'),
                    'performed_by': current_profile.id,
                    'performed_by_name': current_profile.full_name or current_profile.username,
                    'status': 'completed'
                }
                
                # Add new location if specified
                if data.get('new_location'):
                    location_parts = data.get('new_location').split(' - ')
                    if len(location_parts) == 2:
                        location_name, room_name = location_parts
                        loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', location_name).eq('room_name', room_name).execute()
                        if loc_response.data:
                            repair_data['new_location_id'] = loc_response.data[0]['location_id']
                
                supabase.table('repair_log').insert(repair_data).execute()
                success_count += 1
                
            except Exception as e:
                logging.error(f"Error processing repair for asset {asset_id}: {e}")
                continue
        
        if success_count > 0:
            return {"status": "success", "message": f"Repair report submitted for {success_count} asset(s)"}
        else:
            return {"status": "error", "message": "Failed to submit repair reports"}

    except Exception as e:
        logging.error(f"Error submitting repair report: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/damage/report")
async def submit_damage_report(request: Request, current_profile = Depends(get_current_profile)):
    """Submit damage report - creates approval request"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime
    import json

    try:
        data = await request.json()
        supabase = get_supabase()
        asset_ids = data.get('asset_ids', [])
        
        success_count = 0
        for asset_id in asset_ids:
            try:
                # Get asset name
                asset_response = supabase.table('assets').select('asset_name').eq('asset_id', asset_id).execute()
                asset_name = asset_response.data[0]['asset_name'] if asset_response.data else f"Asset {asset_id}"
                
                # Add to damage_log table first
                damage_data = {
                    'asset_id': int(asset_id),
                    'asset_name': asset_name,
                    'damage_type': data.get('damage_type'),
                    'severity': data.get('severity'),
                    'description': data.get('damage_description'),
                    'reported_by': current_profile.id,
                    'reported_by_name': current_profile.full_name or current_profile.username,
                    'status': 'pending'
                }
                supabase.table('damage_log').insert(damage_data).execute()
                
                # Create approval request
                approval_data = {
                    'type': 'damage_report',
                    'asset_id': int(asset_id),
                    'asset_name': asset_name,
                    'submitted_by': current_profile.id,
                    'status': 'pending',
                    'description': f"Damage Report: {data.get('damage_type')} - {data.get('severity')}",
                    'notes': json.dumps({
                        'damage_type': data.get('damage_type'),
                        'severity': data.get('severity'),
                        'description': data.get('damage_description')
                    })
                }
                
                # Role-based approval will be handled in approvals page filtering
                
                supabase.table('approvals').insert(approval_data).execute()
                success_count += 1
                
            except Exception as e:
                logging.error(f"Error processing damage report for asset {asset_id}: {e}")
                continue
        
        if success_count > 0:
            return {"status": "success", "message": f"Damage report submitted for approval: {success_count} asset(s)"}
        else:
            return {"status": "error", "message": "Failed to submit damage reports"}

    except Exception as e:
        logging.error(f"Error submitting damage report: {e}")
        return {"status": "error", "message": str(e)}