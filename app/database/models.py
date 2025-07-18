from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime

from app.database.database import Base

# User roles as constants
ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_USER = "user"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    email = Column(String)
    full_name = Column(String)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    photo_url = Column(String)
    last_login = Column(DateTime(timezone=True))
    remember_token = Column(String)

    # Relationships
    approvals = relationship("Approval", back_populates="admin", foreign_keys="Approval.admin_id")
    approval_requests = relationship("Approval", back_populates="requester", foreign_keys="Approval.requester_id")

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, index=True)  # add, edit, relocate, dispose, damage, repair
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    request_data = Column(Text)  # JSON data of the request including asset_id/asset_tag
    notes = Column(Text)
    requester_id = Column(Integer, ForeignKey("users.id"))
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    requester = relationship("User", foreign_keys=[requester_id], back_populates="approval_requests")
    admin = relationship("User", foreign_keys=[admin_id], back_populates="approvals")