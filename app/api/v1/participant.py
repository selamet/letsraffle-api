"""
Anonymous participant endpoints (authenticated with a participant token)
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_participant_token
from app.models import get_db
from app.models.draw import Draw, Participant
from app.schemas.draw import ParticipantMe, MatchResult
from app.services.match_service import build_match_result

router = APIRouter()


def get_current_participant(
    x_participant_token: str = Header(..., alias="X-Participant-Token"),
    db: Session = Depends(get_db)
) -> Participant:
    """Resolve the participant from the `X-Participant-Token` header."""
    payload = decode_participant_token(x_participant_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid participant token")

    participant = db.query(Participant).filter(
        Participant.id == payload["pid"],
        Participant.draw_id == payload.get("did")
    ).first()
    if not participant:
        # Removed by the organizer or draw deleted.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    return participant


@router.get("/participants/me", response_model=ParticipantMe)
async def get_participant_me(
    participant: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db)
):
    """Return the participant and the current state of their draw."""
    draw = db.query(Draw).filter(Draw.id == participant.draw_id).one()
    return ParticipantMe(
        participant_id=participant.id,
        draw_id=draw.id,
        invite_code=draw.invite_code,
        draw_status=draw.status,
        draw_date=draw.draw_date,
        first_name=participant.first_name
    )


@router.get("/participants/me/result", response_model=MatchResult)
async def get_participant_result(
    participant: Participant = Depends(get_current_participant),
    db: Session = Depends(get_db)
):
    """
    Return who the participant gives a gift to.

    - 409 while the draw has not been completed yet
    """
    draw = db.query(Draw).filter(Draw.id == participant.draw_id).one()
    return build_match_result(db, draw, participant)
