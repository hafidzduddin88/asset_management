# app/routes/asset.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import RedirectResponse
from app.utils.auth import get_current_profile

router = APIRouter()


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
    """Redirect to asset management list"""
    return RedirectResponse(url="/asset_management/list", status_code=301)