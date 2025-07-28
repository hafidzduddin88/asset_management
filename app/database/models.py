from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime

from app.database.database import Base

class UserRole(enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String)
    full_name = Column(String)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.STAFF)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    photo_url = Column(String)
    last_login = Column(DateTime(timezone=True))
    remember_token = Column(String)

