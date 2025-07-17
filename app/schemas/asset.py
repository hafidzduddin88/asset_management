# app/schemas/asset.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AssetBase(BaseModel):
    """Base schema for asset."""
    name: str
    asset_tag: str
    description: str
    category: str
    location: str
    purchase_cost: Optional[str] = None
    photo_url: Optional[str] = None
    photo_drive_id: Optional[str] = None

class AssetCreate(AssetBase):
    """Schema for creating an asset."""
    purchase_date: Optional[datetime] = None

class AssetUpdate(BaseModel):
    """Schema for updating an asset."""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    purchase_cost: Optional[str] = None
    purchase_date: Optional[datetime] = None
    status: Optional[str] = None
    photo_url: Optional[str] = None
    photo_drive_id: Optional[str] = None

class AssetResponse(AssetBase):
    """Schema for asset response."""
    id: int
    status: str
    purchase_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    owner_id: int
    
    class Config:
        orm_mode = True