from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from datetime import datetime

from app.database.database import Base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.STAFF)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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