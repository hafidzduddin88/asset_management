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
    # Get user roles for filtering
    user_roles = {}
    for approval in all_approvals:
        user_id = approval.get('submitted_by_id') or approval.get('submitted_by')
        if user_id and user_id not in user_roles:
            try:
                user_response = supabase.table('profiles').select('username, full_name, role').eq('id', user_id).execute()
                if user_response.data:
                    user = user_response.data[0]
                    user_roles[user_id] = user.get('role', 'staff')
                    approval['submitted_by_name'] = user.get('full_name') or user.get('username') or 'Unknown User'
                    approval['submitted_by_role'] = user.get('role', 'staff')
            except Exception as e:
                logging.warning(f"Could not fetch user {user_id}: {e}")
                approval['submitted_by_name'] = 'Unknown User'
                approval['submitted_by_role'] = 'staff'
        elif user_id in user_roles:
            approval['submitted_by_role'] = user_roles[user_id]
    
    # Filter pending approvals based on current user role, but show all completed approvals
    filtered_pending = []
    for approval in all_approvals:
        if approval.get('status') == 'pending':
            submitted_by_role = approval.get('submitted_by_role', 'staff')
            
            if current_profile.role == 'manager':
                # Manager can only approve requests from admin
                if submitted_by_role == 'admin':
                    filtered_pending.append(approval)
            elif current_profile.role == 'admin':
                # Admin can approve requests from manager and staff
                if submitted_by_role in ['manager', 'staff']:
                    filtered_pending.append(approval)
    
    pending_approvals = sorted(filtered_pending, key=lambda x: x.get('created_at', ''), reverse=True)
    # Show all completed approvals regardless of role
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
            # Process damage report approval
            notes_data = json.loads(approval.get('notes', '{}'))
            asset_id = approval.get('asset_id')
            
            # Add to damage_log
            damage_log_data = {
                'asset_id': asset_id,
                'asset_name': approval.get('asset_name', ''),
                'damage_type': notes_data.get('damage_type', ''),
                'severity': notes_data.get('severity', ''),
                'description': notes_data.get('description', ''),
                'reported_by': approval.get('submitted_by'),
                'approved_by': current_profile.id,
                'status': 'approved'
            }
            supabase.table('damage_log').insert(damage_log_data).execute()
            
            # Update asset status to Under Repair
            update_asset(asset_id, {'status': 'Under Repair'})

        elif approval_type == 'lost_report':
            # Process lost report approval
            notes_data = json.loads(approval.get('notes', '{}'))
            asset_id = approval.get('asset_id')
            
            # Add to lost_log
            lost_log_data = {
                'asset_id': asset_id,
                'asset_name': approval.get('asset_name', ''),
                'lost_reason': notes_data.get('lost_reason', '') or notes_data.get('circumstances', ''),
                'description': notes_data.get('description', ''),
                'lost_date': notes_data.get('lost_date', ''),
                'lost_location': notes_data.get('lost_location', ''),
                'reported_by': approval.get('submitted_by'),
                'approved_by': current_profile.id,
                'status': 'approved'
            }
            supabase.table('lost_log').insert(lost_log_data).execute()
            
            # Update asset status to Lost
            update_asset(asset_id, {'status': 'Lost'})

        elif approval_type == 'relocation':
            # Process relocation approval
            notes_data = json.loads(approval.get('notes', '{}'))
            asset_id = approval.get('asset_id')
            
            # Add to relocation_log
            relocation_log_data = {
                'asset_id': asset_id,
                'asset_name': approval.get('asset_name', ''),
                'from_location': notes_data.get('from_location', ''),
                'to_location': notes_data.get('to_location', ''),
                'reason': notes_data.get('reason', ''),
                'moved_by': approval.get('submitted_by'),
                'approved_by': current_profile.id,
                'status': 'approved'
            }
            supabase.table('relocation_log').insert(relocation_log_data).execute()
            
            # Update asset location
            location_updates = {}
            if notes_data.get('new_location_id'):
                location_updates['location_id'] = notes_data.get('new_location_id')
            if notes_data.get('new_room_name'):
                location_updates['room_name'] = notes_data.get('new_room_name')
            if location_updates:
                update_asset(asset_id, location_updates)

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
