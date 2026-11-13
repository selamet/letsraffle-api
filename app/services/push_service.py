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
from app.utils.names import public_display_name

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
    "participant_joined_digest": {
        "TR": {"title": "Yeni katılımcılar 🎉", "body": "{count} kişi daha katıldı. Toplam {total} kişi oldu."},
        "EN": {"title": "New participants 🎉", "body": "{count} more people joined. {total} in total."},
    },
    "draw_not_run": {
        "TR": {"title": "Çekiliş yapılamadı ⏳", "body": "Şu an {count} katılımcı var, en az 3 gerekiyor. Davet et ya da tarihi güncelle."},
        "EN": {"title": "The draw couldn't run ⏳", "body": "There are {count} participants so far and at least 3 are needed. Invite more people or change the date."},
    },
    "draw_reminder": {
        "TR": {"title": "Çekiliş yarın! 🎄", "body": "Çekilişin 24 saat içinde yapılacak."},
        "EN": {"title": "Draw tomorrow! 🎄", "body": "Your draw takes place within 24 hours."},
    },
}


# The organizer hears about a new participant right away, then at most once per this window.
JOIN_PUSH_COOLDOWN = timedelta(hours=1)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands back naive datetimes; everything is stored in UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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

    def notify_participant_joined(self, draw_id: int, participant_name: str, now: Optional[datetime] = None) -> int:
        """
        Tell the organizer someone joined.

        The first join is announced right away; further joins within JOIN_PUSH_COOLDOWN are left
        for `send_join_digests`, so a busy draw does not buzz the organizer for every person.
        """
        draw = self.db.query(Draw).filter(Draw.id == draw_id).first()
        if not draw or not draw.creator_id:
            return 0
        now = now or datetime.now(timezone.utc)
        last = _aware(draw.join_push_sent_at)
        if last is not None and now - last < JOIN_PUSH_COOLDOWN:
            return 0
        draw.join_push_sent_at = now
        self.db.commit()
        return self._deliver(self._organizer_devices(draw), "participant_joined", draw, name=participant_name)

    def send_join_digests(self, now: Optional[datetime] = None) -> int:
        """Summarize the joins that were held back by the cooldown (one notification per draw)."""
        now = now or datetime.now(timezone.utc)
        draws = self.db.query(Draw).filter(
            Draw.status == DrawStatus.ACTIVE.value,
            Draw.creator_id.isnot(None),
            Draw.join_push_sent_at.isnot(None),
            Draw.join_push_sent_at <= now - JOIN_PUSH_COOLDOWN,
        ).all()

        sent = 0
        for draw in draws:
            newcomers = (
                self.db.query(Participant)
                .filter(Participant.draw_id == draw.id, Participant.created_at > draw.join_push_sent_at)
                .order_by(Participant.id.asc())
                .all()
            )
            if not newcomers:
                continue
            devices = self._organizer_devices(draw)
            if len(newcomers) == 1:
                name = public_display_name(newcomers[0].first_name, newcomers[0].last_name)
                sent += self._deliver(devices, "participant_joined", draw, name=name)
            else:
                total = self.db.query(Participant).filter(Participant.draw_id == draw.id).count()
                sent += self._deliver(
                    devices, "participant_joined_digest", draw,
                    payload_type="participant_joined", count=len(newcomers), total=total,
                )
            draw.join_push_sent_at = now
        self.db.commit()
        return sent

    def notify_draw_not_run(self, draw_id: int, participant_count: int) -> int:
        """Tell the organizer their scheduled draw could not run because too few people joined."""
        draw = self.db.query(Draw).filter(Draw.id == draw_id).first()
        if not draw or not draw.creator_id:
            return 0
        return self._deliver(self._organizer_devices(draw), "draw_not_run", draw, count=participant_count)

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

    def _organizer_devices(self, draw: Draw) -> List[Device]:
        return self.db.query(Device).filter(Device.user_id == draw.creator_id).all()

    def _participant_devices(self, draw_id: int) -> List[Device]:
        return (
            self.db.query(Device)
            .join(DeviceParticipant, DeviceParticipant.device_id == Device.id)
            .join(Participant, Participant.id == DeviceParticipant.participant_id)
            .filter(Participant.draw_id == draw_id)
            .distinct()
            .all()
        )

    def _deliver(self, devices: Iterable[Device], kind: str, draw: Draw, payload_type: Optional[str] = None, **fmt) -> int:
        """`payload_type` is the `type` the app routes on; it defaults to the message kind."""
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
                "type": payload_type or kind,
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
