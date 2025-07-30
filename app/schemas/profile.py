from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.database.models import UserRole

class ProfileResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    business_unit: Optional[str] = None
    role: UserRole
    is_active: bool
    photo_url: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Computed fields for compatibility
    @property
    def email(self) -> str:
        return self.username
    
    @property
    def auth_user_id(self) -> str:
        return self.id

    class Config:
        from_attributes = True