# app/routes/damage.py
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/damage")
async def damaged_assets_page(request: Request, current_profile = Depends(get_current_profile)):
    """Damaged assets page with search and log functionality"""
    try:
        from app.utils.database_manager import get_all_assets, get_dropdown_options

        all_assets = get_all_assets() or []
        dropdown_options = get_dropdown_options() or {}

        return templates.TemplateResponse("damage/index.html", {
            "request": request,
            "user": current_profile,
            "assets_data": all_assets,
            "dropdown_options": dropdown_options
        })
    except Exception as e:
        logging.error(f"Error loading damage page: {e}")
        return templates.TemplateResponse("damage/index.html", {
            "request": request,
            "user": current_profile,
            "assets_data": [],
            "dropdown_options": {},
            "error": "Failed to load asset issue page. Please try again."
        })


@router.post("/lost")
async def submit_lost_report(request: Request, current_profile = Depends(get_current_profile)):
    """Submit lost report - syncs to Supabase"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime

    try:
        data = await request.json()
        supabase = get_supabase()
        
        # Add to lost_log table
        lost_data = {
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_profile.id,
            'status': 'pending'
        }
        supabase.table('lost_log').insert(lost_data).execute()

        # Add approval request
        approval_data = {
            'type': 'lost_report',
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_profile.id,
            'status': 'pending',
            'description': f"Lost report: {data.get('description')}"
        }
        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Lost report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

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
        
        # Add to disposal_log table
        disposal_data = {
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason', 'User request'),
            'description': data.get('description'),
            'requested_by': current_profile.id,
            'status': 'pending'
        }
        supabase.table('disposal_log').insert(disposal_data).execute()

        # Add approval request
        approval_data = {
            'type': 'disposal_request',
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_profile.id,
            'status': 'pending',
            'description': f"Disposal request: {data.get('description')}"
        }
        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Disposal request submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        logging.error(f"Error submitting disposal request: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/report")
async def submit_damage_report(request: Request, current_profile = Depends(get_current_profile)):
    """Submit damage report - syncs to Supabase"""
    from app.utils.database_manager import add_approval_request, get_supabase
    from datetime import datetime

    try:
        data = await request.json()
        supabase = get_supabase()
        
        # Add to damage_log table
        damage_data = {
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_profile.id,
            'status': 'pending'
        }
        supabase.table('damage_log').insert(damage_data).execute()

        # Add approval request
        approval_data = {
            'type': 'damage_report',
            'asset_id': int(data.get('asset_id')),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_profile.id,
            'status': 'pending',
            'description': f"Damage report: {data.get('damage_description')}",
            'notes': f"Type: {data.get('damage_type')}, Severity: {data.get('severity')}"
        }
        approval_success = add_approval_request(approval_data)

        if approval_success:
            return {"status": "success", "message": "Damage report submitted for approval"}
        else:
            return {"status": "error", "message": "Failed to submit approval request"}

    except Exception as e:
        logging.error(f"Error submitting damage report: {e}")
        return {"status": "error", "message": str(e)}