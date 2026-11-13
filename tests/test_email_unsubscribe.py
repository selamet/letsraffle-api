"""
Announcement e-mails: opt-out link, recipients and rendering.
"""
from email import message_from_string
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import create_participant_token, create_unsubscribe_token, decode_unsubscribe_token
from app.models.draw import Draw, Participant
from app.models.email import CampaignEmail, EmailUnsubscribe
from app.models.user import User
from app.services.announcement_service import collect_recipients, mark_sent
from app.services.email_service import EmailService

URL = "/api/v1/email/unsubscribe"
CAMPAIGN = "2027-launch"


@pytest.fixture
def email_service():
    with patch.object(EmailService, "_create_ses_client", lambda self: MagicMock()):
        yield EmailService()


class TestUnsubscribeToken:
    def test_round_trip_normalizes_address_and_language(self):
        payload = decode_unsubscribe_token(create_unsubscribe_token("  Ayse@Test.com ", "EN"))
        assert payload == {"email": "ayse@test.com", "lang": "en"}

    def test_other_token_types_are_rejected(self):
        assert decode_unsubscribe_token(create_participant_token(1, 1)) is None
        assert decode_unsubscribe_token("garbage") is None
        assert decode_unsubscribe_token("") is None


class TestUnsubscribeEndpoint:
    def test_opening_the_link_changes_nothing(self, client, test_db):
        response = client.get(URL, params={"token": create_unsubscribe_token("a@test.com", "TR")})
        assert response.status_code == 200
        assert "Listeden çık" in response.text and 'method="post"' in response.text
        assert test_db.query(EmailUnsubscribe).count() == 0

    def test_post_unsubscribes_and_is_idempotent(self, client, test_db):
        params = {"token": create_unsubscribe_token("A@Test.com", "EN")}
        first = client.post(URL, params=params)
        second = client.post(URL, params=params, data={"List-Unsubscribe": "One-Click"})
        assert first.status_code == 200 and second.status_code == 200
        assert "You are unsubscribed" in first.text
        assert [row.email for row in test_db.query(EmailUnsubscribe).all()] == ["a@test.com"]

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_invalid_token(self, client, test_db, method):
        response = getattr(client, method)(URL, params={"token": "nope"})
        assert response.status_code == 400
        assert test_db.query(EmailUnsubscribe).count() == 0


class TestRecipients:
    def _seed(self, db):
        organizer = User(email="Organizer@test.com", password="x")
        loner = User(email="loner@test.com", password="x")
        db.add_all([organizer, loner])
        db.flush()
        draw = Draw(creator_id=organizer.id, language="EN")
        db.add(draw)
        db.flush()
        db.add_all([
            Participant(draw_id=draw.id, first_name="Org", last_name="A", email="organizer@test.com"),
            Participant(draw_id=draw.id, first_name="Guest", last_name="B", email="guest@test.com"),
            Participant(draw_id=draw.id, first_name="Bad", last_name="C", email="not-an-address"),
        ])
        db.commit()

    def test_users_only_by_default_with_draw_language(self, test_db):
        self._seed(test_db)
        assert collect_recipients(test_db, CAMPAIGN) == [("loner@test.com", "TR"), ("organizer@test.com", "EN")]

    def test_all_audience_adds_participants(self, test_db):
        self._seed(test_db)
        emails = [email for email, _ in collect_recipients(test_db, CAMPAIGN, "all")]
        assert emails == ["guest@test.com", "loner@test.com", "organizer@test.com"]

    def test_unsubscribed_and_already_sent_are_skipped(self, test_db):
        self._seed(test_db)
        test_db.add(EmailUnsubscribe(email="loner@test.com"))
        test_db.commit()
        mark_sent(test_db, CAMPAIGN, "Organizer@test.com")
        assert collect_recipients(test_db, CAMPAIGN) == []
        assert [email for email, _ in collect_recipients(test_db, "another-campaign")] == ["organizer@test.com"]
        assert test_db.query(CampaignEmail).count() == 1


class TestAnnouncementEmail:
    @pytest.mark.parametrize("language,phrase", [("TR", "Çekilişini başlat"), ("EN", "Start your draw")])
    def test_render_has_unsubscribe_link_and_assets(self, email_service, language, phrase):
        subject, html, text, link = email_service.render_announcement(CAMPAIGN, "ayse@test.com", language)
        token = link.split("token=", 1)[1]
        assert decode_unsubscribe_token(token) == {"email": "ayse@test.com", "lang": language.lower()}
        assert "/api/v1/email/unsubscribe?token=" in link
        assert link in html and link in text
        assert phrase in html
        assert "2027" in subject
        assert f"/email/2027/poster-{language.lower()}.jpg" in html
        assert "apps.apple.com" in html
        assert "{{" not in html and "IMG/" not in html

    def test_send_sets_one_click_unsubscribe_headers(self, email_service):
        email_service.ses_client.send_raw_email.return_value = {"MessageId": "1"}
        assert email_service.send_announcement_email(CAMPAIGN, "ayse@test.com", "TR") is True
        kwargs = email_service.ses_client.send_raw_email.call_args.kwargs
        assert kwargs["Destinations"] == ["ayse@test.com"]
        message = message_from_string(kwargs["RawMessage"]["Data"])
        assert message["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "/api/v1/email/unsubscribe?token=" in message["List-Unsubscribe"].replace("\n", "").replace(" ", "")
        assert message["To"] == "ayse@test.com"

    def test_send_failure_returns_false(self, email_service):
        email_service.ses_client.send_raw_email.side_effect = RuntimeError("boom")
        assert email_service.send_announcement_email(CAMPAIGN, "ayse@test.com", "TR") is False
