# /app/app/routes/repair.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.post("/action")
async def submit_repair_action(request: Request, current_user = Depends(get_current_user)):
    """Submit repair action - syncs to Google Sheets"""
    from app.utils.sheets import add_repair_log, update_asset
    from datetime import datetime
    
    try:
        # Get JSON data
        data = await request.json()
        action_type = data.get('action_type')  # 'store' or 'allocate'
        
        # Add to Repair_Log sheet
        repair_data = {
            'asset_id': data.get('asset_id'),
            'asset_name': data.get('asset_name'),
            'repair_action': 'Store Asset' if action_type == 'store' else 'Allocate Asset',
            'action_type': action_type,
            'description': data.get('description', ''),
            'performed_by': current_user.username,
            'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'new_location': data.get('location', ''),
            'new_room': data.get('room', ''),
            'notes': data.get('notes', '')
        }
        
        # Add to repair log
        log_success = add_repair_log(repair_data)
        
        # Update asset in Assets sheet
        if action_type == 'store':
            # Store asset: Status -> In Storage, Location -> HO-Ciputat, Room -> 1022 - Gudang Support TOG
            update_data = {
                'Status': 'In Storage',
                'Bisnis Unit': 'General Affair',
                'Location': 'HO - Ciputat',
                'Room': '1022 - Gudang Support TOG'
            }
        else:  # allocate
            # Allocate asset: Status -> Active, Location/Room from form
            update_data = {
                'Status': 'Active',
                'Bisnis Unit': data.get('business_unit', ''),
                'Location': data.get('location', ''),
                'Room': data.get('room', '')
            }
        
        asset_success = update_asset(data.get('asset_id'), update_data)
        
        if log_success and asset_success:
            return {"status": "success", "message": f"Repair action completed and synced to Google Sheets"}
        else:
            return {"status": "error", "message": "Failed to sync with Google Sheets"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}