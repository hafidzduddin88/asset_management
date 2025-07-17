# app/routes/approvals.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
from datetime import datetime

from app.database.database import get_db
from app.database.models import Approval, User, ApprovalStatus
from app.database.dependencies import get_current_active_user, get_admin_user

router = APIRouter(tags=["approvals"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/approvals", response_class=HTMLResponse)
async def list_approvals(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """List pending approvals (admin only)."""
    approvals = (
        db.query(Approval)
        .filter(Approval.status == ApprovalStatus.PENDING)
        .order_by(Approval.created_at.desc())
        .all()
    )
    
    return templates.TemplateResponse(
        "approvals/list.html",
        {
            "request": request,
            "user": current_user,
            "approvals": approvals
        }
    )

@router.get("/approvals/{approval_id}", response_class=HTMLResponse)
async def approval_detail(
    request: Request,
    approval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Approval detail page (admin only)."""
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        return RedirectResponse(url="/approvals", status_code=status.HTTP_303_SEE_OTHER)
    
    # Parse request data
    request_data = json.loads(approval.request_data) if approval.request_data else {}
    
    return templates.TemplateResponse(
        "approvals/detail.html",
        {
            "request": request,
            "user": current_user,
            "approval": approval,
            "request_data": request_data
        }
    )

@router.post("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Approve a request (admin only)."""
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval or approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")
    
    # Update approval
    approval.status = ApprovalStatus.APPROVED
    approval.admin_id = current_user.id
    approval.notes = notes
    approval.approved_at = datetime.utcnow()
    
    # Process the approval based on action type
    # This would be implemented based on the specific action types
    
    db.commit()
    
    return RedirectResponse(url="/approvals", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Reject a request (admin only)."""
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval or approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")
    
    # Update approval
    approval.status = ApprovalStatus.REJECTED
    approval.admin_id = current_user.id
    approval.notes = notes
    approval.approved_at = datetime.utcnow()
    
    db.commit()
    
    return RedirectResponse(url="/approvals", status_code=status.HTTP_303_SEE_OTHER)