from fastapi import APIRouter, Request, Depends, HTTPException
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_profile
from app.database.models import UserRole

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def approvals_list(request: Request, current_profile=Depends(get_current_profile)):
    """List pending approvals based on user role"""
    from app.utils.sheets import get_all_approvals
    
    all_approvals = get_all_approvals()
    
    if current_profile.role == UserRole.ADMIN:
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['disposal', 'edit_asset']]
    elif current_profile.role == UserRole.MANAGER:
        approvals_data = [a for a in all_approvals if a.get('Type') in ['disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse("approvals/list.html", {
        "request": request,
        "user": current_profile,
        "approvals_data": approvals_data
    })


@router.post("/approve/{approval_id}")
async def approve_request(approval_id: int, request: Request, current_profile=Depends(get_current_profile)):
    """Approve a pending request"""
    from app.utils.sheets import update_approval_status, get_all_approvals, add_damage_log, update_asset, add_asset
    from datetime import datetime
    import json
    import logging
    
    approvals = get_all_approvals()
    approval = next((a for a in approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return {"status": "error", "message": "Approval not found"}
    
    success = update_approval_status(approval_id, 'Approved', current_profile.email)
    
    if not success:
        return {"status": "error", "message": "Failed to approve request"}
    
    try:
        if approval.get('Type') == 'damage_report':
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
                'notes': f'Approved by {current_profile.email}'
            }
            add_damage_log(damage_data)
            update_asset(approval.get('Asset_ID'), {
                'Status': 'Under Repair',
                'Location': 'HO - Ciputat',
                'Room': '1022 - Gudang Support TOG'
            })
        
        elif approval.get('Type') == 'add_asset':
            request_data_str = approval.get('Request_Data', '')
            if request_data_str and request_data_str != '{}':
                request_data = json.loads(request_data_str)
                success = add_asset(request_data)
                if not success:
                    return {"status": "error", "message": "Failed to add asset to Google Sheets"}
            else:
                return {"status": "error", "message": "No valid request data found in approval"}
        
        elif approval.get('Type') == 'relocation':
            relocation_data = json.loads(approval.get('Request_Data', '{}'))
            update_asset(approval.get('Asset_ID'), {
                'Location': relocation_data.get('new_location'),
                'Room': relocation_data.get('new_room')
            })
        
        elif approval.get('Type') == 'edit_asset':
            update_data = json.loads(approval.get('Request_Data', '{}'))
            from app.utils.sheets import update_asset as sheets_update_asset
            sheets_update_asset(approval.get('Asset_ID'), update_data)
        
        elif approval.get('Type') == 'disposal':
            disposal_data = {
                'asset_id': approval.get('Asset_ID'),
                'asset_name': approval.get('Asset_Name'),
                'disposal_reason': approval.get('Disposal_Reason', ''),
                'disposal_method': approval.get('Disposal_Method', ''),
                'description': approval.get('Description', ''),
                'requested_by': approval.get('Submitted_By'),
                'request_date': approval.get('Submitted_Date'),
                'disposal_date': datetime.now().strftime('%Y-%m-%d'),
                'disposed_by': current_profile.email,
                'notes': f"Approved by {current_profile.email}"
            }
            from app.utils.sheets import add_disposal_log
            add_disposal_log(disposal_data)
            update_asset(approval.get('Asset_ID'), {'Status': 'Disposed'})
        
        elif approval.get('Type') == 'repair_action':
            from app.utils.sheets import add_repair_log
            repair_data = {
                'asset_id': approval.get('Asset_ID'),
                'asset_name': approval.get('Asset_Name'),
                'repair_action': 'Store Asset',
                'action_type': 'store',
                'description': approval.get('Description'),
                'performed_by': current_profile.email,
                'action_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'new_location': 'HO - Ciputat',
                'new_room': '1022 - Gudang Support TOG',
                'notes': f"Approved by {current_profile.email}"
            }
            add_repair_log(repair_data)
            update_asset(approval.get('Asset_ID'), {
                'Status': 'In Storage',
                'Bisnis Unit': 'General Affair',
                'Location': 'HO - Ciputat',
                'Room': '1022 - Gudang Support TOG'
            })
        
        return {"status": "success", "message": "Request approved successfully"}
    
    except Exception as e:
        logging.error(f"Error processing approval: {str(e)}")
        return {"status": "error", "message": f"Error: {str(e)}"}


@router.post("/reject/{approval_id}")
async def reject_request(approval_id: int, request: Request, current_profile=Depends(get_current_profile)):
    """Reject a pending request"""
    from app.utils.sheets import update_approval_status
    
    success = update_approval_status(approval_id, 'Rejected', current_profile.email)
    
    if success:
        return {"status": "success", "message": "Request rejected"}
    else:
        return {"status": "error", "message": "Failed to reject request"}