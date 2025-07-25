# /app/app/routes/approvals.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def approvals_list(request: Request, current_user = Depends(get_current_user)):
    """List all pending approvals for admin"""
    from app.utils.sheets import get_all_approvals
    
    # Get real approval data from Google Sheets
    approvals_data = get_all_approvals()
    
    return templates.TemplateResponse("approvals/list.html", {
        "request": request,
        "user": current_user,
        "approvals_data": approvals_data
    })

@router.post("/approve/{approval_id}")
async def approve_request(approval_id: int, request: Request, current_user = Depends(get_current_user)):
    """Approve a pending request"""
    from app.utils.sheets import update_approval_status
    
    success = update_approval_status(approval_id, 'Approved', current_user.username)
    
    if success:
        return {"status": "success", "message": "Request approved successfully"}
    else:
        return {"status": "error", "message": "Failed to approve request"}

@router.post("/reject/{approval_id}")
async def reject_request(approval_id: int, request: Request, current_user = Depends(get_current_user)):
    """Reject a pending request"""
    from app.utils.sheets import update_approval_status
    
    success = update_approval_status(approval_id, 'Rejected', current_user.username)
    
    if success:
        return {"status": "success", "message": "Request rejected"}
    else:
        return {"status": "error", "message": "Failed to reject request"}