from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import json

from app.utils.auth import get_admin_user, get_current_profile
from app.utils.database_manager import get_asset_by_id, add_approval_request, get_supabase, update_asset
from app.utils.flash import set_flash
from app.utils.device_detector import get_template

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/form", response_class=HTMLResponse)
async def disposal_form_page(
    request: Request,
    asset_id: str,
    current_profile = Depends(get_current_profile)
):
    """Disposal request form page for specific asset."""
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
    
    template_path = get_template(request, "disposal/form.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "user": current_profile,
        "asset": asset
    })

@router.get("/success", response_class=HTMLResponse)
async def disposal_success_page(
    request: Request,
    asset_id: str,
    asset_name: str = None,
    current_profile = Depends(get_current_profile)
):
    """Disposal request success page."""
    template_path = get_template(request, "disposal/success.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "user": current_profile,
        "asset_id": asset_id,
        "asset_name": asset_name or "Asset"
    })

@router.get("/error", response_class=HTMLResponse)
async def disposal_error_page(
    request: Request,
    asset_id: str,
    asset_name: str = None,
    error_message: str = None,
    current_profile = Depends(get_current_profile)
):
    """Disposal request error page."""
    template_path = get_template(request, "disposal/error.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "user": current_profile,
        "asset_id": asset_id,
        "asset_name": asset_name or "Asset",
        "error_message": error_message or "An error occurred while submitting your disposal request."
    })

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def disposal_list_page(
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """List all disposed assets for viewing."""
    supabase = get_supabase()
    
    response = supabase.table('assets').select('''
        asset_id, asset_tag, asset_name, status,
        ref_categories(category_name),
        ref_locations(location_name, room_name)
    ''').eq('status', 'Disposed').execute()
    
    disposed_assets = response.data or []
    
    template_path = get_template(request, "disposal/index.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "current_profile": current_profile,
        "user": current_profile,
        "assets": disposed_assets
    })



@router.get("/view/{asset_id}", response_class=HTMLResponse)
async def view_disposal_details(
    asset_id: str,
    request: Request,
    current_profile = Depends(get_current_profile)
):
    """View disposal log details for disposed asset."""
    supabase = get_supabase()
    
    # Get disposal log entry
    response = supabase.table('disposal_log').select('''
        disposal_log_id, asset_id, asset_name, disposal_reason, disposal_method,
        description, requested_by_name, request_date, status, notes,
        approved_by_name, approved_at
    ''').eq('asset_id', asset_id).order('request_date', desc=True).limit(1).execute()
    
    disposal_log = response.data[0] if response.data else None
    if not disposal_log:
        raise HTTPException(status_code=404, detail="Disposal log not found")
    
    # Get asset details
    asset_response = supabase.table('assets').select('''
        asset_id, asset_name, asset_tag, status,
        ref_categories(category_name),
        ref_locations(location_name, room_name)
    ''').eq('asset_id', asset_id).execute()
    
    asset = asset_response.data[0] if asset_response.data else None
    
    template_path = get_template(request, "disposal/modal_view.html")
    return templates.TemplateResponse(template_path, {
        "request": request,
        "disposal_log": disposal_log,
        "asset": asset
    })

@router.post("/submit")
async def submit_disposal_request(
    request: Request,
    asset_id: str = Form(...),
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    current_profile = Depends(get_current_profile)
):
    """Submit disposal request."""
    try:
        asset = get_asset_by_id(asset_id)
        if not asset:
            return RedirectResponse(
                url=f"/disposal/error?asset_id={asset_id}&error_message=Asset not found",
                status_code=status.HTTP_303_SEE_OTHER
            )
        
        # Create approval request
        approval_data = {
            'type': 'disposal_request',
            'asset_id': asset_id,
            'asset_name': asset.get('asset_name', ''),
            'submitted_by': current_profile.id,
            'submitted_date': datetime.now().isoformat(),
            'description': f"Disposal request: {disposal_reason} - {disposal_method}",
            'notes': json.dumps({"disposal_reason": disposal_reason, "disposal_method": disposal_method, "description": description or "", "notes": notes or ""}),
            'status': 'pending'
        }
        
        approval_success = add_approval_request(approval_data)
        
        # Log disposal request
        supabase = get_supabase()
        disposal_log_data = {
            "asset_id": int(asset_id),
            "asset_name": asset.get('asset_name', ''),
            "disposal_reason": disposal_reason,
            "disposal_method": disposal_method,
            "description": description or '',
            "notes": notes or '',
            "requested_by": current_profile.id,
            "requested_by_name": current_profile.full_name or current_profile.username,
            "status": "pending"
        }
        
        supabase.table('disposal_log').insert(disposal_log_data).execute()
        
        if approval_success:
            return RedirectResponse(
                url=f"/disposal/success?asset_id={asset_id}&asset_name={asset.get('asset_name', '')}",
                status_code=status.HTTP_303_SEE_OTHER
            )
        else:
            return RedirectResponse(
                url=f"/disposal/error?asset_id={asset_id}&asset_name={asset.get('asset_name', '')}&error_message=Failed to submit disposal request",
                status_code=status.HTTP_303_SEE_OTHER
            )
    
    except Exception as e:
        return RedirectResponse(
            url=f"/disposal/error?asset_id={asset_id}&error_message=An unexpected error occurred",
            status_code=status.HTTP_303_SEE_OTHER
        )

