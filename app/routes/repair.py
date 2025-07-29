# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_profile = Depends(get_current_profile)):
    """Submit repair action - creates approval request for store, direct action for allocate"""
    from app.utils.sheets import add_repair_log, update_asset, add_approval_request
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        if action_type == 'store':
            # Store action requires approval - only create approval request
            approval_data = {
                'type': 'repair_action',
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'submitted_by': current_profile.full_name or current_profile.email,
                'submitted_date': datetime.now().strftime('%Y-%m-%d'),
                'description': f"Request to store asset: {data.get('description')}",
                'action': 'Store Asset'
            }
            
            approval_success = add_approval_request(approval_data)
            
            if approval_success:
                return {"status": "success", "message": "Store request submitted for admin approval"}
            else:
                return {"status": "error", "message": "Failed to submit approval request"}
        
        else:  # allocate - direct action
            # Add to Repair_Log sheet
            repair_data = {
                'asset_id': data.get('asset_id'),
                'asset_name': data.get('asset_name'),
                'repair_action': 'Allocate Asset',
                'action_type': action_type,
                'description': data.get('description', ''),
                'performed_by': current_profile.full_name or current_profile.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': data.get('location', ''),
                'new_room': data.get('room', ''),
                'notes': data.get('notes', '')
            }
            
            # Add to repair log
            log_success = add_repair_log(repair_data)
            
            # Update asset from Under Repair to Active
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
            
            asset_success = update_asset(data.get('asset_id'), update_data)
            
            if log_success and asset_success:
                return {"status": "success", "message": "Asset allocated successfully and synced to Google Sheets"}
            else:
                return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}