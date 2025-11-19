import datetime

from enum import Enum
from app.models.base import BaseModel
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, UniqueConstraint


class DrawType(str, Enum):
    MANUAL = "manual"
    DYNAMIC = "dynamic"


class DrawStatus(str, Enum):
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Language(str, Enum):
    TR = "TR"
    EN = "EN"


class Draw(BaseModel):
    """Draw a model representing a gift exchange event."""

    __tablename__ = "draws"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    creator = relationship("User", backref="created_draws", foreign_keys=[creator_id], passive_deletes=True)
    status = Column(String(50), default=DrawStatus.ACTIVE.value, nullable=False)
    draw_type = Column(String(50), default=DrawType.MANUAL.value, nullable=False)
    draw_date = Column(DateTime(timezone=True), nullable=True)
    require_address = Column(Boolean(False), default=False)
    require_phone = Column(Boolean(False), default=False)
    invite_code = Column(String(255), unique=True, nullable=True, index=True)
    language = Column(String(2), default=Language.TR.value, nullable=False)

    participants = relationship("Participant", back_populates="draw", cascade="all, delete-orphan")

    @property
    def is_active(self) -> bool:
        if not self.draw_date:
            return False
        try:
            from datetime import timezone
            now = datetime.datetime.now(timezone.utc)
        except (AttributeError, ImportError):
            now = datetime.datetime.utcnow()
        return self.status == DrawStatus.ACTIVE.value and self.draw_date > now

    def __repr__(self):
        return f"<Draw(id={self.id}, creator_id={self.creator_id}, status={self.status})>"


class Participant(BaseModel):
    """Participant model representing a person in a draw."""

    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    draw_id = Column(Integer, ForeignKey("draws.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)

    draw = relationship("Draw", back_populates="participants")

    def __repr__(self):
        return f"<Participant(id={self.id}, name={self.first_name} {self.last_name}, draw_id={self.draw_id})>"


class DrawResult(BaseModel):
    """DrawResult model representing the result of a draw (who gives to whom)."""

    __tablename__ = "draw_results"
    __table_args__ = (
        UniqueConstraint('draw_id', 'giver_participant_id', name='uq_draw_giver'),
    )

    id = Column(Integer, primary_key=True, index=True)
    draw_id = Column(Integer, ForeignKey("draws.id", ondelete="CASCADE"), nullable=False, index=True)
    giver_participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True)

    # Relationships
    draw = relationship("Draw", foreign_keys=[draw_id])
    giver = relationship("Participant", foreign_keys=[giver_participant_id])
    receiver = relationship("Participant", foreign_keys=[receiver_participant_id])

    def __repr__(self):
        return f"<DrawResult(id={self.id}, draw_id={self.draw_id}, giver={self.giver_participant_id} -> receiver={self.receiver_participant_id})>"