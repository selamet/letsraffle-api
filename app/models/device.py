"""
Push notification device registrations
"""

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Device(BaseModel):
    """An app installation that can receive push notifications."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(255), unique=True, index=True, nullable=False)
    platform = Column(String(20), nullable=False, default="ios")
    language = Column(String(2), nullable=False, default="TR")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    participant_links = relationship("DeviceParticipant", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Device(id={self.id}, platform={self.platform}, user_id={self.user_id})>"


class DeviceParticipant(BaseModel):
    """Links a device to participants that joined a draw from it (no account needed)."""

    __tablename__ = "device_participants"
    __table_args__ = (
        UniqueConstraint("device_id", "participant_id", name="uq_device_participant"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True)

    device = relationship("Device", back_populates="participant_links")
