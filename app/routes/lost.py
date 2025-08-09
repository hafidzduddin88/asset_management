# app/routes/lost.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json

from app.utils.auth import get_current_profile
from app.utils.database_manager import get_all_assets, get_supabase, add_approval_request
from app.utils.device_detector import get_template

router = APIRouter(prefix="/lost", tags=["lost"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def lost_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """Lost assets page for all users."""
    # Get all active assets
    all_assets = get_all_assets()
    active_assets = [asset for asset in all_assets if asset.get('status') not in ['Disposed', 'Lost']]
    
    template_path = get_template(request, "lost/index.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "assets": active_assets
        }
    )

@router.post("/report/{asset_id}")
async def report_lost_asset(
    asset_id: str,
    request: Request,
    lost_date: str = Form(...),
    lost_location: str = Form(...),
    circumstances: str = Form(...),
    description: str = Form(None),
    current_profile = Depends(get_current_profile)
):
    """Report an asset as lost."""
    from app.utils.database_manager import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        return JSONResponse({"status": "error", "message": "Asset not found"})
    
    if asset.get('status') in ['Disposed', 'Lost']:
        return JSONResponse({"status": "error", "message": "Asset is already disposed or lost"})
    
    try:
        supabase = get_supabase()
        
        # Insert lost log
        lost_data = {
            "asset_id": asset_id,
            "asset_name": asset.get('asset_name', ''),
            "lost_date": lost_date,
            "lost_location": lost_location,
            "circumstances": circumstances,
            "description": description,
            "reported_by": current_profile.id,
            "reported_by_name": current_profile.full_name or current_profile.username,
            "status": "pending"
        }
        
        supabase.table("lost_log").insert(lost_data).execute()
        
        # Create approval request
        approval_data = {
            "type": "lost_report",
            "asset_id": asset_id,
            "asset_name": asset.get('asset_name', ''),
            "submitted_by": current_profile.id,
            "submitted_date": datetime.now().isoformat(),
            "description": f"Lost asset report: {circumstances}",
            "metadata": json.dumps({
                "lost_date": lost_date,
                "lost_location": lost_location,
                "circumstances": circumstances,
                "description": description
            }),
            "requires_admin_approval": True if current_profile.role.value in ['staff', 'manager'] else False,
            "requires_manager_approval": True if current_profile.role.value == 'admin' else False,
            "status": "pending"
        }
        
        add_approval_request(approval_data)
        
        return JSONResponse({"status": "success", "message": "Lost asset report submitted for approval"})
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error reporting lost asset: {str(e)}"})