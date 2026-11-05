"""
Participant token and in-app match result tests
"""

import pytest

from app.core.security import create_access_token, create_participant_token, decode_participant_token
from app.models.draw import Draw
from app.services.draw_service import DrawService


def _create_draw(client, auth_headers, organizer_email="testuser@example.com"):
    response = client.post("/api/v1/draws/dynamic", headers=auth_headers, json={
        "participants": [{"firstName": "Org", "lastName": "Test", "email": organizer_email}]
    })
    assert response.status_code == 201
    return response.json()


def _join(client, code, name):
    response = client.post(f"/api/v1/draws/join/{code}", json={
        "firstName": name, "lastName": "Test", "email": f"{name.lower()}@test.com", "address": f"{name} street"
    })
    assert response.status_code == 201
    return response.json()


def _complete(test_db, draw_id):
    DrawService(test_db).execute_draw(draw_id)
    test_db.commit()


@pytest.mark.dynamic_draw
class TestParticipantTokens:
    def test_create_and_join_return_tokens(self, client, auth_headers):
        created = _create_draw(client, auth_headers)
        joined = _join(client, created["inviteCode"], "Mert")

        organizer_payload = decode_participant_token(created["participantToken"])
        joiner_payload = decode_participant_token(joined["participantToken"])
        assert organizer_payload["did"] == created["drawId"]
        assert joiner_payload["pid"] == joined["participantId"]

    def test_me_resolves_participant(self, client, auth_headers):
        created = _create_draw(client, auth_headers)
        joined = _join(client, created["inviteCode"], "Elif")

        response = client.get("/api/v1/participants/me", headers={"X-Participant-Token": joined["participantToken"]})

        assert response.status_code == 200
        data = response.json()
        assert data["inviteCode"] == created["inviteCode"]
        assert data["drawStatus"] == "active"
        assert data["firstName"] == "Elif"

    @pytest.mark.parametrize("token", ["garbage", create_access_token({"sub": "testuser@example.com"})])
    def test_rejects_invalid_or_foreign_tokens(self, client, token):
        response = client.get("/api/v1/participants/me", headers={"X-Participant-Token": token})
        assert response.status_code == 401

    def test_participant_token_cannot_authenticate_as_user(self, client, test_user):
        token = create_participant_token(1, 1)
        response = client.get("/api/v1/draws", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_removed_participant_token_is_not_found(self, client, auth_headers):
        created = _create_draw(client, auth_headers)
        joined = _join(client, created["inviteCode"], "Zeynep")
        client.delete(f"/api/v1/draws/{created['drawId']}/participants/{joined['participantId']}", headers=auth_headers)

        response = client.get("/api/v1/participants/me", headers={"X-Participant-Token": joined["participantToken"]})
        assert response.status_code == 404


@pytest.mark.dynamic_draw
class TestMatchResult:
    def test_result_before_completion_is_conflict(self, client, auth_headers):
        created = _create_draw(client, auth_headers)
        joined = _join(client, created["inviteCode"], "Mert")

        response = client.get("/api/v1/participants/me/result", headers={"X-Participant-Token": joined["participantToken"]})

        assert response.status_code == 409

    def test_each_participant_sees_only_own_match(self, client, auth_headers, test_db):
        created = _create_draw(client, auth_headers)
        tokens = {name: _join(client, created["inviteCode"], name) for name in ["Mert", "Elif", "Zeynep"]}
        _complete(test_db, created["drawId"])

        receivers = set()
        for name, joined in tokens.items():
            response = client.get("/api/v1/participants/me/result", headers={"X-Participant-Token": joined["participantToken"]})
            assert response.status_code == 200
            receiver = response.json()["receiver"]
            assert receiver["firstName"] != name, "nobody gives to themselves"
            assert "email" not in receiver
            receivers.add(receiver["firstName"])

        organizer = client.get("/api/v1/participants/me/result", headers={"X-Participant-Token": created["participantToken"]})
        receivers.add(organizer.json()["receiver"]["firstName"])
        assert receivers == {"Org", "Mert", "Elif", "Zeynep"}, "every participant receives exactly once"

    def test_organizer_my_result_uses_account_email(self, client, auth_headers, test_db):
        created = _create_draw(client, auth_headers)
        for name in ["Mert", "Elif"]:
            _join(client, created["inviteCode"], name)
        _complete(test_db, created["drawId"])

        response = client.get(f"/api/v1/draws/{created['inviteCode']}/my-result", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["receiver"]["firstName"] in {"Mert", "Elif"}

    def test_my_result_forbidden_for_other_users(self, client, auth_headers, second_auth_headers):
        created = _create_draw(client, auth_headers)
        response = client.get(f"/api/v1/draws/{created['inviteCode']}/my-result", headers=second_auth_headers)
        assert response.status_code == 403
