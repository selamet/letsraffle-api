"""
E-mails around a draw: join confirmation, "draw created" and the day-before reminder.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import decode_participant_token
from app.models.draw import Draw, DrawStatus, DrawType, Participant
from app.services import draw_email_service
from app.services.email_service import EmailService
from app.utils.names import draw_display_name


@pytest.fixture
def email_service():
    with patch.object(EmailService, "_create_ses_client", lambda self: MagicMock()):
        service = EmailService()
        service.ses_client.send_email.return_value = {"MessageId": "1"}
        yield service


def _draw(db, user, language="TR", draw_date=None, code="miskin-penguen-53", participants=1):
    draw = Draw(creator_id=user.id, draw_type=DrawType.DYNAMIC.value, status=DrawStatus.ACTIVE.value,
                invite_code=code, language=language, draw_date=draw_date)
    db.add(draw)
    db.flush()
    for i in range(participants):
        db.add(Participant(draw_id=draw.id, first_name=f"Kişi{i}", last_name="Test", email=f"p{i}@test.com"))
    db.commit()
    return draw


def _sent(service):
    kwargs = service.ses_client.send_email.call_args.kwargs
    return kwargs["Destination"]["ToAddresses"], kwargs["Message"]["Subject"]["Data"], kwargs["Message"]["Body"]["Html"]["Data"]


class TestHelpers:
    @pytest.mark.parametrize("code,expected", [
        ("miskin-penguen-53", "Miskin Penguen No. 53"),
        ("jolly-reindeer-742", "Jolly Reindeer No. 742"),
        ("custom", "Custom"),
        ("", ""),
    ])
    def test_draw_display_name(self, code, expected):
        assert draw_display_name(code) == expected

    def test_draw_date_is_shown_in_turkiye_time_or_utc(self):
        when = datetime(2026, 12, 24, 17, 0, tzinfo=timezone.utc)
        assert EmailService.format_draw_date(when, "TR") == "24 Aralık 2026, 20:00"
        assert EmailService.format_draw_date(when, "EN") == "24 December 2026, 17:00 UTC"
        assert EmailService.format_draw_date(when.replace(tzinfo=None), "TR") == "24 Aralık 2026, 20:00"
        assert EmailService.format_draw_date(None, "TR") is None


class TestJoinConfirmation:
    @pytest.mark.parametrize("language,phrase", [("TR", "Listedesin!"), ("EN", "You're in!")])
    def test_sent_to_the_participant_with_a_status_link(self, test_db, test_user, email_service, language, phrase):
        draw = _draw(test_db, test_user, language=language, draw_date=datetime(2026, 12, 24, 17, 0, tzinfo=timezone.utc))
        participant = test_db.query(Participant).first()

        assert draw_email_service.send_join_confirmation(test_db, participant.id, email_service) is True

        to, subject, html = _sent(email_service)
        assert to == ["p0@test.com"]
        assert "Miskin Penguen No. 53" in subject and "Miskin Penguen No. 53" in html
        assert phrase.replace("'", "&#39;") in html or phrase in html
        assert ("24 Aralık 2026, 20:00" if language == "TR" else "24 December 2026, 17:00 UTC") in html
        token = html.split("/reveal/", 1)[1].split('"', 1)[0]
        assert decode_participant_token(token)["pid"] == participant.id
        assert "{{" not in html and "{%" not in html

    def test_unscheduled_draw_says_the_organizer_starts_it(self, test_db, test_user, email_service):
        draw = _draw(test_db, test_user)
        draw_email_service.send_join_confirmation(test_db, draw.participants[0].id, email_service)
        assert "Organizatör başlattığında" in _sent(email_service)[2]

    def test_missing_participant_sends_nothing(self, test_db, email_service):
        assert draw_email_service.send_join_confirmation(test_db, 999, email_service) is False
        email_service.ses_client.send_email.assert_not_called()

    def test_joining_queues_the_confirmation(self, client, auth_headers, monkeypatch):
        queued = []
        monkeypatch.setattr("app.tasks.email_tasks.send_join_confirmation_email_task.delay", lambda *a: queued.append(a))
        created = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
            "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
        }).json()
        joined = client.post(f"/api/v1/draws/join/{created['inviteCode']}", json={
            "firstName": "Mert", "lastName": "Kaya", "email": "mert@test.com"
        }).json()
        assert queued == [(joined["participantId"],)]


class TestDrawCreated:
    def test_sent_to_the_account_address_with_invite_and_manage_links(self, test_db, test_user, email_service):
        draw = _draw(test_db, test_user)

        assert draw_email_service.send_draw_created(test_db, draw.id, email_service) is True

        to, subject, html = _sent(email_service)
        assert to == [test_user.email]
        assert subject == "🎁 Çekilişin hazır: Miskin Penguen No. 53"
        assert "/draw/join/miskin-penguen-53" in html
        assert "/draws/miskin-penguen-53" in html
        assert "Sevgili Kişi0," in html
        assert "Sen başlattığında" in html

    def test_creating_a_draw_queues_the_email(self, client, auth_headers, monkeypatch):
        queued = []
        monkeypatch.setattr("app.tasks.email_tasks.send_draw_created_email_task.delay", lambda *a: queued.append(a))
        created = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
            "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
        }).json()
        assert queued == [(created["drawId"],)]


class TestReminder:
    def test_sent_once_for_draws_within_24_hours(self, test_db, test_user, email_service):
        now = datetime.now(timezone.utc)
        soon = _draw(test_db, test_user, draw_date=now + timedelta(hours=5), participants=4)
        later = _draw(test_db, test_user, draw_date=now + timedelta(days=3), code="sakar-kizak-120")
        unscheduled = _draw(test_db, test_user, code="obur-simit-777")

        first = draw_email_service.send_due_reminder_emails(test_db, email_service, now=now)
        second = draw_email_service.send_due_reminder_emails(test_db, email_service, now=now)

        assert (first, second) == (1, 0)
        to, subject, html = _sent(email_service)
        assert to == [test_user.email]
        assert subject == "⏰ Çekilişin yarın: Miskin Penguen No. 53"
        assert "4 kişi" in html
        assert "en az 3 katılımcı" not in html
        assert soon.reminder_email_sent_at is not None
        assert later.reminder_email_sent_at is None and unscheduled.reminder_email_sent_at is None

    def test_warns_when_there_are_too_few_participants(self, test_db, test_user, email_service):
        now = datetime.now(timezone.utc)
        _draw(test_db, test_user, language="EN", draw_date=now + timedelta(hours=2), participants=2)
        draw_email_service.send_due_reminder_emails(test_db, email_service, now=now)
        html = _sent(email_service)[2]
        assert "2 people" in html
        assert "at least 3 participants" in html

    def test_failed_send_is_retried_next_time(self, test_db, test_user, email_service):
        now = datetime.now(timezone.utc)
        draw = _draw(test_db, test_user, draw_date=now + timedelta(hours=2))
        email_service.ses_client.send_email.side_effect = RuntimeError("boom")
        assert draw_email_service.send_due_reminder_emails(test_db, email_service, now=now) == 0
        assert draw.reminder_email_sent_at is None
        email_service.ses_client.send_email.side_effect = None
        assert draw_email_service.send_due_reminder_emails(test_db, email_service, now=now) == 1
