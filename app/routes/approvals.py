# /app/app/routes/approvals.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def approvals_list(request: Request, current_user = Depends(get_current_user)):
    """List all pending approvals for admin"""
    from app.utils.sheets import get_all_approvals
    
    # Get real approval data from Google Sheets
    approvals_data = get_all_approvals()
    
    return templates.TemplateResponse("approvals/list.html", {
        "request": request,
        "user": current_user,
        "approvals_data": approvals_data
    })

@router.post("/approve/{approval_id}")
async def approve_request(approval_id: int, request: Request, current_user = Depends(get_current_user)):
    """Approve a pending request"""
    from app.utils.sheets import update_approval_status, get_all_approvals, add_damage_log, update_asset, add_asset
    from datetime import datetime
    
    # Get approval details first
    approvals = get_all_approvals()
    approval = next((a for a in approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return {"status": "error", "message": "Approval not found"}
    
    # Update approval status
    success = update_approval_status(approval_id, 'Approved', current_user.username)
    
    if success:
        # Process based on approval type
        if approval.get('Type') == 'damage_report':
            # Add to damage log when approved
            damage_data = {
                'asset_id': approval.get('Asset_ID'),
                'asset_name': approval.get('Asset_Name'),
                'damage_type': approval.get('Damage_Type'),
                'severity': approval.get('Severity'),
                'description': approval.get('Description'),
                'reported_by': approval.get('Submitted_By'),
                'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'location': approval.get('Location', ''),
                'room': '',
                'notes': 'Approved by admin'
            }
            add_damage_log(damage_data)
            
            # Update asset status to Under Repair and move to storage
            update_asset(approval.get('Asset_ID'), {
                'Status': 'Under Repair',
                'Location': 'HO - Ciputat',
                'Room': '1022 - Gudang Support TOG'
            })
            
        elif approval.get('Type') == 'add_asset':
            # Add new asset to Assets sheet when approved
            import json
            request_data = json.loads(approval.get('Request_Data', '{}'))
            success = add_asset(request_data)
            if not success:
                return {"status": "error", "message": "Failed to add asset to Google Sheets"}
            
        elif approval.get('Type') == 'repair_action':
            # Add to repair log when store action approved
            from app.utils.sheets import add_repair_log
            repair_data = {
                'asset_id': approval.get('Asset_ID'),
                'asset_name': approval.get('Asset_Name'),
                'repair_action': 'Store Asset',
                'action_type': 'store',
                'description': approval.get('Description'),
                'performed_by': current_user.username,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': 'HO - Ciputat',
                'new_room': '1022 - Gudang Support TOG',
                'notes': 'Approved by admin'
            }
            add_repair_log(repair_data)
            
            # Update asset status from Under Repair to In Storage
            update_asset(approval.get('Asset_ID'), {
                'Status': 'In Storage',
                'Bisnis Unit': 'General Affair',
                'Location': 'HO - Ciputat',
                'Room': '1022 - Gudang Support TOG'
            })
        
        return {"status": "success", "message": "Request approved successfully"}
    else:
        return {"status": "error", "message": "Failed to approve request"}

@router.post("/reject/{approval_id}")
async def reject_request(approval_id: int, request: Request, current_user = Depends(get_current_user)):
    """Reject a pending request"""
    from app.utils.sheets import update_approval_status
    
    success = update_approval_status(approval_id, 'Rejected', current_user.username)
    
    if success:
        return {"status": "success", "message": "Request rejected"}
    else:
        return {"status": "error", "message": "Failed to reject request"}