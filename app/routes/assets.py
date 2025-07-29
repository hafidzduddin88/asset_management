# app/routes/asset.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(request: Request, current_profile=Depends(get_current_profile)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Ambil data asset dari Google Sheets
    all_assets = get_all_assets()
    
    # Filter hanya aset aktif (bukan Disposed)
    active_assets = [asset for asset in all_assets if asset.get("Status", "").lower() != "disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_profile,
        "assets_data": active_assets
    })