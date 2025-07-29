from pydantic import BaseModel, EmailStr
from uuid import UUID
from enum import Enum
from typing import Optional
from datetime import datetime


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"


class ProfileSchema(BaseModel):
    id: UUID
    auth_user_id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    photo_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True
