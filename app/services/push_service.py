"""
Push notification use cases (match revealed, participant joined, draw reminder)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device, DeviceParticipant
from app.models.draw import Draw, DrawStatus, Participant
from app.services.apns_client import APNsClient, APNsConfig, DeliveryResult

logger = logging.getLogger(__name__)

MESSAGES: Dict[str, Dict[str, Dict[str, str]]] = {
    "match_revealed": {
        "TR": {"title": "Çekiliş tamamlandı! 🎁", "body": "Kime hediye alacağını görmek için dokun."},
        "EN": {"title": "The draw is complete! 🎁", "body": "Tap to see who you're gifting."},
    },
    "participant_joined": {
        "TR": {"title": "Yeni katılımcı 🎉", "body": "{name} çekilişine katıldı."},
        "EN": {"title": "New participant 🎉", "body": "{name} joined your draw."},
    },
    "draw_reminder": {
        "TR": {"title": "Çekiliş yarın! 🎄", "body": "Çekilişin 24 saat içinde yapılacak."},
        "EN": {"title": "Draw tomorrow! 🎄", "body": "Your draw takes place within 24 hours."},
    },
}


class PushService:
    def __init__(self, db: Session, client: Optional[APNsClient] = None):
        self.db = db
        if client is None:
            config = APNsConfig.from_settings()
            client = APNsClient(config) if config else None
        self.client = client

    @property
    def enabled(self) -> bool:
        return self.client is not None

    # Use cases

    def notify_match_revealed(self, draw_id: int) -> int:
        draw = self.db.query(Draw).filter(Draw.id == draw_id).first()
        if not draw:
            return 0
        return self._deliver(self._participant_devices(draw.id), "match_revealed", draw)

    def notify_participant_joined(self, draw_id: int, participant_name: str) -> int:
        draw = self.db.query(Draw).filter(Draw.id == draw_id).first()
        if not draw or not draw.creator_id:
            return 0
        devices = self.db.query(Device).filter(Device.user_id == draw.creator_id).all()
        return self._deliver(devices, "participant_joined", draw, name=participant_name)

    def send_due_reminders(self, now: Optional[datetime] = None) -> int:
        """Notify organizers and participants of draws happening within 24 hours (once per draw)."""
        now = now or datetime.now(timezone.utc)
        draws = self.db.query(Draw).filter(
            Draw.status == DrawStatus.ACTIVE.value,
            Draw.draw_date.isnot(None),
            Draw.draw_date > now,
            Draw.draw_date <= now + timedelta(hours=24),
            Draw.reminder_sent_at.is_(None),
        ).all()

        sent = 0
        for draw in draws:
            devices = {d.id: d for d in self._participant_devices(draw.id)}
            if draw.creator_id:
                for device in self.db.query(Device).filter(Device.user_id == draw.creator_id):
                    devices[device.id] = device
            sent += self._deliver(devices.values(), "draw_reminder", draw)
            draw.reminder_sent_at = now
        self.db.commit()
        return sent

    # Internals

    def _participant_devices(self, draw_id: int) -> List[Device]:
        return (
            self.db.query(Device)
            .join(DeviceParticipant, DeviceParticipant.device_id == Device.id)
            .join(Participant, Participant.id == DeviceParticipant.participant_id)
            .filter(Participant.draw_id == draw_id)
            .distinct()
            .all()
        )

    def _deliver(self, devices: Iterable[Device], kind: str, draw: Draw, **fmt) -> int:
        if not self.enabled:
            return 0
        sent = 0
        invalid: List[Device] = []
        for device in devices:
            text = MESSAGES[kind].get(device.language, MESSAGES[kind]["TR"])
            payload = {
                "aps": {
                    "alert": {"title": text["title"], "body": text["body"].format(**fmt)},
                    "sound": "default",
                },
                "type": kind,
                "drawId": draw.id,
                "inviteCode": draw.invite_code,
            }
            result = self.client.send(device.token, payload)
            if result == DeliveryResult.SENT:
                sent += 1
            elif result == DeliveryResult.INVALID_TOKEN:
                invalid.append(device)
        for device in invalid:
            self.db.delete(device)
        if invalid:
            self.db.commit()
        logger.info(f"Push '{kind}' for draw {draw.id}: sent={sent}, removed_tokens={len(invalid)}")
        return sent
