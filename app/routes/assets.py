# /app/app/routes/assets.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets")
async def assets_page(request: Request, current_user = Depends(get_current_user)):
    """Assets listing page with filtering and pagination"""
    from app.utils.sheets import get_all_assets
    
    # Get real asset data from Google Sheets
    all_assets = get_all_assets()
    
    # Filter only active assets
    active_assets = [asset for asset in all_assets if asset.get("Status", "") != "Disposed"]
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": active_assets
    })