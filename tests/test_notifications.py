"""
Organizer notifications: join digest and "the draw could not run".
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.device import Device
from app.models.draw import Draw, DrawStatus, DrawType, Participant
from app.services import draw_email_service
from app.services.email_service import EmailService
from app.services.push_service import PushService
from app.tasks import draw as draw_tasks
from tests.test_push import FakeAPNs, apns_key  # noqa: F401  (fixture)

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)


def _draw(db, user, language="TR", draw_date=None):
    draw = Draw(creator_id=user.id, draw_type=DrawType.DYNAMIC.value, status=DrawStatus.ACTIVE.value,
                invite_code="miskin-penguen-53", language=language, draw_date=draw_date)
    db.add(draw)
    db.flush()
    db.add(Device(token="org-device", language=language, user_id=user.id))
    db.commit()
    return draw


def _join(db, draw, name, at):
    participant = Participant(draw_id=draw.id, first_name=name, last_name="Kaya", email=f"{name.lower()}@test.com", created_at=at)
    db.add(participant)
    db.commit()
    return participant


def _alerts(fake):
    return [json.loads(r.content) for r in fake.requests]


class TestJoinDigest:
    def test_first_join_is_announced_and_the_next_ones_wait(self, test_db, test_user, apns_key):
        draw = _draw(test_db, test_user)
        fake = FakeAPNs()
        service = PushService(test_db, fake.client(apns_key[1]))

        first = service.notify_participant_joined(draw.id, "Mert K.", now=NOW)
        second = service.notify_participant_joined(draw.id, "Ayşe D.", now=NOW + timedelta(minutes=10))

        assert (first, second) == (1, 0)
        assert _alerts(fake)[0]["aps"]["alert"]["body"] == "Mert K. çekilişine katıldı."

    def test_held_back_joins_are_summarized_once(self, test_db, test_user, apns_key):
        draw = _draw(test_db, test_user)
        fake = FakeAPNs()
        service = PushService(test_db, fake.client(apns_key[1]))
        _join(test_db, draw, "Mert", NOW)
        service.notify_participant_joined(draw.id, "Mert K.", now=NOW)
        _join(test_db, draw, "Ayşe", NOW + timedelta(minutes=10))
        _join(test_db, draw, "Can", NOW + timedelta(minutes=20))

        too_early = service.send_join_digests(now=NOW + timedelta(minutes=30))
        digest = service.send_join_digests(now=NOW + timedelta(hours=1))
        again = service.send_join_digests(now=NOW + timedelta(hours=3))

        assert (too_early, digest, again) == (0, 1, 0)
        payload = _alerts(fake)[-1]
        assert payload["aps"]["alert"]["body"] == "2 kişi daha katıldı. Toplam 3 kişi oldu."
        # the app routes on the type it already knows
        assert payload["type"] == "participant_joined"
        assert payload["inviteCode"] == "miskin-penguen-53"

    def test_a_single_held_back_join_is_named(self, test_db, test_user, apns_key):
        draw = _draw(test_db, test_user, language="EN")
        fake = FakeAPNs()
        service = PushService(test_db, fake.client(apns_key[1]))
        service.notify_participant_joined(draw.id, "Mert K.", now=NOW)
        _join(test_db, draw, "Ayşe", NOW + timedelta(minutes=10))

        assert service.send_join_digests(now=NOW + timedelta(hours=2)) == 1
        assert _alerts(fake)[-1]["aps"]["alert"]["body"] == "Ayşe K. joined your draw."

    def test_join_after_the_cooldown_is_announced_right_away(self, test_db, test_user, apns_key):
        draw = _draw(test_db, test_user)
        fake = FakeAPNs()
        service = PushService(test_db, fake.client(apns_key[1]))
        service.notify_participant_joined(draw.id, "Mert K.", now=NOW)
        assert service.notify_participant_joined(draw.id, "Ayşe D.", now=NOW + timedelta(hours=2)) == 1


class TestDrawNotRun:
    def test_push_tells_the_organizer_how_many_joined(self, test_db, test_user, apns_key):
        draw = _draw(test_db, test_user)
        fake = FakeAPNs()

        sent = PushService(test_db, fake.client(apns_key[1])).notify_draw_not_run(draw.id, 2)

        assert sent == 1
        payload = _alerts(fake)[0]
        assert payload["type"] == "draw_not_run"
        assert "2 katılımcı" in payload["aps"]["alert"]["body"]

    def test_organizer_is_notified_once_per_schedule(self, test_db, test_user, monkeypatch):
        draw = _draw(test_db, test_user, draw_date=NOW - timedelta(hours=1))
        pushes, emails = [], []
        monkeypatch.setattr("app.tasks.push_tasks.send_draw_not_run_push_task.delay", lambda *a: pushes.append(a))
        monkeypatch.setattr("app.tasks.email_tasks.send_draw_not_run_email_task.delay", lambda *a: emails.append(a))

        first = draw_tasks._notify_not_run(test_db, draw, 2, NOW)
        second = draw_tasks._notify_not_run(test_db, draw, 2, NOW + timedelta(hours=1))

        assert (first, second) == (True, False)
        assert pushes == [(draw.id, 2)] and emails == [(draw.id,)]

    def test_new_date_re_arms_the_notices(self, client, auth_headers, test_db, test_user):
        draw = _draw(test_db, test_user, draw_date=NOW - timedelta(hours=1))
        draw.not_run_notified_at = NOW
        draw.reminder_sent_at = NOW
        draw.reminder_email_sent_at = NOW
        test_db.commit()
        new_date = (datetime.now(timezone.utc) + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)

        response = client.put(f"/api/v1/draws/{draw.id}/schedule", headers=auth_headers, json={"drawDate": new_date.isoformat()})

        assert response.status_code == 200
        test_db.refresh(draw)
        assert draw.not_run_notified_at is None
        assert draw.reminder_sent_at is None and draw.reminder_email_sent_at is None

    def test_email_explains_what_to_do(self, test_db, test_user):
        draw = _draw(test_db, test_user, draw_date=datetime(2026, 12, 24, 17, 0, tzinfo=timezone.utc))
        _join(test_db, draw, "Selamet", NOW)
        _join(test_db, draw, "Mert", NOW)
        with patch.object(EmailService, "_create_ses_client", lambda self: MagicMock()):
            service = EmailService()
            service.ses_client.send_email.return_value = {"MessageId": "1"}

            assert draw_email_service.send_draw_not_run(test_db, draw.id, service) is True

            kwargs = service.ses_client.send_email.call_args.kwargs
        assert kwargs["Destination"]["ToAddresses"] == [test_user.email]
        assert kwargs["Message"]["Subject"]["Data"] == "⏳ Çekiliş yapılamadı: Miskin Penguen No. 53"
        html = kwargs["Message"]["Body"]["Html"]["Data"]
        assert "2 kişi" in html and "24 Aralık 2026, 20:00" in html
        assert "/draws/miskin-penguen-53" in html
