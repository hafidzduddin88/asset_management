# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_approvals, get_supabase
from app.utils.device_detector import get_template

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """View approval logs for staff only."""
    # Only staff can access logs
    if current_profile.role != 'staff':
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    
    supabase = get_supabase()
    # Get all approvals with submitter and approver full names
    response = supabase.table('approvals').select('''
        approval_id, type, asset_id, asset_name, status, submitted_by, submitted_date,
        description, approved_by, approved_date, notes, created_at,
        from_location_id, to_location_id,
        submitted_profile:profiles!approvals_submitted_by_fkey(full_name, username),
        approved_profile:profiles!approvals_approved_by_fkey(full_name, username)
    ''').order('submitted_date', desc=True).execute()
    
    all_approvals = response.data or []
    
    # Process approvals to add name fields
    for approval in all_approvals:
        # Submitted by info
        submitted_profile = approval.get('submitted_profile')
        if submitted_profile:
            approval['submitted_by_name'] = submitted_profile.get('full_name') or submitted_profile.get('username') or 'Unknown User'
            approval['submitted_by_info'] = {
                'full_name': submitted_profile.get('full_name') or 'Unknown',
                'username': submitted_profile.get('username') or 'Unknown'
            }
        else:
            approval['submitted_by_name'] = 'Unknown User'
            approval['submitted_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
        
        # Approved by info
        approved_profile = approval.get('approved_profile')
        if approved_profile:
            approval['approved_by_name'] = approved_profile.get('full_name') or approved_profile.get('username') or 'Unknown User'
            approval['approved_by_info'] = {
                'full_name': approved_profile.get('full_name') or 'Unknown',
                'username': approved_profile.get('username') or 'Unknown'
            }
        else:
            approval['approved_by_name'] = 'Unknown User'
            approval['approved_by_info'] = {'full_name': 'Unknown', 'username': 'Unknown'}
    
    # Staff can only see their own requests
    approvals = [a for a in all_approvals if a.get('submitted_by') == current_profile.id]
    
    # Separate pending and completed, sort by date (newest first)
    pending_approvals = sorted([a for a in approvals if a.get('status') == 'pending'], 
                              key=lambda x: x.get('created_at', ''), reverse=True)
    completed_approvals = sorted([a for a in approvals if a.get('status') in ['approved', 'rejected']], 
                                key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)
    
    template_path = get_template(request, "logs/index.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )