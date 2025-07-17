# app/routes/api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.database.models import Asset, User
from app.database.dependencies import get_current_active_user, get_admin_user
from app.schemas.asset import AssetCreate, AssetResponse, AssetUpdate

router = APIRouter(prefix="/api", tags=["API"])

@router.get("/assets", response_model=List[AssetResponse])
async def get_assets(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all assets."""
    assets = db.query(Asset).offset(skip).limit(limit).all()
    return assets

@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get asset by ID."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.post("/assets", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset: AssetCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Create new asset (admin only)."""
    db_asset = Asset(**asset.dict(), owner_id=current_user.id)
    db.add(db_asset)
    db.commit()
    db.refresh(db_asset)
    return db_asset

@router.put("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: int, 
    asset: AssetUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
):
    """Update asset (admin only)."""
    db_asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if db_asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    for key, value in asset.dict(exclude_unset=True).items():
        setattr(db_asset, key, value)
    
    db.commit()
    db.refresh(db_asset)
    return db_asset