# app/routes/asset.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets/debug")
async def debug_assets(request: Request, current_profile=Depends(get_current_profile)):
    """Debug endpoint to test database connection"""
    from app.utils.database_manager import test_database_connection
    
    debug_info = test_database_connection()
    return {"debug_info": debug_info}

@router.get("/assets")
async def assets_page(
    request: Request, 
    current_profile=Depends(get_current_profile)
):
    """Assets listing page with filtering"""
    from app.utils.database_manager import get_all_assets, get_dropdown_options
    
    # Get all assets and dropdown options for filtering
    all_assets = get_all_assets()
    dropdown_options = get_dropdown_options()
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_profile,
        "assets": all_assets,
        "dropdown_options": dropdown_options
    })