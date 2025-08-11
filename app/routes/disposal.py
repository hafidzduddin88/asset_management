# app/routes/disposal.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from app.utils.auth import get_admin_user
from app.utils.database_manager import get_all_assets, update_asset
from app.utils.flash import set_flash
from app.utils.device_detector import get_template

router = APIRouter(prefix="/disposal", tags=["disposal"])
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def disposal_page(
    request: Request,
    current_profile = Depends(get_admin_user)
):
    """Disposal assets page (admin only)."""
    # Get assets that are ready to dispose only
    all_assets = get_all_assets()
    disposable_assets = [asset for asset in all_assets if asset.get('status') == 'To Be Disposed']
    
    template_path = get_template(request, "disposal/index.html")
    return templates.TemplateResponse(
        template_path,
        {
            "request": request,
            "user": current_profile,
            "assets": disposable_assets
        }
    )

@router.post("/dispose/{asset_id}")
async def dispose_asset(
    asset_id: str,
    request: Request,
    disposal_reason: str = Form(...),
    disposal_method: str = Form(...),
    description: str = Form(None),
    notes: str = Form(None),
    current_profile = Depends(get_admin_user)
):
    """Dispose an asset (admin only)."""
    from app.utils.database_manager import get_asset_by_id
    
    # Get asset data
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.get('status') != 'To Be Disposed':
        raise HTTPException(status_code=400, detail="Asset must be marked 'To Be Disposed' first")
    
    # Create disposal approval request
    from app.utils.database_manager import add_approval_request
    
    approval_data = {
        'type': 'disposal_request',
        'asset_id': asset_id,
        'asset_name': asset.get('asset_name', ''),
        'submitted_by': current_profile.id,
        'submitted_date': datetime.now().isoformat(),
        'description': f"Disposal request: {disposal_reason} - {disposal_method}",
        'metadata': f'{{"disposal_reason": "{disposal_reason}", "disposal_method": "{disposal_method}", "description": "{description or ""}", "notes": "{notes or ""}"}}',
        'requires_admin_approval': True if current_profile.role.value in ['staff', 'manager'] else False,
        'requires_manager_approval': True if current_profile.role.value == 'admin' else False,
        'status': 'pending'
    }
    
    approval_success = add_approval_request(approval_data)
    
    if approval_success:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, f"Disposal request for {asset.get('asset_name', '')} submitted for approval", "success")
        return response
    else:
        response = RedirectResponse(url="/disposal", status_code=status.HTTP_303_SEE_OTHER)
        set_flash(response, "Error submitting disposal request", "error")
        return response