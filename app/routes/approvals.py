# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_approvals, update_approval_status

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Approvals page for admin and manager."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get all approvals from Google Sheets
    all_approvals = get_all_approvals()
    
    # Filter approvals based on user role
    if current_profile.role == 'admin':
        # Admin sees manager/staff requests (add_asset, damage_report, etc.)
        approvals_data = [a for a in all_approvals if a.get('Type') not in ['admin_add_asset', 'disposal', 'edit_asset']]
    elif current_profile.role == 'manager':
        # Manager sees admin requests (admin_add_asset) and disposal/edit_asset
        approvals_data = [a for a in all_approvals if a.get('Type') in ['admin_add_asset', 'disposal', 'edit_asset']]
    else:
        approvals_data = []
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_profile,
            "approvals_data": approvals_data
        }
    )

@router.post("/approve/{approval_id}")
async def approve_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Approve a request."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('ID')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('Type') == 'damage_report':
            # Update asset status to "Under Repair"
            from app.utils.sheets import update_asset
            success = update_asset(approval.get('Asset_ID'), {'Status': 'Under Repair'})
            if not success:
                return JSONResponse({"status": "error", "message": "Failed to update asset status"})
        
        elif approval.get('Type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    update_data = {
                        'Location': relocation_data.get('new_location'),
                        'Room': relocation_data.get('new_room')
                    }
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), update_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('Type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    from app.utils.sheets import update_asset
                    success = update_asset(approval.get('Asset_ID'), edit_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        elif approval.get('Type') == 'admin_add_asset':
            # Process admin asset addition approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    asset_data = json.loads(request_data_str)
                    from app.utils.sheets import add_asset
                    success = add_asset(asset_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to add asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing asset addition: {str(e)}"})
        
        elif approval.get('Type') == 'add_asset':
            # Process manager/staff asset addition approval
            import json
            try:
                request_data_str = approval.get('Request_Data', '')
                if request_data_str:
                    asset_data = json.loads(request_data_str)
                    from app.utils.sheets import add_asset
                    success = add_asset(asset_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to add asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing asset addition: {str(e)}"})
        
        # Update approval status in Google Sheets
        success = update_approval_status(
            approval_id, 
            'Approved',
            current_profile.full_name or current_profile.email
        )
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """Reject a request."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status
    success = update_approval_status(
        approval_id,
        'Rejected', 
        current_profile.full_name or current_profile.email
    )
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})