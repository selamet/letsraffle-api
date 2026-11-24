"""
Which client (iOS or web) created a draw, signed a user up or joined a draw
"""

import pytest

from app.core.client_source import detect_client_source
from app.models import Draw, Participant, User

IOS = {"X-Client": "ios/1.0.2"}
WEB = {"X-Client": "web"}
IOS_UA = "LetsRaffle/7 CFNetwork/1568.100.1 Darwin/24.0.0"
SAFARI_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari/604.1"

PARTICIPANTS = [
    {"firstName": "Ali", "lastName": "Kaya", "email": "ali@example.com"},
    {"firstName": "Bora", "lastName": "Demir", "email": "bora@example.com"},
    {"firstName": "Cem", "lastName": "Öz", "email": "cem@example.com"},
]


@pytest.mark.parametrize("header, agent, expected", [
    ("ios/1.0.2", None, "ios"),
    ("iOS", SAFARI_UA, "ios"),  # the header wins over the User-Agent
    ("web", IOS_UA, "web"),
    (None, IOS_UA, "ios"),  # iOS builds that do not send the header yet
    (None, SAFARI_UA, "web"),
    ("android/1.0", "okhttp/4.12", "unknown"),
    (None, "python-requests/2.32", "unknown"),
    (None, None, "unknown"),
])
def test_detect_client_source(header, agent, expected):
    assert detect_client_source(header, agent) == expected


def _manual_draw(client, headers):
    response = client.post(
        "/api/v1/draws/manual",
        headers=headers,
        json={"addressRequired": False, "phoneNumberRequired": False, "participants": PARTICIPANTS},
    )
    assert response.status_code == 201
    return response.json()["drawId"]


def test_manual_draw_records_source_on_draw_and_participants(client, test_db):
    draw_id = _manual_draw(client, IOS)
    draw = test_db.query(Draw).filter(Draw.id == draw_id).one()
    assert draw.source == "ios"
    assert {p.source for p in draw.participants} == {"ios"}


def test_manual_draw_falls_back_to_user_agent(client, test_db):
    draw_id = _manual_draw(client, {"User-Agent": SAFARI_UA})
    assert test_db.query(Draw).filter(Draw.id == draw_id).one().source == "web"


def test_dynamic_draw_and_join_record_their_own_source(client, auth_headers, test_db):
    response = client.post(
        "/api/v1/draws/dynamic",
        headers={**auth_headers, **IOS},
        json={"addressRequired": False, "phoneNumberRequired": False, "participants": PARTICIPANTS[:1]},
    )
    assert response.status_code == 201
    invite_code = response.json()["inviteCode"]

    joined = client.post(f"/api/v1/draws/join/{invite_code}", headers=WEB, json=PARTICIPANTS[1])
    assert joined.status_code == 201

    draw = test_db.query(Draw).filter(Draw.invite_code == invite_code).one()
    assert draw.source == "ios"
    sources = {p.email: p.source for p in test_db.query(Participant).filter(Participant.draw_id == draw.id)}
    assert sources == {"ali@example.com": "ios", "bora@example.com": "web"}


def test_register_records_source(client, test_db):
    response = client.post(
        "/api/v1/auth/register", headers=WEB, json={"email": "yeni@example.com", "password": "NewPassword123!"}
    )
    assert response.status_code == 201
    assert test_db.query(User).filter(User.email == "yeni@example.com").one().source == "web"


def test_admin_filters_and_counts_draws_by_source(admin_client, test_db):
    ios_draw = Draw(status="active", source="ios")
    web_draw = Draw(status="active", source="web")
    old_draw = Draw(status="active")
    test_db.add_all([ios_draw, web_draw, old_draw])
    test_db.commit()

    def listed(params):
        html = admin_client.get("/admin/draws", params=params).text
        return {d.id for d in (ios_draw, web_draw, old_draw) if f'href="/admin/draws/{d.id}"' in html}

    assert listed({}) == {ios_draw.id, web_draw.id, old_draw.id}
    assert listed({"source": "ios"}) == {ios_draw.id}
    assert listed({"source": "web"}) == {web_draw.id}
    assert listed({"source": "none"}) == {old_draw.id}
    assert listed({"source": "bogus"}) == {ios_draw.id, web_draw.id, old_draw.id}

    overview = admin_client.get("/admin").text
    assert 'href="/admin/draws?source=ios"' in overview
    assert "Kaynağa göre çekilişler" in overview


def test_admin_shows_source_on_detail_pages(admin_client, test_db):
    user = User(email="mobil@example.com", source="ios")
    test_db.add(user)
    test_db.flush()
    draw = Draw(creator_id=user.id, status="active", source="ios")
    test_db.add(draw)
    test_db.flush()
    test_db.add(Participant(draw_id=draw.id, first_name="Ece", last_name="Su", email="ece@example.com", source="web"))
    test_db.commit()

    detail = admin_client.get(f"/admin/draws/{draw.id}").text
    assert '<span class="pill">iOS</span>' in detail and '<span class="pill">Web</span>' in detail
    assert '<span class="pill">iOS</span>' in admin_client.get(f"/admin/users/{user.id}").text
    assert '<span class="pill">iOS</span>' in admin_client.get("/admin/users").text
