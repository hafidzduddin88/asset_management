# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app.utils.auth import get_admin_user, get_current_profile, get_current_profile
from app.utils.database_manager import get_all_assets, update_asset
from app.utils.flash import set_flash
from app.utils.device_detector import get_template

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    asset_id: int = None,
    current_profile = Depends(get_current_profile)
):
    """Disposal page - request form or SuperAdmin execution list."""
    from app.utils.database_manager import get_supabase
    
    supabase = get_supabase()
    
    if asset_id:
        # Asset disposal request form
        response = supabase.table('assets').select('*').eq('asset_id', asset_id).execute()
        asset_data = response.data[0] if response.data else None
        
        template_path = get_template(request, "disposal/form.html")
        return templates.TemplateResponse(
            template_path,
            {
                "request": request,
                "current_profile": current_profile,
                "asset": asset_data
            }
        )
    else:
        # SuperAdmin disposal execution list
        if current_profile.role != 'admin':
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get assets marked "To be Disposed"
        response = supabase.table('assets').select('''
            asset_id, asset_tag, asset_name, status,
            ref_categories(category_name),
            ref_locations(location_name, room_name)
        ''').eq('status', 'To be Disposed').execute()
        
        assets_to_dispose = response.data or []
        
        template_path = get_template(request, "disposal/index.html")
        return templates.TemplateResponse(
            template_path,
            {
                "request": request,
                "current_profile": current_profile,
                "assets": assets_to_dispose
            }
        )

@router.post("/request/{asset_id}")
async def request_disposal(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    current_profile = Depends(get_current_profile)
):
    """Request asset disposal (changes status to 'To be Disposed')."""
    from app.utils.database_manager import get_asset_by_id, add_approval_request
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Create disposal request approval
    approval_data = {
        'type': 'disposal_request',
        'asset_id': asset_id,
        'asset_name': asset.get('asset_name', ''),
        'submitted_by': current_profile.id,
        'submitted_date': datetime.now().isoformat(),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'notes': f'{{"disposal_reason": "{disposal_reason}", "disposal_method": "{disposal_method}", "description": "{description or ""}", "notes": "{notes or ""}"}}',
        'requires_admin_approval': True if current_profile.role in ['staff', 'manager'] else False,
        'requires_manager_approval': True if current_profile.role == 'admin' else False,
        'status': 'pending'
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/asset_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('asset_name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/asset_management", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response

@router.post("/execute/{asset_id}")
async def execute_disposal(
    asset_id: str,
    request: Request,
    disposal_method: str = Form(...),
    notes: str = Form(None),
    current_profile = Depends(get_admin_user)
):
    """Execute disposal (SuperAdmin only: 'To be Disposed' → 'Disposed')."""
    from app.utils.database_manager import get_asset_by_id, get_supabase
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.get('status') != 'To be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be 'To be Disposed' status")
    
    supabase = get_supabase()
    
    # Get storage location with fallback
    storage_response = supabase.table('ref_locations').select('location_id, location_name, room_name').eq('location_name', 'HO-Ciputat').eq('room_name', '1022 - Gudang Support TOG').execute()
    
    if storage_response.data:
        storage_location_id = storage_response.data[0]['location_id']
        storage_room = '1022 - Gudang Support TOG'
    else:
        # Fallback: Use first available location
        fallback_response = supabase.table('ref_locations').select('location_id, location_name, room_name').limit(1).execute()
        if fallback_response.data:
            storage_location_id = fallback_response.data[0]['location_id']
            storage_room = fallback_response.data[0]['room_name']
        else:
            raise HTTPException(status_code=500, detail="No storage location available")
    
    # Insert disposal log
    disposal_data = {
        "asset_id": asset_id,
        "asset_name": asset.get('asset_name'),
        "disposal_method": disposal_method,
        "notes": notes or '',
        "disposed_by": current_profile.id,
        "disposed_by_name": current_profile.full_name or current_profile.username,
        "created_at": "now()",
        "status": "Disposed"
    }
    
    supabase.table("disposal_log").insert(disposal_data).execute()
    
    # Update asset status to Disposed
    success = update_asset(asset_id, {
        'status': 'Disposed',
        'location_id': storage_location_id,
        'room_name': storage_room
    })
    
    if success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Asset {asset.get('asset_name', '')} disposed successfully", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error disposing asset", "error")
        return response