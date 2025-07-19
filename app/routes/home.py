from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import User, Approval, ApprovalStatus, UserRole
from app.database.dependencies import get_current_user
from app.utils.sheets import get_all_assets
from app.utils.flash import get_flash

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
@router.head("/", response_class=HTMLResponse)
@router.get("/home", response_class=HTMLResponse)
@router.head("/home", response_class=HTMLResponse)
async def home(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Home page / Dashboard."""
    
    # Get assets from Google Sheets
    assets = get_all_assets()
    
    # Get dashboard stats
    total_assets = len(assets)
    active_assets = len([a for a in assets if a.get('Status') == 'Active'])
    damaged_assets = len([a for a in assets if a.get('Status') == 'Damaged'])
    disposed_assets = len([a for a in assets if a.get('Status') == 'Disposed'])
    
    # Get pending approvals (for admins)
    pending_approvals = []
    if current_user.role == UserRole.ADMIN:
        pending_approvals = (
            db.query(Approval)
            .filter(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.created_at.desc())
            .limit(5)
            .all()
        )
    
    # Get recent assets (sort by ID in reverse to get newest first)
    recent_assets = sorted(assets, key=lambda x: x.get('ID', '0'), reverse=True)[:5]
    
    # Get flash messages
    flash = get_flash(request)
    
    return templates.TemplateResponse(
        "dashboard_modern.html",
        {
            "request": request,
            "user": current_user,
            "total_assets": total_assets,
            "active_assets": active_assets,
            "damaged_assets": damaged_assets,
            "disposed_assets": disposed_assets,
            "pending_approvals": pending_approvals,
            "recent_assets": recent_assets,
            "flash": flash
        },
    )