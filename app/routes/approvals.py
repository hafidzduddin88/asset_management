# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_approvals, update_approval_status, get_supabase, update_asset
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
    
    # Get all approvals with user details
    all_approvals = get_all_approvals()
    
    # Get user details and location details for approvals
    supabase = get_supabase()
    for approval in all_approvals:
        # Get submitted by user details
        user_id = approval.get('submitted_by_id') or approval.get('submitted_by')
        if user_id:
            try:
                user_response = supabase.table('profiles').select('username, full_name').eq('id', user_id).execute()
                if user_response.data:
                    user = user_response.data[0]
                    approval['submitted_by_info'] = {
                        'full_name': user.get('full_name') or 'Unknown',
                        'username': user.get('username') or 'Unknown'
                    }
                    approval['submitted_by_name'] = user.get('full_name') or user.get('username') or 'Unknown User'
                else:
                    approval['submitted_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
                    approval['submitted_by_name'] = 'Unknown User'
            except:
                approval['submitted_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
                approval['submitted_by_name'] = 'Unknown User'
        
        # Get approved by user details
        if approval.get('approved_by'):
            try:
                user_response = supabase.table('profiles').select('username, full_name').eq('id', approval['approved_by']).execute()
                if user_response.data:
                    user = user_response.data[0]
                    approval['approved_by_info'] = {
                        'full_name': user.get('full_name') or 'Unknown',
                        'username': user.get('username') or 'Unknown'
                    }
                    approval['approved_by_name'] = user.get('full_name') or user.get('username') or 'Unknown User'
                else:
                    approval['approved_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
                    approval['approved_by_name'] = 'Unknown User'
            except:
                approval['approved_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
                approval['approved_by_name'] = 'Unknown User'
        
        # Get location details - always show TO location
        if approval.get('to_location_id'):
            try:
                loc_response = supabase.table('ref_locations').select('location_name, room_name').eq('location_id', approval['to_location_id']).execute()
                if loc_response.data:
                    location = loc_response.data[0]
                    approval['location_name'] = location.get('location_name', '')
                    approval['room_name'] = location.get('room_name', '')
                else:
                    approval['location_name'] = 'Unknown Location'
                    approval['room_name'] = 'Unknown Room'
            except:
                approval['location_name'] = 'Unknown Location'
                approval['room_name'] = 'Unknown Room'
    
    # Filter approvals based on role-based approval workflow
    if current_profile.role == 'admin':
        # Admin approves requests from staff and manager
        approvals_data = [a for a in all_approvals if a.get('requires_admin_approval') == True]
    elif current_profile.role == 'manager':
        # Manager approves requests from admin
        approvals_data = [a for a in all_approvals if a.get('requires_manager_approval') == True]
    else:
        approvals_data = []
    
    # Separate pending and completed approvals
    pending_approvals = [a for a in approvals_data if a.get('status') == 'pending']
    completed_approvals = [a for a in approvals_data if a.get('status') in ['approved', 'rejected']]
    
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
    
    # Get approval details
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('approval_id')) == str(approval_id)), None)
    
    if not approval:
        return JSONResponse({"status": "error", "message": "Approval not found"})
    
    # Process approval based on type
    try:
        if approval.get('type') == 'damage_report':
            # Get storage location ID (HO-Ciputat, 1022 - Gudang Support TOG)
            supabase = get_supabase()
            storage_response = supabase.table('ref_locations').select('location_id').eq('location_name', 'HO-Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
            
            if storage_response.data:
                storage_location_id = storage_response.data[0]['location_id']
                
                # Update asset status to "Under Repair" and move to storage
                from app.utils.database_manager import update_asset
                success = update_asset(approval.get('asset_id'), {
                    'status': 'Under Repair',
                    'location_id': storage_location_id,
                    'room_name': '1022 - Gudang Support TOG'
                })
                if not success:
                    return JSONResponse({"status": "error", "message": "Failed to update asset status and location"})
            else:
                return JSONResponse({"status": "error", "message": "Storage location not found"})
            
            # Update damage_log with approver info
            supabase.table('damage_log').update({
                'status': 'approved',
                'approved_by': current_profile.id,
                'approved_by_name': current_profile.full_name or current_profile.username
            }).eq('asset_id', approval.get('asset_id')).execute()
        
        elif approval.get('type') == 'relocation':
            # Process relocation approval
            import json
            try:
                request_data_str = approval.get('notes', '')
                if request_data_str:
                    relocation_data = json.loads(request_data_str)
                    new_location = relocation_data.get('new_location')
                    new_room = relocation_data.get('new_room')
                    
                    supabase = get_supabase()
                    
                    # Get current asset data
                    asset_response = supabase.table('assets').select('location_id, ref_locations(location_name, room_name)').eq('asset_id', approval.get('asset_id')).execute()
                    current_location_id = asset_response.data[0]['location_id'] if asset_response.data else None
                    current_location_data = asset_response.data[0]['ref_locations'] if asset_response.data and asset_response.data[0].get('ref_locations') else {}
                    
                    # Get new location_id
                    loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', new_location).eq('room_name', new_room).execute()
                    
                    if loc_response.data:
                        new_location_id = loc_response.data[0]['location_id']
                        
                        # Create relocation_log entry
                        relocation_log_data = {
                            'asset_id': approval.get('asset_id'),
                            'asset_name': approval.get('asset_name'),
                            'old_location_id': current_location_id,
                            'old_location_name': current_location_data.get('location_name', ''),
                            'old_room_name': current_location_data.get('room_name', ''),
                            'new_location_id': new_location_id,
                            'new_location_name': new_location,
                            'new_room_name': new_room,
                            'reason': relocation_data.get('reason', ''),
                            'notes': relocation_data.get('notes', ''),
                            'requested_by': approval.get('submitted_by'),
                            'requested_by_name': approval.get('submitted_by_name', ''),
                            'approved_by': current_profile.id,
                            'approved_by_name': current_profile.full_name or current_profile.username,
                            'status': 'approved',
                            'approved_at': 'now()'
                        }
                        
                        supabase.table('relocation_log').insert(relocation_log_data).execute()
                        
                        # Determine new status based on location
                        new_status = 'In Storage' if new_location == 'HO-Ciputat' and new_room == '1022 - Gudang Support TOG' else 'Active'
                        
                        update_data = {
                            'location_id': new_location_id,
                            'room_name': new_room,
                            'status': new_status
                        }
                        
                        from app.utils.database_manager import update_asset
                        success = update_asset(approval.get('asset_id'), update_data)
                        if not success:
                            return JSONResponse({"status": "error", "message": "Failed to relocate asset"})
                    else:
                        return JSONResponse({"status": "error", "message": "Location not found"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing relocation: {str(e)}"})
            
        elif approval.get('type') == 'edit_asset':
            # Process edit asset approval
            import json
            try:
                request_data_str = approval.get('notes', '')
                if request_data_str:
                    edit_data = json.loads(request_data_str)
                    # Convert field names to match database schema
                    db_data = {}
                    field_mapping = {
                        'status': 'status',
                        'company_name': 'company_id',
                        'location_name': 'location_id', 
                        'room_name': 'room_name',
                        'business_unit_name': 'business_unit_id'
                    }
                    
                    # Convert name fields to IDs
                    supabase = get_supabase()
                    if edit_data.get('company_name'):
                        comp_response = supabase.table('ref_companies').select('company_id').eq('company_name', edit_data['company_name']).execute()
                        if comp_response.data:
                            db_data['company_id'] = comp_response.data[0]['company_id']
                    
                    if edit_data.get('location_name') and edit_data.get('room_name'):
                        loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', edit_data['location_name']).eq('room_name', edit_data['room_name']).execute()
                        if loc_response.data:
                            db_data['location_id'] = loc_response.data[0]['location_id']
                            db_data['room_name'] = edit_data['room_name']
                    
                    if edit_data.get('business_unit_name'):
                        unit_response = supabase.table('ref_business_units').select('business_unit_id').eq('business_unit_name', edit_data['business_unit_name']).execute()
                        if unit_response.data:
                            db_data['business_unit_id'] = unit_response.data[0]['business_unit_id']
                    
                    if edit_data.get('status'):
                        db_data['status'] = edit_data['status']
                    
                    from app.utils.database_manager import update_asset
                    success = update_asset(approval.get('asset_id'), db_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing edit: {str(e)}"})
        
        elif approval.get('type') == 'admin_add_asset':
            # Process admin asset addition approval
            import json
            try:
                request_data_str = approval.get('notes', '')
                if request_data_str:
                    asset_data = json.loads(request_data_str)
                    from app.utils.database_manager import add_asset
                    success = add_asset(asset_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to add asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing asset addition: {str(e)}"})
        
        elif approval.get('type') == 'add_asset':
            # Process manager/staff asset addition approval
            import json
            try:
                request_data_str = approval.get('notes', '')
                if request_data_str:
                    asset_data = json.loads(request_data_str)
                    from app.utils.database_manager import add_asset
                    success = add_asset(asset_data)
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to add asset"})
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing asset addition: {str(e)}"})
        
        elif approval.get('type') == 'repair':
            # Process repair approval
            import json
            try:
                metadata = approval.get('metadata', {})
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                repair_asset_id = metadata.get('asset_id')
                repair_action = metadata.get('repair_action')
                repair_description = metadata.get('repair_description')
                return_location = metadata.get('return_location', '')
                return_room = metadata.get('return_room', '')
                
                if repair_asset_id:
                    # Insert repair log
                    repair_data = {
                        "asset_id": approval.get('asset_id'),
                        "asset_name": approval.get('asset_name'),
                        "repair_action": repair_action,
                        "description": repair_description,
                        "performed_by": approval.get('submitted_by'),
                        "created_at": "now()",
                        "status": "Completed"
                    }
                    
                    supabase = get_supabase()
                    supabase.table("repair_log").insert(repair_data).execute()
                    
                    # Update damage status to Repaired for this asset
                    supabase.table("damage_log").update({"status": "Repaired"}).eq("asset_id", repair_asset_id).eq("status", "approved").execute()
                    
                    # Determine new status and location
                    if return_location and return_room:
                        # Get location ID for return location
                        loc_response = supabase.table('ref_locations').select('location_id').eq('location_name', return_location).eq('room_name', return_room).execute()
                        if loc_response.data:
                            location_id = loc_response.data[0]['location_id']
                            # Update asset to Active status and return location
                            supabase.table("assets").update({
                                "status": "Active",
                                "location_id": location_id,
                                "room_name": return_room
                            }).eq("asset_id", approval.get('asset_id')).execute()
                        else:
                            return JSONResponse({"status": "error", "message": "Return location not found"})
                    else:
                        # No return location specified, keep in storage
                        storage_response = supabase.table('ref_locations').select('location_id').eq('location_name', 'HO-Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
                        if storage_response.data:
                            storage_location_id = storage_response.data[0]['location_id']
                            supabase.table("assets").update({
                                "status": "In Storage",
                                "location_id": storage_location_id,
                                "room_name": "1022 - Gudang Support TOG"
                            }).eq("asset_id", approval.get('asset_id')).execute()
                        else:
                            return JSONResponse({"status": "error", "message": "Storage location not found"})
                    
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing repair: {str(e)}"})
        
        elif approval.get('type') == 'lost_report':
            # Process lost asset approval
            try:
                # Get storage location ID
                supabase = get_supabase()
                storage_response = supabase.table('ref_locations').select('location_id').eq('location_name', 'HO-Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
                
                if storage_response.data:
                    storage_location_id = storage_response.data[0]['location_id']
                    
                    # Update asset status to Lost and move to storage
                    from app.utils.database_manager import update_asset
                    success = update_asset(approval.get('asset_id'), {
                        'status': 'Lost',
                        'location_id': storage_location_id,
                        'room_name': '1022 - Gudang Support TOG'
                    })
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset status and location"})
                else:
                    return JSONResponse({"status": "error", "message": "Storage location not found"})
                
                # Update lost_log with approver info
                supabase.table('lost_log').update({
                    'status': 'approved',
                    'approved_by': current_profile.id,
                    'approved_by_name': current_profile.full_name or current_profile.username
                }).eq('asset_id', approval.get('asset_id')).execute()
                
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing lost report: {str(e)}"})
        
        elif approval.get('type') == 'disposal_request':
            # Process disposal approval
            import json
            try:
                metadata = approval.get('metadata', '{}')
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                
                disposal_reason = metadata.get('disposal_reason', '')
                disposal_method = metadata.get('disposal_method', '')
                description = metadata.get('description', '')
                notes = metadata.get('notes', '')
                
                supabase = get_supabase()
                
                # Get storage location ID
                storage_response = supabase.table('ref_locations').select('location_id').eq('location_name', 'HO-Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
                
                if storage_response.data:
                    storage_location_id = storage_response.data[0]['location_id']
                    
                    # Insert disposal log
                    disposal_data = {
                        "asset_id": approval.get('asset_id'),
                        "asset_name": approval.get('asset_name'),
                        "disposal_reason": disposal_reason,
                        "disposal_method": disposal_method,
                        "description": description,
                        "notes": notes,
                        "disposed_by": current_profile.id,
                        "disposed_by_name": current_profile.full_name or current_profile.username,
                        "created_at": "now()",
                        "status": "Disposed"
                    }
                    
                    supabase.table("disposal_log").insert(disposal_data).execute()
                    
                    # Update asset status to Disposed (final disposal)
                    from app.utils.database_manager import update_asset
                    success = update_asset(approval.get('asset_id'), {
                        'status': 'Disposed',
                        'location_id': storage_location_id,
                        'room_name': '1022 - Gudang Support TOG'
                    })
                    if not success:
                        return JSONResponse({"status": "error", "message": "Failed to update asset status and location"})
                else:
                    return JSONResponse({"status": "error", "message": "Storage location not found"})
                
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"Error processing disposal: {str(e)}"})
        
        # Update approval status in database
        success = update_approval_status(
            approval_id, 
            'approved',
            current_profile.id,
            current_profile.full_name or current_profile.username
        )
        
        if success:
            return JSONResponse({"status": "success", "message": "Request approved successfully"})
        else:
            return JSONResponse({"status": "error", "message": "Failed to update approval status"})
            
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error processing approval: {str(e)}"})

@router.post("/{approval_id}/rejected")
async def reject_request(
    approval_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Reject a request."""
    if current_profile.role not in ['admin', 'manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update approval status and log tables
    all_approvals = get_all_approvals()
    approval = next((a for a in all_approvals if str(a.get('approval_id')) == str(approval_id)), None)
    
    if approval:
        # Update corresponding log table
        supabase = get_supabase()
        approver_name = current_profile.full_name or current_profile.username
        
        if approval.get('type') == 'damage_report':
            supabase.table('damage_log').update({
                'status': 'rejected',
                'approved_by': current_profile.id,
                'approved_by_name': approver_name
            }).eq('asset_id', approval.get('asset_id')).execute()
        elif approval.get('type') == 'lost_report':
            supabase.table('lost_log').update({
                'status': 'rejected',
                'approved_by': current_profile.id,
                'approved_by_name': approver_name
            }).eq('asset_id', approval.get('asset_id')).execute()
        elif approval.get('type') == 'repair':
            # For repair rejection, keep damage status as reported
            pass
        elif approval.get('type') == 'disposal_request':
            # For disposal rejection, just update the approval - no disposal log entry needed
            pass
        elif approval.get('type') == 'relocation':
            # For relocation rejection, no relocation_log entry is created
            # Only the approval record is updated
            pass
    
    # Update approval status
    success = update_approval_status(
        approval_id,
        'rejected', 
        current_profile.id,
        current_profile.full_name or current_profile.username
    )
    
    if success:
        return JSONResponse({"status": "success", "message": "Request rejected"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to update approval status"})