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
    """Lost assets page - redirect to asset management."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/asset_management", status_code=302)

@router.get("/form", response_class=HTMLResponse)
async def lost_form_page(
    request: Request,
    asset_id: int,
    current_profile = Depends(get_current_profile)
):
    """Lost report form page for specific asset."""
    # Get asset data with proper relationships
    supabase = get_supabase()
    response = supabase.table('assets').select('''
        *,
        ref_categories(category_name),
        ref_locations(location_name, room_name)
    ''').eq('asset_id', asset_id).execute()
    
    asset = response.data[0] if response.data else None
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    template_path = get_template(request, "lost/form.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "current_profile": current_profile,
            "user": current_profile,
            "asset": asset
        }
    )

@router.get("/success", response_class=HTMLResponse)
async def lost_success_page(
    request: Request,
    asset_name: str = None,
    current_profile = Depends(get_current_profile)
):
    """Lost report success page."""
    template_path = get_template(request, "lost/success.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "current_profile": current_profile,
            "user": current_profile,
            "asset_name": asset_name or "Asset"
        }
    )

@router.get("/error", response_class=HTMLResponse)
async def lost_error_page(
    request: Request,
    asset_id: int = None,
    asset_name: str = None,
    error_message: str = None,
    current_profile = Depends(get_current_profile)
):
    """Lost report error page."""
    template_path = get_template(request, "lost/error.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "current_profile": current_profile,
            "user": current_profile,
            "asset_id": asset_id,
            "asset_name": asset_name or "Asset",
            "error_message": error_message
        }
    )

@router.post("/submit")
async def submit_lost_report(
    request: Request,
    asset_id: str = Form(...),
    lost_reason: str = Form(...),
    description: str = Form(...),
    notes: str = Form(None),
    current_profile = Depends(get_current_profile)
):
    """Submit lost report from form page."""
    from app.utils.database_manager import get_asset_by_id
    from fastapi.responses import RedirectResponse
    from app.utils.flash import set_flash
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        response = RedirectResponse(url="/asset_management/list", status_code=302)
        set_flash(response, "Asset not found", "error")
        return response
    
    if asset.get('status') in ['Disposed', 'Lost']:
        response = RedirectResponse(url="/asset_management/list", status_code=302)
        set_flash(response, "Asset is already disposed or lost", "error")
        return response
    
    try:
        # Create approval request
        approval_data = {
            "type": "lost_report",
            "asset_id": asset_id,
            "asset_name": asset.get('asset_name', ''),
            "submitted_by": current_profile.id,
            "submitted_date": datetime.now().isoformat(),
            "description": f"Lost asset report: {lost_reason}",
            "from_location_id": asset.get('location_id'),
            "notes": json.dumps({
                "lost_reason": lost_reason,
                "description": description,
                "notes": notes or ""
            }),
            "status": "pending"
        }
        
        success = add_approval_request(approval_data)
        
        if success:
            return RedirectResponse(url=f"/lost/success?asset_name={asset.get('asset_name', 'Asset')}", status_code=302)
        else:
            return RedirectResponse(url=f"/lost/error?asset_id={asset_id}&asset_name={asset.get('asset_name', 'Asset')}&error_message=Failed to create approval request", status_code=302)
        
    except Exception as e:
        return RedirectResponse(url=f"/lost/error?asset_id={asset_id}&asset_name={asset.get('asset_name', 'Asset')}&error_message={str(e)}", status_code=302)

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
    """Report an asset as lost (detailed form)."""
    from app.utils.database_manager import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        return JSONResponse({"status": "error", "message": "Asset not found"})
    
    if asset.get('status') in ['Disposed', 'Lost']:
        return JSONResponse({"status": "error", "message": "Asset is already disposed or lost"})
    
    try:
        # Create approval request
        approval_data = {
            "type": "lost_report",
            "asset_id": asset_id,
            "asset_name": asset.get('asset_name', ''),
            "submitted_by": current_profile.id,
            "submitted_date": datetime.now().isoformat(),
            "description": f"Lost asset report: {circumstances}",
            "from_location_id": asset.get('location_id'),
            "notes": json.dumps({
                "lost_date": lost_date,
                "lost_location": lost_location,
                "circumstances": circumstances,
                "description": description or ""
            }),
            "status": "pending"
        }
        
        add_approval_request(approval_data)
        
        return JSONResponse({"status": "success", "message": "Lost asset report submitted for approval"})
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Error reporting lost asset: {str(e)}"})