# app/routes/approvals.py
import logging
import json
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_approvals, get_supabase, update_asset, prepare_asset_data, invalidate_cache, update_approval_status
from app.utils.device_detector import get_template

router = APIRouter(prefix="/approvals", tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Approvals page for admin and manager."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    all_approvals = get_all_approvals()
    
    supabase = get_supabase()
    for approval in all_approvals:
        user_id = approval.get('submitted_by_id') or approval.get('submitted_by')
        if user_id:
            try:
                user_response = supabase.table('profiles').select('username, full_name').eq('id', user_id).execute()
                if user_response.data:
                    user = user_response.data[0]
                    approval['submitted_by_name'] = user.get('full_name') or user.get('username') or 'Unknown User'
            except Exception as e:
                logging.warning(f"Could not fetch user {user_id}: {e}")
                approval['submitted_by_name'] = 'Unknown User'

    pending_approvals = sorted([a for a in all_approvals if a.get('status') == 'pending'], 
                              key=lambda x: x.get('created_at', ''), reverse=True)
    completed_approvals = sorted([a for a in all_approvals if a.get('status') in ['approved', 'rejected']], 
                                key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)
    
    template_path = get_template(request, "approvals/list.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals,
            "pending_count": len(pending_approvals),
            "completed_count": len(completed_approvals)
        }
    )

@router.post("/{approval_id}/approved")
async def approve_request(
    approval_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Approve a request."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    supabase = get_supabase()
    approval = next((a for a in get_all_approvals() if str(a.get('approval_id')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"}, status_code=404)

    try:
        approval_type = approval.get('type')

        if approval_type in ['add_asset', 'admin_add_asset']:
            asset_data = json.loads(approval.get('notes', '{}'))
            
            prepared_data = prepare_asset_data(asset_data)
            if not prepared_data:
                return JSONResponse({"status": "error", "message": "Failed to prepare asset data for transaction."})

            rpc_params = {
                'approval_id_in': int(approval_id),
                'approver_id_in': str(current_profile.id),
                'new_asset_data': prepared_data
            }
            
            response = supabase.rpc('approve_and_create_asset', rpc_params).execute()
            
            if response.data:
                invalidate_cache()
                return JSONResponse({"status": "success", "message": "Request approved and asset created successfully"})
            else:
                error_info = response.get('error') or 'No data returned from RPC'
                logging.error(f"RPC call failed for approval {approval_id}: {error_info}")
                return JSONResponse({"status": "error", "message": f"Database transaction failed: {error_info}"})

        # --- Handle all other approval types below ---

        elif approval_type == 'damage_report':
            # (Your original logic for damage_report)
            pass

        elif approval_type == 'relocation':
            # (Your original logic for relocation)
            pass

        # ... other elif blocks for other approval types ...

        # If the approval type was not for adding an asset, it falls through to here.
        # Update the status for all other approval types.
        success = update_approval_status(
            approval_id, 
            'approved',
            current_profile.id
        )

        if success:
            invalidate_cache()
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status for non-asset request."})

    except Exception as e:
        logging.error(f"Critical error processing approval {approval_id}: {str(e)}")
        return JSONResponse({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}, status_code=500)


@router.post("/{approval_id}/rejected")
async def reject_request(
    approval_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Reject a request."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = update_approval_status(approval_id, 'rejected', current_profile.id)
    
    if success:
        invalidate_cache()
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})
