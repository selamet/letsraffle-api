"""
Push notification device registration endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional
from app.core.security import decode_participant_token
from app.models import get_db, User
from app.models.device import Device, DeviceParticipant
from app.models.draw import Participant
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/devices", response_model=DeviceRegisterResponse)
async def register_device(
    request: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Register (upsert) an APNs device token.

    - With a bearer token the device is linked to the user (organizer notifications)
    - Without one, any previous user link is cleared (e.g. after logout)
    - Valid `participantTokens` link anonymous participations; invalid ones are ignored
    """
    device = db.query(Device).filter(Device.token == request.token).first()
    if not device:
        device = Device(token=request.token)
        db.add(device)

    device.platform = request.platform
    device.language = request.language
    device.user_id = current_user.id if current_user else None
    db.flush()

    linked_ids = {link.participant_id for link in device.participant_links}
    for participant_token in request.participant_tokens:
        payload = decode_participant_token(participant_token)
        if not payload or payload["pid"] in linked_ids:
            continue
        exists = db.query(Participant.id).filter(
            Participant.id == payload["pid"], Participant.draw_id == payload.get("did")
        ).first()
        if exists:
            device.participant_links.append(DeviceParticipant(participant_id=payload["pid"]))
            linked_ids.add(payload["pid"])

    db.commit()
    logger.info(f"Device registered: device_id={device.id}, user_id={device.user_id}, participants={len(linked_ids)}")

    return DeviceRegisterResponse(user_linked=device.user_id is not None, participant_count=len(linked_ids))


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(token: str, db: Session = Depends(get_db)):
    """Remove a device token (logout / notifications disabled). Idempotent."""
    device = db.query(Device).filter(Device.token == token).first()
    if device:
        db.delete(device)
        db.commit()
