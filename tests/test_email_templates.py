"""
Draw result / password reset emails: the result email links to the reveal page
and never contains the receiver's details.
"""
from unittest.mock import patch

import pytest

from app.core.security import decode_participant_token
from app.models.draw import Draw, Participant
from app.services.email_service import EmailService


@pytest.fixture
def email_service():
    with patch.object(EmailService, "_create_ses_client", lambda self: None):
        yield EmailService()


@pytest.mark.parametrize("language", ["TR", "EN"])
def test_result_email_links_to_reveal_page_without_receiver(email_service, language):
    draw = Draw(id=12, language=language)
    giver = Participant(id=34, first_name="Ayşe", last_name="Yılmaz", email="ayse@test.com")

    ctx = email_service._build_template_context(giver, draw)
    html = email_service.jinja_env.get_template(email_service._get_template_config(language)["template"]).render(**ctx)

    token = ctx["reveal_link"].rsplit("/reveal/", 1)[1]
    payload = decode_participant_token(token)
    assert payload["pid"] == 34 and payload["did"] == 12
    assert ctx["reveal_link"] in html
    assert "Ayşe" in html
    for leaked in ("target_name", "target_email", "target_address", "Yılmaz"):
        assert leaked not in html


@pytest.mark.parametrize("language", ["TR", "EN"])
def test_reset_email_renders_link(email_service, language):
    cfg = "reset_password_tr" if language == "TR" else "reset_password_en"
    html = email_service.jinja_env.get_template(email_service.TEMPLATE_CONFIG[cfg]["template"]).render(
        lang=language.lower(), asset_base="https://letsraffle.co", reset_link="https://letsraffle.co/reset-password?token=abc"
    )
    assert "reset-password?token=abc" in html
    assert "https://letsraffle.co/email/santa-thinking.png" in html
