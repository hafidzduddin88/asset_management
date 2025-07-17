# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    """Base schema for user."""
    username: str
    email: EmailStr
    full_name: str

class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str
    role: str = "staff"

class UserUpdate(BaseModel):
    """Schema for updating a user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    role: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True

class Token(BaseModel):
    """Schema for JWT token."""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Schema for JWT token data."""
    username: Optional[str] = None
    role: Optional[str] = None