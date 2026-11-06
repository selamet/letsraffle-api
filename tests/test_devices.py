"""
Device registration tests
"""

import pytest

from app.core.security import create_participant_token
from app.models.device import Device, DeviceParticipant

TOKEN = "a1b2c3d4e5f6a7b8c9d0"


def _join(client, auth_headers):
    created = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
        "participants": [{"firstName": "Org", "lastName": "Test", "email": "org@test.com"}]
    }).json()
    joined = client.post(f"/api/v1/draws/join/{created['inviteCode']}", json={
        "firstName": "Mert", "lastName": "Kaya", "email": "mert@test.com"
    }).json()
    return created, joined


@pytest.mark.organizer
class TestDeviceRegistration:
    def test_anonymous_registration_links_valid_participant_tokens(self, client, auth_headers, test_db):
        _, joined = _join(client, auth_headers)

        response = client.post("/api/v1/devices", json={
            "token": TOKEN, "language": "en",
            "participantTokens": [joined["participantToken"], "garbage", create_participant_token(9999, 1)],
        })

        assert response.status_code == 200
        assert response.json() == {"userLinked": False, "participantCount": 1}
        device = test_db.query(Device).one()
        assert device.language == "EN"
        assert device.user_id is None

    def test_registration_is_an_upsert(self, client, auth_headers, test_db):
        _, joined = _join(client, auth_headers)
        payload = {"token": TOKEN, "participantTokens": [joined["participantToken"]]}

        client.post("/api/v1/devices", json=payload)
        second = client.post("/api/v1/devices", json=payload, headers=auth_headers)

        assert second.json() == {"userLinked": True, "participantCount": 1}
        assert test_db.query(Device).count() == 1
        assert test_db.query(DeviceParticipant).count() == 1

    def test_registering_without_auth_clears_user_link(self, client, auth_headers, test_db):
        client.post("/api/v1/devices", json={"token": TOKEN}, headers=auth_headers)
        response = client.post("/api/v1/devices", json={"token": TOKEN})
        assert response.json()["userLinked"] is False

    def test_unregister_is_idempotent(self, client, test_db):
        client.post("/api/v1/devices", json={"token": TOKEN})
        assert client.delete(f"/api/v1/devices/{TOKEN}").status_code == 204
        assert client.delete(f"/api/v1/devices/{TOKEN}").status_code == 204
        assert test_db.query(Device).count() == 0

    @pytest.mark.parametrize("payload", [{"token": "short"}, {"token": TOKEN, "platform": "android"}, {"token": TOKEN, "language": "DE"}])
    def test_validation(self, client, payload):
        assert client.post("/api/v1/devices", json=payload).status_code == 422

    def test_account_deletion_detaches_devices(self, client, auth_headers, test_db):
        client.post("/api/v1/devices", json={"token": TOKEN}, headers=auth_headers)
        client.delete("/api/v1/auth/me", headers=auth_headers)
        test_db.expire_all()
        assert test_db.query(Device).one().user_id is None
