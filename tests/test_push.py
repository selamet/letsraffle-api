"""
APNs client and push notification use case tests
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.security import create_participant_token
from app.models import User
from app.models.device import Device, DeviceParticipant
from app.models.draw import Draw, DrawStatus, DrawType, Participant
from app.services.apns_client import APNsClient, APNsConfig, DeliveryResult
from app.services.push_service import PushService
from app.tasks import push_tasks


@pytest.fixture
def apns_key():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return key, pem


class FakeAPNs:
    """Records requests; responds per device token."""

    def __init__(self, responses=None):
        self.requests = []
        self.responses = responses or {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        token = request.url.path.rsplit("/", 1)[-1]
        status, reason = self.responses.get(token, (200, None))
        return httpx.Response(status, json={"reason": reason} if reason else None)

    def client(self, pem):
        config = APNsConfig(key_id="KEY123", team_id="TEAM123", private_key=pem, topic="com.letsraffle.ios", use_sandbox=True)
        return APNsClient(config, transport=httpx.MockTransport(self.handler))


def _draw(db, creator=None, status=DrawStatus.ACTIVE.value, draw_date=None):
    draw = Draw(creator_id=creator.id if creator else None, draw_type=DrawType.DYNAMIC.value, status=status,
                invite_code="merry-star-200", language="TR", draw_date=draw_date)
    db.add(draw)
    db.flush()
    return draw


def _participant_device(db, draw, token, language="TR"):
    participant = Participant(draw_id=draw.id, first_name="Mert", last_name="Kaya", email=f"{token}@test.com")
    db.add(participant)
    db.flush()
    device = Device(token=token, language=language)
    device.participant_links.append(DeviceParticipant(participant_id=participant.id))
    db.add(device)
    db.commit()
    return device


class TestAPNsClient:
    def test_sends_signed_alert(self, apns_key):
        key, pem = apns_key
        fake = FakeAPNs()

        result = fake.client(pem).send("abc123", {"aps": {"alert": "hi"}})

        assert result == DeliveryResult.SENT
        request = fake.requests[0]
        assert request.url.host == "api.sandbox.push.apple.com"
        assert request.headers["apns-topic"] == "com.letsraffle.ios"
        assert request.headers["apns-push-type"] == "alert"
        token = request.headers["authorization"].removeprefix("bearer ")
        assert jwt.get_unverified_header(token)["kid"] == "KEY123"
        assert jwt.decode(token, key.public_key(), algorithms=["ES256"])["iss"] == "TEAM123"

    def test_provider_token_is_reused(self, apns_key):
        client = FakeAPNs().client(apns_key[1])
        assert client.provider_token() == client.provider_token()

    @pytest.mark.parametrize("status,reason,expected", [
        (410, "Unregistered", DeliveryResult.INVALID_TOKEN),
        (400, "BadDeviceToken", DeliveryResult.INVALID_TOKEN),
        (500, "InternalServerError", DeliveryResult.FAILED),
    ])
    def test_error_mapping(self, apns_key, status, reason, expected):
        fake = FakeAPNs({"tok": (status, reason)})
        assert fake.client(apns_key[1]).send("tok", {}) == expected


class TestPushService:
    def test_disabled_without_configuration(self, test_db):
        service = PushService(test_db)
        assert service.enabled is False
        assert service.notify_match_revealed(1) == 0

    def test_match_revealed_targets_participant_devices_in_their_language(self, test_db, apns_key):
        draw = _draw(test_db)
        _participant_device(test_db, draw, "tok-tr", "TR")
        _participant_device(test_db, draw, "tok-en", "EN")
        fake = FakeAPNs()

        sent = PushService(test_db, fake.client(apns_key[1])).notify_match_revealed(draw.id)

        assert sent == 2
        bodies = {r.url.path.rsplit("/", 1)[-1]: json.loads(r.content) for r in fake.requests}
        assert bodies["tok-en"]["aps"]["alert"]["title"].startswith("The draw is complete")
        assert bodies["tok-tr"]["aps"]["alert"]["title"].startswith("Çekiliş tamamlandı")
        assert bodies["tok-tr"]["type"] == "match_revealed"
        assert bodies["tok-tr"]["inviteCode"] == "merry-star-200"

    def test_participant_joined_targets_organizer_devices(self, test_db, test_user, apns_key):
        draw = _draw(test_db, creator=test_user)
        test_db.add(Device(token="org-device", language="EN", user_id=test_user.id))
        test_db.add(Device(token="someone-else", language="EN"))
        test_db.commit()
        fake = FakeAPNs()

        PushService(test_db, fake.client(apns_key[1])).notify_participant_joined(draw.id, "Mert K.")

        assert [r.url.path for r in fake.requests] == ["/3/device/org-device"]
        assert json.loads(fake.requests[0].content)["aps"]["alert"]["body"] == "Mert K. joined your draw."

    def test_invalid_tokens_are_removed(self, test_db, apns_key):
        draw = _draw(test_db)
        _participant_device(test_db, draw, "dead-token")
        fake = FakeAPNs({"dead-token": (410, "Unregistered")})

        PushService(test_db, fake.client(apns_key[1])).notify_match_revealed(draw.id)

        assert test_db.query(Device).count() == 0

    def test_reminders_are_sent_once_for_draws_within_24h(self, test_db, test_user, apns_key):
        now = datetime.now(timezone.utc)
        soon = _draw(test_db, creator=test_user, draw_date=now + timedelta(hours=5))
        _participant_device(test_db, soon, "participant-device")
        test_db.add(Device(token="org-device", user_id=test_user.id))
        later = Draw(draw_type=DrawType.DYNAMIC.value, status=DrawStatus.ACTIVE.value, invite_code="later-draw-1",
                     language="TR", draw_date=now + timedelta(days=3))
        test_db.add(later)
        test_db.commit()
        fake = FakeAPNs()
        service = PushService(test_db, fake.client(apns_key[1]))

        first = service.send_due_reminders(now=now)
        second = service.send_due_reminders(now=now)

        assert first == 2
        assert second == 0
        assert soon.reminder_sent_at is not None
        assert later.reminder_sent_at is None


class TestHooks:
    def test_join_enqueues_organizer_push(self, client, auth_headers, monkeypatch):
        calls = []
        monkeypatch.setattr(push_tasks.send_participant_joined_push_task, "delay", lambda *a: calls.append(a))
        created = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
            "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
        }).json()

        client.post(f"/api/v1/draws/join/{created['inviteCode']}", json={
            "firstName": "Mert", "lastName": "Kaya", "email": "mert@test.com"
        })

        assert calls == [(created["drawId"], "Mert K.")]

    def test_broker_failure_does_not_break_join(self, client, auth_headers, monkeypatch):
        def boom(*args):
            raise ConnectionError("broker down")
        monkeypatch.setattr(push_tasks.send_participant_joined_push_task, "delay", boom)
        created = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
            "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
        }).json()

        response = client.post(f"/api/v1/draws/join/{created['inviteCode']}", json={
            "firstName": "Mert", "lastName": "Kaya", "email": "mert@test.com"
        })

        assert response.status_code == 201
