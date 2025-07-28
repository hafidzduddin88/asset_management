from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum as SqlEnum
from sqlalchemy.sql import func
from app.database.database import Base

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), nullable=True)
    full_name = Column(String(100), nullable=True)
    role = Column(SqlEnum(UserRole, name="user_role", native_enum=True), nullable=False, default=UserRole.STAFF)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    photo_url = Column(Text, nullable=True)
    remember_token = Column(String(64), nullable=True)