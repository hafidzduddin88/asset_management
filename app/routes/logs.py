# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Profile
from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_profile = Depends(get_current_profile)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_profile.role.value == 'staff':
        # Staff can only see their own requests
        user_identifier = current_profile.full_name or current_profile.email
        approvals = [a for a in all_approvals if a.get('Submitted_By') == user_identifier]
    else:
        # Manager and admin can see all approvals
        approvals = all_approvals
    
    # Separate pending and completed
    pending_approvals = [a for a in approvals if a.get('Status') == 'Pending']
    completed_approvals = [a for a in approvals if a.get('Status') in ['Approved', 'Rejected']]
    
    return templates.TemplateResponse(
        "logs/index.html",
        {
            "request": request,
            "user": current_profile,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )