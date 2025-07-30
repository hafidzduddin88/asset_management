# /app/database/models.py

from enum import Enum
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Enum as SqlEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database.database import Base
import uuid

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    username = Column(String(255), unique=True, nullable=False)
    full_name = Column(Text, nullable=True)
    role = Column(
        SqlEnum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.STAFF
    )
    is_active = Column(Boolean, nullable=False, default=True)
    photo_url = Column(Text, nullable=True)
    business_unit = Column(Text, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
