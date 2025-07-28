from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, Enum as SqlEnum
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum

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
    email = Column(String(100), unique=True, index=True, nullable=True)
    full_name = Column(String(100), nullable=True)

    role = Column(
        SqlEnum(
            UserRole,
            native_enum=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls]  # penting!
        ),
        nullable=False,
        default=UserRole.STAFF
    )

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    photo_url = Column(Text, nullable=True)
    remember_token = Column(String(64), nullable=True)