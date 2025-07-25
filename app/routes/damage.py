# /app/app/routes/damage_report.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets
    import logging
    
    # Get real asset data from Google Sheets
    all_assets = get_all_assets()
    
    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets
    })

@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):

@router.post("/lost")
async def submit_lost_report(request: Request, current_user = Depends(get_current_user)):
    """Submit lost report - syncs to Google Sheets"""
    from app.utils.sheets import add_lost_log, add_approval_request
    from datetime import datetime
    
    try:
        data = await request.json()
        
        # Add to Lost_Log sheet
        lost_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'last_location': data.get('last_location'),
            'last_room': data.get('last_room', ''),
            'date_lost': data.get('date_lost'),
            'description': data.get('description'),
            'reported_by': current_user.username,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }
        
        log_success = add_lost_log(lost_data)
        
        # Add to approval requests
        approval_data = {
            'type': 'lost_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.username,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Lost report: {data.get('description')}",
            'location': data.get('last_location')
        }
        
        approval_success = add_approval_request(approval_data)
        
        if log_success and approval_success:
            return {"status": "success", "message": "Lost report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/disposal")
async def submit_disposal_request(request: Request, current_user = Depends(get_current_user)):
    """Submit disposal request - syncs to Google Sheets"""
    from app.utils.sheets import add_disposal_log, add_approval_request
    from datetime import datetime
    
    try:
        data = await request.json()
        
        # Add to Disposal_Log sheet
        disposal_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'disposal_reason': data.get('disposal_reason'),
            'disposal_method': data.get('disposal_method', 'Standard'),
            'description': data.get('description'),
            'requested_by': current_user.username,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'notes': data.get('notes', '')
        }
        
        log_success = add_disposal_log(disposal_data)
        
        # Add to approval requests
        approval_data = {
            'type': 'disposal_request',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.username,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Disposal request: {data.get('description')}"
        }
        
        approval_success = add_approval_request(approval_data)
        
        if log_success and approval_success:
            return {"status": "success", "message": "Disposal request submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - syncs to Google Sheets"""
    from app.utils.sheets import add_damage_log, add_approval_request, update_asset
    from datetime import datetime
    import json
    
    try:
        # Get JSON data
        data = await request.json()
        
        # Add to Damage_Log sheet
        damage_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity'),
            'description': data.get('damage_description'),
            'reported_by': current_user.username,
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'location': data.get('location', ''),
            'room': data.get('room', ''),
            'notes': data.get('notes', '')
        }
        
        # Add to damage log
        log_success = add_damage_log(damage_data)
        
        # Add to approval requests
        approval_data = {
            'type': 'damage_report',
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'submitted_by': current_user.username,
            'submitted_date': datetime.now().strftime('%Y-%m-%d'),
            'description': f"Damage report: {data.get('damage_description')}",
            'damage_type': data.get('damage_type'),
            'severity': data.get('severity')
        }
        
        approval_success = add_approval_request(approval_data)
        
        if log_success and approval_success:
            return {"status": "success", "message": "Damage report submitted and logged to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}