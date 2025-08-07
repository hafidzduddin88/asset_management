# app/routes/asset.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from app.utils.auth import get_current_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/assets")
async def assets_page(
    request: Request, 
    current_profile=Depends(get_current_profile),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=10, le=100),
    status: str = Query('active')
):
    """Assets listing page with filtering and pagination"""
    from app.utils.database_manager import get_assets_paginated
    
    # Get paginated assets from Supabase
    assets_result = get_assets_paginated(page=page, per_page=per_page, status_filter=status)
    
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "user": current_profile,
        "assets_data": assets_result['data'],
        "pagination": {
            "current_page": assets_result['page'],
            "per_page": assets_result['per_page'],
            "total_pages": assets_result['total_pages'],
            "total_count": assets_result['count']
        },
        "current_status": status
    })