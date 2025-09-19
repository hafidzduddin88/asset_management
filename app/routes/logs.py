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
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Get user details for submitted_by and approved_by UUIDs
    supabase = get_supabase()
    for approval in all_approvals:
        if approval.get('submitted_by'):
            try:
                user_response = supabase.table('profiles').select('username, full_name').eq('id', approval['submitted_by']).execute()
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
    
    # Filter based on user role
    if current_profile.role.value == 'staff':
        # Staff can only see their own requests
        approvals = [a for a in all_approvals if a.get('submitted_by') == current_profile.id]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
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