"""
Lookup helpers for draw matches
"""

from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.draw import Draw, DrawResult, DrawStatus, Participant
from app.schemas.draw import MatchReceiver, MatchResult


def find_match_receiver(db: Session, draw_id: int, giver_participant_id: int) -> Optional[Participant]:
    """Return the participant the giver was matched with, if the draw has results."""
    result = db.query(DrawResult).filter(
        DrawResult.draw_id == draw_id,
        DrawResult.giver_participant_id == giver_participant_id
    ).first()
    if not result:
        return None
    return db.query(Participant).filter(Participant.id == result.receiver_participant_id).first()


def build_match_result(db: Session, draw: Draw, participant: Participant) -> MatchResult:
    """
    Build the in-app result for a participant.

    Raises 409 while the draw is not completed and 404 if no match exists.
    """
    if draw.status != DrawStatus.COMPLETED.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draw not completed")

    receiver = find_match_receiver(db, draw.id, participant.id)
    if not receiver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    return MatchResult(
        draw_id=draw.id,
        invite_code=draw.invite_code,
        receiver=MatchReceiver(
            first_name=receiver.first_name,
            last_name=receiver.last_name,
            address=receiver.address,
            phone=receiver.phone
        )
    )
