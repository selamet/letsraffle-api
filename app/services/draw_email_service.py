"""
E-mails around a draw's life cycle that are not the result itself:
the organizer's "created" summary, a participant's join confirmation and the day-before reminder.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.draw import Draw, DrawStatus, Participant
from app.models.user import User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


def _organizer(db: Session, draw: Draw) -> Optional[Participant]:
    """The organizer is the first participant of a dynamic draw."""
    return (
        db.query(Participant)
        .filter(Participant.draw_id == draw.id)
        .order_by(Participant.id.asc())
        .first()
    )


def send_join_confirmation(db: Session, participant_id: int, service: Optional[EmailService] = None) -> bool:
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if not participant:
        return False
    draw = db.query(Draw).filter(Draw.id == participant.draw_id).first()
    if not draw:
        return False
    return (service or EmailService()).send_join_confirmation_email(participant, draw)


def send_draw_created(db: Session, draw_id: int, service: Optional[EmailService] = None) -> bool:
    draw = db.query(Draw).filter(Draw.id == draw_id).first()
    if not draw or not draw.creator_id:
        return False
    creator = db.query(User).filter(User.id == draw.creator_id).first()
    if not creator:
        return False
    organizer = _organizer(db, draw)
    return (service or EmailService()).send_draw_created_email(
        draw, creator.email, organizer.first_name if organizer else ""
    )


def send_due_reminder_emails(db: Session, service: Optional[EmailService] = None, now: Optional[datetime] = None) -> int:
    """E-mail organizers whose draw takes place within 24 hours (once per draw). Returns how many were sent."""
    now = now or datetime.now(timezone.utc)
    draws = db.query(Draw).filter(
        Draw.status == DrawStatus.ACTIVE.value,
        Draw.creator_id.isnot(None),
        Draw.draw_date.isnot(None),
        Draw.draw_date > now,
        Draw.draw_date <= now + timedelta(hours=24),
        Draw.reminder_email_sent_at.is_(None),
    ).all()
    if not draws:
        return 0

    service = service or EmailService()
    sent = 0
    for draw in draws:
        creator = db.query(User).filter(User.id == draw.creator_id).first()
        if not creator:
            continue
        organizer = _organizer(db, draw)
        count = db.query(Participant).filter(Participant.draw_id == draw.id).count()
        if service.send_draw_reminder_email(draw, creator.email, organizer.first_name if organizer else "", count):
            # only marked on success, so a failed send is retried on the next run
            draw.reminder_email_sent_at = now
            db.commit()
            sent += 1
    return sent
