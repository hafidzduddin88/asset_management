from typing import Optional
from datetime import datetime
from app.utils.auth import UserRole
from pydantic import BaseModel

class ProfileResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    photo_url: Optional[str] = None
    business_unit: Optional[str] = None
    last_login_at: Optional[datetime] = None
    
    # Computed fields for compatibility
    @property
    def email(self) -> str:
        return self.username
    
    @property
    def auth_user_id(self) -> str:
        return self.id

    class Config:
        from_attributes = True