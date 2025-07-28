# app/routes/logs.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import User
from app.database.dependencies import get_current_active_user
from app.utils.sheets import get_all_approvals

router = APIRouter(prefix="/logs", tags=["logs"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def logs_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """View approval logs based on user role."""
    all_approvals = get_all_approvals()
    
    # Filter based on user role
    if current_user.role == 'staff':
        # Staff can only see their own requests
        approvals = [a for a in all_approvals if a.get('Submitted_By') == current_user.username]
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
            "user": current_user,
            "pending_approvals": pending_approvals,
            "completed_approvals": completed_approvals
        }
    )