from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Asset, Approval, User, AssetStatus, ApprovalStatus
from app.utils.auth import get_current_active_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Home page / Dashboard."""
    
    # Get dashboard stats
    total_assets = db.query(Asset).count()
    active_assets = db.query(Asset).filter(Asset.status == AssetStatus.ACTIVE).count()
    damaged_assets = db.query(Asset).filter(Asset.status == AssetStatus.DAMAGED).count()
    disposed_assets = db.query(Asset).filter(Asset.status == AssetStatus.DISPOSED).count()
    
    # Get pending approvals (for admins)
    pending_approvals = []
    if current_user.role == "admin":
        pending_approvals = (
            db.query(Approval)
            .filter(Approval.status == ApprovalStatus.PENDING)
            .order_by(Approval.created_at.desc())
            .limit(5)
            .all()
        )
    
    # Get recent assets
    recent_assets = (
        db.query(Asset)
        .order_by(Asset.created_at.desc())
        .limit(5)
        .all()
    )
    
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
        },
    )