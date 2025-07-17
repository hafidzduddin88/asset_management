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

class AssetStatus(str, enum.Enum):
    ACTIVE = "active"
    DAMAGED = "damaged"
    REPAIRED = "repaired"
    DISPOSED = "disposed"

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
    assets = relationship("Asset", back_populates="owner")
    approvals = relationship("Approval", back_populates="admin")
    approval_requests = relationship("Approval", back_populates="requester", foreign_keys="Approval.requester_id")

class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    asset_tag = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    category = Column(String, index=True)
    location = Column(String, index=True)
    purchase_date = Column(DateTime)
    purchase_cost = Column(String)
    status = Column(Enum(AssetStatus), default=AssetStatus.ACTIVE)
    photo_url = Column(String)
    photo_drive_id = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    owner = relationship("User", back_populates="assets")
    approvals = relationship("Approval", back_populates="asset")
    damages = relationship("Damage", back_populates="asset")
    relocations = relationship("Relocation", back_populates="asset")
    disposals = relationship("Disposal", back_populates="asset")

class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, index=True)  # add, edit, relocate, dispose, damage, repair
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    request_data = Column(Text)  # JSON data of the request
    notes = Column(Text)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    requester_id = Column(Integer, ForeignKey("users.id"))
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    asset = relationship("Asset", back_populates="approvals")
    requester = relationship("User", foreign_keys=[requester_id], back_populates="approval_requests")
    admin = relationship("User", foreign_keys=[admin_id], back_populates="approvals")

class Damage(Base):
    __tablename__ = "damages"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    reported_by = Column(Integer, ForeignKey("users.id"))
    damage_date = Column(DateTime, default=datetime.utcnow)
    description = Column(Text)
    photo_url = Column(String)
    is_repaired = Column(Boolean, default=False)
    repair_date = Column(DateTime, nullable=True)
    repair_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    asset = relationship("Asset", back_populates="damages")
    reporter = relationship("User")

class Relocation(Base):
    __tablename__ = "relocations"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    previous_location = Column(String)
    new_location = Column(String)
    relocated_by = Column(Integer, ForeignKey("users.id"))
    relocation_date = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    asset = relationship("Asset", back_populates="relocations")
    user = relationship("User")

class Disposal(Base):
    __tablename__ = "disposals"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    disposed_by = Column(Integer, ForeignKey("users.id"))
    disposal_date = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text)
    notes = Column(Text)
    evidence_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    asset = relationship("Asset", back_populates="disposals")
    user = relationship("User")