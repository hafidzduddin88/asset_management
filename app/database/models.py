from enum import Enum
from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.database import Base

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default="uuid_generate_v4()")
    auth_user_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    email = Column(String(100), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(SqlEnum(UserRole, name="user_role", native_enum=False), nullable=False, default=UserRole.STAFF)
    is_active = Column(Boolean, nullable=False, default=True)
    photo_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)