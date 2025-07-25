# /app/app/routes/damage_report.py
from fastapi import APIRouter, Request, Depends
from starlette.templating import Jinja2Templates
from app.utils.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def damaged_assets_page(request: Request, current_user = Depends(get_current_user)):
    """Damaged assets page with search and log functionality"""
    from app.utils.sheets import get_all_assets
    import logging
    
    # Get real asset data from Google Sheets
    all_assets = get_all_assets()
    
    return templates.TemplateResponse("damaged_assets.html", {
        "request": request,
        "user": current_user,
        "assets_data": all_assets
    })

@router.post("/report")
async def submit_damage_report(request: Request, current_user = Depends(get_current_user)):
    """Submit damage report - requires admin approval"""
    # This would handle the form submission
    # For now, just return success
    return {"status": "success", "message": "Damage report submitted for approval"}