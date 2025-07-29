from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    staff = "staff"


class ProfileSchema(BaseModel):
    id: UUID
    auth_user_id: UUID
    email: EmailStr
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    photo_url: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True  # formerly orm_mode
