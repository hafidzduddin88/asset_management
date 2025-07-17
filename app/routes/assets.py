# app/routes/assets.py
from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database.database import get_db
from app.database.models import Asset, User, AssetStatus
from app.database.dependencies import get_current_active_user

router = APIRouter(tags=["assets"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/assets", response_class=HTMLResponse)
async def list_assets(
    request: Request,
    status: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List assets with optional filtering."""
    query = db.query(Asset)
    
    # Apply filters
    if status:
        query = query.filter(Asset.status == status)
    if category:
        query = query.filter(Asset.category == category)
    if location:
        query = query.filter(Asset.location == location)
    if search:
        query = query.filter(
            Asset.name.ilike(f"%{search}%") | 
            Asset.asset_tag.ilike(f"%{search}%") |
            Asset.description.ilike(f"%{search}%")
        )
    
    # Get assets
    assets = query.order_by(Asset.created_at.desc()).all()
    
    # Get filter options
    categories = db.query(Asset.category).distinct().all()
    locations = db.query(Asset.location).distinct().all()
    
    return templates.TemplateResponse(
        "assets/list.html",
        {
            "request": request,
            "user": current_user,
            "assets": assets,
            "categories": [c[0] for c in categories if c[0]],
            "locations": [l[0] for l in locations if l[0]],
            "statuses": [s.value for s in AssetStatus],
            "selected_status": status,
            "selected_category": category,
            "selected_location": location,
            "search": search
        }
    )

@router.get("/assets/{asset_id}", response_class=HTMLResponse)
async def asset_detail(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Asset detail page."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)
    
    return templates.TemplateResponse(
        "assets/detail.html",
        {
            "request": request,
            "user": current_user,
            "asset": asset
        }
    )