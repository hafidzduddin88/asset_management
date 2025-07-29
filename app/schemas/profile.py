from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.database.models import UserRole

class ProfileResponse(BaseModel):
    id: str
    auth_user_id: str
    email: str
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    photo_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True